from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .models import AppConfig, Candle, SymbolSpec, VCPConfig
from .techniques import normalize_setup, normalize_technique


COLUMN_ALIASES = {
    "datetime": ("datetime", "time", "date", "timestamp"),
    "open": ("open",),
    "high": ("high",),
    "low": ("low",),
    "close": ("close",),
    "volume": ("volume", "vol"),
}
REQUIRED_COLUMNS = {"datetime", "open", "high", "low", "close"}


def load_config(path: str | Path, require_symbols: bool = True) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. "
            "Create one from examples/config.example.yml or pass the correct --config path."
        )
    raw = yaml.safe_load(config_path.read_text()) or {}

    timeframe = _normalize_timeframe(raw.get("timeframe", "D1"))
    technique = normalize_technique(raw.get("technique", "minervini-vcp"))
    setup = normalize_setup(raw.get("setup", "all"))

    vcp_raw = raw.get("vcp", {}) or {}
    vcp = VCPConfig(**{key: value for key, value in vcp_raw.items() if hasattr(VCPConfig, key)})

    symbols = []
    for item in raw.get("symbols", []) or []:
        csv_path = Path(item["csv_path"])
        if not csv_path.is_absolute():
            csv_path = (config_path.parent / csv_path).resolve()
        symbols.append(
            SymbolSpec(
                symbol=str(item["symbol"]),
                market=str(item.get("market", "unknown")),
                tradingview_symbol=str(item.get("tradingview_symbol", item["symbol"])),
                csv_path=csv_path,
            )
        )

    if require_symbols and not symbols:
        raise ValueError("config must include at least one symbol")

    return AppConfig(timeframe=timeframe, symbols=symbols, vcp=vcp, technique=technique, setup=setup)


def load_ohlcv_csv(path: str | Path) -> list[Candle]:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {csv_path}")

        field_map = _resolve_field_map(reader.fieldnames)
        missing = REQUIRED_COLUMNS - set(field_map)
        if missing:
            raise ValueError(f"CSV missing columns {sorted(missing)}: {csv_path}")

        candles_by_time: dict[datetime, Candle] = {}
        for row_number, row in enumerate(reader, start=2):
            try:
                dt = _parse_datetime(row[field_map["datetime"]])
                candle = Candle(
                    datetime=dt,
                    open=_parse_float(row[field_map["open"]], "open", row_number),
                    high=_parse_float(row[field_map["high"]], "high", row_number),
                    low=_parse_float(row[field_map["low"]], "low", row_number),
                    close=_parse_float(row[field_map["close"]], "close", row_number),
                    volume=_parse_float(_optional_row_value(row, field_map, "volume"), "volume", row_number),
                )
            except KeyError as exc:
                raise ValueError(f"CSV row {row_number} is missing field {exc}: {csv_path}") from exc

            if candle.high < candle.low:
                raise ValueError(f"CSV row {row_number} has high lower than low: {csv_path}")
            candles_by_time[dt] = candle

    candles = [candles_by_time[key] for key in sorted(candles_by_time)]
    if not candles:
        raise ValueError(f"CSV contains no candles: {csv_path}")
    return candles


def _resolve_field_map(fields: list[str]) -> dict[str, str]:
    normalized = {field.strip().lower(): field for field in fields}
    resolved: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                resolved[canonical] = normalized[alias]
                break
    return resolved


def _optional_row_value(row: dict[str, str], field_map: dict[str, str], name: str) -> str:
    field = field_map.get(name)
    if field is None:
        return "0"
    return row.get(field, "0") or "0"


def config_to_json(config: AppConfig) -> dict[str, Any]:
    return {
        "timeframe": config.timeframe,
        "technique": config.technique,
        "setup": config.setup,
        "vcp": config.vcp.__dict__,
        "symbols": [
            {
                "symbol": item.symbol,
                "market": item.market,
                "tradingview_symbol": item.tradingview_symbol,
                "csv_path": str(item.csv_path),
            }
            for item in config.symbols
        ],
    }


def _parse_datetime(value: str) -> datetime:
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
    raise ValueError(f"invalid datetime: {value!r}")


def _parse_float(value: str, field: str, row_number: int) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError as exc:
        raise ValueError(f"invalid {field} at CSV row {row_number}: {value!r}") from exc


def _normalize_timeframe(value: object) -> str:
    timeframe = str(value).upper()
    if timeframe not in {"D1", "H4"}:
        raise ValueError("supported timeframes are D1 and H4")
    return timeframe
