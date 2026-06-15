from __future__ import annotations

import json
import math
import os
import re
import time
from collections.abc import Callable
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from datetime import timedelta
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import requests
from bs4 import BeautifulSoup

from .chart import render_chart
from .data import load_config
from .detector import detect_pattern
from .exness import is_exness_supported_symbol
from .models import Candle, ScanResult, SymbolSpec, VCPConfig
from .providers import load_ccxt_ohlcv_many, load_yahoo_ohlcv_many
from .providers import load_vnstock_ohlcv_many
from .scanner import _apply_ema_side_guard, _apply_near_trigger_volume_signal, _setups_to_scan
from .universe import get_universe


STOCKCHARTS_RRG_URL = "https://stockcharts.com/d-rrg/rrg"
FIALDA_RRG_URL = "https://fwtapi2.fialda.com/api/services/app/RRG/RRGData"
FIALDA_INITIAL_DATA_URL = "https://fwtapi2.fialda.com/api/services/app/Configuration/GetInitialData"
FIALDA_ICB_TREE_URL = "https://fwtapi2.fialda.com/api/services/app/ICB/GetIcbTree"
DEFAULT_STOCKCHARTS_AUTH = "89768844867688448576149"
RRG_TAIL_ROWS = 10
RRG_REQUEST_DAYS = 60
RRG_CHUNK_SIZE = 45
RRG_PREVIEW_DPI = 72
RRG_PREVIEW_QUALITY = 64
FIALDA_SYMBOL_CHUNK_SIZE = 80
FIALDA_SECTOR_IDS = ("1", "12", "31", "61", "91", "100", "124", "130", "138", "166")

SECTOR_ETFS = {
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Information Technology": "XLK",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}

QUADRANT_COLORS = {
    "LEADING": "#16a34a",
    "IMPROVING": "#2563eb",
    "WEAKENING": "#ea580c",
    "LAGGING": "#dc2626",
}
QUADRANT_BACKGROUNDS = {
    "LEADING": "#dcfce7",
    "IMPROVING": "#dbeafe",
    "WEAKENING": "#fef3c7",
    "LAGGING": "#fee2e2",
}
RRG_REFERENCE_MARKETS = {"US stock", "Vietnam stock", "Crypto", "Forex", "Commodity", "Commodity ETF"}
RRG_MARKET_REPRESENTATIVES = {
    "US stock": ["SPY"],
    "Vietnam stock": ["VNINDEX"],
    "Crypto": ["BTCUSDT", "ETHUSDT"],
    "Forex": ["DXY"],
    "Commodity": ["XAUUSD"],
    "Commodity ETF": ["DBC"],
}
COMMODITY_STOCKCHARTS_SYMBOLS = {
    "XAUUSD": "$GOLD",
    "GOLD": "$GOLD",
    "XAGUSD": "$SILVER",
    "SILVER": "$SILVER",
    "WTI": "$WTIC",
    "USOIL": "$WTIC",
    "BRENT": "$BRENT",
    "UKOIL": "$BRENT",
    "NATGAS": "$NATGAS",
    "XNGUSD": "$NATGAS",
    "XCUUSD": "$COPPER",
    "COPPER": "$COPPER",
    "CORN": "$CORN",
    "WHEAT": "$WHEAT",
    "SOYBEANS": "$SOYB",
    "SOYB": "$SOYB",
    "COFFEE": "$COFFEE",
    "COCOA": "$COCOA",
    "SUGAR": "$SUGAR",
    "COTTON": "$COTTON",
    "GOLD_ETF": "GLD",
    "SILVER_ETF": "SLV",
}


@dataclass(frozen=True)
class RRGSelection:
    symbol: str
    sector: str
    benchmark: str
    latest: dict
    intent: dict
    sector_latest: dict
    sector_intent: dict
    rrg_series: list[dict]


def rrg_quadrant(x: float, y: float) -> str:
    if x >= 100 and y >= 100:
        return "LEADING"
    if x < 100 and y >= 100:
        return "IMPROVING"
    if x >= 100 and y < 100:
        return "WEAKENING"
    return "LAGGING"


def rrg_intent(points: list[dict]) -> dict:
    if len(points) < 4:
        return {"accepted": False, "reason": "not enough points", "score": -999.0}
    tail = points[-RRG_TAIL_ROWS:]
    latest = tail[-1]
    previous = tail[-2]
    before_previous = tail[-3]
    x = float(latest["x"])
    y = float(latest["y"])
    dx1 = x - float(previous["x"])
    dy1 = y - float(previous["y"])
    dx2 = float(previous["x"]) - float(before_previous["x"])
    dy2 = float(previous["y"]) - float(before_previous["y"])
    quadrant = rrg_quadrant(x, y)
    two_steps_down = dy1 < 0 and dy2 < 0
    accepted = quadrant in {"LEADING", "IMPROVING"} and dy1 > 0 and not two_steps_down
    score = (x - 100) + (y - 100) * 1.4 + dx1 * 2 + dy1 * 3
    return {
        "accepted": accepted,
        "quadrant": quadrant,
        "dx1": dx1,
        "dy1": dy1,
        "dx2": dx2,
        "dy2": dy2,
        "two_steps_down": two_steps_down,
        "score": score,
    }


def rrg_confidence(intent: dict) -> dict:
    quadrant = str(intent.get("quadrant") or "")
    dx1 = _float_value(intent.get("dx1"))
    dy1 = _float_value(intent.get("dy1"))
    dy2 = _float_value(intent.get("dy2"))
    two_steps_down = bool(intent.get("two_steps_down"))

    if not quadrant:
        return {
            "label": "RRG Unavailable",
            "tone": "neutral",
            "blocks_pattern": False,
            "note": "No RRG reference data was available for this symbol.",
        }
    if quadrant in {"LEADING", "IMPROVING"} and dy1 > 0 and not two_steps_down:
        return {
            "label": "RRG Supportive Reference",
            "tone": "supportive",
            "blocks_pattern": False,
            "note": "Relative strength and momentum are rising. Use as confirmation only, not as a scanner gate.",
        }
    if dy1 > 0 or (dy1 >= 0 and dx1 > 0):
        return {
            "label": "RRG Early Reference",
            "tone": "early",
            "blocks_pattern": False,
            "note": "RRG is improving from a slower position. The price setup remains the primary signal.",
        }
    if two_steps_down or (dy1 < 0 and dy2 < 0):
        return {
            "label": "RRG Warning Reference",
            "tone": "warning",
            "blocks_pattern": False,
            "note": "RRG momentum is falling. Do not remove the setup automatically; review the price chart carefully.",
        }
    return {
        "label": "RRG Neutral Reference",
        "tone": "neutral",
        "blocks_pattern": False,
        "note": "RRG is mixed or flat. Keep the pattern decision on the price setup.",
    }


def attach_rrg_references(payload: dict, output_dir: str | Path, timeframe: str = "D1") -> dict:
    rows = _rrg_reference_rows(payload)
    symbols_by_market: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        market = str(row.get("market") or "")
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        if market in RRG_REFERENCE_MARKETS:
            symbols_by_market[market].add(symbol)

    if not any(symbols_by_market.values()):
        payload["rrg_reference"] = {
            "enabled": True,
            "status": "no_supported_symbols",
            "attached_count": 0,
            "note": "RRG reference supports US stock, Vietnam stock, crypto, forex, commodity, and commodity ETF symbols when data is available.",
        }
        return payload

    rrg_dir = Path(output_dir) / "rrg-reference"
    _clear_images(rrg_dir)
    selections: dict[str, RRGSelection] = {}
    errors: list[str] = []
    fetchers = {
        "US stock": _usstock_rrg_references,
        "Crypto": lambda symbols: _crypto_rrg_references(symbols, timeframe),
        "Vietnam stock": _vnstock_rrg_references,
        "Forex": _forex_rrg_references,
        "Commodity": lambda symbols: _commodity_rrg_references(symbols, "Commodity"),
        "Commodity ETF": lambda symbols: _commodity_rrg_references(symbols, "Commodity ETF"),
    }
    representative_fetchers = {
        "US stock": _usstock_rrg_references,
        "Crypto": lambda symbols: _crypto_rrg_references(symbols, "D1"),
        "Vietnam stock": _vnstock_rrg_references,
        "Forex": _forex_rrg_references,
        "Commodity": lambda symbols: _commodity_rrg_references(symbols, "Commodity"),
        "Commodity ETF": lambda symbols: _commodity_rrg_references(symbols, "Commodity ETF"),
    }
    for market, symbols in sorted(symbols_by_market.items()):
        if not symbols:
            continue
        try:
            selections.update(fetchers[market](sorted(symbols)))
        except Exception as exc:  # RRG is reference-only; never fail the old pattern scan.
            errors.append(f"{market}: {exc}")

    market_representatives = _market_representative_rrg_rows(symbols_by_market, representative_fetchers, errors)

    chart_cache: dict[str, Path] = {}
    attached = 0
    all_selections = list(selections.values())
    for row in rows:
        symbol = str(row.get("symbol") or "")
        selected = selections.get(symbol)
        if selected is None:
            continue
        rrg_path = chart_cache.get(symbol)
        if rrg_path is None:
            try:
                rrg_path = _render_stock_rrg_proof(selected, all_selections, rrg_dir)
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")
                continue
            chart_cache[symbol] = rrg_path
        row["rrg"] = _rrg_json(selected, rrg_path)
        attached += 1

    payload["rrg_reference"] = {
        "enabled": True,
        "status": "attached" if attached else "no_data",
        "attached_count": attached,
        "symbol_count": sum(len(symbols) for symbols in symbols_by_market.values()),
        "market_representatives": market_representatives,
        "errors": errors[:8],
        "note": "RRG is attached as a non-blocking reference. It does not decide whether a pattern stays on the watchlist.",
    }
    return payload


def _market_representative_rrg_rows(
    symbols_by_market: dict[str, set[str]],
    fetchers: dict[str, Callable[[list[str]], dict[str, RRGSelection]]],
    errors: list[str],
) -> list[dict]:
    rows: list[dict] = []
    for market in sorted(symbols_by_market):
        symbols = RRG_MARKET_REPRESENTATIVES.get(market) or []
        if not symbols:
            continue
        try:
            selections = fetchers[market](symbols)
        except Exception as exc:  # Keep representative context non-blocking.
            errors.append(f"{market} representative: {exc}")
            continue
        for symbol in symbols:
            selected = selections.get(symbol)
            if selected is None:
                continue
            rows.append(
                {
                    "symbol": _market_representative_display_symbol(market, symbol),
                    "market": market,
                    "timeframe": "D1",
                    "setup": "market",
                    "evidence": {"status": "RRG_MARKET_REPRESENTATIVE", "score": 0},
                    "rrg": _rrg_json(selected),
                }
            )
    return rows


def _market_representative_display_symbol(market: str, symbol: str) -> str:
    return symbol


def build_usstock_rrg_demo(
    out_dir: str | Path,
    timeframe: str = "D1",
    config_path: str | Path | None = None,
    period: str = "2y",
    technique: str | None = None,
    setup: str | None = None,
    max_sectors: int | None = None,
    max_symbols: int | None = None,
) -> Path:
    active_timeframe = timeframe.upper()
    if active_timeframe not in {"D1", "H4"}:
        raise ValueError("supported timeframes are D1 and H4")
    vcp_config, active_technique, active_setup = _demo_config(config_path, technique, setup)
    setup_names = _setups_to_scan(active_technique, active_setup)

    output_dir = Path(out_dir)
    chart_dir = output_dir / "charts"
    rrg_dir = output_dir / "rrg"
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_images(chart_dir)
    _clear_images(rrg_dir)

    sp500 = _load_sp500_constituents()
    sector_series = _fetch_us_sector_rrg()
    accepted_sectors = _accepted_sectors(sector_series)
    if max_sectors is not None:
        accepted_sectors = accepted_sectors[: max(0, max_sectors)]
    stock_rrg = _accepted_stocks_for_sectors(accepted_sectors, sp500)
    rrg_approved_before_broker = len(stock_rrg)
    stock_rrg = _filter_exness_supported_us_stocks(stock_rrg)
    stock_rrg.sort(key=lambda item: float(item.intent["score"]), reverse=True)
    if max_symbols is not None:
        stock_rrg = stock_rrg[: max(0, max_symbols)]

    symbols = [item.symbol for item in stock_rrg]
    downloaded = load_yahoo_ohlcv_many([_yahoo_symbol(symbol) for symbol in symbols], period=period, timeframe=active_timeframe)

    candidates: list[dict] = []
    rejected: list[dict] = []
    rrg_chart_cache: dict[str, Path] = {}
    for item in stock_rrg:
        yahoo_symbol = _yahoo_symbol(item.symbol)
        candles = downloaded.get(yahoo_symbol)
        if isinstance(candles, Exception) or not candles:
            rejected.append(
                {
                    "symbol": item.symbol,
                    "market": "US stock",
                    "timeframe": active_timeframe,
                    "technique": active_technique,
                    "setup": active_setup,
                    "evidence": {
                        "qualified": False,
                        "status": "data_error",
                        "score": 0,
                        "failures": [str(candles) if isinstance(candles, Exception) else f"No data returned for {yahoo_symbol}"],
                    },
                    "rrg": _rrg_json(item),
                }
            )
            continue
        for setup_name in setup_names:
            symbol_spec = SymbolSpec(
                symbol=item.symbol,
                market="US stock",
                tradingview_symbol=f"US:{item.symbol}",
                csv_path=Path(f"yahoo:{yahoo_symbol}"),
            )
            evidence = detect_pattern(candles, active_technique, vcp_config, setup_name)
            evidence = _apply_ema_side_guard(evidence, candles, vcp_config, active_technique, setup_name)
            evidence = _apply_near_trigger_volume_signal(evidence, candles, vcp_config)
            scan_result = ScanResult(
                symbol=symbol_spec,
                timeframe=active_timeframe,
                evidence=evidence,
                technique=active_technique,
                setup=setup_name,
            )
            if evidence.qualified:
                chart_path = render_chart(scan_result, candles, chart_dir, vcp_config)
                rrg_path = rrg_chart_cache.get(item.symbol)
                if rrg_path is None:
                    rrg_path = _render_stock_rrg_proof(item, stock_rrg, rrg_dir)
                    rrg_chart_cache[item.symbol] = rrg_path
                scan_result = ScanResult(
                    symbol=symbol_spec,
                    timeframe=active_timeframe,
                    evidence=evidence,
                    chart_path=str(chart_path),
                    technique=active_technique,
                    setup=setup_name,
                )
                row = scan_result.to_json()
                row["rrg"] = _rrg_json(item, rrg_path)
                candidates.append(row)
            else:
                row = scan_result.to_json()
                row["rrg"] = _rrg_json(item)
                rejected.append(row)

    candidates.sort(
        key=lambda row: (
            float(row.get("rrg", {}).get("stock_intent", {}).get("score") or 0),
            float(row.get("evidence", {}).get("score") or 0),
        ),
        reverse=True,
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timeframe": active_timeframe,
        "market": "US stock",
        "rrg_filter": {
            "sector_count": len(accepted_sectors),
            "approved_symbol_count": len(stock_rrg),
            "rrg_approved_before_broker": rrg_approved_before_broker,
            "broker_rejected_symbol_count": max(0, rrg_approved_before_broker - len(stock_rrg)),
            "broker_filter": "exness",
            "tail_rows": RRG_TAIL_ROWS,
            "request_days": RRG_REQUEST_DAYS,
            "sectors": [_sector_json(item) for item in accepted_sectors],
        },
        "qualified_count": len(candidates),
        "candidates": candidates,
        "rejected": rejected,
        "config": {
            "timeframe": active_timeframe,
            "period": period,
            "technique": active_technique,
            "setup": active_setup,
            "setup_names": list(setup_names),
            "data_source": "StockCharts RRG + Yahoo Finance",
            "broker_filter": "exness",
            "vcp": vcp_config.__dict__,
        },
    }
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(payload, indent=2))
    _write_usstock_rrg_dashboard(payload, output_dir / "index.html")
    return results_path


