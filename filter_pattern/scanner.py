from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path

from .chart import render_chart
from .data import config_to_json, load_config, load_ohlcv_csv
from .detector import detect_pattern
from .direction import DirectionMarketContext, annotate_result_with_direction_authority, build_market_context
from .exness import filter_exness_supported
from .models import Candle, ScanResult, SymbolSpec, VCPConfig, VCPEvidence
from .providers import load_ccxt_ohlcv_many, load_vnstock_ohlcv_many, load_yahoo_ohlcv_many
from .report import apply_watchlist_changes, refresh_trigger_warnings, result_payload, write_html_report
from .techniques import MINERVINI_VCP_SCAN_SETUPS, NHATHOAI_SCAN_SETUPS, normalize_setup, normalize_technique
from .universe import UniverseSymbol, expand_crypto_universe, get_universe


NEAR_MATCH_CHART_LIMIT = 20
REVIEW_SETUP_CHART_LIMIT = 1000
COMMODITY_PROXY_ENV = "COMMODITY_PROXY_MAP"
DEFAULT_COMMODITY_PROXY_SYMBOLS = {
    "XAUUSD": ("PAXGUSDT", "XAUTUSDT"),
    "GOLD": ("PAXGUSDT", "XAUTUSDT"),
    "XAGUSD": ("KAGUSDT",),
    "SILVER": ("KAGUSDT",),
}


class ProxyCandleSeries(list):
    def __init__(self, candles: list[Candle], proxy_data: dict):
        super().__init__(candles)
        self.proxy_data = proxy_data


def scan(config_path: str | Path, out_dir: str | Path, timeframe: str = "D1", technique: str | None = None) -> Path:
    return _scan_csv(config_path, out_dir, timeframe, technique, None)


def scan_csv(
    config_path: str | Path,
    out_dir: str | Path,
    timeframe: str = "D1",
    technique: str | None = None,
    setup: str | None = None,
) -> Path:
    return _scan_csv(config_path, out_dir, timeframe, technique, setup)


def scan_all_csv(
    config_path: str | Path,
    out_dir: str | Path,
    timeframe: str = "D1",
) -> Path:
    config = load_config(config_path)
    if timeframe.upper() != config.timeframe:
        raise ValueError(f"requested timeframe {timeframe} does not match config timeframe {config.timeframe}")

    output_dir = Path(out_dir)
    chart_dir = output_dir / "charts"
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_old_charts(chart_dir)

    candidates: list[dict] = []
    rejected: list[dict] = []
    rejected_candles: dict[str, tuple[ScanResult, list]] = {}
    pattern_runs = _all_pattern_runs()

    for symbol in config.symbols:
        try:
            candles = load_ohlcv_csv(symbol.csv_path)
        except (FileNotFoundError, ValueError) as exc:
            rejected.append(
                ScanResult(
                    symbol=symbol,
                    timeframe=config.timeframe,
                    evidence=VCPEvidence(
                        qualified=False,
                        status="data_error",
                        score=0.0,
                        pivot=None,
                        current_close=None,
                        distance_to_pivot_pct=None,
                        contractions=[],
                        reasons=[],
                        failures=[str(exc)],
                    ),
                    technique="all-patterns",
                    setup="all",
                ).to_json()
            )
            continue

        for technique_name, setup_name in pattern_runs:
            evidence = detect_pattern(candles, technique_name, config.vcp, setup_name)
            evidence = _apply_ema_side_guard(evidence, candles, config.vcp, technique_name, setup_name)
            evidence = _apply_near_trigger_volume_signal(evidence, candles, config.vcp)
            scan_result = ScanResult(
                symbol=symbol,
                timeframe=config.timeframe,
                evidence=evidence,
                technique=technique_name,
                setup=setup_name,
            )
            if evidence.qualified:
                chart_path = render_chart(scan_result, candles, chart_dir, config.vcp)
                scan_result = ScanResult(
                    symbol=symbol,
                    timeframe=config.timeframe,
                    evidence=evidence,
                    chart_path=str(chart_path),
                    technique=technique_name,
                    setup=setup_name,
                )
                candidates.append(_result_json_with_direction(scan_result, candles))
            else:
                rejected_item = _result_json_with_direction(scan_result, candles)
                rejected.append(rejected_item)
                rejected_candles[_result_key(rejected_item)] = (scan_result, candles)

    candidates.sort(key=lambda item: item["evidence"]["score"], reverse=True)
    config_json = config_to_json(config)
    config_json.update(
        {
            "data_source": "TradingView CSV",
            "technique": "all-patterns",
            "setup": "all",
            "symbol_count": len(config.symbols),
            "pattern_count": len(pattern_runs),
            "patterns": [{"technique": technique, "setup": setup} for technique, setup in pattern_runs],
        }
    )
    payload = _payload_with_near_match_charts(candidates, rejected, config_json, rejected_candles, chart_dir, config.vcp)
    _attach_rrg_references_if_available(payload, output_dir, config.timeframe)
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(payload, indent=2))
    write_html_report(results_path, output_dir / "index.html")
    return results_path


