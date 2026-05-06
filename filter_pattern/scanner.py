from __future__ import annotations

import json
from pathlib import Path

from .chart import render_chart
from .data import config_to_json, load_config, load_ohlcv_csv
from .detector import detect_pattern
from .exness import filter_exness_supported
from .models import ScanResult, SymbolSpec, VCPConfig, VCPEvidence
from .providers import load_ccxt_ohlcv_many, load_vnstock_ohlcv_many, load_yahoo_ohlcv_many
from .report import apply_watchlist_changes, refresh_trigger_warnings, result_payload, write_html_report
from .techniques import MINERVINI_VCP_SCAN_SETUPS, NHATHOAI_SCAN_SETUPS, normalize_setup, normalize_technique
from .universe import UniverseSymbol, get_universe


NEAR_MATCH_CHART_LIMIT = 20


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
                candidates.append(scan_result.to_json())
            else:
                rejected_item = scan_result.to_json()
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
                candidates.append(scan_result.to_json())
            else:
                rejected_item = scan_result.to_json()
                rejected.append(rejected_item)
                rejected_candles[_result_key(rejected_item)] = (scan_result, candles)

    candidates.sort(key=lambda item: item["evidence"]["score"], reverse=True)
    config_json = config_to_json(config)
    config_json["technique"] = active_technique
    config_json["setup"] = active_setup
    payload = _payload_with_near_match_charts(candidates, rejected, config_json, rejected_candles, chart_dir, config.vcp)
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
    universe_name: str = "default",
    broker_filter: str = "all",
    technique: str | None = None,
    setup: str | None = None,
    data_provider: str = "yahoo",
    markets: str | None = None,
    near_match_chart_limit: int = NEAR_MATCH_CHART_LIMIT,
    previous_results_path: str | Path | None = None,
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
    if limit is not None:
        universe = universe[:limit]

    downloaded = _download_market_data(universe, period, active_timeframe, data_provider)

    for item in universe:
        symbol = _symbol_from_universe(item, data_provider)
        data = downloaded.get(item.yahoo_symbol)
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
                candidates.append(scan_result.to_json())
            else:
                rejected_item = scan_result.to_json()
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
            "markets": markets or "all",
            "technique": active_technique,
            "setup": active_setup,
            "vcp": vcp_config.__dict__,
            "universe_count": len(universe),
        },
        rejected_candles,
        chart_dir,
        vcp_config,
        near_match_chart_limit,
    )
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
    universe_name: str = "default",
    broker_filter: str = "all",
    data_provider: str = "yahoo",
    markets: str | None = None,
    near_match_chart_limit: int = NEAR_MATCH_CHART_LIMIT,
    previous_results_path: str | Path | None = None,
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
    if limit is not None:
        universe = universe[:limit]

    pattern_runs = _all_pattern_runs()
    downloaded = _download_market_data(universe, period, active_timeframe, data_provider)

    for item in universe:
        symbol = _symbol_from_universe(item, data_provider)
        data = downloaded.get(item.yahoo_symbol)
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
                candidates.append(scan_result.to_json())
            else:
                rejected_item = scan_result.to_json()
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
            "markets": markets or "all",
            "technique": "all-patterns",
            "setup": "all",
            "vcp": vcp_config.__dict__,
            "universe_count": len(universe),
            "pattern_count": len(pattern_runs),
            "patterns": [{"technique": technique, "setup": setup} for technique, setup in pattern_runs],
        },
        rejected_candles,
        chart_dir,
        vcp_config,
        near_match_chart_limit,
    )
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
    if provider == "yahoo":
        return load_yahoo_ohlcv_many([item.yahoo_symbol for item in universe], period=period, timeframe=timeframe)
    if provider == "ccxt":
        crypto_items = [item for item in universe if item.market == "Crypto"]
        results = {
            item.yahoo_symbol: ValueError("CCXT provider only supports Crypto symbols in this scanner")
            for item in universe
            if item.market != "Crypto"
        }
        ccxt_results = load_ccxt_ohlcv_many([item.symbol for item in crypto_items], period=period, timeframe=timeframe)
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
        results: dict[str, list | Exception] = {}
        yahoo_symbols = [item.yahoo_symbol for item in yahoo_items + vietnam_items]
        yahoo_results = load_yahoo_ohlcv_many(yahoo_symbols, period=period, timeframe=timeframe)
        results.update(yahoo_results)
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
        ccxt_results = load_ccxt_ohlcv_many([item.symbol for item in crypto_items], period=period, timeframe=timeframe)
        for item in crypto_items:
            results[item.yahoo_symbol] = ccxt_results.get(item.symbol, ValueError(f"No CCXT data returned for {item.symbol}"))
        return results
    raise ValueError("unknown data provider. Choose one of: yahoo, mixed, ccxt, vnstock")


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


def _needs_vnstock_fallback(data: list | Exception | None, timeframe: str) -> bool:
    if not isinstance(data, list):
        return True
    minimum = 80 if timeframe == "D1" else 60
    return len(data) < minimum


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
    for chart_path in chart_dir.glob("*.png"):
        chart_path.unlink()


def _payload_with_near_match_charts(
    candidates: list[dict],
    rejected: list[dict],
    config: dict,
    rejected_candles: dict[str, tuple[ScanResult, list]],
    chart_dir: Path,
    vcp_config: VCPConfig,
    near_match_chart_limit: int = NEAR_MATCH_CHART_LIMIT,
) -> dict:
    payload = result_payload(candidates, rejected, config)
    for near_match in payload.get("near_matches", [])[: max(0, near_match_chart_limit)]:
        stored = rejected_candles.get(_result_key(near_match))
        if stored is None:
            continue
        scan_result, candles = stored
        chart_path = render_chart(scan_result, candles, chart_dir, vcp_config)
        near_match["chart_path"] = str(chart_path)
        for rejected_item in rejected:
            if _result_key(rejected_item) == _result_key(near_match):
                rejected_item["chart_path"] = str(chart_path)
                break
    refresh_trigger_warnings(payload)
    return payload


def _result_key(item: dict) -> str:
    return (
        f"{item.get('market')}::{item.get('symbol')}::{item.get('tradingview_symbol')}::"
        f"{item.get('timeframe')}::{item.get('technique')}::{item.get('setup')}"
    )


def _symbol_from_universe(item: UniverseSymbol, data_provider: str = "yahoo") -> SymbolSpec:
    provider = data_provider.lower()
    source_path = f"yahoo:{item.yahoo_symbol}"
    if item.market == "Vietnam stock" and provider == "vnstock":
        source_path = f"vnstock:{item.symbol}"
    if item.market == "Crypto" and provider in {"mixed", "ccxt"}:
        source_path = f"ccxt:{item.symbol}"
    return SymbolSpec(
        symbol=item.symbol,
        market=item.market,
        tradingview_symbol=item.tradingview_symbol,
        csv_path=Path(source_path),
    )
