"""CLI extension for the market module.

  python -m packages.market_cli demo            seed sample portfolio + prices
  python -m packages.market_cli portfolio       show positions, value, P/L
  python -m packages.market_cli vol SYMBOL      annualized volatility
"""
from __future__ import annotations

import argparse
import os
import sys

from packages.markets.demo import seed_demo
from packages.markets.engine import MarketLedger

DEFAULT_DB = os.environ.get("LFA_MARKET_DB", "./data/db/market.db")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lfa-markets",
                                 description="Portfolio analytics (descriptive only — no predictions)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="seed sample portfolio + synthetic price history")
    imp = sub.add_parser("import-prices", help="import price CSV [date,close]")
    imp.add_argument("file")
    imp.add_argument("symbol")
    pos = sub.add_parser("add-position", help="record a position")
    pos.add_argument("symbol")
    pos.add_argument("quantity", type=float)
    pos.add_argument("avg_cost", type=float)
    sub.add_parser("portfolio", help="show portfolio summary")
    vol = sub.add_parser("vol", help="annualized volatility of a symbol")
    vol.add_argument("symbol")
    vol.add_argument("--window", type=int, default=90)

    args = ap.parse_args(argv)
    mkt = MarketLedger(DEFAULT_DB)

    if args.cmd == "demo":
        print(seed_demo(mkt))
        print("portfolio:")
        _print_portfolio(mkt)
    elif args.cmd == "import-prices":
        n = mkt.import_prices_csv(args.file, args.symbol)
        print(f"imported {n} price rows for {args.symbol}")
    elif args.cmd == "add-position":
        pid = mkt.add_position(args.symbol, args.quantity, args.avg_cost)
        print(f"position #{pid}: {args.quantity} {args.symbol} @ {args.avg_cost}")
    elif args.cmd == "portfolio":
        _print_portfolio(mkt)
    elif args.cmd == "vol":
        v = mkt.volatility(args.symbol, args.window)
        print(f"{v['symbol']}: daily_vol={v['daily_volatility']:.4f} "
              f"annualized={v['annualized_volatility']:.2%} ({v['points']} returns)")
        print("(descriptive statistic of past prices — not a prediction)")


def _print_portfolio(mkt):
    s = mkt.portfolio_summary()
    print(f"{'Symbol':<10} {'Qty':>10} {'AvgCost':>12} {'Last':>12} "
          f"{'Value':>14} {'P/L':>12}")
    for p in s["positions"]:
        last = f"{p['last_price']:.2f}" if p["last_price"] is not None else "n/a"
        val = f"{p['value']:,.2f}" if p["value"] is not None else "n/a"
        pl = f"{p['pl']:+,.2f}" if p["pl"] is not None else "n/a"
        print(f"{p['symbol']:<10} {p['quantity']:>10} {p['avg_cost']:>12.2f} "
              f"{last:>12} {val:>14} {pl:>12}")
    print(f"\nTotal: value {s['total_value']:,.2f} | cost {s['total_cost']:,.2f} | "
          f"P/L {s['total_pl']:+,.2f}")


if __name__ == "__main__":
    sys.exit(main())