def _scan_csv(
    config_path: str | Path,
    out_dir: str | Path,
    timeframe: str = "D1",
    technique: str | None = None,
    setup: str | None = None,
) -> Path:
    config = load_config(config_path)
    if timeframe.upper() != config.timeframe:
        raise ValueError(f"requested timeframe {timeframe} does not match config timeframe {config.timeframe}")
    active_technique = normalize_technique(technique or config.technique)
    active_setup = normalize_setup(setup or config.setup)
    setup_names = _setups_to_scan(active_technique, active_setup)

    output_dir = Path(out_dir)
    chart_dir = output_dir / "charts"
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_old_charts(chart_dir)

    candidates: list[dict] = []
    rejected: list[dict] = []
    rejected_candles: dict[str, tuple[ScanResult, list]] = {}

    for symbol in config.symbols:
        try:
            candles = load_ohlcv_csv(symbol.csv_path)
        except (FileNotFoundError, ValueError) as exc:
            rejected.append(
                ScanResult(
                    symbol=symbol,
                    timeframe=config.timeframe,
                    evidence=VCPEvidence(
                        qualified=False,
                        status="data_error",
                        score=0.0,
                        pivot=None,
                        current_close=None,
                        distance_to_pivot_pct=None,
                        contractions=[],
                        reasons=[],
                        failures=[str(exc)],
                    ),
                    technique=active_technique,
                    setup=active_setup,
                ).to_json()
            )
            continue

        for setup_name in setup_names:
            evidence = detect_pattern(candles, active_technique, config.vcp, setup_name)
            evidence = _apply_ema_side_guard(evidence, candles, config.vcp, active_technique, setup_name)
            evidence = _apply_near_trigger_volume_signal(evidence, candles, config.vcp)
            scan_result = ScanResult(
                symbol=symbol,
                timeframe=config.timeframe,
                evidence=evidence,
                technique=active_technique,
                setup=setup_name,
            )

            if evidence.qualified:
                chart_path = render_chart(scan_result, candles, chart_dir, config.vcp)
                scan_result = ScanResult(
                    symbol=symbol,
                    timeframe=config.timeframe,
                    evidence=evidence,
                    chart_path=str(chart_path),
                    technique=active_technique,
                    setup=setup_name,
                )
                candidates.append(_result_json_with_direction(scan_result, candles))
            else:
                rejected_item = _result_json_with_direction(scan_result, candles)
                rejected.append(rejected_item)
                rejected_candles[_result_key(rejected_item)] = (scan_result, candles)

    candidates.sort(key=lambda item: item["evidence"]["score"], reverse=True)
    config_json = config_to_json(config)
    config_json["technique"] = active_technique
    config_json["setup"] = active_setup
    payload = _payload_with_near_match_charts(candidates, rejected, config_json, rejected_candles, chart_dir, config.vcp)
    _attach_rrg_references_if_available(payload, output_dir, config.timeframe)
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(payload, indent=2))
    write_html_report(results_path, output_dir / "index.html")
    return results_path


def scan_market(
    out_dir: str | Path,
    timeframe: str = "D1",
    config_path: str | Path | None = None,
    period: str = "2y",
    limit: int | None = None,
    shard_index: int = 0,
    shard_count: int = 1,
    universe_name: str = "default",
    broker_filter: str = "all",
    technique: str | None = None,
    setup: str | None = None,
    data_provider: str = "yahoo",
    markets: str | None = None,
    near_match_chart_limit: int = NEAR_MATCH_CHART_LIMIT,
    previous_results_path: str | Path | None = None,
    chart_workers: int = 1,
) -> Path:
    active_timeframe = _normalize_timeframe(timeframe)

    vcp_config, config_technique, config_setup = _load_market_config(config_path)
    active_technique = normalize_technique(technique or config_technique)
    active_setup = normalize_setup(setup or config_setup)
    setup_names = _setups_to_scan(active_technique, active_setup)
    output_dir = Path(out_dir)
    chart_dir = output_dir / "charts"
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_old_charts(chart_dir)

    candidates: list[dict] = []
    rejected: list[dict] = []
    rejected_candles: dict[str, tuple[ScanResult, list]] = {}
    universe = get_universe(universe_name)
    if broker_filter == "exness":
        universe = filter_exness_supported(universe)
    elif broker_filter != "all":
        raise ValueError("unknown broker filter. Choose one of: all, exness")
    universe = _filter_markets(universe, markets)
    universe, crypto_settings = _expand_crypto_if_supported(universe, data_provider)
    universe = _shard_universe(universe, shard_index, shard_count)
    if limit is not None:
        universe = universe[:limit]

    _print_scan_plan(active_timeframe, active_technique, setup_names, universe, data_provider)
    downloaded = _download_market_data(universe, period, active_timeframe, data_provider)
    direction_contexts = _direction_contexts_for_universe(universe, downloaded)

    for index, item in enumerate(universe, start=1):
        _print_scan_progress(index, len(universe), item, "scan-market")
        data = downloaded.get(item.yahoo_symbol)
        symbol = _symbol_from_universe(item, data_provider, data)
        if isinstance(data, Exception):
            rejected.append(
                ScanResult(
                    symbol=symbol,
                    timeframe=active_timeframe,
                    evidence=VCPEvidence(
                        qualified=False,
                        status="data_error",
                        score=0.0,
                        pivot=None,
                        current_close=None,
                        distance_to_pivot_pct=None,
                        contractions=[],
                        reasons=[],
                        failures=[str(data)],
                    ),
                    technique=active_technique,
                    setup=active_setup,
                ).to_json()
            )
            continue
        if data is None:
            rejected.append(
                ScanResult(
                    symbol=symbol,
                    timeframe=active_timeframe,
                    evidence=VCPEvidence(
                        qualified=False,
                        status="data_error",
                        score=0.0,
                        pivot=None,
                        current_close=None,
                        distance_to_pivot_pct=None,
                        contractions=[],
                        reasons=[],
                        failures=[f"No data returned for {item.yahoo_symbol}"],
                    ),
                    technique=active_technique,
                    setup=active_setup,
                ).to_json()
            )
            continue

        try:
            candles = data
        except ValueError as exc:
            rejected.append(
                ScanResult(
                    symbol=symbol,
                    timeframe=active_timeframe,
                    evidence=VCPEvidence(
                        qualified=False,
                        status="data_error",
                        score=0.0,
                        pivot=None,
                        current_close=None,
                        distance_to_pivot_pct=None,
                        contractions=[],
                        reasons=[],
                        failures=[str(exc)],
                    ),
                    technique=active_technique,
                    setup=active_setup,
                ).to_json()
            )
            continue

        for setup_name in setup_names:
            evidence = detect_pattern(candles, active_technique, vcp_config, setup_name)
            evidence = _apply_ema_side_guard(evidence, candles, vcp_config, active_technique, setup_name)
            evidence = _apply_near_trigger_volume_signal(evidence, candles, vcp_config)
            scan_result = ScanResult(
                symbol=symbol,
                timeframe=active_timeframe,
                evidence=evidence,
                technique=active_technique,
                setup=setup_name,
            )
            if evidence.qualified:
                chart_path = render_chart(scan_result, candles, chart_dir, vcp_config)
                scan_result = ScanResult(
                    symbol=symbol,
                    timeframe=active_timeframe,
                    evidence=evidence,
                    chart_path=str(chart_path),
                    technique=active_technique,
                    setup=setup_name,
                )
                candidates.append(_result_json_with_direction(scan_result, candles, direction_contexts.get(symbol.symbol)))
            else:
                rejected_item = _result_json_with_direction(scan_result, candles, direction_contexts.get(symbol.symbol))
                rejected.append(rejected_item)
                rejected_candles[_result_key(rejected_item)] = (scan_result, candles)

    candidates.sort(key=lambda item: item["evidence"]["score"], reverse=True)
    payload = _payload_with_near_match_charts(
        candidates,
        rejected,
        {
            "timeframe": active_timeframe,
            "data_source": _data_source_label(data_provider),
            "period": period,
            "universe": universe_name,
            "broker_filter": broker_filter,
            "data_provider": data_provider,
            **crypto_settings,
            "markets": markets or "all",
            "shard_index": shard_index,
            "shard_count": shard_count,
            "technique": active_technique,
            "setup": active_setup,
            "vcp": vcp_config.__dict__,
            "universe_count": len(universe),
            "chart_workers": chart_workers,
        },
        rejected_candles,
        chart_dir,
        vcp_config,
        near_match_chart_limit,
        chart_workers=chart_workers,
    )
    _attach_rrg_references_if_available(payload, output_dir, active_timeframe)
    apply_watchlist_changes(payload, previous_results_path)
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(payload, indent=2))
    write_html_report(results_path, output_dir / "index.html")
    return results_path


