"""Synthetic demo ledger — generates a realistic 3-month CSV for onboarding.

Usage: python -m packages.demo.generate [output.csv]
"""
from __future__ import annotations

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

MERCHANTS = [
    # (name, category-ish description, amount range cents, monthly probability)
    ("REWE Markt GmbH", "REWE SAGT DANKE", (1500, 6500), 0.85),
    ("EDEKA Neukauf", "EDEKA DANKE FUER IHREN EINKAUF", (1200, 5400), 0.7),
    ("Netflix International B.V.", "NETFLIX.COM AMSTERDAM", (1299, 1299), 1.0),
    ("Spotify AB", "SPOTIFY STOCKHOLM", (1099, 1099), 1.0),
    ("Stadtwerke Musterstadt", "ABSCHLAG ENERGIE STADTWERKE", (6500, 8500), 1.0),
    ("Telekom Deutschland", "MOBILFUNK RECHNUNG", (1999, 3999), 1.0),
    ("Allianz Versicherung", "PRAMIENSAVE VERSICHERUNG", (3200, 3200), 1.0),
    ("Restaurant Akropolis", "KARTENZAHLung GASTRONOMIE", (1800, 5200), 0.4),
    ("Amazon EU S.a.r.l.", "AMAZON.DE MKTPL", (999, 8900), 0.5),
]

SALARY = ("Arbeitgeber Musterfirma GmbH", "GEHALT OKTOBER", 285000)


def generate(out_path: str, months: int = 3) -> Path:
    rng = random.Random(42)
    today = date.today().replace(day=1)
    rows: list[tuple[str, str, str]] = []

    for back in range(months - 1, -1, -1):
        month_start = (today - timedelta(days=30 * back)).replace(day=1)
        # salary on the 1st
        pay_day = month_start
        rows.append((pay_day.isoformat(), f"+{SALARY[2]/100:.2f}",
                     f"{SALARY[0]} {SALARY[1]}"))
        day = month_start
        while day.month == month_start.month and day <= date.today():
            # fixed monthly bills land deterministically in the first days
            for name, desc, amount, dom in [
                (MERCHANTS[2][0], MERCHANTS[2][1], 1299, 3),   # Netflix
                (MERCHANTS[3][0], MERCHANTS[3][1], 1099, 5),   # Spotify
                (MERCHANTS[4][0], MERCHANTS[4][1], 7500, 2),   # Stadtwerke
                (MERCHANTS[5][0], MERCHANTS[5][1], 2999, 7),   # Telekom
            ]:
                bill_day = month_start.replace(day=min(dom, 28))
                if day == bill_day:
                    rows.append((day.isoformat(), f"-{amount/100:.2f}", f"{name} {desc}"))
            for name, desc, (lo, hi), prob in MERCHANTS:
                if name in {MERCHANTS[2][0], MERCHANTS[3][0], MERCHANTS[4][0], MERCHANTS[5][0]}:
                    continue  # fixed bills already emitted above
                if rng.random() < prob / 25:  # per-day chance ≈ monthly prob / ~25 variable days
                    amount = rng.randint(lo, hi)
                    rows.append((day.isoformat(), f"-{amount/100:.2f}", f"{name} {desc}"))
            day += timedelta(days=1)

    rows.sort(key=lambda r: r[0])
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Buchungsdatum", "Betrag", "Verwendungszweck"])
        for r in rows:
            w.writerow(r)
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "./examples/synthetic-ledger/demo_statement.csv"
    p = generate(path)
    print(f"Demo statement written: {p}")
