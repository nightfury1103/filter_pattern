from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from filter_pattern.models import Candle
from filter_pattern.providers import (
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


def test_period_date_range_uses_requested_period() -> None:
    start, end = _period_date_range("30d")

    assert start < end


def chart_payload(times=None, scale=1):
    times = times if times is not None else ["2026-01-02T02:00:00"]
    return {
        "t": [int(datetime.fromisoformat(t).replace(tzinfo=timezone.utc).timestamp()) for t in times],
        "o": [33.4 * scale] * len(times), "h": [34 * scale] * len(times),
        "l": [33 * scale] * len(times), "c": [33.8 * scale] * len(times),
        "v": [2000] * len(times),
    }


def response(payload, status=200, text=""):
    return Mock(status_code=status, text=text, json=Mock(return_value=payload))


@pytest.fixture
def chart_apis(monkeypatch):
    monkeypatch.delenv("VNSTOCK_SOURCE", raising=False)
    monkeypatch.setenv("VNSTOCK_REQUEST_TIMEOUT_SECONDS", "8")
    monkeypatch.setattr("filter_pattern.providers._period_date_range", lambda period: ("2026-01-01", "2026-01-31"))
    get = Mock(return_value=response(chart_payload()))
    post = Mock(return_value=response([{"symbol": "FPT", **chart_payload(scale=1000)}]))
    monkeypatch.setattr("filter_pattern.providers.requests.get", get)
    monkeypatch.setattr("filter_pattern.providers.requests.post", post)
    return get, post


def test_entrade_parsing_units_and_request_range(chart_apis):
    get, post = chart_apis
    before = int(datetime.now(timezone.utc).timestamp())
    result = load_vnstock_ohlcv_many(["FPT"], source="DNSE")["FPT"]
    after = int(datetime.now(timezone.utc).timestamp())
    assert result == [Candle(datetime(2026, 1, 2), 33.4, 34, 33, 33.8, 2000)]
    get.assert_called_once()
    post.assert_not_called()
    args, kw = get.call_args
    assert args == ("https://services.entrade.com.vn/chart-api/v2/ohlcs/stock",)
    assert kw["timeout"] == 8
    assert kw["params"]["symbol"] == "FPT"
    assert kw["params"]["resolution"] == "1D"
    assert kw["params"]["from"] == int(datetime(2025, 12, 31, 17, tzinfo=timezone.utc).timestamp())
    assert before <= kw["params"]["to"] <= after


@pytest.mark.parametrize("source", [None, "AUTO", "automatic", "vci"])
def test_vietcap_scales_prices_and_filters_start(chart_apis, source):
    get, post = chart_apis
    post.return_value = response([chart_payload(["2025-12-31T00:00:00", "2026-01-02T00:00:00"], scale=1000)])
    result = load_vnstock_ohlcv_many(["FPT"], source=source)["FPT"]
    assert result == [Candle(datetime(2026, 1, 2), 33.4, 34, 33, 33.8, 2000)]
    get.assert_not_called()
    post.assert_called_once()
    args, kw = post.call_args
    assert args == ("https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",)
    assert kw["timeout"] == 8
    assert kw["json"]["symbols"] == ["FPT"]
    assert kw["json"]["timeFrame"] == "ONE_DAY"
    assert kw["json"]["countBack"] >= 31
    assert kw["headers"] == {
        "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Mozilla/5.0",
        "Origin": "https://trading.vietcap.com.vn", "Referer": "https://trading.vietcap.com.vn/",
    }


@pytest.mark.parametrize("failure", [requests.Timeout("timed out"), response({}, 503, "unavailable"), response([chart_payload([])])])
def test_vietcap_failure_or_empty_data_falls_back(chart_apis, failure):
    get, post = chart_apis
    if isinstance(failure, Exception):
        post.side_effect = failure
    else:
        post.return_value = failure
    result = load_vnstock_ohlcv_many(["FPT"], source="automatic")["FPT"]
    assert result[0].close == 33.8
    get.assert_called_once()
    post.assert_called_once()


def test_both_failures_are_stored_and_next_symbol_still_loads(chart_apis, monkeypatch):
    get, post = chart_apis
    monkeypatch.setattr("filter_pattern.providers.time.sleep", Mock())
    get.side_effect = [response({}, 400, "invalid symbol"), response(chart_payload())]
    post.return_value = response({}, 502, "x" * 1000)
    result = load_vnstock_ohlcv_many(["BAD", "FPT"])
    error = result["BAD"]
    assert isinstance(error, Exception)
    assert "DNSE: HTTP 400" in str(error) and "VCI: HTTP 502" in str(error)
    assert "x" * 201 not in str(error)
    assert isinstance(result["FPT"], list)


@pytest.mark.parametrize("source, failing", [("dnse", "get"), ("VCI", "post")])
def test_explicit_source_forces_one_provider_on_failure(chart_apis, source, failing):
    get, post = chart_apis
    active, other = (get, post) if failing == "get" else (post, get)
    active.side_effect = requests.ConnectionError("unavailable")
    assert isinstance(load_vnstock_ohlcv_many(["FPT"], source=source)["FPT"], Exception)
    active.assert_called_once()
    other.assert_not_called()


def test_source_environment_and_argument_precedence(chart_apis, monkeypatch):
    get, post = chart_apis
    monkeypatch.setenv("VNSTOCK_SOURCE", "vci")
    assert isinstance(load_vnstock_ohlcv_many(["FPT"])["FPT"], list)
    get.assert_not_called()
    post.assert_called_once()
    assert isinstance(load_vnstock_ohlcv_many(["FPT"], source="DNSE")["FPT"], list)
    get.assert_called_once()
    post.assert_called_once()


def test_daily_local_dates_sort_and_keep_last_duplicate(chart_apis):
    get, _ = chart_apis
    payload = chart_payload(["2026-01-03T02:00:00", "2026-01-02T00:00:00", "2026-01-03T02:00:00", "2026-01-03T17:00:00"])
    payload["c"][2] = 33.9
    get.return_value = response(payload)
    result = load_vnstock_ohlcv_many(["FPT"], source="DNSE")["FPT"]
    assert [c.datetime for c in result] == [datetime(2026, 1, 2), datetime(2026, 1, 3), datetime(2026, 1, 4)]
    assert result[1].close == 33.9
    assert all(c.datetime.tzinfo is None for c in result)


@pytest.mark.parametrize("bad", [None, float("nan"), 0, -1, "missing"])
def test_invalid_prices_skipped_and_missing_volume_defaults_to_zero(chart_apis, bad):
    get, _ = chart_apis
    payload = chart_payload(["2026-01-02T00:00:00", "2026-01-03T00:00:00"])
    payload["o"][0] = bad
    payload["v"][1] = None
    get.return_value = response(payload)
    result = load_vnstock_ohlcv_many(["FPT"], source="DNSE")["FPT"]
    assert result == [Candle(datetime(2026, 1, 3), 33.4, 34, 33, 33.8, 0)]


@pytest.mark.parametrize("payload, message", [
    ({}, "requires arrays"), ([], "requires arrays"),
    ({**chart_payload(), "v": []}, "equal length"),
    ({**chart_payload(), "c": "not an array"}, "requires arrays"),
])
def test_malformed_entrade_payload_stored_as_clear_error(chart_apis, payload, message):
    get, _ = chart_apis
    get.return_value = response(payload)
    result = load_vnstock_ohlcv_many(["FPT"], source="DNSE")["FPT"]
    assert isinstance(result, Exception)
    assert message in str(result)


@pytest.mark.parametrize("payload", [{}, [], [{}, {}]])
def test_malformed_vietcap_envelope_is_rejected(chart_apis, payload):
    _, post = chart_apis
    post.return_value = response(payload)
    result = load_vnstock_ohlcv_many(["FPT"], source="VCI")["FPT"]
    assert isinstance(result, Exception)
    assert "one symbol object" in str(result)


@pytest.mark.parametrize("source", ["DNSE", "VCI"])
def test_hourly_api_data_is_resampled_in_local_time(chart_apis, source):
    get, post = chart_apis
    times = ["2026-01-02T02:00:00", "2026-01-02T03:00:00", "2026-01-02T06:00:00"]
    payload = chart_payload(times, scale=1000 if source == "VCI" else 1)
    payload["v"] = [100, 200, 400]
    (post if source == "VCI" else get).return_value = response([payload] if source == "VCI" else payload)
    result = load_vnstock_ohlcv_many(["FPT"], timeframe="H4", source=source)["FPT"]
    assert result == [Candle(datetime(2026, 1, 2, 8), 33.4, 34, 33, 33.8, 300),
                      Candle(datetime(2026, 1, 2, 12), 33.4, 34, 33, 33.8, 400)]
    if source == "DNSE":
        assert get.call_args.kwargs["params"]["resolution"] == "1H"
    else:
        body = post.call_args.kwargs["json"]
        assert body["timeFrame"] == "ONE_HOUR"
        assert 31 * 24 <= body["countBack"] <= 5000


def test_hourly_count_back_is_capped(chart_apis, monkeypatch):
    _, post = chart_apis
    monkeypatch.setattr("filter_pattern.providers._period_date_range", lambda period: ("2016-01-01", "2026-01-31"))
    load_vnstock_ohlcv_many(["FPT"], period="10y", timeframe="H4", source="VCI")
    assert post.call_args.kwargs["json"]["countBack"] == 5000


@pytest.mark.parametrize("timeout, expected", [("0", 15), ("-2", 15), ("bad", 20), ("3", 3)])
def test_http_timeout_is_always_positive(chart_apis, monkeypatch, timeout, expected):
    get, post = chart_apis
    monkeypatch.setenv("VNSTOCK_REQUEST_TIMEOUT_SECONDS", timeout)
    post.side_effect = requests.Timeout("timed out")
    load_vnstock_ohlcv_many(["FPT"])
    assert get.call_args.kwargs["timeout"] == expected
    assert post.call_args.kwargs["timeout"] == expected


def test_keyboard_interrupt_propagates(chart_apis):
    get, post = chart_apis
    post.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        load_vnstock_ohlcv_many(["FPT"])
    get.assert_not_called()


def test_per_symbol_throttle_and_symbol_deduplication(chart_apis, monkeypatch):
    get, post = chart_apis
    sleep = Mock()
    monkeypatch.setattr("filter_pattern.providers.time.sleep", sleep)
    monkeypatch.setattr("filter_pattern.providers.time.monotonic", lambda: 10.0)
    result = load_vnstock_ohlcv_many(["FPT", "FPT", "E1VFVN30"])
    assert list(result) == ["FPT", "E1VFVN30"]
    assert post.call_count == 2
    get.assert_not_called()
    sleep.assert_called_once_with(60 / 18)