def scan_all_market(
    out_dir: str | Path,
    timeframe: str = "D1",
    config_path: str | Path | None = None,
    period: str = "2y",
    limit: int | None = None,
    shard_index: int = 0,
    shard_count: int = 1,
    universe_name: str = "default",
    broker_filter: str = "all",
    data_provider: str = "yahoo",
    markets: str | None = None,
    near_match_chart_limit: int = NEAR_MATCH_CHART_LIMIT,
    previous_results_path: str | Path | None = None,
    chart_workers: int = 1,
) -> Path:
    active_timeframe = _normalize_timeframe(timeframe)

    vcp_config, _config_technique, _config_setup = _load_market_config(config_path)
    output_dir = Path(out_dir)
    chart_dir = output_dir / "charts"
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_old_charts(chart_dir)

    candidates: list[dict] = []
    rejected: list[dict] = []
    rejected_candles: dict[str, tuple[ScanResult, list]] = {}
    universe = get_universe(universe_name)
    if broker_filter == "exness":
        universe = filter_exness_supported(universe)
    elif broker_filter != "all":
        raise ValueError("unknown broker filter. Choose one of: all, exness")
    universe = _filter_markets(universe, markets)
    universe, crypto_settings = _expand_crypto_if_supported(universe, data_provider)
    universe = _shard_universe(universe, shard_index, shard_count)
    if limit is not None:
        universe = universe[:limit]

    pattern_runs = _all_pattern_runs()
    _print_scan_plan(active_timeframe, "all-patterns", [setup for _technique, setup in pattern_runs], universe, data_provider)
    downloaded = _download_market_data(universe, period, active_timeframe, data_provider)
    direction_contexts = _direction_contexts_for_universe(universe, downloaded)

    for index, item in enumerate(universe, start=1):
        _print_scan_progress(index, len(universe), item, "scan-all-market")
        data = downloaded.get(item.yahoo_symbol)
        symbol = _symbol_from_universe(item, data_provider, data)
        if isinstance(data, Exception):
            rejected.append(
                ScanResult(
                    symbol=symbol,
                    timeframe=active_timeframe,
                    evidence=VCPEvidence(
                        qualified=False,
                        status="data_error",
                        score=0.0,
                        pivot=None,
                        current_close=None,
                        distance_to_pivot_pct=None,
                        contractions=[],
                        reasons=[],
                        failures=[str(data)],
                    ),
                    technique="all-patterns",
                    setup="all",
                ).to_json()
            )
            continue
        if data is None:
            rejected.append(
                ScanResult(
                    symbol=symbol,
                    timeframe=active_timeframe,
                    evidence=VCPEvidence(
                        qualified=False,
                        status="data_error",
                        score=0.0,
                        pivot=None,
                        current_close=None,
                        distance_to_pivot_pct=None,
                        contractions=[],
                        reasons=[],
                        failures=[f"No data returned for {item.yahoo_symbol}"],
                    ),
                    technique="all-patterns",
                    setup="all",
                ).to_json()
            )
            continue

        candles = data
        for technique_name, setup_name in pattern_runs:
            evidence = detect_pattern(candles, technique_name, vcp_config, setup_name)
            evidence = _apply_ema_side_guard(evidence, candles, vcp_config, technique_name, setup_name)
            evidence = _apply_near_trigger_volume_signal(evidence, candles, vcp_config)
            scan_result = ScanResult(
                symbol=symbol,
                timeframe=active_timeframe,
                evidence=evidence,
                technique=technique_name,
                setup=setup_name,
            )
            if evidence.qualified:
                chart_path = render_chart(scan_result, candles, chart_dir, vcp_config)
                scan_result = ScanResult(
                    symbol=symbol,
                    timeframe=active_timeframe,
                    evidence=evidence,
                    chart_path=str(chart_path),
                    technique=technique_name,
                    setup=setup_name,
                )
                candidates.append(_result_json_with_direction(scan_result, candles, direction_contexts.get(symbol.symbol)))
            else:
                rejected_item = _result_json_with_direction(scan_result, candles, direction_contexts.get(symbol.symbol))
                rejected.append(rejected_item)
                rejected_candles[_result_key(rejected_item)] = (scan_result, candles)

    candidates.sort(key=lambda item: item["evidence"]["score"], reverse=True)
    payload = _payload_with_near_match_charts(
        candidates,
        rejected,
        {
            "timeframe": active_timeframe,
            "data_source": _data_source_label(data_provider),
            "period": period,
            "universe": universe_name,
            "broker_filter": broker_filter,
            "data_provider": data_provider,
            **crypto_settings,
            "markets": markets or "all",
            "shard_index": shard_index,
            "shard_count": shard_count,
            "technique": "all-patterns",
            "setup": "all",
            "vcp": vcp_config.__dict__,
            "universe_count": len(universe),
            "pattern_count": len(pattern_runs),
            "patterns": [{"technique": technique, "setup": setup} for technique, setup in pattern_runs],
            "chart_workers": chart_workers,
        },
        rejected_candles,
        chart_dir,
        vcp_config,
        near_match_chart_limit,
        chart_workers=chart_workers,
    )
    _attach_rrg_references_if_available(payload, output_dir, active_timeframe)
    apply_watchlist_changes(payload, previous_results_path)
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(payload, indent=2))
    write_html_report(results_path, output_dir / "index.html")
    return results_path


