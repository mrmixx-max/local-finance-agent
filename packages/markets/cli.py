"""Market module CLI: python -m packages.markets.cli <command>

Commands:
  demo                       seed synthetic portfolio + 1y prices
  import-prices SYM FILE     import price CSV [date,close] for symbol
  add-position SYM QTY COST  record a position
  portfolio                  print current value / cost / P&L
  vol SYM [DAYS]             annualized volatility over lookback
"""
from __future__ import annotations

import argparse
import os
import sys

from packages.markets.engine import MarketLedger

DEFAULT_DB = os.environ.get("LFA_MARKET_DB", "./data/db/markets.db")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lfa-markets",
                                 description="Portfolio analytics (descriptive only — no predictions, no advice)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    imp = sub.add_parser("import-prices")
    imp.add_argument("symbol"); imp.add_argument("file")
    pos = sub.add_parser("add-position")
    pos.add_argument("symbol"); pos.add_argument("quantity", type=float)
    pos.add_argument("avg_cost", type=float)
    sub.add_parser("portfolio")
    vol = sub.add_parser("vol"); vol.add_argument("symbol"); vol.add_argument("days", nargs="?", type=int, default=90)
    args = ap.parse_args(argv)

    m = MarketLedger(DEFAULT_DB)

    if args.cmd == "demo":
        from packages.markets.demo import seed_demo
        r = seed_demo(m)
        for sym, info in r.items():
            print(f"{sym}: {info['price_rows']} price rows imported")

    elif args.cmd == "import-prices":
        n = m.import_prices_csv(args.file, args.symbol)
        print(f"imported {n} price rows for {args.symbol.upper()}")

    elif args.cmd == "add-position":
        pid = m.add_position(args.symbol, args.quantity, args.avg_cost)
        print(f"position #{pid}: {args.quantity} x {args.symbol.upper()} @ {args.avg_cost}")

    elif args.cmd == "portfolio":
        s = m.portfolio_summary()
        print(f"{'Symbol':<10} {'Qty':>10} {'ØKauf':>12} {'Last':>12} {'Wert':>14} {'G/V':>12}")
        for p in s["positions"]:
            last = f"{p['last_price']:.2f}" if p["last_price"] is not None else "—"
            val = f"{p['value']:.2f}" if p["value"] is not None else "—"
            pl = f"{p['pl']:+.2f}" if p["pl"] is not None else "—"
            print(f"{p['symbol']:<10} {p['quantity']:>10.4f} {p['avg_cost']:>12.2f} {last:>12} {val:>14} {pl:>12}")
        print(f"\nTotal: Wert {s['total_value']:.2f} · Kosten {s['total_cost']:.2f} · G/V {s['total_pl']:+.2f}")

    elif args.cmd == "vol":
        v = m.volatility(args.symbol, args.days)
        print(f"{v['symbol']}: {v['points']} Renditen | "
              f"daily vol {v['daily_volatility']*100:.2f}% | "
              f"annualisiert {v['annualized_volatility']*100:.1f}%")


if __name__ == "__main__":
    sys.exit(main())
