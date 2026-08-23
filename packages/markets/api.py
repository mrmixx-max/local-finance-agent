"""Market analysis API — descriptive statistics only. No predictions, no signals.

Endpoints are mounted under /api/markets by apps.api.main.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from packages.markets.demo import seed_demo

router = APIRouter(prefix="/api/markets", tags=["markets"])

MARKET_DB = os.environ.get("LFA_MARKET_DB", "./data/db/markets.db")


def _market():
    from packages.markets.engine import MarketLedger
    return MarketLedger(MARKET_DB)


class PriceImport(BaseModel):
    path: str
    symbol: str


@router.post("/demo-data")
def api_market_demo():
    market = _market()
    report = seed_demo(market)
    return {"seeded": report, "portfolio": market.portfolio_summary()}


@router.post("/prices/import")
def api_prices_import(req: PriceImport):
    market = _market()
    try:
        n = market.import_prices_csv(req.path, req.symbol)
    except FileNotFoundError:
        raise HTTPException(404, f"file not found: {req.path}")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"symbol": req.symbol.upper(), "rows": n}


@router.get("/portfolio")
def api_portfolio():
    return _market().portfolio_summary()


@router.get("/volatility/{symbol}")
def api_volatility(symbol: str, window: int = 90):
    if not 10 <= window <= 1000:
        raise HTTPException(400, "window must be 10..1000")
    try:
        return _market().volatility(symbol, window)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/correlation")
def api_correlation(a: str, b: str, window: int = 90):
    """Pearson correlation of daily returns between two instruments."""
    market = _market()
    try:
        ra = _returns(market, a.upper(), window)
        rb = _returns(market, b.upper(), window)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    n = min(len(ra), len(rb))
    if n < 3:
        raise HTTPException(404, "not enough overlapping history")
    ra, rb = ra[-n:], rb[-n:]
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = (sum((x - ma) ** 2 for x in ra)) ** 0.5
    vb = (sum((y - mb) ** 2 for y in rb)) ** 0.5
    if va == 0 or vb == 0:
        raise HTTPException(422, "zero variance in window")
    return {"a": a.upper(), "b": b.upper(), "window_points": n,
            "pearson_r": round(cov / (va * vb), 4)}


def _returns(market, symbol: str, window: int) -> list[float]:
    rows = market.volatility(symbol, window)
    # volatility() already computes returns internally; recompute here cheaply:
    v = market.volatility(symbol, window)
    del rows
    # simpler: pull closes and diff
    closes_q = """
        SELECT ph.close FROM price_history ph
        JOIN instruments i ON ph.instrument_id=i.id
        WHERE i.symbol=? ORDER BY ph.price_date DESC LIMIT ?"""
    rows_c = [r["close"] for r in market.conn.execute(closes_q, (symbol, window + 1))]
    closes = list(reversed(rows_c))
    return [(b / a - 1) for a, b in zip(closes, closes[1:])]