def build_vnstock_rrg_demo(
    out_dir: str | Path,
    timeframe: str = "D1",
    config_path: str | Path | None = None,
    period: str = "2y",
    technique: str | None = None,
    setup: str | None = None,
    max_sectors: int | None = None,
    max_symbols: int | None = None,
) -> Path:
    active_timeframe = timeframe.upper()
    if active_timeframe not in {"D1", "H4"}:
        raise ValueError("supported timeframes are D1 and H4")
    vcp_config, active_technique, active_setup = _demo_config(config_path, technique, setup)
    setup_names = _setups_to_scan(active_technique, active_setup)

    output_dir = Path(out_dir)
    chart_dir = output_dir / "charts"
    rrg_dir = output_dir / "rrg"
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_images(chart_dir)
    _clear_images(rrg_dir)

    icb_tree = _fetch_fialda_icb_tree()
    sector_lookup = _vn_sector_lookup(icb_tree)
    universe_symbols = {item.symbol for item in get_universe("broad") if item.market == "Vietnam stock"}
    symbol_sector = _vn_symbol_sector_map(icb_tree, _fetch_fialda_symbols(), universe_symbols)
    sector_series = _fetch_vn_sector_rrg()
    accepted_sectors = _accepted_vn_sectors(sector_series, sector_lookup)
    if max_sectors is not None:
        accepted_sectors = accepted_sectors[: max(0, max_sectors)]
    stock_rrg = _accepted_vn_stocks_for_sectors(accepted_sectors, symbol_sector)
    stock_rrg.sort(key=lambda item: float(item.intent["score"]), reverse=True)
    if max_symbols is not None:
        stock_rrg = stock_rrg[: max(0, max_symbols)]

    symbols = [item.symbol for item in stock_rrg]
    downloaded = load_vnstock_ohlcv_many(symbols, period=period, timeframe=active_timeframe)

    candidates: list[dict] = []
    rejected: list[dict] = []
    rrg_chart_cache: dict[str, Path] = {}
    for item in stock_rrg:
        candles = downloaded.get(item.symbol)
        if isinstance(candles, Exception) or not candles:
            rejected.append(
                {
                    "symbol": item.symbol,
                    "market": "Vietnam stock",
                    "timeframe": active_timeframe,
                    "technique": active_technique,
                    "setup": active_setup,
                    "evidence": {
                        "qualified": False,
                        "status": "data_error",
                        "score": 0,
                        "failures": [str(candles) if isinstance(candles, Exception) else f"No VNStock data returned for {item.symbol}"],
                    },
                    "rrg": _rrg_json(item),
                }
            )
            continue
        meta = symbol_sector.get(item.symbol, {})
        exchange = str(meta.get("exchange") or "HOSE")
        for setup_name in setup_names:
            symbol_spec = SymbolSpec(
                symbol=item.symbol,
                market="Vietnam stock",
                tradingview_symbol=f"{exchange}:{item.symbol}",
                csv_path=Path(f"vnstock:{item.symbol}"),
            )
            evidence = detect_pattern(candles, active_technique, vcp_config, setup_name)
            evidence = _apply_ema_side_guard(evidence, candles, vcp_config, active_technique, setup_name)
            evidence = _apply_near_trigger_volume_signal(evidence, candles, vcp_config)
            scan_result = ScanResult(
                symbol=symbol_spec,
                timeframe=active_timeframe,
                evidence=evidence,
                technique=active_technique,
                setup=setup_name,
            )
            if evidence.qualified:
                chart_path = render_chart(scan_result, candles, chart_dir, vcp_config)
                rrg_path = rrg_chart_cache.get(item.symbol)
                if rrg_path is None:
                    rrg_path = _render_stock_rrg_proof(item, stock_rrg, rrg_dir)
                    rrg_chart_cache[item.symbol] = rrg_path
                scan_result = ScanResult(
                    symbol=symbol_spec,
                    timeframe=active_timeframe,
                    evidence=evidence,
                    chart_path=str(chart_path),
                    technique=active_technique,
                    setup=setup_name,
                )
                row = scan_result.to_json()
                row["rrg"] = _rrg_json(item, rrg_path)
                candidates.append(row)
            else:
                row = scan_result.to_json()
                row["rrg"] = _rrg_json(item)
                rejected.append(row)

    candidates.sort(
        key=lambda row: (
            float(row.get("rrg", {}).get("stock_intent", {}).get("score") or 0),
            float(row.get("evidence", {}).get("score") or 0),
        ),
        reverse=True,
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timeframe": active_timeframe,
        "market": "Vietnam stock",
        "rrg_filter": {
            "sector_count": len(accepted_sectors),
            "approved_symbol_count": len(stock_rrg),
            "tail_rows": RRG_TAIL_ROWS,
            "request_days": RRG_REQUEST_DAYS,
            "benchmark": "VNINDEX",
            "sectors": [_sector_json(item) for item in accepted_sectors],
        },
        "qualified_count": len(candidates),
        "candidates": candidates,
        "rejected": rejected,
        "config": {
            "timeframe": active_timeframe,
            "period": period,
            "technique": active_technique,
            "setup": active_setup,
            "setup_names": list(setup_names),
            "data_source": "Fialda RRG + VNStock",
            "broker_filter": "none",
            "vcp": vcp_config.__dict__,
        },
    }
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(payload, indent=2))
    _write_usstock_rrg_dashboard(payload, output_dir / "index.html")
    return results_path


