"""Recurring cost detector — finds subscriptions and regular charges.

Heuristic: group outflows by merchant; a merchant is "recurring" when it has
>= min_occurrences transactions with similar amounts (±tolerance) and roughly
regular intervals.
"""
from __future__ import annotations

from statistics import median
from typing import Any

from packages.ledger.engine import Ledger


def detect_recurring(
    ledger: Ledger,
    min_occurrences: int = 3,
    amount_tolerance: float = 0.15,   # ±15% around the median
    interval_tolerance_days: int = 5,
) -> list[dict[str, Any]]:
    rows = ledger.conn.execute(
        """SELECT m.id AS merchant_id, m.canonical_name AS merchant,
                  t.txn_date, t.amount_cents
           FROM transactions t JOIN merchants m ON t.merchant_id = m.id
           WHERE t.amount_cents < 0
           ORDER BY m.id, t.txn_date"""
    ).fetchall()

    by_merchant: dict[int, list] = {}
    for r in rows:
        by_merchant.setdefault(r["merchant_id"], []).append(r)

    results = []
    for mid, txns in by_merchant.items():
        if len(txns) < min_occurrences:
            continue
        amounts = [-t["amount_cents"] for t in txns]
        med = median(amounts)
        if med == 0:
            continue
        similar = [t for t in txns if abs(-t["amount_cents"] - med) / med <= amount_tolerance]
        if len(similar) < min_occurrences:
            continue

        # interval check on dates of the "similar" subset
        from datetime import date
        dates = sorted(date.fromisoformat(t["txn_date"]) for t in similar)
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        if not gaps:
            continue
        med_gap = median(gaps)
        if not (5 <= med_gap <= 400):          # weekly..yearly cadence
            continue
        regularity = sum(1 for g in gaps if abs(g - med_gap) <= interval_tolerance_days) / len(gaps)
        if regularity < 0.6:
            continue

        results.append({
            "merchant": similar[0]["merchant"],
            "merchant_id": mid,
            "typical_amount_cents": int(med),
            "interval_days": int(med_gap),
            "occurrences": len(similar),
            "regularity": round(regularity, 2),
            "last_seen": dates[-1].isoformat(),
            "estimated_monthly_cents": int(med * 30.44 / med_gap),
        })

    results.sort(key=lambda r: -r["estimated_monthly_cents"])
    return results
