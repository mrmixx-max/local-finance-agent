"""CSV statement importer — tolerant, dedup-aware, provenance-tracked.

Supported input: generic bank CSV exports with a header row. Column names are
auto-mapped from common variants (date/datum/buchung, amount/betrag/saldo,
description/verwendung/zweck). Amounts may use German (1.234,56) or English
(1,234.56) formats and +/- signs.
"""
from __future__ import annotations

import csv
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from packages.ledger.engine import Ledger, TxnIn, _norm_desc

# Header synonyms → canonical field
COLUMN_ALIASES = {
    "date": ["date", "datum", "buchung", "buchungsdatum", "valuta", "value date", "transaktion"],
    "amount": ["amount", "betrag", "wert", "umsatz", "betrag (€)", "betrag_eur"],
    "description": ["description", "verwendung", "verwendungszweck", "zweck", "buchungstext",
                    "name", "empfänger", "payee", "details"],
}

DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"]


def sniff_dialect(path: Path) -> csv.Dialect:
    sample = path.open(encoding="utf-8-sig", newline="").readline()
    delim = ";" if sample.count(";") > sample.count(",") else ","
    class D(csv.Dialect):
        delimiter = delim
        quotechar = '"'
        doublequote = True
        skipinitialspace = True
        lineterminator = "\n"
        quoting = csv.QUOTE_MINIMAL
    return D


def map_columns(header: list[str]) -> dict[str, int]:
    """Map header row to canonical fields; raises if required columns are missing."""
    lowered = [h.strip().lower() for h in header]
    mapping: dict[str, int] = {}
    for canon, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[canon] = lowered.index(alias)
                break
    missing = {"date", "amount", "description"} - set(mapping)
    if missing:
        raise ValueError(f"CSV header missing columns {missing}; got {header}")
    return mapping


def parse_amount(raw: str, currency_hint: str = "EUR") -> int:
    """Parse '−1.234,56', '-1234.56', '1234.56 EUR' → signed cents."""
    s = raw.strip().replace("EUR", "").replace("€", "").strip()
    s = s.replace("\u2212", "-").replace("−", "-")  # unicode minus
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = re.sub(r"[^\d.,]", "", s).strip(".")
    if not s:
        raise InvalidOperation(raw)
    # Decide separator role: the LAST separator is the decimal point.
    last_comma, last_dot = s.rfind(","), s.rfind(".")
    if last_comma > last_dot:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    cents = int((Decimal(s) * 100).to_integral_value())
    return -cents if neg else cents


def parse_date(raw: str) -> str:
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {raw!r}")


def import_csv(ledger: Ledger, path: str | Path, account: str | None = None) -> dict:
    """Import a CSV file into the ledger. Returns an import report."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)

    doc_id = ledger.register_document(str(p))
    dialect = sniff_dialect(p)
    account_name = account or p.stem  # fall back to filename as account name

    inserted, duplicates, errors = 0, 0, []
    with p.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, dialect)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"{p.name}: empty file")
        colmap = map_columns(header)

        for lineno, row in enumerate(reader, start=2):
            if not any(cell.strip() for cell in row):
                continue
            try:
                txn_date = parse_date(row[colmap["date"]])
                amount_cents = parse_amount(row[colmap["amount"]])
                description = row[colmap["description"]].strip() or "(no description)"
                txn_id, was_dup = ledger.add_transaction(
                    TxnIn(account=account_name, txn_date=txn_date,
                          amount_cents=amount_cents, raw_description=description),
                    doc_id,
                )
                if was_dup:
                    duplicates += 1
                else:
                    inserted += 1
            except Exception as exc:  # collect per-row errors, keep importing
                errors.append({"line": lineno, "raw": row, "error": str(exc)})

    return {
        "file": str(p),
        "doc_id": doc_id,
        "account": account_name,
        "inserted": inserted,
        "duplicates": duplicates,
        "errors": errors,
    }