def build_crypto_rrg_demo(
    out_dir: str | Path,
    timeframe: str = "D1",
    config_path: str | Path | None = None,
    period: str = "2y",
    technique: str | None = None,
    setup: str | None = None,
    max_symbols: int | None = None,
) -> Path:
    active_timeframe = timeframe.upper()
    if active_timeframe not in {"D1", "H4"}:
        raise ValueError("supported timeframes are D1 and H4")
    vcp_config, active_technique, active_setup = _demo_config(config_path, technique, setup)
    setup_names = _setups_to_scan(active_technique, active_setup)

    output_dir = Path(out_dir)
    chart_dir = output_dir / "charts"
    rrg_dir = output_dir / "rrg"
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_images(chart_dir)
    _clear_images(rrg_dir)

    crypto_items = [item for item in get_universe("default") if item.market == "Crypto"]
    stock_rrg = _accepted_crypto_symbols([item.symbol for item in crypto_items], active_timeframe)
    stock_rrg.sort(key=lambda item: float(item.intent["score"]), reverse=True)
    if max_symbols is not None:
        stock_rrg = stock_rrg[: max(0, max_symbols)]

    symbols = [item.symbol for item in stock_rrg]
    downloaded = load_ccxt_ohlcv_many(
        symbols,
        period=period,
        timeframe=active_timeframe,
        exchange_id=os.getenv("CRYPTO_EXCHANGES", "binance,bybit,okx,mexc"),
        market_type=os.getenv("CRYPTO_MARKET_TYPE", "perp"),
    )
    tv_by_symbol = {item.symbol: item.tradingview_symbol for item in crypto_items}

    candidates: list[dict] = []
    rejected: list[dict] = []
    rrg_chart_cache: dict[str, Path] = {}
    for item in stock_rrg:
        candles = downloaded.get(item.symbol)
        if isinstance(candles, Exception) or not candles:
            rejected.append(
                {
                    "symbol": item.symbol,
                    "market": "Crypto",
                    "timeframe": active_timeframe,
                    "technique": active_technique,
                    "setup": active_setup,
                    "evidence": {
                        "qualified": False,
                        "status": "data_error",
                        "score": 0,
                        "failures": [str(candles) if isinstance(candles, Exception) else f"No CCXT data returned for {item.symbol}"],
                    },
                    "rrg": _rrg_json(item),
                }
            )
            continue
        for setup_name in setup_names:
            symbol_spec = SymbolSpec(
                symbol=item.symbol,
                market="Crypto",
                tradingview_symbol=tv_by_symbol.get(item.symbol, f"BINANCE:{item.symbol}.P"),
                csv_path=Path(f"ccxt:{item.symbol}"),
            )
            evidence = detect_pattern(candles, active_technique, vcp_config, setup_name)
            evidence = _apply_ema_side_guard(evidence, candles, vcp_config, active_technique, setup_name)
            evidence = _apply_near_trigger_volume_signal(evidence, candles, vcp_config)
            scan_result = ScanResult(
                symbol=symbol_spec,
                timeframe=active_timeframe,
                evidence=evidence,
                technique=active_technique,
                setup=setup_name,
            )
            if evidence.qualified:
                chart_path = render_chart(scan_result, candles, chart_dir, vcp_config)
                rrg_path = rrg_chart_cache.get(item.symbol)
                if rrg_path is None:
                    rrg_path = _render_stock_rrg_proof(item, stock_rrg, rrg_dir)
                    rrg_chart_cache[item.symbol] = rrg_path
                scan_result = ScanResult(
                    symbol=symbol_spec,
                    timeframe=active_timeframe,
                    evidence=evidence,
                    chart_path=str(chart_path),
                    technique=active_technique,
                    setup=setup_name,
                )
                row = scan_result.to_json()
                row["rrg"] = _rrg_json(item, rrg_path)
                candidates.append(row)
            else:
                row = scan_result.to_json()
                row["rrg"] = _rrg_json(item)
                rejected.append(row)

    candidates.sort(
        key=lambda row: (
            float(row.get("rrg", {}).get("stock_intent", {}).get("score") or 0),
            float(row.get("evidence", {}).get("score") or 0),
        ),
        reverse=True,
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timeframe": active_timeframe,
        "market": "Crypto",
        "rrg_filter": {
            "sector_count": 0,
            "approved_symbol_count": len(stock_rrg),
            "tail_rows": RRG_TAIL_ROWS,
            "request_days": RRG_REQUEST_DAYS,
            "benchmark": "$ONE",
            "period": _crypto_rrg_period(active_timeframe),
            "sectors": [],
        },
        "qualified_count": len(candidates),
        "candidates": candidates,
        "rejected": rejected,
        "config": {
            "timeframe": active_timeframe,
            "period": period,
            "technique": active_technique,
            "setup": active_setup,
            "setup_names": list(setup_names),
            "data_source": "StockCharts crypto RRG + CCXT",
            "broker_filter": "none",
            "crypto_exchanges": os.getenv("CRYPTO_EXCHANGES", "binance,bybit,okx,mexc"),
            "crypto_market_type": os.getenv("CRYPTO_MARKET_TYPE", "perp"),
            "vcp": vcp_config.__dict__,
        },
    }
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(payload, indent=2))
    _write_usstock_rrg_dashboard(payload, output_dir / "index.html")
    return results_path


def build_crypto_rrg_overview(
    out_dir: str | Path,
    timeframe: str = "D1",
    max_symbols: int | None = None,
) -> Path:
    active_timeframe = timeframe.upper()
    if active_timeframe not in {"D1", "H4"}:
        raise ValueError("supported timeframes are D1 and H4")

    output_dir = Path(out_dir)
    rrg_dir = output_dir / "rrg"
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_images(rrg_dir)

    crypto_items = [item for item in get_universe("default") if item.market == "Crypto"]
    selections = _all_crypto_rrg_symbols([item.symbol for item in crypto_items], active_timeframe)
    selections.sort(key=lambda item: float(item.intent.get("score") or 0), reverse=True)
    if max_symbols is not None:
        selections = selections[: max(0, max_symbols)]

    overview_path = _render_rrg_overview_chart(selections, rrg_dir / "crypto-daily-rrg-overview.jpg", "Crypto Daily RRG vs $ONE")
    rows = [
        {
            "symbol": item.symbol,
            "market": "Crypto",
            "timeframe": active_timeframe,
            "technique": "rrg-overview",
            "setup": "all",
            "evidence": {
                "qualified": False,
                "status": "rrg_overview",
                "score": item.intent.get("score", 0),
                "reasons": [f"RRG quadrant: {item.intent.get('quadrant')}"],
                "failures": [],
            },
            "rrg": _rrg_json(item),
        }
        for item in selections
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timeframe": active_timeframe,
        "market": "Crypto",
        "rrg_filter": {
            "approved_symbol_count": len(selections),
            "tail_rows": RRG_TAIL_ROWS,
            "request_days": RRG_REQUEST_DAYS,
            "benchmark": "$ONE",
            "period": _crypto_rrg_period(active_timeframe),
            "overview_chart_path": str(overview_path),
        },
        "candidates": rows,
        "rejected": [],
        "config": {
            "timeframe": active_timeframe,
            "technique": "rrg-overview",
            "setup": "all",
            "data_source": "StockCharts crypto RRG",
            "broker_filter": "none",
        },
    }
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(payload, indent=2))
    _write_crypto_rrg_overview_dashboard(payload, output_dir / "index.html")
    return results_path


def _all_crypto_rrg_symbols(symbols: list[str], timeframe: str) -> list[RRGSelection]:
    stockcharts_symbols = [_crypto_stockcharts_symbol(symbol) for symbol in symbols]
    display_by_stockcharts = dict(zip(stockcharts_symbols, symbols, strict=False))
    combined: dict[str, list[dict]] = {}
    for index in range(0, len(stockcharts_symbols), RRG_CHUNK_SIZE):
        chunk = stockcharts_symbols[index : index + RRG_CHUNK_SIZE]
        combined.update(_series_from_stockcharts(_fetch_crypto_rrg(chunk, timeframe), chunk))
        time.sleep(0.08)

    selections: list[RRGSelection] = []
    for stockcharts_symbol, points in combined.items():
        selection = _selection_from_points(
            display_by_stockcharts.get(stockcharts_symbol, _crypto_from_stockcharts_symbol(stockcharts_symbol)),
            "Crypto",
            "$ONE",
            points,
        )
        if selection is not None:
            selections.append(selection)
    return selections


def _demo_config(config_path: str | Path | None, technique: str | None, setup: str | None) -> tuple[VCPConfig, str, str]:
    if config_path is None:
        return VCPConfig(), technique or "nhathoai", setup or "all"
    config = load_config(config_path, require_symbols=False)
    return config.vcp, technique or config.technique, setup or config.setup


def _fetch_us_sector_rrg() -> dict[str, list[dict]]:
    symbols = list(SECTOR_ETFS.values())
    return _series_from_stockcharts(_fetch_stockcharts_rrg(symbols, "SPY"), symbols)


def _accepted_sectors(sector_series: dict[str, list[dict]]) -> list[dict]:
    etf_to_sector = {etf: sector for sector, etf in SECTOR_ETFS.items()}
    accepted = []
    for etf, points in sector_series.items():
        intent = rrg_intent(points)
        if not intent.get("accepted"):
            continue
        accepted.append(
            {
                "sector": etf_to_sector[etf],
                "etf": etf,
                "latest": points[-1],
                "intent": intent,
                "series": points[-RRG_TAIL_ROWS:],
            }
        )
    accepted.sort(key=lambda item: float(item["intent"]["score"]), reverse=True)
    return accepted