def _load_market_config(config_path: str | Path | None) -> tuple[VCPConfig, str, str]:
    if config_path is None:
        return VCPConfig(), "minervini-vcp", "all"
    config = load_config(config_path, require_symbols=False)
    return config.vcp, config.technique, config.setup


def _normalize_timeframe(timeframe: str) -> str:
    normalized = timeframe.upper()
    if normalized not in {"D1", "H4"}:
        raise ValueError("supported timeframes are D1 and H4")
    return normalized


def _download_market_data(
    universe: list[UniverseSymbol],
    period: str,
    timeframe: str,
    data_provider: str,
) -> dict[str, list | Exception]:
    provider = data_provider.lower()
    crypto_settings = _crypto_scan_settings()
    if provider == "yahoo":
        return load_yahoo_ohlcv_many([item.yahoo_symbol for item in universe], period=period, timeframe=timeframe)
    if provider == "ccxt":
        crypto_items = [item for item in universe if item.market == "Crypto"]
        results = {
            item.yahoo_symbol: ValueError("CCXT provider only supports Crypto symbols in this scanner")
            for item in universe
            if item.market != "Crypto"
        }
        if crypto_items:
            ccxt_results = load_ccxt_ohlcv_many(
                [item.symbol for item in crypto_items],
                period=period,
                timeframe=timeframe,
                exchange_id=crypto_settings.exchanges,
                market_type=crypto_settings.market_type,
            )
            for item in crypto_items:
                results[item.yahoo_symbol] = ccxt_results.get(item.symbol, ValueError(f"No CCXT data returned for {item.symbol}"))
        return results
    if provider == "vnstock":
        vietnam_items = [item for item in universe if item.market == "Vietnam stock"]
        results = {
            item.yahoo_symbol: ValueError("VNStock provider only supports Vietnam stock symbols in this scanner")
            for item in universe
            if item.market != "Vietnam stock"
        }
        vnstock_results = load_vnstock_ohlcv_many([item.symbol for item in vietnam_items], period=period, timeframe=timeframe)
        for item in vietnam_items:
            results[item.yahoo_symbol] = vnstock_results.get(item.symbol, ValueError(f"No VNStock data returned for {item.symbol}"))
        return results
    if provider == "mixed":
        crypto_items = [item for item in universe if item.market == "Crypto"]
        vietnam_items = [item for item in universe if item.market == "Vietnam stock"]
        yahoo_items = [item for item in universe if item.market not in {"Crypto", "Vietnam stock"}]
        commodity_items = [item for item in yahoo_items if item.market == "Commodity"]
        results: dict[str, list | Exception] = {}
        yahoo_symbols = [item.yahoo_symbol for item in yahoo_items + vietnam_items]
        yahoo_results = load_yahoo_ohlcv_many(yahoo_symbols, period=period, timeframe=timeframe)
        results.update(yahoo_results)
        _apply_commodity_proxy_fallback(results, commodity_items, period, timeframe, crypto_settings)
        yahoo_vietnam_results = {item.yahoo_symbol: yahoo_results.get(item.yahoo_symbol) for item in vietnam_items}
        results.update(yahoo_vietnam_results)
        vietnam_fallback_items = [
            item for item in vietnam_items if _needs_vnstock_fallback(yahoo_vietnam_results.get(item.yahoo_symbol), timeframe)
        ]
        if vietnam_fallback_items:
            print(
                "Yahoo Vietnam fallback: trying VNStock for "
                f"{len(vietnam_fallback_items)} symbol(s): {', '.join(item.symbol for item in vietnam_fallback_items[:20])}"
                f"{'...' if len(vietnam_fallback_items) > 20 else ''}"
            )
            vnstock_results = load_vnstock_ohlcv_many(
                [item.symbol for item in vietnam_fallback_items], period=period, timeframe=timeframe
            )
            recovered = 0
            failed = 0
            for item in vietnam_fallback_items:
                fallback = vnstock_results.get(item.symbol, ValueError(f"No VNStock data returned for {item.symbol}"))
                if not isinstance(fallback, Exception):
                    results[item.yahoo_symbol] = fallback
                    recovered += 1
                else:
                    failed += 1
            print(f"Yahoo Vietnam fallback: VNStock recovered {recovered}, still failed {failed}")
        if crypto_items:
            ccxt_results = load_ccxt_ohlcv_many(
                [item.symbol for item in crypto_items],
                period=period,
                timeframe=timeframe,
                exchange_id=crypto_settings.exchanges,
                market_type=crypto_settings.market_type,
            )
            for item in crypto_items:
                results[item.yahoo_symbol] = ccxt_results.get(item.symbol, ValueError(f"No CCXT data returned for {item.symbol}"))
        return results
    raise ValueError("unknown data provider. Choose one of: yahoo, mixed, ccxt, vnstock")


