from __future__ import annotations

from datetime import datetime, timedelta

from filter_pattern.direction import (
    DirectionBias,
    DirectionMarketContext,
    backtest_direction,
    calculate_direction,
    collect_direction_backtest_samples,
    setup_direction_from_evidence,
)
from filter_pattern.models import Candle


def test_direction_blocks_short_when_weak_asset_starts_accumulating() -> None:
    candles = _candles_from_closes(
        [100 - index * 0.35 for index in range(140)]
        + [51 + index * 0.42 for index in range(45)]
    )

    snapshot = calculate_direction(candles)

    assert snapshot.phase == "Accumulation / Recovery"
    assert snapshot.bias == DirectionBias.WATCH_LONG
    assert snapshot.allows_short is False
    assert "Block shorts" in snapshot.trade_filter


def test_direction_blocks_long_when_strong_asset_starts_distributing() -> None:
    candles = _candles_from_closes(
        [50 + index * 0.38 for index in range(140)]
        + [103 - index * 0.48 for index in range(45)]
    )

    snapshot = calculate_direction(candles)

    assert snapshot.phase == "Distribution / Cooling"
    assert snapshot.bias == DirectionBias.WATCH_SHORT
    assert snapshot.allows_long is False
    assert "Block longs" in snapshot.trade_filter


def test_vcp_is_treated_as_long_direction() -> None:
    assert setup_direction_from_evidence({"reasons": ["Pattern: Original VCP"]}, "minervini-vcp", "original-vcp") == "long"


def test_crypto_price_only_direction_is_context_only() -> None:
    candles = _candles_from_closes([140 - index * 0.24 for index in range(300)])

    snapshot = calculate_direction(candles, market="Crypto")

    assert snapshot.bias == DirectionBias.WATCH_ONLY
    assert snapshot.allows_short is False
    assert "Context only for Crypto" in snapshot.trade_filter


def test_us_stock_long_requires_market_context_when_provided() -> None:
    candles = _candles_from_closes([50 + index * 0.28 for index in range(300)])
    context = DirectionMarketContext(
        market="US stock",
        long_allowed=False,
        short_allowed=False,
        label="US equity risk-off",
        reasons=("SPY/QQQ/breadth not aligned",),
    )

    snapshot = calculate_direction(candles, market="US stock", context=context)

    assert snapshot.bias == DirectionBias.WATCH_LONG
    assert snapshot.allows_long is False
    assert "market context" in snapshot.trade_filter


def test_us_stock_backtest_uses_market_context_to_filter_long_authority() -> None:
    candles_by_symbol = {
        "SPY": _candles_from_closes([100 + index * 0.15 for index in range(320)]),
        "QQQ": _candles_from_closes([100 - index * 0.12 for index in range(320)]),
        "AAPL": _candles_from_closes([50 + index * 0.30 for index in range(320)]),
    }
    samples = collect_direction_backtest_samples(
        candles_by_symbol,
        markets_by_symbol={symbol: "US stock" for symbol in candles_by_symbol},
        horizon=10,
        step=10,
        min_history=220,
    )

    assert all(sample.bias != DirectionBias.LONG_ALLOWED for sample in samples)


def test_direction_backtest_scores_allowed_and_blocked_signals() -> None:
    candles_by_symbol = {
        "UP": _candles_from_closes([50 + index * 0.28 for index in range(300)]),
        "DOWN": _candles_from_closes([140 - index * 0.24 for index in range(300)]),
    }

    report = backtest_direction(candles_by_symbol, horizon=10, step=10, min_history=180)

    assert report.sample_count > 0
    assert report.long_allowed.sample_count > 0
    assert report.long_allowed.hit_rate >= 0.8
    assert report.short_allowed.sample_count == 0
    assert report.watch_only.sample_count > 0


def _candles_from_closes(closes: list[float]) -> list[Candle]:
    start = datetime(2024, 1, 1)
    candles = []
    for index, close in enumerate(closes):
        candles.append(
            Candle(
                datetime=start + timedelta(days=index),
                open=close * 0.997,
                high=close * 1.006,
                low=close * 0.994,
                close=close,
                volume=100_000 + index,
            )
        )
    return candles