def _accepted_stocks_for_sectors(accepted_sectors: list[dict], sp500: list[dict]) -> list[RRGSelection]:
    selections: list[RRGSelection] = []
    for sector in accepted_sectors:
        members = [_stockcharts_symbol(row["Symbol"]) for row in sp500 if row["GICS Sector"] == sector["sector"]]
        combined: dict[str, list[dict]] = {}
        for index in range(0, len(members), RRG_CHUNK_SIZE):
            chunk = members[index : index + RRG_CHUNK_SIZE]
            combined.update(_series_from_stockcharts(_fetch_stockcharts_rrg(chunk, sector["etf"]), chunk))
            time.sleep(0.08)
        for symbol, points in combined.items():
            intent = rrg_intent(points)
            if not intent.get("accepted"):
                continue
            selections.append(
                RRGSelection(
                    symbol=symbol.replace("/", "."),
                    sector=sector["sector"],
                    benchmark=sector["etf"],
                    latest=points[-1],
                    intent=intent,
                    sector_latest=sector["latest"],
                    sector_intent=sector["intent"],
                    rrg_series=points[-RRG_TAIL_ROWS:],
                )
            )
    return selections


def _filter_exness_supported_us_stocks(selections: list[RRGSelection]) -> list[RRGSelection]:
    return [item for item in selections if is_exness_supported_symbol(item.symbol, "US stock")]


def _accepted_crypto_symbols(symbols: list[str], timeframe: str) -> list[RRGSelection]:
    stockcharts_symbols = [_crypto_stockcharts_symbol(symbol) for symbol in symbols]
    combined: dict[str, list[dict]] = {}
    for index in range(0, len(stockcharts_symbols), RRG_CHUNK_SIZE):
        chunk = stockcharts_symbols[index : index + RRG_CHUNK_SIZE]
        combined.update(_series_from_stockcharts(_fetch_crypto_rrg(chunk, timeframe), chunk))
        time.sleep(0.08)

    selections: list[RRGSelection] = []
    for stockcharts_symbol, points in combined.items():
        intent = rrg_intent(points)
        if not intent.get("accepted"):
            continue
        symbol = _crypto_from_stockcharts_symbol(stockcharts_symbol)
        selections.append(
            RRGSelection(
                symbol=symbol,
                sector="Crypto",
                benchmark="$ONE",
                latest=points[-1],
                intent=intent,
                sector_latest={},
                sector_intent={},
                rrg_series=points[-RRG_TAIL_ROWS:],
            )
        )
    return selections


def _rrg_reference_rows(payload: dict) -> list[dict]:
    rows: list[dict] = []
    seen: set[int] = set()
    for bucket in ("candidates", "trigger_warnings", "review_setups", "near_matches"):
        for row in payload.get(bucket, []) or []:
            marker = id(row)
            if marker in seen:
                continue
            seen.add(marker)
            rows.append(row)
    return rows


def _usstock_rrg_references(symbols: list[str]) -> dict[str, RRGSelection]:
    sp500 = _safe_load_sp500_constituents()
    sector_by_symbol = {
        _stockcharts_symbol(str(row.get("Symbol", ""))).upper(): str(row.get("GICS Sector") or "US stock")
        for row in sp500
        if row.get("Symbol")
    }
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    display_by_stockcharts: dict[str, str] = {}
    for symbol in symbols:
        stockcharts_symbol = _stockcharts_symbol(symbol.upper())
        sector = sector_by_symbol.get(stockcharts_symbol.upper(), "US stock")
        benchmark = SECTOR_ETFS.get(sector, "SPY")
        groups[(sector, benchmark)].append(stockcharts_symbol)
        display_by_stockcharts[stockcharts_symbol] = symbol

    selections: dict[str, RRGSelection] = {}
    for (sector, benchmark), members in groups.items():
        combined: dict[str, list[dict]] = {}
        for index in range(0, len(members), RRG_CHUNK_SIZE):
            chunk = members[index : index + RRG_CHUNK_SIZE]
            combined.update(_series_from_stockcharts(_fetch_stockcharts_rrg(chunk, benchmark), chunk))
            time.sleep(0.08)
        for stockcharts_symbol, points in combined.items():
            symbol = display_by_stockcharts.get(stockcharts_symbol, stockcharts_symbol.replace("/", "."))
            selection = _selection_from_points(symbol, sector, benchmark, points)
            if selection is not None:
                selections[symbol] = selection
    return selections


def _crypto_rrg_references(symbols: list[str], timeframe: str) -> dict[str, RRGSelection]:
    stockcharts_symbols = [_crypto_stockcharts_symbol(symbol) for symbol in symbols]
    display_by_stockcharts = dict(zip(stockcharts_symbols, symbols, strict=False))
    combined: dict[str, list[dict]] = {}
    for index in range(0, len(stockcharts_symbols), RRG_CHUNK_SIZE):
        chunk = stockcharts_symbols[index : index + RRG_CHUNK_SIZE]
        combined.update(_series_from_stockcharts(_fetch_crypto_rrg(chunk, timeframe), chunk))
        time.sleep(0.08)

    selections: dict[str, RRGSelection] = {}
    for stockcharts_symbol, points in combined.items():
        symbol = display_by_stockcharts.get(stockcharts_symbol, _crypto_from_stockcharts_symbol(stockcharts_symbol))
        selection = _selection_from_points(symbol, "Crypto", "$ONE", points)
        if selection is not None:
            selections[symbol] = selection
    return selections


def _vnstock_rrg_references(symbols: list[str]) -> dict[str, RRGSelection]:
    normalized_symbols = [symbol.upper() for symbol in symbols]
    display_by_symbol = dict(zip(normalized_symbols, symbols, strict=False))
    sector_by_symbol = _safe_vn_sector_by_symbol(set(normalized_symbols))
    combined: dict[str, list[dict]] = {}
    for index in range(0, len(normalized_symbols), FIALDA_SYMBOL_CHUNK_SIZE):
        chunk = normalized_symbols[index : index + FIALDA_SYMBOL_CHUNK_SIZE]
        combined.update(_series_from_fialda(_fetch_fialda_rrg(chunk, []), chunk))
        time.sleep(0.08)

    selections: dict[str, RRGSelection] = {}
    for normalized_symbol, points in combined.items():
        symbol = display_by_symbol.get(normalized_symbol, normalized_symbol)
        meta = sector_by_symbol.get(normalized_symbol, {})
        selection = _selection_from_points(symbol, str(meta.get("sector") or "Vietnam stock"), "VNINDEX", points)
        if selection is not None:
            selections[symbol] = selection
    return selections


def _forex_rrg_references(symbols: list[str]) -> dict[str, RRGSelection]:
    stockcharts_symbols = [_forex_stockcharts_symbol(symbol) for symbol in symbols]
    display_by_stockcharts = dict(zip(stockcharts_symbols, symbols, strict=False))
    combined: dict[str, list[dict]] = {}
    for index in range(0, len(stockcharts_symbols), RRG_CHUNK_SIZE):
        chunk = stockcharts_symbols[index : index + RRG_CHUNK_SIZE]
        combined.update(_series_from_stockcharts(_fetch_stockcharts_rrg(chunk, "$ONE"), chunk))
        time.sleep(0.08)

    selections: dict[str, RRGSelection] = {}
    for stockcharts_symbol, points in combined.items():
        symbol = display_by_stockcharts.get(stockcharts_symbol, stockcharts_symbol.removeprefix("$"))
        selection = _selection_from_points(symbol, "Forex", "$ONE", points)
        if selection is not None:
            selections[symbol] = selection
    return selections


def _commodity_rrg_references(symbols: list[str], market: str) -> dict[str, RRGSelection]:
    mapped: list[tuple[str, str]] = []
    for symbol in symbols:
        stockcharts_symbol = _commodity_stockcharts_symbol(symbol, market)
        if stockcharts_symbol:
            mapped.append((symbol, stockcharts_symbol))
    if not mapped:
        return {}

    symbols_by_stockcharts: dict[str, list[str]] = defaultdict(list)
    for symbol, stockcharts_symbol in mapped:
        if symbol not in symbols_by_stockcharts[stockcharts_symbol]:
            symbols_by_stockcharts[stockcharts_symbol].append(symbol)
    stockcharts_symbols = list(symbols_by_stockcharts)
    benchmark = "DBC" if market == "Commodity ETF" else "$ONE"
    sector = "Commodity ETF" if market == "Commodity ETF" else "Commodity"
    combined: dict[str, list[dict]] = {}
    for index in range(0, len(stockcharts_symbols), RRG_CHUNK_SIZE):
        chunk = stockcharts_symbols[index : index + RRG_CHUNK_SIZE]
        combined.update(_series_from_stockcharts(_fetch_stockcharts_rrg(chunk, benchmark), chunk))
        time.sleep(0.08)

    selections: dict[str, RRGSelection] = {}
    for stockcharts_symbol, points in combined.items():
        for symbol in symbols_by_stockcharts.get(stockcharts_symbol, [stockcharts_symbol]):
            selection = _selection_from_points(symbol, sector, benchmark, points)
            if selection is not None:
                selections[symbol] = selection
    return selections


def _forex_stockcharts_symbol(symbol: str) -> str:
    cleaned = re.sub(r"[^A-Z]", "", str(symbol).upper())
    return f"${cleaned}" if cleaned else ""


def _commodity_stockcharts_symbol(symbol: str, market: str) -> str:
    cleaned = str(symbol).upper().strip()
    if market == "Commodity ETF":
        if cleaned in COMMODITY_STOCKCHARTS_SYMBOLS:
            return COMMODITY_STOCKCHARTS_SYMBOLS[cleaned]
        return cleaned
    return COMMODITY_STOCKCHARTS_SYMBOLS.get(cleaned, "")


def _selection_from_points(symbol: str, sector: str, benchmark: str, points: list[dict]) -> RRGSelection | None:
    if len(points) < 4:
        return None
    tail = points[-RRG_TAIL_ROWS:]
    intent = rrg_intent(tail)
    return RRGSelection(
        symbol=symbol,
        sector=sector,
        benchmark=benchmark,
        latest=tail[-1],
        intent=intent,
        sector_latest={},
        sector_intent={},
        rrg_series=tail,
    )


def _safe_load_sp500_constituents() -> list[dict]:
    try:
        return _load_sp500_constituents()
    except Exception:
        return []


def _safe_vn_sector_by_symbol(symbols: set[str]) -> dict[str, dict]:
    try:
        return _vn_symbol_sector_map(_fetch_fialda_icb_tree(), _fetch_fialda_symbols(), symbols)
    except Exception:
        return {}