def _apply_commodity_proxy_fallback(
    results: dict[str, list | Exception],
    commodity_items: list[UniverseSymbol],
    period: str,
    timeframe: str,
    crypto_settings: object,
) -> None:
    fallback_items = []
    proxy_symbols: list[str] = []
    for item in commodity_items:
        yahoo_data = results.get(item.yahoo_symbol)
        reason = _commodity_proxy_fallback_reason(yahoo_data, timeframe)
        if reason is None:
            continue
        candidates = _commodity_proxy_candidates(item.symbol)
        if not candidates:
            continue
        fallback_items.append((item, reason, candidates))
        for candidate in candidates:
            if candidate not in proxy_symbols:
                proxy_symbols.append(candidate)

    if not proxy_symbols:
        return

    print(
        "Yahoo commodity proxy fallback: trying CCXT proxy for "
        f"{len(fallback_items)} symbol(s): {', '.join(item.symbol for item, _reason, _candidates in fallback_items[:20])}"
        f"{'...' if len(fallback_items) > 20 else ''}"
    )
    ccxt_results = load_ccxt_ohlcv_many(
        proxy_symbols,
        period=period,
        timeframe=timeframe,
        exchange_id=crypto_settings.exchanges,
        market_type=crypto_settings.market_type,
    )
    recovered = 0
    failed = 0
    for item, reason, candidates in fallback_items:
        fallback = None
        proxy_symbol = ""
        for candidate in candidates:
            candidate_result = ccxt_results.get(candidate)
            if isinstance(candidate_result, Exception) or _commodity_proxy_fallback_reason(candidate_result, timeframe) is not None:
                continue
            fallback = candidate_result
            proxy_symbol = candidate
            break
        if fallback is None:
            failed += 1
            continue
        results[item.yahoo_symbol] = ProxyCandleSeries(
            fallback,
            {
                "enabled": True,
                "source": "ccxt",
                "proxy_symbol": proxy_symbol,
                "original_yahoo_symbol": item.yahoo_symbol,
                "reason": reason,
            },
        )
        recovered += 1
    print(f"Yahoo commodity proxy fallback: CCXT proxy recovered {recovered}, still failed {failed}")


def _commodity_proxy_fallback_reason(data: object, timeframe: str) -> str | None:
    if isinstance(data, Exception) or data is None:
        return "Yahoo commodity data unavailable"
    if not isinstance(data, list) or not data:
        return "Yahoo commodity data unavailable"
    min_rows = 80 if timeframe.upper() == "D1" else 60
    if len(data) < min_rows:
        return "Yahoo commodity data is too sparse"
    window = data[-min(len(data), 140):]
    highs = [float(candle.high) for candle in window if getattr(candle, "high", None) is not None]
    lows = [float(candle.low) for candle in window if getattr(candle, "low", None) is not None]
    closes = [float(candle.close) for candle in window if getattr(candle, "close", None) is not None]
    if not highs or not lows or not closes:
        return "Yahoo commodity data unavailable"
    reference = max(abs(closes[-1]), 1e-12)
    range_pct = ((max(highs) - min(lows)) / reference) * 100
    unique_closes = len({round(close, 8) for close in closes})
    volumes = [float(getattr(candle, "volume", 0.0) or 0.0) for candle in window]
    no_volume = max(volumes or [0.0]) <= 0.0
    if range_pct < 0.25 or unique_closes <= 3 or (range_pct < 1.0 and no_volume):
        return "Yahoo commodity data is flat/stale"
    return None


def _commodity_proxy_candidates(symbol: str) -> tuple[str, ...]:
    normalized = symbol.upper().strip()
    env_map = _commodity_proxy_env_map()
    if normalized in env_map:
        return env_map[normalized]
    return DEFAULT_COMMODITY_PROXY_SYMBOLS.get(normalized, ())


def _commodity_proxy_env_map() -> dict[str, tuple[str, ...]]:
    raw = os.environ.get(COMMODITY_PROXY_ENV, "")
    mapping: dict[str, tuple[str, ...]] = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            symbol, proxies = chunk.split(":", 1)
        elif "=" in chunk:
            symbol, proxies = chunk.split("=", 1)
        else:
            continue
        proxy_symbols = tuple(proxy.strip().upper() for proxy in proxies.replace("|", "/").split("/") if proxy.strip())
        if symbol.strip() and proxy_symbols:
            mapping[symbol.strip().upper()] = proxy_symbols
    return mapping


def _filter_markets(universe: list[UniverseSymbol], markets: str | None) -> list[UniverseSymbol]:
    if markets is None or not markets.strip() or markets.strip().lower() == "all":
        return universe
    allowed = {market.strip().lower() for market in markets.split(",") if market.strip()}
    if not allowed:
        return universe
    filtered = [item for item in universe if item.market.lower() in allowed]
    if not filtered:
        available = ", ".join(sorted({item.market for item in universe}))
        requested = ", ".join(sorted(allowed))
        raise ValueError(f"market filter matched no symbols: {requested}. Available markets: {available}")
    return filtered


