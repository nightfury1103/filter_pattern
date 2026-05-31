from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from filter_pattern.direction_backtest import run_direction_backtest
from filter_pattern.models import Candle
from filter_pattern.universe import UniverseSymbol


def test_run_direction_backtest_writes_json_and_html(tmp_path: Path, monkeypatch) -> None:
    universe = [
        UniverseSymbol("SPY", "US stock", "AMEX:SPY", "SPY"),
        UniverseSymbol("QQQ", "US stock", "NASDAQ:QQQ", "QQQ"),
        UniverseSymbol("AAPL", "US stock", "NASDAQ:AAPL", "AAPL"),
    ]

    def fake_universe(name: str):
        return universe

    def fake_loader(symbols: list[str], period: str = "5y", timeframe: str = "D1"):
        return {
            "SPY": _candles_from_closes([100 * (1.0018**index) for index in range(600)]),
            "QQQ": _candles_from_closes([100 * (1.0020**index) for index in range(600)]),
            "AAPL": _candles_from_closes([50 * (1.0022**index) for index in range(600)]),
        }

    monkeypatch.setattr("filter_pattern.direction_backtest.get_universe", fake_universe)
    monkeypatch.setattr("filter_pattern.direction_backtest.load_yahoo_ohlcv_many", fake_loader)

    results_path = run_direction_backtest(tmp_path / "direction-bt", limit=2, horizon=10, step=2, min_history=180)
    payload = json.loads(results_path.read_text())
    html = (tmp_path / "direction-bt/index.html").read_text()

    assert payload["backtest"]["sample_count"] > 0
    assert set(payload["backtests_by_market"]) == {"US stock"}
    assert payload["backtests_by_market"]["US stock"]["validation"]["long_authority"] == "validated"
    assert payload["backtests_by_market"]["US stock"]["long_allowed"]["hit_rate"] >= 0.8
    assert payload["backtest"]["long_allowed"]["hit_rate"] >= 0.8
    assert payload["backtest"]["short_allowed"]["sample_count"] == 0
    assert "Direction Authority Backtest" in html
    assert "Market-Level Validation" in html
    assert "US stock" in html
    assert "LONG ALLOWED" in html
    assert "WATCH / BLOCKED" in html


def _candles_from_closes(closes: list[float]) -> list[Candle]:
    start = datetime(2024, 1, 1)
    return [
        Candle(
            datetime=start + timedelta(days=index),
            open=close * 0.997,
            high=close * 1.006,
            low=close * 0.994,
            close=close,
            volume=100_000 + index,
        )
        for index, close in enumerate(closes)
    ]