def _fetch_crypto_rrg(symbols: list[str], timeframe: str) -> dict:
    params = {
        "cmd": "getrrgdata2",
        "auth": os.getenv("STOCKCHARTS_RRG_AUTH", DEFAULT_STOCKCHARTS_AUTH),
        "f": "json",
        "s": ",".join(symbols),
        "b": "$ONE",
        "d": str(RRG_REQUEST_DAYS),
        "p": _crypto_rrg_period(timeframe),
        "_": str(int(time.time())),
    }
    response = requests.get(
        STOCKCHARTS_RRG_URL + "?" + urlencode(params, safe="$,/"),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": "https://stockcharts.com/freecharts/rrg/?period=daily&group=cryptousdbase&isArrowMode=true",
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def _crypto_stockcharts_symbol(symbol: str) -> str:
    cleaned = (
        symbol.upper()
        .split(":")[-1]
        .replace("-", "")
        .replace("/", "")
        .replace("_", "")
        .removesuffix(".P")
        .removesuffix("PERP")
    )
    base = cleaned.removesuffix("USDT").removesuffix("USD")
    return f"${base}USD"


def _crypto_from_stockcharts_symbol(symbol: str) -> str:
    base = symbol.upper().removeprefix("$").removesuffix("USD")
    return f"{base}USDT"


def _crypto_rrg_period(timeframe: str) -> str:
    return "240" if timeframe.upper() == "H4" else "d"


def _fetch_vn_sector_rrg() -> dict[str, list[dict]]:
    return _series_from_fialda(_fetch_fialda_rrg([], list(FIALDA_SECTOR_IDS)), list(FIALDA_SECTOR_IDS))


def _accepted_vn_sectors(sector_series: dict[str, list[dict]], sector_lookup: dict[str, dict]) -> list[dict]:
    accepted = []
    for sector_id, points in sector_series.items():
        intent = rrg_intent(points)
        if not intent.get("accepted"):
            continue
        sector = sector_lookup.get(str(sector_id), {"sector": f"ICB {sector_id}", "sector_code": str(sector_id)})
        accepted.append(
            {
                "sector": sector["sector"],
                "etf": sector["sector_code"],
                "sector_id": str(sector_id),
                "latest": points[-1],
                "intent": intent,
                "series": points[-RRG_TAIL_ROWS:],
            }
        )
    accepted.sort(key=lambda item: float(item["intent"]["score"]), reverse=True)
    return accepted


def _accepted_vn_stocks_for_sectors(accepted_sectors: list[dict], symbol_sector: dict[str, dict]) -> list[RRGSelection]:
    accepted_sector_ids = {str(item["sector_id"]) for item in accepted_sectors}
    sector_by_id = {str(item["sector_id"]): item for item in accepted_sectors}
    symbols = sorted(symbol for symbol, meta in symbol_sector.items() if str(meta.get("sector_id")) in accepted_sector_ids)
    combined: dict[str, list[dict]] = {}
    for index in range(0, len(symbols), FIALDA_SYMBOL_CHUNK_SIZE):
        chunk = symbols[index : index + FIALDA_SYMBOL_CHUNK_SIZE]
        combined.update(_series_from_fialda(_fetch_fialda_rrg(chunk, []), chunk))
        time.sleep(0.08)

    selections: list[RRGSelection] = []
    for symbol, points in combined.items():
        intent = rrg_intent(points)
        if not intent.get("accepted"):
            continue
        meta = symbol_sector.get(symbol)
        if not meta:
            continue
        sector = sector_by_id.get(str(meta.get("sector_id")))
        if not sector:
            continue
        selections.append(
            RRGSelection(
                symbol=symbol,
                sector=str(meta["sector"]),
                benchmark="VNINDEX",
                latest=points[-1],
                intent=intent,
                sector_latest=sector["latest"],
                sector_intent=sector["intent"],
                rrg_series=points[-RRG_TAIL_ROWS:],
            )
        )
    return selections


def _fetch_fialda_rrg(symbols: list[str], icbs: list[str]) -> dict:
    from_date, to_date = _fialda_date_range()
    payload = {
        "fromDate": from_date,
        "toDate": to_date,
        "parent": "VNINDEX",
        "symbols": symbols,
        "icbs": icbs,
        "parentType": 0,
    }
    response = requests.post(
        FIALDA_RRG_URL,
        headers=_fialda_headers(),
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("success") is False:
        raise RuntimeError(f"Fialda RRG request failed: {data.get('error')}")
    return data


def _fetch_fialda_icb_tree() -> list[dict]:
    response = requests.get(FIALDA_ICB_TREE_URL, headers=_fialda_headers(), timeout=60)
    response.raise_for_status()
    return response.json().get("result") or []


def _fetch_fialda_symbols() -> list[dict]:
    response = requests.get(FIALDA_INITIAL_DATA_URL, headers=_fialda_headers(), timeout=60)
    response.raise_for_status()
    return response.json().get("result", {}).get("symbols") or []


def _series_from_fialda(payload: dict, symbols: list[str]) -> dict[str, list[dict]]:
    rows = payload.get("result") or []
    series = {str(symbol): [] for symbol in symbols}
    for row in rows:
        rrg = row.get("rrgdata") or {}
        for symbol in symbols:
            key = str(symbol)
            point = rrg.get(key)
            if not point or point.get("ratio") is None or point.get("mom") is None:
                continue
            series[key].append(
                {
                    "x": float(point["ratio"]),
                    "y": float(point["mom"]),
                    "price": point.get("price"),
                    "date": row.get("date"),
                }
            )
    return {symbol: points for symbol, points in series.items() if points}


def _vn_symbol_sector_map(icb_tree: list[dict], symbols: list[dict], allowed_symbols: set[str]) -> dict[str, dict]:
    code_to_top = _vn_icb_code_to_top_sector(icb_tree)
    sector_map: dict[str, dict] = {}
    for item in symbols:
        symbol = str(item.get("symbol") or "")
        if symbol not in allowed_symbols or item.get("type") != "Stock":
            continue
        top = code_to_top.get(str(item.get("icbCode") or "")) or code_to_top.get(str(item.get("icbCode_Lvl4") or ""))
        if not top:
            continue
        sector_map[symbol] = {
            "sector_id": top["sector_id"],
            "sector_code": top["sector_code"],
            "sector": top["sector"],
            "exchange": item.get("exchange") or "HOSE",
        }
    return sector_map


def _vn_icb_code_to_top_sector(icb_tree: list[dict]) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for top in icb_tree:
        top_info = {
            "sector_id": str(top.get("icbId")),
            "sector_code": str(top.get("icbCode") or top.get("icbId")),
            "sector": _clean_icb_name(str(top.get("icbName") or top.get("icbCode") or top.get("icbId"))),
        }
        for node in _walk_icb_tree(top):
            code = str(node.get("icbCode") or "")
            if code:
                mapping[code] = top_info
    return mapping


def _vn_sector_lookup(icb_tree: list[dict]) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for top in icb_tree:
        sector_id = str(top.get("icbId"))
        lookup[sector_id] = {
            "sector_id": sector_id,
            "sector_code": str(top.get("icbCode") or sector_id),
            "sector": _clean_icb_name(str(top.get("icbName") or sector_id)),
        }
    return lookup


def _walk_icb_tree(node: dict):
    yield node
    for child in node.get("childs") or []:
        yield from _walk_icb_tree(child)


def _clean_icb_name(value: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", value).strip()


def _fialda_date_range() -> tuple[str, str]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=45)
    return start.isoformat(), end.isoformat()


def _fialda_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        ".AspNetCore.Culture": "en-US",
        "Abp.TenantId": "6",
        "Cache-Control": "private, no-cache, no-store, must-revalidate",
        "X-Alt-Referer": "https://fwt.fialda.com/rrg",
        "sa": os.getenv("FIALDA_SA", "017606206392180531429"),
        "appId": os.getenv("FIALDA_APP_ID", "F7335346-0CB8-49A1-B9CB-A59504CBEF14"),
        "Content-Type": "application/json;charset=utf-8",
        "Origin": "https://fwt.fialda.com",
        "Referer": "https://fwt.fialda.com/",
    }


def _fetch_stockcharts_rrg(symbols: list[str], benchmark: str) -> dict:
    params = {
        "cmd": "getrrgdata2",
        "auth": os.getenv("STOCKCHARTS_RRG_AUTH", DEFAULT_STOCKCHARTS_AUTH),
        "f": "json",
        "s": ",".join(symbols),
        "b": benchmark,
        "d": str(RRG_REQUEST_DAYS),
        "p": "d",
        "_": str(int(time.time())),
    }
    response = requests.get(
        STOCKCHARTS_RRG_URL + "?" + urlencode(params, safe="$,/"),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def _series_from_stockcharts(payload: dict, symbols: list[str]) -> dict[str, list[dict]]:
    rows = payload.get("rrgdata") or []
    series = {symbol: [] for symbol in symbols}
    for row in rows:
        rrg = row.get("rrgdata") or {}
        for symbol in symbols:
            point = rrg.get(symbol)
            if not point or point.get("jdkratio") is None or point.get("jdkmom") is None:
                continue
            series[symbol].append(
                {
                    "x": float(point["jdkratio"]),
                    "y": float(point["jdkmom"]),
                    "price": point.get("price"),
                    "start": row.get("start"),
                    "end": row.get("end"),
                }
            )
    return {symbol: points for symbol, points in series.items() if points}


def _load_sp500_constituents() -> list[dict]:
    response = requests.get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", {"id": "constituents"})
    if table is None:
        raise RuntimeError("Could not find S&P 500 constituents table")
    headers = [th.get_text(" ", strip=True) for th in table.find_all("th")]
    rows = []
    for tr in table.find_all("tr")[1:]:
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def _render_stock_rrg_proof(selected: RRGSelection, selections: list[RRGSelection], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    sector_items = [item for item in selections if item.sector == selected.sector]
    all_x = [point["x"] for item in sector_items for point in item.rrg_series]
    all_y = [point["y"] for item in sector_items for point in item.rrg_series]
    x_pad = max(2.5, (max(all_x) - min(all_x)) * 0.14)
    y_pad = max(2.0, (max(all_y) - min(all_y)) * 0.16)
    xlim = (min(min(all_x) - x_pad, 94), max(max(all_x) + x_pad, 106))
    ylim = (min(min(all_y) - y_pad, 94), max(max(all_y) + y_pad, 106))

    fig, ax = plt.subplots(figsize=(19.5, 11.2), dpi=150)
    fig.patch.set_facecolor("#f8fafc")
    ax.set_facecolor("#ffffff")
    _draw_rrg_background(ax, xlim, ylim)

    sector_items.sort(key=lambda item: abs(item.latest["x"] - 100) + abs(item.latest["y"] - 100), reverse=True)
    for index, item in enumerate(sector_items):
        xs = [point["x"] for point in item.rrg_series]
        ys = [point["y"] for point in item.rrg_series]
        quadrant = rrg_quadrant(xs[-1], ys[-1])
        color = QUADRANT_COLORS[quadrant]
        is_selected = item.symbol == selected.symbol
        alpha = 0.96 if is_selected else (0.46 if index < 24 else 0.24)
        width = 2.4 if is_selected else 1.05
        zorder = 8 if is_selected else 3
        ax.plot(xs, ys, color=color, linewidth=width, alpha=alpha, zorder=zorder)
        for step in range(1, len(xs)):
            is_final = step == len(xs) - 1
            ax.annotate(
                "",
                xy=(xs[step], ys[step]),
                xytext=(xs[step - 1], ys[step - 1]),
                arrowprops=_rrg_arrow_props(color, alpha, is_selected=is_selected, is_final=is_final),
                zorder=zorder + 1,
            )
        ax.scatter(
            xs[-1],
            ys[-1],
            s=82 if is_selected else 20,
            facecolors=color if is_selected else color,
            edgecolor=color if is_selected else "white",
            linewidth=2.8 if is_selected else 0.5,
            alpha=0.92 if is_selected else alpha,
            zorder=zorder + 2,
        )
        if is_selected:
            ax.scatter(
                xs[-1],
                ys[-1],
                s=260,
                facecolors="none",
                edgecolor=color,
                linewidth=3.4,
                alpha=0.96,
                zorder=zorder + 5,
            )
            ax.annotate(
                "CURRENT",
                xy=(xs[-1], ys[-1]),
                xytext=(18, 18),
                textcoords="offset points",
                fontsize=11,
                weight="bold",
                color="white",
                ha="left",
                va="bottom",
                bbox={"boxstyle": "round,pad=0.32", "facecolor": color, "edgecolor": "white", "linewidth": 1.4},
                arrowprops={"arrowstyle": "->", "color": color, "lw": 2.2, "shrinkA": 0, "shrinkB": 8},
                zorder=zorder + 6,
            )
        if is_selected or index < 20:
            ax.text(
                xs[-1] + (0.36 if is_selected else 0.08),
                ys[-1] + (0.30 if is_selected else 0.08),
                item.symbol,
                fontsize=18 if is_selected else 8.0,
                weight="bold",
                color="#111827",
                path_effects=[pe.withStroke(linewidth=4.6 if is_selected else 2.8, foreground="white", alpha=0.95)],
                zorder=zorder + 3,
            )

    _label_rrg_quadrants(ax, xlim, ylim)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_xlabel(f"JdK RS-Ratio < 100 weaker vs {selected.benchmark} | stronger > 100", fontsize=12, weight="bold")
    ax.set_ylabel("JdK RS-Momentum < 100 falling | rising > 100", fontsize=12, weight="bold")
    fig.text(
        0.055,
        0.965,
        f"RRG Proof - {selected.symbol} inside {selected.sector} vs {selected.benchmark}",
        fontsize=21,
        weight="bold",
        color="#0f172a",
        ha="left",
        va="top",
    )
    fig.text(
        0.055,
        0.932,
        f"Daily RRG | Tail: older -> current, last {RRG_TAIL_ROWS} rows | Stock: {selected.intent['quadrant']} | Current dy {selected.intent['dy1']:.3f}",
        fontsize=10.5,
        color="#475569",
        ha="left",
        va="top",
    )
    plt.subplots_adjust(left=0.075, right=0.99, top=0.86, bottom=0.10)
    output_path = out_dir / f"{_safe_name(selected.symbol)}-rrg-proof.jpg"
    fig.savefig(output_path, format="jpg", pil_kwargs={"quality": 86, "optimize": True, "progressive": True})
    preview_path = _preview_path(output_path)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        preview_path,
        dpi=RRG_PREVIEW_DPI,
        format="jpg",
        pil_kwargs={"quality": RRG_PREVIEW_QUALITY, "optimize": True, "progressive": True},
    )
    plt.close(fig)
    return output_path


def _render_rrg_overview_chart(selections: list[RRGSelection], output_path: Path, title: str) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not selections:
        raise ValueError("no RRG selections available for overview chart")
    all_x = [point["x"] for item in selections for point in item.rrg_series]
    all_y = [point["y"] for item in selections for point in item.rrg_series]
    x_pad = max(2.5, (max(all_x) - min(all_x)) * 0.14)
    y_pad = max(2.0, (max(all_y) - min(all_y)) * 0.16)
    xlim = (min(min(all_x) - x_pad, 94), max(max(all_x) + x_pad, 106))
    ylim = (min(min(all_y) - y_pad, 94), max(max(all_y) + y_pad, 106))

    fig, ax = plt.subplots(figsize=(20, 11.4), dpi=150)
    fig.patch.set_facecolor("#f8fafc")
    ax.set_facecolor("#ffffff")
    _draw_rrg_background(ax, xlim, ylim)

    ranked = sorted(selections, key=lambda item: float(item.intent.get("score") or 0), reverse=True)
    label_symbols = {item.symbol for item in ranked[:36]}
    for index, item in enumerate(ranked):
        xs = [point["x"] for point in item.rrg_series]
        ys = [point["y"] for point in item.rrg_series]
        quadrant = rrg_quadrant(xs[-1], ys[-1])
        color = QUADRANT_COLORS[quadrant]
        alpha = 0.86 if item.symbol in label_symbols else 0.28
        width = 1.65 if item.symbol in label_symbols else 0.85
        zorder = 6 if item.symbol in label_symbols else 2
        ax.plot(xs, ys, color=color, linewidth=width, alpha=alpha, zorder=zorder)
        for step in range(1, len(xs)):
            is_final = step == len(xs) - 1
            ax.annotate(
                "",
                xy=(xs[step], ys[step]),
                xytext=(xs[step - 1], ys[step - 1]),
                arrowprops=_rrg_arrow_props(color, alpha, is_selected=False, is_final=is_final),
                zorder=zorder + 1,
            )
        ax.scatter(xs[-1], ys[-1], s=34 if item.symbol in label_symbols else 12, facecolors=color, edgecolor="white", linewidth=0.7, alpha=alpha, zorder=zorder + 2)
        if item.symbol in label_symbols:
            ax.text(
                xs[-1] + 0.08,
                ys[-1] + 0.08,
                item.symbol,
                fontsize=8.2,
                weight="bold",
                color="#111827",
                path_effects=[pe.withStroke(linewidth=2.8, foreground="white", alpha=0.95)],
                zorder=zorder + 3,
            )

    _label_rrg_quadrants(ax, xlim, ylim)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_xlabel("JdK RS-Ratio < 100 weaker vs $ONE | stronger > 100", fontsize=12, weight="bold")
    ax.set_ylabel("JdK RS-Momentum < 100 falling | rising > 100", fontsize=12, weight="bold")
    latest_dates = sorted({str(point.get("end") or point.get("date") or point.get("start")) for item in selections for point in item.rrg_series if point.get("end") or point.get("date") or point.get("start")})
    latest = f" | Latest row: {latest_dates[-1]}" if latest_dates else ""
    fig.text(0.055, 0.965, title, fontsize=21, weight="bold", color="#0f172a", ha="left", va="top")
    fig.text(
        0.055,
        0.932,
        f"Daily RRG | Tail: older -> current, last {RRG_TAIL_ROWS} rows | Symbols: {len(selections)}{latest}",
        fontsize=10.5,
        color="#475569",
        ha="left",
        va="top",
    )
    plt.subplots_adjust(left=0.075, right=0.99, top=0.86, bottom=0.10)
    fig.savefig(output_path, format="jpg", pil_kwargs={"quality": 88, "optimize": True, "progressive": True})
    preview_path = _preview_path(output_path)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        preview_path,
        dpi=RRG_PREVIEW_DPI,
        format="jpg",
        pil_kwargs={"quality": RRG_PREVIEW_QUALITY, "optimize": True, "progressive": True},
    )
    plt.close(fig)
    return output_path


def _preview_path(output_path: Path) -> Path:
    return output_path.parent / "preview" / output_path.name


def _rrg_arrow_props(color: str, alpha: float, *, is_selected: bool, is_final: bool) -> dict:
    if is_selected and is_final:
        return {
            "arrowstyle": "-|>,head_width=0.65,head_length=1.0",
            "color": color,
            "lw": 5.2,
            "alpha": 1.0,
            "mutation_scale": 30,
            "shrinkA": 0,
            "shrinkB": 0,
        }
    if is_selected:
        return {
            "arrowstyle": "->",
            "color": color,
            "lw": 1.8,
            "alpha": alpha * 0.72,
            "mutation_scale": 13,
            "shrinkA": 0,
            "shrinkB": 0,
        }
    return {
        "arrowstyle": "->",
        "color": color,
        "lw": 0.75,
        "alpha": alpha,
        "mutation_scale": 9,
        "shrinkA": 0,
        "shrinkB": 0,
    }


def _draw_rrg_background(ax, xlim: tuple[float, float], ylim: tuple[float, float]) -> None:
    y100 = max(0, min(1, (100 - ylim[0]) / (ylim[1] - ylim[0])))
    ax.axvspan(xlim[0], 100, ymin=y100, ymax=1, facecolor=QUADRANT_BACKGROUNDS["IMPROVING"], alpha=0.55, zorder=0)
    ax.axvspan(100, xlim[1], ymin=y100, ymax=1, facecolor=QUADRANT_BACKGROUNDS["LEADING"], alpha=0.55, zorder=0)
    ax.axvspan(xlim[0], 100, ymin=0, ymax=y100, facecolor=QUADRANT_BACKGROUNDS["LAGGING"], alpha=0.50, zorder=0)
    ax.axvspan(100, xlim[1], ymin=0, ymax=y100, facecolor=QUADRANT_BACKGROUNDS["WEAKENING"], alpha=0.45, zorder=0)
    ax.axhline(100, color="#111827", linewidth=1.1, alpha=0.78, zorder=1)
    ax.axvline(100, color="#111827", linewidth=1.1, alpha=0.78, zorder=1)
    ax.grid(True, color="#cbd5e1", linewidth=0.8, alpha=0.72)


def _label_rrg_quadrants(ax, xlim: tuple[float, float], ylim: tuple[float, float]) -> None:
    ax.text(xlim[0] + 0.55, ylim[1] - 0.45, "IMPROVING", fontsize=16, weight="bold", color=QUADRANT_COLORS["IMPROVING"], va="top")
    ax.text(xlim[1] - 0.55, ylim[1] - 0.45, "LEADING", fontsize=16, weight="bold", color="#166534", ha="right", va="top")
    ax.text(xlim[0] + 0.55, ylim[0] + 0.35, "LAGGING", fontsize=16, weight="bold", color="#991b1b", va="bottom")
    ax.text(xlim[1] - 0.55, ylim[0] + 0.35, "WEAKENING", fontsize=16, weight="bold", color="#9a3412", ha="right", va="bottom")


def _write_usstock_rrg_dashboard(payload: dict, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidates = payload.get("candidates", [])
    sectors = payload.get("rrg_filter", {}).get("sectors", [])
    cards = "\n".join(_candidate_card(item, output_path.parent) for item in candidates)
    if not cards:
        cards = '<section class="empty">No symbols passed both RRG direction and pattern scan.</section>'
    sector_rows = "\n".join(_sector_row(item) for item in sectors)
    setup_counts = defaultdict(int)
    for item in candidates:
        setup_counts[str(item.get("setup", "all")).upper()] += 1
    setup_text = ", ".join(f"{escape(k)} {v}" for k, v in sorted(setup_counts.items())) or "none"
    market = str(payload.get("market") or "US stock")
    is_crypto = market == "Crypto"
    broker_filter = str(payload.get("config", {}).get("broker_filter") or payload.get("rrg_filter", {}).get("broker_filter") or "exness")
    broker_label = broker_filter.upper() if broker_filter != "exness" else "Exness"
    has_broker_filter = broker_filter not in {"", "all", "none"}
    setup_metric_label = f"Broker: {broker_label}" if has_broker_filter else "Setups"
    universe_text = "the Exness-supported universe" if has_broker_filter and broker_filter == "exness" else "the universe"
    setup_options = _option_tags(sorted({str(item.get("setup", "")).lower() for item in candidates if item.get("setup")}))
    sector_options = _option_tags(sorted({str(item.get("rrg", {}).get("sector", "")) for item in candidates if item.get("rrg", {}).get("sector")}))
    quadrant_options = _option_tags(
        sorted({str(item.get("rrg", {}).get("stock_intent", {}).get("quadrant", "")) for item in candidates if item.get("rrg", {}).get("stock_intent", {}).get("quadrant")})
    )
    sector_filter_control = ""
    if not is_crypto:
        sector_filter_control = f'<select id="sectorFilter"><option value="all">All sectors</option>{sector_options}</select>'
    sector_strip = ""
    if not is_crypto:
        sector_strip = f"""
    <section class="panel sector-strip">
      <h2>Sector RRG Gate</h2>
      <table class="sector-table"><tbody>{sector_rows}</tbody></table>
    </section>"""
    rrg_scan_label = "RRG Symbols Scanned" if is_crypto else "RRG Stocks Scanned"
    filter_text = "RRG filters symbols directly" if is_crypto else f"Sector RRG filters {universe_text}"
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>US Stock RRG Pattern Dashboard</title>
<style>
:root {{ --bg:#eef2f1; --panel:#ffffff; --ink:#1f2933; --muted:#7a8580; --line:#dde5e1; --green:#0f7a4f; --green-2:#0d5f3f; --soft:#f6faf8; --warn:#b45309; --blue:#2563eb; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:linear-gradient(135deg,#e8efed,#f7f8f4); color:var(--ink); font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; letter-spacing:0; }}
.shell {{ min-height:100vh; max-width:1920px; margin:0 auto; padding:22px; }}
main {{ min-width:0; }}
.topbar {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; }}
.profile {{ text-align:right; font-size:13px; color:var(--muted); }}
.profile strong {{ display:block; color:var(--ink); font-size:14px; }}
h1 {{ margin:0 0 4px; font-size:30px; letter-spacing:0; }}
.subhead {{ margin:0 0 18px; color:var(--muted); }}
.metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin-bottom:18px; }}
.metric {{ background:var(--panel); border:1px solid rgba(255,255,255,.9); border-radius:8px; padding:17px; box-shadow:0 12px 28px rgba(22,45,37,.08); min-height:116px; }}
.metric.primary {{ background:linear-gradient(135deg,var(--green),#179b68); color:white; }}
.metric span {{ display:block; color:var(--muted); font-size:12px; font-weight:700; }}
.metric.primary span {{ color:#d9f6e8; }}
.metric b {{ display:block; font-size:clamp(20px, 2.4vw, 32px); margin-top:12px; line-height:1.1; overflow-wrap:anywhere; }}
.toolbar {{ display:grid; grid-template-columns:minmax(260px,2fr) repeat(4,minmax(132px,1fr)); gap:10px; margin:0 0 12px; position:sticky; top:0; z-index:20; padding:12px 0; background:rgba(238,242,241,.96); backdrop-filter:blur(8px); border-bottom:1px solid var(--line); }}
input, select {{ width:100%; height:40px; border:1px solid var(--line); border-radius:7px; padding:0 10px; background:#fff; color:var(--ink); font:inherit; font-size:13px; }}
.filter-count {{ margin:0 0 14px; color:var(--muted); font-size:13px; }}
.sector-strip {{ margin-bottom:16px; }}
.candidate-list {{ display:block; }}
.panel {{ background:rgba(255,255,255,.86); border:1px solid rgba(255,255,255,.9); border-radius:8px; padding:18px; box-shadow:0 12px 34px rgba(22,45,37,.09); }}
.panel h2 {{ margin:0 0 12px; font-size:18px; }}
.sector-table {{ width:100%; border-collapse:collapse; font-size:13px; }}
.sector-table td {{ border-top:1px solid var(--line); padding:10px 6px; }}
.pill {{ display:inline-flex; align-items:center; border-radius:999px; padding:4px 8px; font-size:11px; font-weight:800; background:#eef7f2; color:var(--green); }}
.candidate {{ margin-bottom:18px; }}
.candidate-head {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:12px; }}
.candidate h3 {{ margin:0; font-size:22px; }}
.candidate-meta {{ color:var(--muted); font-size:13px; margin-top:4px; }}
.score {{ text-align:right; min-width:110px; }}
.score b {{ color:var(--green); font-size:24px; }}
.setup-strip {{ display:flex; align-items:center; justify-content:space-between; gap:12px; margin:4px 0 10px; padding:10px 12px; border:1px solid #d6e4de; border-radius:8px; background:#f3faf6; color:#174b34; font-size:13px; font-weight:800; }}
.setup-strip span {{ color:#5f6f68; font-size:12px; font-weight:700; }}
.chart-row {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:14px; align-items:start; }}
.shot {{ background:#f8fbfa; border:1px solid var(--line); border-radius:8px; padding:10px; }}
.shot strong {{ display:block; font-size:12px; color:#52615a; margin:0 0 8px; text-transform:uppercase; }}
.shot img {{ display:block; width:100%; height:auto; border-radius:6px; border:1px solid #e4ebe7; background:white; }}
.shot-main img {{ min-height:520px; object-fit:contain; }}
.shot-rrg img {{ min-height:500px; object-fit:contain; }}
.empty {{ border:1px dashed var(--line); border-radius:8px; padding:24px; background:white; color:var(--muted); }}
a {{ color:var(--green-2); }}
@media (max-width:1100px) {{ .toolbar,.chart-row,.metrics {{ grid-template-columns:1fr; }} .topbar {{ display:block; }} .shot-main img,.shot-rrg img {{ min-height:0; }} }}
</style>
</head>
<body>
<div class="shell">
  <main>
    <div class="topbar"><div><h1>Comprehensive Filter Pattern</h1><p class="subhead">Long-only {escape(market)} demo. {escape(filter_text)} before pattern scanning.</p></div><div class="profile"><strong>{escape(market)}</strong>{escape(payload.get("generated_at", ""))}</div></div>
    <section class="metrics">
      <div class="metric primary"><span>Pattern Candidates</span><b>{len(candidates)}</b></div>
      <div class="metric"><span>RRG Sectors</span><b>{payload.get("rrg_filter", {}).get("sector_count", 0)}</b></div>
      <div class="metric"><span>{escape(rrg_scan_label)}</span><b>{payload.get("rrg_filter", {}).get("approved_symbol_count", 0)}</b></div>
      <div class="metric"><span>{escape(setup_metric_label)}</span><b>{escape(setup_text)}</b></div>
    </section>
    <div class="toolbar">
      <input id="search" type="search" placeholder="Search symbol, setup, sector">
      <select id="setupFilter"><option value="all">All setups</option>{setup_options}</select>
      {sector_filter_control}
      <select id="quadrantFilter"><option value="all">All RRG quadrants</option>{quadrant_options}</select>
      <select id="scoreFilter"><option value="0">Score 0+</option><option value="80">Score 80+</option><option value="90">Score 90+</option><option value="95">Score 95+</option></select>
    </div>
    <div id="filterCount" class="filter-count"></div>
    {sector_strip}
    <section class="candidate-list">
      {cards}
    </section>
  </main>
</div>
<script>
const search = document.getElementById('search');
const setupFilter = document.getElementById('setupFilter');
const sectorFilter = document.getElementById('sectorFilter');
const quadrantFilter = document.getElementById('quadrantFilter');
const scoreFilter = document.getElementById('scoreFilter');
const filterCount = document.getElementById('filterCount');
const filterable = Array.from(document.querySelectorAll('[data-filterable="true"]'));

function applyFilters() {{
  const text = search.value.trim().toLowerCase();
  const setup = setupFilter.value;
  const sector = sectorFilter ? sectorFilter.value : 'all';
  const quadrant = quadrantFilter.value;
  const minimumScore = Number(scoreFilter.value || '0');
  let visible = 0;
  for (const node of filterable) {{
    const haystack = (node.dataset.symbols || node.textContent || '').toLowerCase();
    const matchesText = !text || haystack.includes(text);
    const matchesSetup = setup === 'all' || node.dataset.setup === setup;
    const matchesSector = sector === 'all' || node.dataset.sector === sector;
    const matchesQuadrant = quadrant === 'all' || node.dataset.quadrant === quadrant;
    const matchesScore = Number(node.dataset.score || '0') >= minimumScore;
    const show = matchesText && matchesSetup && matchesSector && matchesQuadrant && matchesScore;
    node.style.display = show ? '' : 'none';
    if (show) visible += 1;
  }}
  filterCount.textContent = `${{visible}} result card(s) visible`;
}}

for (const control of [search, setupFilter, sectorFilter, quadrantFilter, scoreFilter].filter(Boolean)) {{
  control.addEventListener(control === search ? 'input' : 'change', applyFilters);
}}
applyFilters();
</script>
</body>
</html>"""
    output_path.write_text(html)
    return output_path


def _write_crypto_rrg_overview_dashboard(payload: dict, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overview_chart = _relative_image(payload.get("rrg_filter", {}).get("overview_chart_path"), output_path.parent)
    overview_preview = _relative_preview_image(payload.get("rrg_filter", {}).get("overview_chart_path"), output_path.parent)
    rows = payload.get("candidates", [])
    quadrant_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        quadrant_counts[str(row.get("rrg", {}).get("stock_intent", {}).get("quadrant", ""))] += 1
    table_rows = "\n".join(_crypto_rrg_overview_row(row) for row in rows)
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Crypto Daily RRG Overview</title>
<style>
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#0f1218; color:#e5e7eb; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; letter-spacing:0; }}
.shell {{ max-width:1900px; margin:0 auto; padding:18px; }}
.top {{ display:flex; justify-content:space-between; gap:18px; align-items:end; margin-bottom:14px; }}
h1 {{ margin:0 0 4px; font-size:26px; }}
.muted {{ color:#94a3b8; font-size:13px; }}
.metrics {{ display:grid; grid-template-columns:repeat(5,minmax(110px,1fr)); gap:10px; margin:0 0 14px; }}
.metric {{ background:#111827; border:1px solid #273244; border-radius:8px; padding:12px; }}
.metric strong {{ display:block; font-size:24px; color:white; margin-bottom:5px; }}
.metric span {{ color:#94a3b8; font-size:12px; font-weight:800; text-transform:uppercase; }}
.chart {{ display:block; background:#fff; border:1px solid #273244; border-radius:8px; overflow:hidden; margin-bottom:14px; }}
.chart strong {{ display:block; padding:10px 12px; background:#111827; color:#e5e7eb; border-bottom:1px solid #273244; }}
.chart img {{ display:block; width:100%; height:auto; }}
table {{ width:100%; border-collapse:collapse; background:#111827; border:1px solid #273244; border-radius:8px; overflow:hidden; font-size:13px; }}
th,td {{ padding:9px 10px; border-bottom:1px solid #273244; text-align:left; }}
th {{ color:#cbd5e1; background:#151f2e; font-size:12px; text-transform:uppercase; }}
td {{ color:#e5e7eb; }}
.pill {{ display:inline-flex; min-width:92px; justify-content:center; border-radius:999px; padding:4px 8px; font-size:11px; font-weight:900; }}
.LEADING {{ background:#14532d; color:#dcfce7; }}
.IMPROVING {{ background:#075985; color:#e0f2fe; }}
.WEAKENING {{ background:#9a3412; color:#ffedd5; }}
.LAGGING {{ background:#991b1b; color:#fee2e2; }}
@media (max-width:900px) {{ .top {{ display:block; }} .metrics {{ grid-template-columns:repeat(2,1fr); }} table {{ font-size:12px; }} }}
</style>
</head>
<body>
<main class="shell">
  <div class="top">
    <div><h1>Crypto Daily RRG Overview</h1><div class="muted">Full StockCharts crypto RRG return set vs $ONE. Use this page to compare against StockCharts before pattern review.</div></div>
    <div class="muted">Generated {escape(str(payload.get("generated_at", "")))}</div>
  </div>
  <section class="metrics">
    <div class="metric"><strong>{len(rows)}</strong><span>Symbols</span></div>
    <div class="metric"><strong>{quadrant_counts.get("LEADING", 0)}</strong><span>Leading</span></div>
    <div class="metric"><strong>{quadrant_counts.get("IMPROVING", 0)}</strong><span>Improving</span></div>
    <div class="metric"><strong>{quadrant_counts.get("WEAKENING", 0)}</strong><span>Weakening</span></div>
    <div class="metric"><strong>{quadrant_counts.get("LAGGING", 0)}</strong><span>Lagging</span></div>
  </section>
  <a class="chart" href="{escape(overview_chart)}"><strong>Daily RRG Chart - all returned crypto symbols</strong><img src="{escape(overview_preview)}" alt="Crypto daily RRG overview"></a>
  <table>
    <thead><tr><th>Symbol</th><th>Quadrant</th><th>dx</th><th>dy</th><th>Score</th><th>Latest row</th></tr></thead>
    <tbody>{table_rows}</tbody>
  </table>
</main>
</body>
</html>"""
    output_path.write_text(html)
    return output_path


def _crypto_rrg_overview_row(row: dict) -> str:
    intent = row.get("rrg", {}).get("stock_intent", {})
    quadrant = str(intent.get("quadrant", ""))
    latest = _latest_rrg_row_date(row.get("rrg", {}))
    return (
        "<tr>"
        f"<td><strong>{escape(str(row.get('symbol', '')))}</strong></td>"
        f"<td><span class=\"pill {escape(quadrant)}\">{escape(quadrant)}</span></td>"
        f"<td>{_fmt(intent.get('dx1'))}</td>"
        f"<td>{_fmt(intent.get('dy1'))}</td>"
        f"<td>{_fmt(intent.get('score'))}</td>"
        f"<td>{escape(latest)}</td>"
        "</tr>"
    )


def _latest_rrg_row_date(rrg: dict) -> str:
    for point in reversed(rrg.get("rrg_series") or []):
        value = point.get("end") or point.get("date") or point.get("start")
        if value:
            return str(value)
    latest = rrg.get("latest") or {}
    return str(latest.get("end") or latest.get("date") or latest.get("start") or "")


def _candidate_card(item: dict, base_dir: Path) -> str:
    evidence = item.get("evidence", {})
    rrg = item.get("rrg", {})
    chart = _relative_image(item.get("chart_path"), base_dir)
    chart_preview = _relative_preview_image(item.get("chart_path"), base_dir)
    rrg_chart = _relative_image(rrg.get("rrg_chart_path"), base_dir)
    rrg_preview = _relative_preview_image(rrg.get("rrg_chart_path"), base_dir)
    setup = str(item.get("setup", ""))
    setup_label = setup.upper()
    sector = str(rrg.get("sector", ""))
    quadrant = str(rrg.get("stock_intent", {}).get("quadrant", ""))
    score = _fmt(evidence.get("score"))
    symbols = " ".join(
        [
            str(item.get("symbol", "")),
            setup,
            setup_label,
            sector,
            quadrant,
            str(rrg.get("benchmark", "")),
        ]
    )
    return f"""
<article class="panel candidate" data-filterable="true" data-setup="{escape(setup.lower())}" data-sector="{escape(sector)}" data-quadrant="{escape(quadrant)}" data-score="{escape(str(evidence.get("score", 0)))}" data-symbols="{escape(symbols)}">
  <div class="candidate-head">
    <div>
      <h3>{escape(str(item.get("symbol", "")))} <span class="pill">{escape(setup_label)}</span></h3>
      <div class="candidate-meta">{escape(str(rrg.get("sector", "")))} vs {escape(str(rrg.get("benchmark", "")))} · {escape(str(rrg.get("stock_intent", {}).get("quadrant", "")))} · head dy {_fmt(rrg.get("stock_intent", {}).get("dy1"))}</div>
    </div>
    <div class="score"><span>Pattern Score</span><br><b>{score}</b></div>
  </div>
  <div class="setup-strip">{escape(setup_label)} setup <span>{escape(str(item.get("symbol", "")))} · current pattern chart and RRG proof</span></div>
  <div class="chart-row">
    <a class="shot shot-main" href="{escape(chart)}"><strong>Current Setup Pattern</strong><img src="{escape(chart_preview)}" alt="{escape(str(item.get("symbol", "")))} setup chart" loading="lazy" decoding="async"></a>
    <a class="shot shot-rrg" href="{escape(rrg_chart)}"><strong>RRG Proof - CURRENT marker is latest position</strong><img src="{escape(rrg_preview)}" alt="{escape(str(item.get("symbol", "")))} RRG proof" loading="lazy" decoding="async"></a>
  </div>
</article>"""


def _sector_row(item: dict) -> str:
    intent = item.get("intent", {})
    return (
        "<tr>"
        f"<td><strong>{escape(str(item.get('etf', '')))}</strong></td>"
        f"<td>{escape(str(item.get('sector', '')))}</td>"
        f"<td><span class=\"pill\">{escape(str(intent.get('quadrant', '')))}</span></td>"
        f"<td>dy {_fmt(intent.get('dy1'))}</td>"
        "</tr>"
    )


def _option_tags(values: list[str]) -> str:
    return "\n".join(f'<option value="{escape(value)}">{escape(value.upper() if value.islower() else value)}</option>' for value in values if value)


def _sector_json(item: dict) -> dict:
    return {
        "sector": item["sector"],
        "etf": item["etf"],
        "latest": item["latest"],
        "intent": item["intent"],
    }


def _rrg_json(item: RRGSelection, rrg_path: Path | None = None) -> dict:
    data = {
        "sector": item.sector,
        "benchmark": item.benchmark,
        "latest": item.latest,
        "stock_intent": item.intent,
        "confidence": rrg_confidence(item.intent),
        "sector_latest": item.sector_latest,
        "sector_intent": item.sector_intent,
        "rrg_series": item.rrg_series,
    }
    if rrg_path is not None:
        data["rrg_chart_path"] = str(rrg_path)
    return data


def _relative_image(path: object, base_dir: Path) -> str:
    if not path:
        return ""
    try:
        return Path(path).resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        try:
            return Path(path).relative_to(base_dir).as_posix()
        except ValueError:
            return Path(path).as_posix()


def _relative_preview_image(path: object, base_dir: Path) -> str:
    if not path:
        return ""
    path_obj = Path(path)
    preview_path = path_obj.parent / "preview" / path_obj.name
    if preview_path.exists():
        return _relative_image(preview_path, base_dir)
    return _relative_image(path, base_dir)


def _fmt(value: object) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def _float_value(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _stockcharts_symbol(symbol: str) -> str:
    return symbol.replace(".", "/")


def _yahoo_symbol(symbol: str) -> str:
    return symbol.replace("/", "-").replace(".", "-")


def _safe_name(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", symbol).strip("-").lower()


def _clear_images(path: Path) -> None:
    if not path.exists():
        return
    for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        for image_path in path.glob(pattern):
            image_path.unlink()
