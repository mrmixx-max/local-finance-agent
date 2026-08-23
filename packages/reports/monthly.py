"""Monthly report generator — Markdown + CSV, fully local, provenance-friendly."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from packages.ledger.engine import Ledger

EUR = "\u20ac"


def fmt_eur(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents)//100:,}.{abs(cents)%100:02d} {EUR}".replace(",", ".")


def monthly_report(ledger: Ledger, year: int, month: int,
                   recurring: list[dict[str, Any]] | None = None) -> str:
    """Render a Markdown monthly report."""
    s = ledger.month_summary(year, month)
    lines = [
        f"# Monatsbericht {month:02d}/{year}",
        "",
        f"- Einnahmen: **{fmt_eur(s['total_inflow_cents'])}**",
        f"- Ausgaben: **{fmt_eur(s['total_outflow_cents'])}**",
        f"- Saldo: **{fmt_eur(s['net_cents'])}**",
        f"- Nicht kategorisierte Buchungen: {ledger.uncategorized_count()}",
        "",
        "## Ausgaben nach Kategorie",
        "",
        "| Kategorie | Ausgaben | Buchungen |",
        "|---|---|---|",
    ]
    for row in s["by_category"]:
        if row["outflow_cents"] > 0:
            lines.append(f"| {row['category']} | {fmt_eur(row['outflow_cents'])} | {row['count']} |")

    if recurring:
        lines += ["", "## Erkannte wiederkehrende Kosten", "",
                  "| Händler | typ. Betrag | Intervall (Tage) | geschätzt/Monat | Häufigkeit |",
                  "|---|---|---|---|---|"]
        for r in recurring:
            lines.append(
                f"| {r['merchant']} | {fmt_eur(r['typical_amount_cents'])} | "
                f"{r['interval_days']} | {fmt_eur(r['estimated_monthly_cents'])} | "
                f"{r['occurrences']}× ({int(r['regularity']*100)}%) |"
            )

    pending = ledger.pending_review()
    if pending:
        lines += ["", f"## Review-Queue ({len(pending)} offen)", ""]
        for p in pending[:15]:
            lines.append(f"- `{p['txn_date']}` {fmt_eur(p['amount_cents'])} — "
                         f"{p['raw_description'][:60]} *({p['reason']})*")
        if len(pending) > 15:
            lines.append(f"- … und {len(pending)-15} weitere")

    return "\n".join(lines) + "\n"


def export_month_csv(ledger: Ledger, year: int, month: int, out_path: str | Path) -> Path:
    """Export the month's transactions as CSV."""
    rows = ledger.conn.execute(
        """SELECT t.txn_date, a.name AS account, t.amount_cents, t.currency,
                  t.raw_description, c.name AS category, m.canonical_name AS merchant,
                  t.confidence, t.id
           FROM transactions t
           LEFT JOIN accounts a ON t.account_id=a.id
           LEFT JOIN categories c ON t.category_id=c.id
           LEFT JOIN merchants m ON t.merchant_id=m.id
           WHERE strftime('%Y', t.txn_date)=? AND strftime('%m', t.txn_date)=?
           ORDER BY t.txn_date""",
        (str(year), f"{month:02d}"),
    ).fetchall()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "account", "amount_cents", "currency", "description",
                    "category", "merchant", "confidence", "txn_id"])
        for r in rows:
            w.writerow([r["txn_date"], r["account"], r["amount_cents"], r["currency"],
                        r["raw_description"], r["category"] or "", r["merchant"] or "",
                        r["confidence"], r["id"]])
    return out
