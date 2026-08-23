"""Demo market data — synthetic price series + sample portfolio.

Deterministic (seeded) so tests and onboarding are reproducible.
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SAMPLE_PORTFOLIO = [
    # symbol, name, asset_class, quantity, avg_cost, start_price, annual_drift, daily_vol
    ("IWDA", "iShares Core MSCI World", "etf", 12.5, 82.40, 80.00, 0.09, 0.011),
    ("BTC-EUR", "Bitcoin", "crypto", 0.15, 41000.0, 38000.0, 0.35, 0.042),
    ("AEK", "Aktien-Euro-Kasse", "fund", 40.0, 21.10, 20.50, 0.05, 0.008),
]


def generate_prices_csv(out_path: str, symbol: str, days: int = 365,
                        start_price: float = 100.0,
                        annual_drift: float = 0.07,
                        daily_vol: float = 0.012) -> Path:
    rng = random.Random(hash(symbol) % (2 ** 32))
    d0 = date.today() - timedelta(days=days)
    px = start_price
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "close"])
        for i in range(days):
            d = d0 + timedelta(days=i)
            if d.weekday() < 5:  # trading days only
                shock = rng.gauss(annual_drift / 252, daily_vol)
                px *= (1 + shock)
                w.writerow([d.isoformat(), f"{px:.2f}"])
    return out


def seed_demo(market: "object") -> dict:
    """Populate a MarketLedger with the sample portfolio + 1y price history."""
    report = {}
    for symbol, name, cls, qty, cost, start, drift, vol in SAMPLE_PORTFOLIO:
        p = generate_prices_csv(f"./examples/synthetic-ledger/prices-{symbol}.csv",
                                symbol, days=365, start_price=start,
                                annual_drift=drift, daily_vol=vol)
        market.ensure_instrument(symbol, name, cls)
        market.add_position(symbol, qty, cost)
        n = market.import_prices_csv(p, symbol)
        report[symbol] = {"price_rows": n}
    return report
