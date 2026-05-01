from __future__ import annotations

from collections import Counter

from filter_pattern.universe import default_universe, get_universe


def test_default_universe_covers_multiple_markets_with_substantial_non_us_lists() -> None:
    counts = Counter(item.market for item in default_universe())

    assert counts["US stock"] >= 60
    assert counts["Vietnam stock"] >= 300
    assert counts["Forex"] >= 30
    assert counts["Crypto"] >= 60
    assert counts["Commodity"] + counts["Commodity ETF"] >= 50


def test_broad_universe_includes_sp500_plus_cross_market_symbols() -> None:
    universe = get_universe("broad")
    counts = Counter(item.market for item in universe)

    assert len(universe) >= 900
    assert counts["US stock"] >= 500
    assert counts["Vietnam stock"] >= 300
    assert counts["Forex"] >= 80
    assert counts["Crypto"] >= 60
    assert counts["Commodity"] >= 30
