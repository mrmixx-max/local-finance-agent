"""Ledger engine — normalized, provenance-tracked local finance storage.

Design principles (from docs/architecture.md):
- Every transaction keeps a link to its source document (provenance).
- Low-confidence categorizations land in the review queue instead of being silently applied.
- Deduplication is deterministic: (account_id, date, amount_cents, merchant_normalized, hash).
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator

DEFAULT_DB = os.environ.get("LFA_DB_PATH", "./data/db/ledger.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'checking'   -- checking|credit|cash
);

CREATE TABLE IF NOT EXISTS merchants (
    id INTEGER PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,
    aliases TEXT NOT NULL DEFAULT '[]'      -- JSON list of raw-name variants
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_id INTEGER REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    doc_id INTEGER NOT NULL REFERENCES documents(id),
    txn_date TEXT NOT NULL,                 -- ISO date
    amount_cents INTEGER NOT NULL,          -- positive = inflow, negative = outflow
    currency TEXT NOT NULL DEFAULT 'EUR',
    raw_description TEXT NOT NULL,
    merchant_id INTEGER REFERENCES merchants(id),
    category_id INTEGER REFERENCES categories(id),
    confidence REAL NOT NULL DEFAULT 0.0,   -- 0..1 categorization confidence
    transfer_group TEXT,                    -- links internal transfers
    dedup_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_txn_date ON transactions(txn_date);
CREATE INDEX IF NOT EXISTS idx_txn_account ON transactions(account_id);

CREATE TABLE IF NOT EXISTS review_items (
    id INTEGER PRIMARY KEY,
    transaction_id INTEGER NOT NULL UNIQUE REFERENCES transactions(id),
    reason TEXT NOT NULL,                   -- low_confidence|new_merchant|ambiguous
    resolved INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recurring_patterns (
    id INTEGER PRIMARY KEY,
    merchant_id INTEGER NOT NULL REFERENCES merchants(id),
    typical_amount_cents INTEGER NOT NULL,
    interval_days INTEGER NOT NULL,
    last_seen TEXT NOT NULL,
    occurrences INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS answer_traces (
    id INTEGER PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    filters_json TEXT NOT NULL,
    txn_ids_json TEXT NOT NULL,             -- ledger rows backing the answer
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _connect(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@dataclass
class TxnIn:
    """Normalized incoming transaction before dedup."""
    account: str
    txn_date: str            # ISO yyyy-mm-dd
    amount_cents: int        # signed
    raw_description: str
    currency: str = "EUR"


class Ledger:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or DEFAULT_DB
        self.conn = _connect(self.db_path)

    # ---------- documents ----------
    def register_document(self, path: str) -> int:
        h = _sha256_file(path)
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO documents(path, sha256) VALUES(?,?)", (path, h)
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM documents WHERE sha256=?", (h,)
        ).fetchone()
        return row["id"]

    # ---------- accounts / categories / merchants ----------
    def ensure_account(self, name: str, kind: str = "checking") -> int:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO accounts(name, kind) VALUES(?,?)", (name, kind)
        )
        self.conn.commit()
        return self._id("accounts", "name", name)

    def ensure_category(self, name: str, parent: str | None = None) -> int:
        parent_id = self._id("categories", "name", parent) if parent else None
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO categories(name, parent_id) VALUES(?,?)",
            (name, parent_id),
        )
        self.conn.commit()
        return self._id("categories", "name", name)

    def ensure_merchant(self, canonical: str, alias: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO merchants(canonical_name, aliases) VALUES(?, '[]')",
            (canonical,),
        )
        self.conn.commit()
        mid = self._id("merchants", "canonical_name", canonical)
        if alias:
            row = self.conn.execute(
                "SELECT aliases FROM merchants WHERE id=?", (mid,)
            ).fetchone()
            aliases = json.loads(row["aliases"])
            if alias not in aliases:
                aliases.append(alias)
                self.conn.execute(
                    "UPDATE merchants SET aliases=? WHERE id=?",
                    (json.dumps(aliases), mid),
                )
                self.conn.commit()
        return mid

    def find_merchant_by_alias(self, raw: str) -> int | None:
        """Match a raw statement description against canonical names and aliases."""
        needle = raw.strip().lower()
        for row in self.conn.execute("SELECT id, canonical_name, aliases FROM merchants"):
            if needle == row["canonical_name"].lower():
                return row["id"]
            if needle in [a.lower() for a in json.loads(row["aliases"])]:
                return row["id"]
            if needle and row["canonical_name"].lower() in needle:
                return row["id"]
        return None

    # ---------- core insert ----------
    def add_transaction(self, t: TxnIn, doc_id: int) -> tuple[int, bool]:
        """Insert a transaction; returns (txn_id, was_duplicate). Duplicates are skipped."""
        h = dedup_hash(t.account, t.txn_date, t.amount_cents, t.raw_description)
        exists = self.conn.execute(
            "SELECT id FROM transactions WHERE dedup_hash=?", (h,)
        ).fetchone()
        if exists:
            return exists["id"], True
        account_id = self.ensure_account(t.account)
        cur = self.conn.execute(
            """INSERT INTO transactions
               (account_id, doc_id, txn_date, amount_cents, currency,
                raw_description, dedup_hash)
               VALUES(?,?,?,?,?,?,?)""",
            (account_id, doc_id, t.txn_date, t.amount_cents, t.currency,
             t.raw_description, h),
        )
        self.conn.commit()
        return cur.lastrowid, False

    def set_category(self, txn_id: int, category_id: int, confidence: float,
                     review_reason: str | None = None) -> None:
        self.conn.execute(
            "UPDATE transactions SET category_id=?, confidence=? WHERE id=?",
            (category_id, confidence, txn_id),
        )
        if review_reason:
            self.conn.execute(
                "INSERT OR IGNORE INTO review_items(transaction_id, reason) VALUES(?,?)",
                (txn_id, review_reason),
            )
        else:
            self.conn.execute(
                "DELETE FROM review_items WHERE transaction_id=?", (txn_id,)
            )
        self.conn.commit()

    # ---------- queries used by agents/reports ----------
    def month_summary(self, year: int, month: int) -> dict[str, Any]:
        rows = self.conn.execute(
            """SELECT c.name AS category,
                      SUM(CASE WHEN t.amount_cents > 0 THEN t.amount_cents ELSE 0 END) AS inflow,
                      SUM(CASE WHEN t.amount_cents < 0 THEN -t.amount_cents ELSE 0 END) AS outflow,
                      COUNT(*) AS n
               FROM transactions t LEFT JOIN categories c ON t.category_id=c.id
               WHERE strftime('%Y', t.txn_date)=? AND strftime('%m', t.txn_date)=?
               GROUP BY c.name ORDER BY outflow DESC""",
            (str(year), f"{month:02d}"),
        ).fetchall()
        inflow = sum(r["inflow"] or 0 for r in rows)
        outflow = sum(r["outflow"] or 0 for r in rows)
        return {
            "year": year, "month": month,
            "total_inflow_cents": inflow,
            "total_outflow_cents": outflow,
            "net_cents": inflow - outflow,
            "by_category": [
                {"category": r["category"] or "Uncategorized",
                 "inflow_cents": r["inflow"] or 0,
                 "outflow_cents": r["outflow"] or 0,
                 "count": r["n"]}
                for r in rows
            ],
        }

    def top_merchants(self, days: int = 90, limit: int = 10):
        return self.conn.execute(
            """SELECT m.canonical_name AS merchant, COUNT(*) n,
                      SUM(-t.amount_cents) spent_cents
               FROM transactions t JOIN merchants m ON t.merchant_id=m.id
               WHERE t.txn_date >= date('now', ?) AND t.amount_cents < 0
               GROUP BY m.id ORDER BY spent_cents DESC LIMIT ?""",
            (f"-{days} days", limit),
        ).fetchall()

    def uncategorized_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) c FROM transactions WHERE category_id IS NULL"
        ).fetchone()["c"]

    def pending_review(self):
        return self.conn.execute(
            """SELECT t.id, t.txn_date, t.amount_cents, t.raw_description,
                      ri.reason
               FROM review_items ri JOIN transactions t ON ri.transaction_id=t.id
               WHERE ri.resolved=0 ORDER BY t.txn_date"""
        ).fetchall()

    def record_trace(self, question: str, answer: str, filters: dict,
                     txn_ids: list[int]) -> None:
        self.conn.execute(
            """INSERT INTO answer_traces(question, answer, filters_json, txn_ids_json)
               VALUES(?,?,?,?)""",
            (question, answer, json.dumps(filters), json.dumps(txn_ids)),
        )
        self.conn.commit()

    # ---------- helpers ----------
    def _id(self, table: str, col: str, val: Any) -> int:
        row = self.conn.execute(f"SELECT id FROM {table} WHERE {col}=?", (val,)).fetchone()
        return row["id"]


def dedup_hash(account: str, txn_date: str, amount_cents: int, raw_desc: str) -> str:
    payload = f"{account}|{txn_date}|{amount_cents}|{_norm_desc(raw_desc)}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _norm_desc(desc: str) -> str:
    """Normalize descriptions so bank noise doesn't defeat dedup."""
    import re
    d = desc.lower().strip()
    d = re.sub(r"\b\d{2}\.\d{2}\.\d{2,4}\b", "", d)      # dates inside text
    d = re.sub(r"\bref\.?:?\s*\w+\b", "", d)             # reference numbers
    d = re.sub(r"[^a-z0-9äöüß ]+", " ", d)
    return re.sub(r"\s+", " ", d).strip()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()
