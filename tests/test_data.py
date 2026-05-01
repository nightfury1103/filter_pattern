from __future__ import annotations

from pathlib import Path

import pytest

from filter_pattern.data import load_config, load_ohlcv_csv


def test_load_ohlcv_csv_sorts_dedupes_and_defaults_missing_volume(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "datetime,open,high,low,close\n"
        "2025-01-03,12,13,11,12.5\n"
        "2025-01-01,10,11,9,10.5\n"
        "2025-01-03,13,14,12,13.5\n"
    )

    candles = load_ohlcv_csv(csv_path)

    assert [item.datetime.date().isoformat() for item in candles] == ["2025-01-01", "2025-01-03"]
    assert candles[-1].close == 13.5
    assert candles[-1].volume == 0


def test_load_ohlcv_csv_rejects_missing_required_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("datetime,open,high,close,volume\n2025-01-01,1,2,1.5,100\n")

    with pytest.raises(ValueError, match="missing columns"):
        load_ohlcv_csv(csv_path)


def test_load_ohlcv_csv_accepts_tradingview_time_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "tv.csv"
    csv_path.write_text(
        "time,open,high,low,close,Volume\n"
        "2026-01-01T04:00:00,10,11,9,10.5,1000\n"
    )

    candles = load_ohlcv_csv(csv_path)

    assert candles[0].datetime.isoformat() == "2026-01-01T04:00:00"
    assert candles[0].volume == 1000


def test_load_config_resolves_relative_paths_and_vcp_thresholds(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "timeframe: D1\n"
        "technique: nhathoai\n"
        "setup: rb\n"
        "vcp:\n"
        "  near_pivot_pct: 4\n"
        "symbols:\n"
        "  - symbol: AAPL\n"
        "    market: US stock\n"
        "    tradingview_symbol: NASDAQ:AAPL\n"
        "    csv_path: data/aapl.csv\n"
    )

    config = load_config(config_path)

    assert config.timeframe == "D1"
    assert config.technique == "nhathoai"
    assert config.setup == "rb"
    assert config.vcp.near_pivot_pct == 4
    assert config.symbols[0].csv_path == (tmp_path / "data/aapl.csv").resolve()


def test_load_config_missing_file_has_actionable_message(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="examples/config.example.yml"):
        load_config(tmp_path / "missing.yml")


def test_load_config_validates_unknown_technique(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "timeframe: D1\n"
        "technique: wrong\n"
        "symbols:\n"
        "  - symbol: AAPL\n"
        "    csv_path: data/aapl.csv\n"
    )

    with pytest.raises(ValueError, match="unknown technique"):
        load_config(config_path)


def test_load_config_can_load_symbolless_market_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "market.yml"
    config_path.write_text(
        "timeframe: D1\n"
        "technique: nhathoai\n"
        "setup: rb\n"
        "vcp:\n"
        "  near_pivot_pct: 3\n"
    )

    config = load_config(config_path, require_symbols=False)

    assert config.symbols == []
    assert config.technique == "nhathoai"
    assert config.setup == "rb"
    assert config.vcp.near_pivot_pct == 3


def test_load_config_accepts_h4_timeframe(tmp_path: Path) -> None:
    config_path = tmp_path / "market.yml"
    config_path.write_text(
        "timeframe: H4\n"
        "technique: nhathoai\n"
        "setup: rb\n"
    )

    config = load_config(config_path, require_symbols=False)

    assert config.timeframe == "H4"
