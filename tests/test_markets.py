"""Tests for the market module: positions, price import, portfolio, volatility."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.markets.demo import generate_prices_csv
from packages.markets.engine import MarketLedger


@pytest.fixture()
def mkt(tmp_path):
    return MarketLedger(str(tmp_path / "market.db"))


def test_position_and_summary(mkt):
    # one year of synthetic prices for IWDA
    csv_path = generate_prices_csv(str(Path(mkt.db_path).parent / "iwda.csv"),
                                   "IWDA", days=365, start_price=80.0)
    n = mkt.import_prices_csv(csv_path, "IWDA")
    assert n >= 240  # ~252 trading days
    mkt.add_position("IWDA", 10.0, 75.0)

    s = mkt.portfolio_summary()
    assert len(s["positions"]) == 1
    pos = s["positions"][0]
    assert pos["quantity"] == 10.0
    assert abs(pos["cost"] - 750.0) < 1e-9
    assert pos["value"] is not None and pos["value"] > 0
    assert s["total_pl"] == pytest.approx(s["total_value"] - 750.0)


def test_price_upsert_is_safe(mkt):
    p = generate_prices_csv(str(Path(mkt.db_path).parent / "btc.csv"),
                            "BTC-EUR", days=30)
    n1 = mkt.import_prices_csv(p, "BTC-EUR")
    n2 = mkt.import_prices_csv(p, "BTC-EUR")
    assert n1 == n2  # upsert, no duplicates
    count = mkt.conn.execute("SELECT COUNT(*) c FROM price_history").fetchone()["c"]
    assert count == n1


def test_volatility(mkt):
    p = generate_prices_csv(str(Path(mkt.db_path).parent / "aek.csv"),
                            "AEK", days=365, daily_vol=0.02)
    mkt.import_prices_csv(p, "AEK")
    v = mkt.volatility("AEK", window_days=365)
    assert 0.01 < v["annualized_volatility"] < 1.5  # sane band for the seeded series
    assert v["points"] >= 200


def test_volatility_insufficient_data(mkt):
    with pytest.raises(ValueError):
        mkt.volatility("UNKNOWN")


def test_scope_guard_no_prediction_api():
    """Guard rail: the module must not expose prediction/signal functions."""
    import packages.markets.engine as eng
    forbidden = ("predict", "forecast", "signal", "recommend", "advice")
    public = [n for n in dir(eng) if not n.startswith("_")]
    for word in forbidden:
        assert not any(word in fn.lower() for fn in public), f"found {word} in {public}"
