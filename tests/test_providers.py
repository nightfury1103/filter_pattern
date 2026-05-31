from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from filter_pattern.models import Candle
from filter_pattern.providers import (
    _candles_from_vnstock_frame,
    _ccxt_symbol_candidates,
    _ccxt_symbol,
    _exchange_ids,
    _period_date_range,
    _resample_to_h4,
    _ccxt_worker_count,
    load_vnstock_ohlcv_many,
)


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


def test_ccxt_symbol_uses_swap_contract_key_for_perp_market_type() -> None:
    assert _ccxt_symbol("BTCUSDT", "perp") == "BTC/USDT:USDT"
    assert _ccxt_symbol("1000SHIBUSDT", "perp") == "1000SHIB/USDT:USDT"
    assert _ccxt_symbol("BTCUSDT", "spot") == "BTC/USDT"


def test_ccxt_symbol_candidates_include_mexc_stock_suffix_fallback_for_perps() -> None:
    assert _ccxt_symbol_candidates("AAPLUSDT", "perp") == ["AAPL/USDT:USDT", "AAPLSTOCK/USDT:USDT"]


def test_ccxt_worker_count_is_configurable_and_bounded(monkeypatch) -> None:
    monkeypatch.setenv("CCXT_MAX_WORKERS", "12")
    assert _ccxt_worker_count(100) == 12

    monkeypatch.setenv("CCXT_MAX_WORKERS", "100")
    assert _ccxt_worker_count(100) == 24

    monkeypatch.setenv("CCXT_MAX_WORKERS", "bad")
    assert _ccxt_worker_count(3) == 3


def test_deployment_defaults_use_16_ccxt_workers() -> None:
    root = Path(__file__).resolve().parents[1]

    run_script = (root / "run.sh").read_text()
    workflow = (root / ".github/workflows/scanner-pages-v2.yml").read_text()

    assert 'CCXT_MAX_WORKERS="${CCXT_MAX_WORKERS:-16}"' in run_script
    assert 'CCXT_MAX_WORKERS: "16"' in workflow


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


def test_vnstock_loader_times_out_slow_symbols(monkeypatch) -> None:
    class FakeQuote:
        pass

    def fake_import(name: str, globals=None, locals=None, fromlist=(), level=0):
        if name == "vnstock":
            return type("FakeModule", (), {"Quote": FakeQuote})
        return original_import(name, globals, locals, fromlist, level)

    def slow_load(*args, **kwargs):
        time.sleep(2)
        return []

    original_import = __import__
    monkeypatch.setenv("VNSTOCK_REQUEST_TIMEOUT_SECONDS", "1")
    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.setattr("filter_pattern.providers._load_vnstock_ohlcv", slow_load)

    start = time.monotonic()
    results = load_vnstock_ohlcv_many(["FPT"], period="30d", timeframe="D1", requests_per_minute=10_000)

    assert time.monotonic() - start < 1.8
    assert isinstance(results["FPT"], RuntimeError)
    assert "timed out" in str(results["FPT"])
