from __future__ import annotations

from datetime import datetime

from filter_pattern.models import Candle
from filter_pattern.providers import _resample_to_h4


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
