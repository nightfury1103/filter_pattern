from __future__ import annotations

from datetime import datetime

from filter_pattern.models import Candle
from filter_pattern.providers import _candles_from_vnstock_frame, _exchange_ids, _period_date_range, _resample_to_h4


def test_resample_to_h4_aggregates_hourly_candles() -> None:
    candles = [
        Candle(datetime=datetime(2026, 1, 1, 1), open=10, high=12, low=9, close=11, volume=100),
        Candle(datetime=datetime(2026, 1, 1, 2), open=11, high=13, low=10, close=12, volume=120),
        Candle(datetime=datetime(2026, 1, 1, 4), open=12, high=15, low=11, close=14, volume=140),
    ]

    h4 = _resample_to_h4(candles)

    assert len(h4) == 2
    assert h4[0].datetime == datetime(2026, 1, 1, 0)
    assert h4[0].open == 10
    assert h4[0].high == 13
    assert h4[0].low == 9
    assert h4[0].close == 12
    assert h4[0].volume == 220
    assert h4[1].datetime == datetime(2026, 1, 1, 4)


def test_exchange_ids_allows_crypto_exchange_fallbacks() -> None:
    assert _exchange_ids("binance, bybit,okx") == ["binance", "bybit", "okx"]
    assert _exchange_ids("") == ["binance"]


def test_vnstock_frame_normalization_sorts_deduplicates_and_maps_ohlcv() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        [
            {"time": "2026-01-02", "open": 12, "high": 14, "low": 11, "close": 13, "volume": 2000},
            {"time": "2026-01-01", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 1000},
            {"time": "2026-01-02", "open": 13, "high": 15, "low": 12, "close": 14, "volume": 3000},
        ]
    )
    frame["time"] = pd.to_datetime(frame["time"])

    candles = _candles_from_vnstock_frame(frame, "FPT", "D1")

    assert len(candles) == 2
    assert candles[0].datetime == datetime(2026, 1, 1)
    assert candles[0].open == 10
    assert candles[1].datetime == datetime(2026, 1, 2)
    assert candles[1].open == 13
    assert candles[1].high == 15
    assert candles[1].volume == 3000


def test_period_date_range_uses_requested_period() -> None:
    start, end = _period_date_range("30d")

    assert start < end