def _shard_universe(universe: list[UniverseSymbol], shard_index: int = 0, shard_count: int = 1) -> list[UniverseSymbol]:
    if shard_count < 1:
        raise ValueError("shard count must be at least 1")
    if shard_count <= 1:
        if shard_index not in {0, -1}:
            raise ValueError("shard index must be 0 when shard count is 1")
        return universe
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError("shard index must be between 0 and shard count - 1")
    return [item for index, item in enumerate(universe) if index % shard_count == shard_index]


def _expand_crypto_if_supported(universe: list[UniverseSymbol], data_provider: str) -> tuple[list[UniverseSymbol], dict[str, object]]:
    settings = _crypto_scan_settings()
    provider = data_provider.lower()
    if provider not in {"mixed", "ccxt"}:
        return universe, settings.to_config()
    if not any(item.market == "Crypto" for item in universe):
        return universe, settings.to_config()
    if settings.mode == "static":
        crypto_count = sum(1 for item in universe if item.market == "Crypto")
        print(f"Crypto universe expansion: static mode, scanning {crypto_count} configured crypto symbol(s)")
        return universe, settings.to_config()
    expanded = expand_crypto_universe(
        universe,
        exchange_id=settings.exchanges,
        market_type=settings.market_type,
        max_symbols=settings.max_symbols,
    )
    crypto_count = sum(1 for item in expanded if item.market == "Crypto")
    max_detail = "unlimited" if settings.max_symbols is None else str(settings.max_symbols)
    print(
        "Crypto universe expansion: "
        f"mode={settings.mode} exchanges={settings.exchanges} max_symbols={max_detail} "
        f"market_type={settings.market_type} scanning={crypto_count} USDT {settings.market_type} pair(s)"
    )
    return expanded, settings.to_config()


class _CryptoScanSettings:
    def __init__(self, mode: str, exchanges: str, market_type: str, max_symbols: int | None) -> None:
        self.mode = mode
        self.exchanges = exchanges
        self.market_type = market_type
        self.max_symbols = max_symbols

    def to_config(self) -> dict[str, object]:
        return {
            "crypto_mode": self.mode,
            "crypto_exchanges": self.exchanges,
            "crypto_market_type": self.market_type,
            "crypto_max_symbols": self.max_symbols,
        }


def _crypto_scan_settings() -> _CryptoScanSettings:
    raw_mode = os.environ.get("CRYPTO_MODE", "wide").strip().lower()
    mode = raw_mode if raw_mode in {"core", "wide", "static"} else "core"
    exchange_override = os.environ.get("CRYPTO_EXCHANGES", "").strip()
    if exchange_override:
        exchanges = exchange_override
    elif mode == "wide":
        exchanges = "binance,bybit,okx,mexc"
    else:
        exchanges = "binance,bybit,okx"
    market_type = _normalize_crypto_market_type(os.environ.get("CRYPTO_MARKET_TYPE", "perp"))

    max_symbols_raw = os.environ.get("CRYPTO_MAX_SYMBOLS", "").strip()
    if max_symbols_raw:
        try:
            max_symbols = max(1, int(max_symbols_raw))
        except ValueError:
            max_symbols = 100 if mode == "core" else None
    elif mode == "core":
        max_symbols = 100
    else:
        max_symbols = None
    return _CryptoScanSettings(mode=mode, exchanges=exchanges, market_type=market_type, max_symbols=max_symbols)


def _normalize_crypto_market_type(market_type: str) -> str:
    normalized = str(market_type or "").strip().lower()
    if normalized in {"spot"}:
        return "spot"
    return "perp"


def _print_scan_plan(
    timeframe: str,
    technique: str,
    setup_names: list[str] | tuple[str, ...],
    universe: list[UniverseSymbol],
    data_provider: str,
) -> None:
    market_counts: dict[str, int] = {}
    for item in universe:
        market_counts[item.market] = market_counts.get(item.market, 0) + 1
    market_summary = ", ".join(f"{market}={count}" for market, count in sorted(market_counts.items()))
    print(
        f"Scan plan: timeframe={timeframe} technique={technique} provider={data_provider} "
        f"symbols={len(universe)} setup_count={len(setup_names)} evaluations={len(universe) * len(setup_names)}"
    )
    print(f"Scan plan markets: {market_summary}")


