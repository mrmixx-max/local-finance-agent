"""Market data layer — portfolio positions and price history, analysis only.

Scope guard (docs/roadmap.md): this module imports prices and computes
descriptive statistics. It does NOT predict, recommend, or signal.
"""
from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean, stdev

MARKET_SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,        -- e.g. 'AAPL', 'BTC-EUR', 'IWDA'
    name TEXT NOT NULL DEFAULT '',
    asset_class TEXT NOT NULL DEFAULT 'equity'  -- equity|etf|crypto|fund|cash
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY,
    instrument_id INTEGER NOT NULL REFERENCES instruments(id),
    quantity REAL NOT NULL,             -- fractional units allowed (ETFs)
    avg_cost_price REAL NOT NULL,       -- per unit, in quote currency
    opened TEXT NOT NULL DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS price_history (
    instrument_id INTEGER NOT NULL REFERENCES instruments(id),
    price_date TEXT NOT NULL,
    close REAL NOT NULL,
    PRIMARY KEY (instrument_id, price_date)
);
"""


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_cost_price: float


class MarketLedger:
    """Separate SQLite file — market data never mixes with the transaction ledger."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(MARKET_SCHEMA)

    # ---------- instruments & positions ----------
    def ensure_instrument(self, symbol: str, name: str = "", asset_class: str = "equity") -> int:
        self.conn.execute(
            "INSERT OR IGNORE INTO instruments(symbol,name,asset_class) VALUES(?,?,?)",
            (symbol.upper(), name, asset_class),
        )
        self.conn.commit()
        return self.conn.execute(
            "SELECT id FROM instruments WHERE symbol=?", (symbol.upper(),)
        ).fetchone()["id"]

    def add_position(self, symbol: str, quantity: float, avg_cost_price: float,
                     name: str = "", asset_class: str = "equity") -> int:
        iid = self.ensure_instrument(symbol, name, asset_class)
        cur = self.conn.execute(
            "INSERT INTO positions(instrument_id,quantity,avg_cost_price) VALUES(?,?,?)",
            (iid, quantity, avg_cost_price),
        )
        self.conn.commit()
        return cur.lastrowid

    # ---------- price import ----------
    def import_prices_csv(self, path: str | Path, symbol: str,
                          date_col: str = "date", close_col: str = "close") -> int:
        """Import a CSV with columns [date, close]. Returns rows inserted.

        Accepts ISO dates or German dd.mm.yyyy. Existing (instrument,date) pairs
        are overwritten (upsert), so re-imports are safe.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(p)
        iid = self.ensure_instrument(symbol)
        n = 0
        with p.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_date = (row.get(date_col) or "").strip()
                raw_close = (row.get(close_col) or "").strip()
                if not raw_date or not raw_close:
                    continue
                d = _normalize_date(raw_date)
                close = float(raw_close.replace(",", "."))
                self.conn.execute(
                    """INSERT INTO price_history(instrument_id,price_date,close) VALUES(?,?,?)
                       ON CONFLICT(instrument_id,price_date) DO UPDATE SET close=excluded.close""",
                    (iid, d, close),
                )
                n += 1
        self.conn.commit()
        return n

    # ---------- analytics ----------
    def latest_prices(self) -> dict[str, float]:
        rows = self.conn.execute(
            """SELECT i.symbol, ph.close FROM price_history ph
               JOIN instruments i ON ph.instrument_id=i.id
               WHERE ph.price_date = (SELECT MAX(price_date) FROM price_history p2
                                      WHERE p2.instrument_id=ph.instrument_id)"""
        ).fetchall()
        return {r["symbol"]: r["close"] for r in rows}

    def portfolio_summary(self) -> dict:
        """Current value, cost, P/L — descriptive numbers only."""
        positions = self._open_positions()
        prices = self.latest_prices()
        lines, total_value, total_cost = [], 0.0, 0.0
        for pos in positions:
            last = prices.get(pos.symbol)
            value = pos.quantity * last if last is not None else None
            cost = pos.quantity * pos.avg_cost_price
            total_cost += cost
            if value is not None:
                total_value += value
            lines.append({
                "symbol": pos.symbol,
                "quantity": pos.quantity,
                "avg_cost": pos.avg_cost_price,
                "last_price": last,
                "value": value,
                "cost": cost,
                "pl": (value - cost) if value is not None else None,
            })
        return {"positions": lines, "total_value": total_value, "total_cost": total_cost,
                "total_pl": total_value - total_cost}

    def volatility(self, symbol: str, window_days: int = 90) -> dict:
        """Annualized stddev of daily log-ish returns over the lookback window."""
        rows = self.conn.execute(
            """SELECT ph.close FROM price_history ph
               JOIN instruments i ON ph.instrument_id=i.id
               WHERE i.symbol=? ORDER BY ph.price_date DESC LIMIT ?""",
            (symbol.upper(), window_days + 1),
        ).fetchall()
        closes = [r["close"] for r in reversed(rows)]
        if len(closes) < 3:
            raise ValueError(f"not enough price history for {symbol} ({len(closes)} pts)")
        rets = [(b / a - 1) for a, b in zip(closes, closes[1:])]
        sd = stdev(rets)
        return {
            "symbol": symbol.upper(),
            "points": len(rets),
            "daily_volatility": sd,
            "annualized_volatility": sd * (252 ** 0.5),
            "mean_daily_return": mean(rets),
            "window_start": len(closes),
        }

    # ---------- helpers ----------
    def _open_positions(self) -> list[Position]:
        rows = self.conn.execute(
            """SELECT i.symbol, p.quantity, p.avg_cost_price
               FROM positions p JOIN instruments i ON p.instrument_id=i.id"""
        ).fetchall()
        return [Position(r["symbol"], r["quantity"], r["avg_cost_price"]) for r in rows]


def _normalize_date(raw: str) -> str:
    from datetime import datetime
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date: {raw!r}")
