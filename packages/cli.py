"""CLI entrypoint: lfa <command>

Commands:
  demo            Generate + import the synthetic demo ledger
  import <file>   Import a CSV statement (account = filename by default)
  categorize      Run the rules engine over uncategorized transactions
  recurring       List detected recurring costs
  report [YYYY M] Print a monthly report
  review          Show pending review items

Run via:  python -m packages.cli <command>
"""
from __future__ import annotations

import argparse
import sys

from packages.agents.recurring import detect_recurring
from packages.demo import generate as generate_demo
from packages.ingest.csv_import import import_csv
from packages.ledger.engine import Ledger, _norm_desc  # noqa: F401 (re-export)
from packages.reports.monthly import export_month_csv, monthly_report
from packages.rules.engine import RulesEngine

MUSE = "hf.co/kizzet373/Dirty-Muse-Writer"  # not used here; pool doc anchor


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lfa", description="Local Finance Agent")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("demo", help="generate + import synthetic demo data")
    imp = sub.add_parser("import", help="import a CSV statement")
    imp.add_argument("file")
    imp.add_argument("--account", default=None)
    sub.add_parser("categorize", help="apply category rules")
    sub.add_parser("recurring", help="detect recurring costs")
    rep = sub.add_parser("report", help="print a monthly report")
    rep.add_argument("year", nargs="?", type=int)
    rep.add_argument("month", nargs="?", type=int)
    sub.add_parser("review", help="show pending review items")

    args = ap.parse_args(argv)
    ledger = Ledger()

    if args.cmd == "demo":
        path = generate_demo("./examples/synthetic-ledger/demo_statement.csv")
        r = import_csv(ledger, path, "Demo-Konto")
        stats = RulesEngine().apply_to_ledger(ledger)
        print(f"imported={r['inserted']} duplicates={r.duplicates if hasattr(r,'duplicates') else r['duplicates']} "
              f"categorized={stats['categorized']} review={stats['review']}")

    elif args.cmd == "import":
        r = import_csv(ledger, args.file, args.account)
        print(f"inserted={r['inserted']} duplicates={r['duplicates']} errors={len(r['errors'])}")
        for e in r["errors"][:5]:
            print(f"  line {e['line']}: {e['error']}")

    elif args.cmd == "categorize":
        stats = RulesEngine().apply_to_ledger(ledger)
        print(stats)

    elif args.cmd == "recurring":
        items = detect_recurring(ledger)
        if not items:
            print("(keine wiederkehrenden Kosten erkannt)")
        for i in items:
            print(f"{i['merchant']:<35} {i['typical_amount_cents']/100:>8.2f} EUR  "
                  f"alle ~{i['interval_days']:>3} Tg  ≈{i['estimated_monthly_cents']/100:.2f}/Monat  "
                  f"({i['occurrences']}x, {int(i['regularity']*100)}%)")

    elif args.cmd == "report":
        from datetime import date
        today = date.today()
        year, month = args.year or today.year, args.month or today.month
        print(monthly_report(ledger, year, month, detect_recurring(ledger)))

    elif args.cmd == "review":
        items = ledger.pending_review()
        if not items:
            print("(review queue leer)")
        for it in items:
            print(f"{it['txn_date']}  {it['amount_cents']/100:>9.2f}  {it['raw_description'][:60]}  [{it['reason']}]")


if __name__ == "__main__":
    sys.exit(main())