def _print_scan_progress(index: int, total: int, item: UniverseSymbol, label: str) -> None:
    if total <= 0:
        return
    interval = max(1, min(100, total // 20 or 1))
    if index == 1 or index == total or index % interval == 0:
        print(f"{label} progress: {index}/{total} {item.market}:{item.symbol}", flush=True)


def _needs_vnstock_fallback(data: list | Exception | None, timeframe: str) -> bool:
    if not isinstance(data, list):
        return True
    minimum = 80 if timeframe == "D1" else 60
    return len(data) < minimum


def _apply_ema_side_guard(
    evidence: VCPEvidence,
    candles: list[Candle],
    config: VCPConfig,
    technique: str,
    setup: str,
) -> VCPEvidence:
    if not evidence.qualified or not candles:
        return evidence

    direction = _evidence_direction(evidence, technique, setup)
    if direction not in {"long", "short"}:
        return evidence

    closes = [candle.close for candle in candles]
    ema = _latest_ema(closes, config.ema_period)
    current_close = closes[-1]
    if ema is None:
        return evidence

    if direction == "long" and current_close >= ema:
        return evidence
    if direction == "short" and current_close <= ema:
        return evidence

    side = "above" if direction == "long" else "below"
    failure = (
        f"EMA21 final-side guard failed: {direction.title()} setup requires latest close {side} EMA{config.ema_period}; "
        f"close={current_close:.4g}, EMA{config.ema_period}={ema:.4g}"
    )
    return replace(
        evidence,
        qualified=False,
        status="rejected",
        score=min(evidence.score, 79.0),
        failures=[*evidence.failures, failure],
    )


def _apply_near_trigger_volume_signal(evidence: VCPEvidence, candles: list[Candle], config: VCPConfig) -> VCPEvidence:
    if not evidence.qualified or len(candles) < 6:
        return evidence

    status = str(evidence.status).upper()
    latest_volume = float(candles[-1].volume or 0.0)
    previous_volumes = [float(candle.volume or 0.0) for candle in candles[-6:-1] if float(candle.volume or 0.0) > 0]
    if latest_volume <= 0 or not previous_volumes:
        return evidence

    previous_average = sum(previous_volumes) / len(previous_volumes)
    if previous_average <= 0:
        return evidence

    ratio = latest_volume / previous_average

    if status == "TRIGGERED":
        signal_prefix = "Trigger volume confirmed" if ratio >= 1.2 else "Trigger volume not confirmed"
        signal_detail = (
            f"{signal_prefix}: latest closed candle volume {latest_volume:,.0f} is {ratio:.2f}x the previous "
            f"{len(previous_volumes)}-candle average"
        )
        if signal_detail in evidence.reasons:
            return evidence
        return replace(evidence, reasons=[*evidence.reasons, signal_detail])

    if status not in {"WAITING", "NEAR_PIVOT", "READY_NEAR_PIVOT", "FORMING"}:
        return evidence

    distance = evidence.distance_to_pivot_pct
    if distance is None or abs(float(distance)) > max(0.1, float(config.near_pivot_pct)):
        return evidence

    rising_three = (
        len(previous_volumes) >= 2
        and previous_volumes[-2] < previous_volumes[-1] < latest_volume
    )
    signal_prefix = "Pre-trigger volume building" if ratio >= 1.2 or rising_three else "Pre-trigger volume watch"
    signal_detail = (
        f"{signal_prefix}: latest volume {latest_volume:,.0f} is {ratio:.2f}x the previous "
        f"{len(previous_volumes)}-candle average while price is {abs(float(distance)):.2f}% from trigger"
    )
    if signal_detail in evidence.reasons:
        return evidence

    return replace(
        evidence,
        reasons=[*evidence.reasons, signal_detail],
    )


def _evidence_direction(evidence: VCPEvidence, technique: str, setup: str) -> str:
    lines = evidence.reasons + evidence.failures
    for line in lines:
        stripped = str(line).strip()
        if stripped.startswith("Direction:"):
            direction = stripped.removeprefix("Direction:").strip().lower()
            if direction in {"long", "short"}:
                return direction
    status = evidence.status.lower()
    if "_long" in status:
        return "long"
    if "_short" in status:
        return "short"
    normalized_setup = setup.lower()
    normalized_technique = technique.lower()
    if normalized_technique in {"minervini-vcp", "vcp"} or normalized_setup in {"vcp", "vcp-1c", "vcp-2c", "vcp-3c"}:
        return "long"
    return ""


def _latest_ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    multiplier = 2 / (period + 1)
    ema = float(values[0])
    for value in values[1:]:
        ema = (float(value) - ema) * multiplier + ema
    return ema


def _data_source_label(data_provider: str) -> str:
    provider = data_provider.lower()
    if provider == "mixed":
        return "Yahoo Finance + VNStock + CCXT"
    if provider == "ccxt":
        return "CCXT"
    if provider == "vnstock":
        return "VNStock"
    return "Yahoo Finance"


def _setups_to_scan(technique: str, setup: str) -> tuple[str, ...]:
    if technique == "nhathoai" and setup == "all":
        return NHATHOAI_SCAN_SETUPS
    return (setup,)


def _all_pattern_runs() -> list[tuple[str, str]]:
    return [
        *[("minervini-vcp", setup_name) for setup_name in MINERVINI_VCP_SCAN_SETUPS],
        *[("nhathoai", setup_name) for setup_name in NHATHOAI_SCAN_SETUPS],
    ]


def _clear_old_charts(chart_dir: Path) -> None:
    if not chart_dir.exists():
        return
    for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        for chart_path in chart_dir.glob(pattern):
            chart_path.unlink()


def _payload_with_near_match_charts(
    candidates: list[dict],
    rejected: list[dict],
    config: dict,
    rejected_candles: dict[str, tuple[ScanResult, list]],
    chart_dir: Path,
    vcp_config: VCPConfig,
    near_match_chart_limit: int = NEAR_MATCH_CHART_LIMIT,
    review_setup_chart_limit: int = REVIEW_SETUP_CHART_LIMIT,
    chart_workers: int = 1,
) -> dict:
    payload = result_payload(candidates, rejected, config)
    chart_rows = (
        payload.get("near_matches", [])[: max(0, near_match_chart_limit)]
        + _review_setup_chart_rows(payload.get("review_setups", []), review_setup_chart_limit)
    )
    rendered_keys = set()
    render_tasks: list[tuple[str, ScanResult, list]] = []
    for chart_row in chart_rows:
        key = _result_key(chart_row)
        if key in rendered_keys:
            continue
        rendered_keys.add(key)
        stored = rejected_candles.get(key)
        if stored is None:
            continue
        scan_result, candles = stored
        render_tasks.append((key, scan_result, candles))
    for key, chart_path in _render_review_charts(render_tasks, chart_dir, vcp_config, chart_workers).items():
        _attach_chart_path(payload, rejected, key, chart_path)
    refresh_trigger_warnings(payload)
    return payload


def _render_review_charts(
    render_tasks: list[tuple[str, ScanResult, list]],
    chart_dir: Path,
    vcp_config: VCPConfig,
    chart_workers: int = 1,
) -> dict[str, str]:
    if not render_tasks:
        return {}
    workers = max(1, int(chart_workers or 1))
    if workers == 1 or len(render_tasks) == 1:
        return {
            key: str(render_chart(scan_result, candles, chart_dir, vcp_config))
            for key, scan_result, candles in render_tasks
        }

    rendered: dict[str, str] = {}
    try:
        with ProcessPoolExecutor(max_workers=min(workers, len(render_tasks))) as executor:
            futures = {
                executor.submit(_render_review_chart_worker, key, scan_result, candles, chart_dir, vcp_config): key
                for key, scan_result, candles in render_tasks
            }
            for future in as_completed(futures):
                key, chart_path = future.result()
                rendered[key] = chart_path
    except (NotImplementedError, OSError):
        return {
            key: str(render_chart(scan_result, candles, chart_dir, vcp_config))
            for key, scan_result, candles in render_tasks
        }
    return rendered


def _render_review_chart_worker(
    key: str,
    scan_result: ScanResult,
    candles: list,
    chart_dir: Path,
    vcp_config: VCPConfig,
) -> tuple[str, str]:
    return key, str(render_chart(scan_result, candles, chart_dir, vcp_config))


def _attach_chart_path(payload: dict, rejected: list[dict], key: str, chart_path: str) -> None:
    for review_item in payload.get("review_setups", []):
        if _result_key(review_item) == key:
            review_item["chart_path"] = chart_path
            break
    for near_match in payload.get("near_matches", []):
        if _result_key(near_match) == key:
            near_match["chart_path"] = chart_path
            break
    for rejected_item in rejected:
        if _result_key(rejected_item) == key:
            rejected_item["chart_path"] = chart_path
            break


def _attach_rrg_references_if_available(payload: dict, output_dir: Path, timeframe: str) -> dict:
    try:
        from .rrg_dashboard import attach_rrg_references

        return attach_rrg_references(payload, output_dir, timeframe)
    except Exception as exc:
        payload["rrg_reference"] = {
            "enabled": True,
            "status": "error",
            "attached_count": 0,
            "error": str(exc),
            "note": "RRG is reference-only. The pattern scan completed and the watchlist was not filtered by RRG.",
        }
        return payload


def _result_json_with_direction(
    scan_result: ScanResult,
    candles: list[Candle],
    context: DirectionMarketContext | None = None,
) -> dict:
    row = annotate_result_with_direction_authority(scan_result.to_json(), candles, context)
    proxy_data = _proxy_data(candles)
    if proxy_data:
        row["proxy_data"] = proxy_data
    return row


def _direction_contexts_for_universe(
    universe: list[UniverseSymbol],
    downloaded: dict[str, list | Exception],
) -> dict[str, DirectionMarketContext]:
    candles_by_symbol: dict[str, list[Candle]] = {}
    markets_by_symbol: dict[str, str] = {}
    for item in universe:
        data = downloaded.get(item.yahoo_symbol)
        if isinstance(data, Exception) or not data:
            continue
        candles_by_symbol[item.symbol] = data
        markets_by_symbol[item.symbol] = item.market
    contexts = {}
    context_by_market = {}
    for item in universe:
        if item.market not in context_by_market:
            context_by_market[item.market] = build_market_context(candles_by_symbol, markets_by_symbol, item.market)
        context = context_by_market[item.market]
        if context is not None:
            contexts[item.symbol] = context
    return contexts


def _review_setup_chart_rows(review_setups: list[dict], limit: int = REVIEW_SETUP_CHART_LIMIT) -> list[dict]:
    if limit <= 0:
        return []
    indexed = list(enumerate(review_setups))
    indexed.sort(key=lambda pair: _review_setup_chart_priority(pair[1], pair[0]), reverse=True)
    return [item for _, item in indexed[:limit]]


def _review_setup_chart_priority(item: dict, index: int) -> tuple[int, float, float, int]:
    evidence = item.get("evidence", {})
    distance = _numeric(evidence.get("distance_to_pivot_pct"))
    detector_score = _numeric(evidence.get("score")) or 0.0
    status = str(evidence.get("status") or "").upper()
    active_status = status in {"WAITING", "NEAR_PIVOT", "READY_NEAR_PIVOT", "FORMING", "TRIGGERED"}
    near_trigger = distance is not None and abs(distance) <= 5.0
    priority = 1 if near_trigger and (detector_score > 0.0 or active_status) else 0
    return (priority, _numeric(item.get("review_score")) or 0.0, detector_score, -index)


def _numeric(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _result_key(item: dict) -> str:
    return (
        f"{item.get('market')}::{item.get('symbol')}::{item.get('tradingview_symbol')}::"
        f"{item.get('timeframe')}::{item.get('technique')}::{item.get('setup')}"
    )


def _symbol_from_universe(item: UniverseSymbol, data_provider: str = "yahoo", data: object = None) -> SymbolSpec:
    provider = data_provider.lower()
    source_path = f"yahoo:{item.yahoo_symbol}"
    if item.market == "Vietnam stock" and provider == "vnstock":
        source_path = f"vnstock:{item.symbol}"
    if item.market == "Crypto" and provider in {"mixed", "ccxt"}:
        source_path = f"ccxt:{item.symbol}"
    proxy_data = _proxy_data(data)
    if proxy_data:
        source_path = f"{proxy_data.get('source', 'proxy')}-proxy:{proxy_data.get('proxy_symbol', '')}"
    return SymbolSpec(
        symbol=item.symbol,
        market=item.market,
        tradingview_symbol=item.tradingview_symbol,
        csv_path=Path(source_path),
    )


def _proxy_data(data: object) -> dict | None:
    proxy_data = getattr(data, "proxy_data", None)
    if isinstance(proxy_data, dict):
        return proxy_data
    return None
