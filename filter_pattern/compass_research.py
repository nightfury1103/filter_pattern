"""Reproducible D1 direction diagnostics; no orders or scanner qualification edits."""
from __future__ import annotations

import hashlib
import json
import random
import sys
from importlib.metadata import PackageNotFoundError, version
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import fmean, median

from .compass import HORIZONS, MODELS, PRIMARY_HORIZON, PRIMARY_MODEL, WARMUP, calculate_compass_series, validate_candles
from .data import load_config, load_ohlcv_csv
from .models import Candle

INSTRUMENTS = (
    ("US500", "S&P 500 index", "Index", "^GSPC", False),
    ("SPY", "SPY ETF", "US stock", "SPY", False),
    ("VN30_ETF", "E1VFVN30 ETF — proxy, không phải VN30 index", "Vietnam stock", "E1VFVN30.VN", True),
    ("BTCUSD", "BTC/USD spot — không phải perpetual", "Crypto", "BTC-USD", False),
    ("ETHUSD", "ETH/USD spot — không phải perpetual", "Crypto", "ETH-USD", False),
    ("GOLD_FUTURES", "Gold futures — proxy, không phải XAUUSD spot", "Commodity", "GC=F", True),
    ("EURUSD", "EUR/USD", "Forex", "EURUSD=X", False),
    ("USDJPY", "USD/JPY", "Forex", "JPY=X", False),
    ("DXY", "US Dollar Index — Yahoo DX-Y.NYB", "Forex", "DX-Y.NYB", False),
)


def _candle_json(candle: Candle) -> dict:
    return {**asdict(candle), "datetime": candle.datetime.isoformat()}


def load_research_data(
    output_dir: Path, period: str = "10y", config_path: str | Path | None = None,
    before: date | None = None, cache_path: str | Path | None = None,
) -> tuple[dict[str, list[Candle]], dict, dict]:
    """Exclusive date cutoff conservatively omits today's potentially open bar."""
    before = before or datetime.now(timezone.utc).date()
    output_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, list[Candle]] = {}
    metadata: dict[str, dict] = {}
    errors: dict[str, str] = {}
    if cache_path:
        cached = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        errors.update(cached.get("errors", {}))
        entries = [(key, row["metadata"], row["candles"]) for key, row in cached["instruments"].items()]
    elif config_path:
        config = load_config(config_path)
        if config.timeframe != "D1":
            raise ValueError("Market Compass research currently supports D1 only")
        entries = []
        for item in config.symbols:
            if item.symbol in metadata:
                raise ValueError(f"Duplicate research symbol: {item.symbol}")
            meta = {"label": item.symbol, "market": item.market, "source": str(item.csv_path), "proxy": False, "provider": "CSV"}
            metadata[item.symbol] = meta
            try:
                entries.append((item.symbol, meta, [_candle_json(c) for c in load_ohlcv_csv(item.csv_path)]))
            except (ValueError, FileNotFoundError) as exc:
                errors[item.symbol] = str(exc)
    else:
        import yfinance as yf

        yf.set_tz_cache_location(str(output_dir / "yahoo-cache"))
        entries = []
        for symbol, label, market, ticker, proxy in INSTRUMENTS:
            meta = {"label": label, "market": market, "source": ticker, "proxy": proxy, "provider": "Yahoo Finance", "adjustment": "auto_adjust=True"}
            metadata[symbol] = meta
            print(f"Compass data: {symbol} ({ticker})", flush=True)
            try:
                frame = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False, threads=False, timeout=20)
                if frame.empty:
                    raise ValueError(f"No Yahoo D1 data for {ticker}; supply exact TradingView CSV instead")
                if getattr(frame.columns, "nlevels", 1) > 1:
                    frame.columns = frame.columns.get_level_values(0)
                rows = [{"datetime": timestamp.isoformat(), "open": float(row["Open"]), "high": float(row["High"]),
                         "low": float(row["Low"]), "close": float(row["Close"]), "volume": float(row.get("Volume", 0) or 0)}
                        for timestamp, row in frame.iterrows()]
                entries.append((symbol, meta, rows))
            except Exception as exc:  # Isolate provider failures per instrument, keep missing symbols visible.
                errors[symbol] = str(exc)
    for symbol, meta, rows in entries:
        metadata[symbol] = dict(meta)
        try:
            candles = [Candle(**{**row, "datetime": datetime.fromisoformat(row["datetime"])}) for row in rows]
            candles = [c for c in candles if c.datetime.date() < before]
            validate_candles(candles)
            if len(candles) <= WARMUP + max(HORIZONS):
                raise ValueError(f"Need more than {WARMUP + max(HORIZONS)} completed D1 candles; got {len(candles)}")
            encoded = json.dumps([_candle_json(c) for c in candles], sort_keys=True, allow_nan=False).encode()
            data[symbol] = candles
            errors.pop(symbol, None)
            metadata[symbol].update({
                "bars": len(candles), "first_date": candles[0].datetime.date().isoformat(),
                "last_date": candles[-1].datetime.date().isoformat(), "sha256": hashlib.sha256(encoded).hexdigest(),
                "excluded_on_or_after_cutoff": len(rows) - len(candles),
                "original_excluded_on_or_after_cutoff": meta.get("original_excluded_on_or_after_cutoff", meta.get("excluded_on_or_after_cutoff", len(rows) - len(candles))),
            })
        except (ValueError, TypeError) as exc:
            errors[symbol] = str(exc)
    # Cached failed symbols may have no data entry; retain their source labels too.
    if cache_path:
        for key, meta in cached.get("metadata", {}).items():
            metadata.setdefault(key, meta)
    bundle = {
        "schema_version": 1, "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_retrieved_at": cached.get("source_retrieved_at", cached.get("retrieved_at")) if cache_path else datetime.now(timezone.utc).isoformat(),
        "before": before.isoformat(), "errors": errors, "metadata": metadata,
        "instruments": {s: {"metadata": metadata[s], "candles": [_candle_json(c) for c in rows]} for s, rows in data.items()},
    }
    (output_dir / "candles.json").write_text(json.dumps(bundle, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return data, metadata, errors


def outcome(candles: list[Candle], index: int, horizon: int) -> dict:
    """Signal at T close; start T+1 open, through T+h close (h full bars)."""
    window = candles[index + 1:index + horizon + 1]
    if len(window) != horizon:
        raise ValueError("Incomplete forward outcome")
    entry = window[0].open
    return {
        "return_pct": 100 * (window[-1].close / entry - 1),
        "low_pct": min(0.0, 100 * (min(c.low for c in window) / entry - 1)),
        "high_pct": max(0.0, 100 * (max(c.high for c in window) / entry - 1)),
        "entry_date": window[0].datetime.date().isoformat(),
        "exit_date": window[-1].datetime.date().isoformat(),
    }


def build_trials(candles: list[Candle], signals: list[dict], horizon: int, cutoff: str) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {"development": [], "holdout": []}
    for index in range(WARMUP, len(candles) - horizon):
        signal = signals[index]
        result = outcome(candles, index, horizon)
        if signal["date"] < cutoff:
            if result["exit_date"] >= cutoff:
                continue  # Purge development labels crossing the test boundary.
            split = "development"
        else:
            split = "holdout"
        groups[split].append({"index": index, "date": signal["date"], "bias": signal["bias"],
                              "scheduled": (index - WARMUP) % horizon == 0, **result})
    return groups


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (position - lower)


def bootstrap_intervals(rows: list[dict], side: str, repetitions: int = 300) -> dict:
    """Circular moving blocks preserve short-range dependence and WAIT coverage."""
    if len(rows) < 80:
        return {"mean_ci95": None, "lift_ci95": None}
    sign = 1 if side == "LONG" else -1
    counts, selected, baseline = [0], [0.0], [0.0]
    for row in rows * 2:
        active = row["bias"] == side
        counts.append(counts[-1] + int(active))
        selected.append(selected[-1] + (sign * row["return_pct"] if active else 0))
        baseline.append(baseline[-1] + sign * row["return_pct"])
    rng = random.Random(17092026)
    means, lifts = [], []
    length = len(rows)
    for _ in range(repetitions):
        n, total, base, remaining = 0, 0.0, 0.0, length
        while remaining:
            size = min(40, remaining)
            start = rng.randrange(length)
            n += counts[start + size] - counts[start]
            total += selected[start + size] - selected[start]
            base += baseline[start + size] - baseline[start]
            remaining -= size
        if n:
            means.append(total / n)
            lifts.append(total / n - base / length)
    if len(means) < repetitions * 0.9:
        return {"mean_ci95": None, "lift_ci95": None}
    return {"mean_ci95": [_quantile(means, 0.025), _quantile(means, 0.975)],
            "lift_ci95": [_quantile(lifts, 0.025), _quantile(lifts, 0.975)]}


def summarize_side(rows: list[dict], side: str) -> dict:
    sign = 1 if side == "LONG" else -1
    selected = [r for r in rows if r["bias"] == side]
    values = [sign * r["return_pct"] for r in selected]
    scheduled = [r for r in selected if r["scheduled"]]
    half = len(rows) // 2
    half_means = []
    for part in (rows[:half], rows[half:]):
        part_values = [sign * r["return_pct"] for r in part if r["bias"] == side]
        half_means.append(fmean(part_values) if part_values else None)
    baseline = fmean(sign * r["return_pct"] for r in rows) if rows else None
    average = fmean(values) if values else None
    intervals = bootstrap_intervals(rows, side)
    return {
        "samples": len(selected), "scheduled_samples": len(scheduled),
        "coverage": len(selected) / len(rows) if rows else 0,
        "hit_rate": sum(v > 0 for v in values) / len(values) if values else None,
        "false_direction_rate": sum(v <= 0 for v in values) / len(values) if values else None,
        "scheduled_hit_rate": sum(sign * r["return_pct"] > 0 for r in scheduled) / len(scheduled) if scheduled else None,
        "mean_return_pct": average, "median_return_pct": median(values) if values else None,
        "baseline_mean_pct": baseline, "lift_pct": average - baseline if average is not None else None,
        "baseline_hit_rate": sum(sign * r["return_pct"] > 0 for r in rows) / len(rows) if rows else None,
        "mean_adverse_pct": fmean(r["low_pct"] if side == "LONG" else -r["high_pct"] for r in selected) if selected else None,
        "mean_favorable_pct": fmean(r["high_pct"] if side == "LONG" else -r["low_pct"] for r in selected) if selected else None,
        "half_means_pct": half_means, **intervals,
    }


def evidence_status(summary: dict) -> str:
    if summary["scheduled_samples"] < 30:
        return "insufficient"
    intervals = (summary["mean_ci95"], summary["lift_ci95"])
    if all(interval and interval[0] > 0 for interval in intervals) and all(v is not None and v > 0 for v in summary["half_means_pct"]):
        return "promising"
    return "not_demonstrated"


def stability(signals: list[dict]) -> dict:
    active = [s for s in signals if s["available"]]
    changes = sum(a["bias"] != b["bias"] for a, b in zip(active, active[1:]))
    episodes = []
    previous = "WAIT"
    for index, signal in enumerate(active):
        bias = signal["bias"]
        if bias != previous and bias in {"LONG", "SHORT"}:
            episodes.append((index, bias))
        previous = bias
    reversals = 0
    for index, side in episodes:
        opposite = "SHORT" if side == "LONG" else "LONG"
        if any(s["bias"] == opposite for s in active[index + 1:index + 6]):
            reversals += 1
    return {"bars": len(active), "state_changes": changes,
            "changes_per_100_bars": changes / max(1, len(active) - 1) * 100,
            "direction_episodes": len(episodes), "opposite_within_5_bars": reversals,
            "wait_coverage": sum(s["bias"] == "WAIT" for s in active) / max(1, len(active))}


def reaction_delay(candles: list[Candle], signals: list[dict], cutoff: str) -> dict:
    """Diagnostic delay after alternating 20-bar closing-price breakouts.

    This is an explicit price reference, not a hindsight claim of true reversals.
    It does not select models or alter the frozen evidence rule.
    """
    previous = None
    delays = []
    events = 0
    for index in range(WARMUP, len(candles) - 10):
        price = candles[index].close
        history = [c.close for c in candles[index - 20:index]]
        side = "LONG" if price > max(history) else "SHORT" if price < min(history) else None
        if side is None or side == previous:
            continue
        previous = side
        if signals[index]["date"] < cutoff:
            continue
        events += 1
        lag = next((offset for offset in range(11) if signals[index + offset]["bias"] == side), None)
        if lag is not None:
            delays.append(lag)
    return {"reference": "alternating_20_bar_close_breakout", "events": events,
            "recognized_within_10": len(delays), "missed_within_10": events - len(delays),
            "median_delay_bars": median(delays) if delays else None}


def evaluate_compass(data: dict[str, list[Candle]], metadata: dict, errors: dict, before: date) -> dict:
    dates = sorted({c.datetime.date().isoformat() for candles in data.values() for c in candles[WARMUP:-max(HORIZONS)]})
    if len(dates) < 100:
        raise ValueError("Not enough eligible dates for a chronological research split")
    cutoff = dates[int(len(dates) * 0.70)]
    assets = {}
    for symbol, candles in data.items():
        signals = calculate_compass_series(candles)
        print(f"Compass evaluation: {symbol} ({len(candles)} bars)", flush=True)
        evaluations = {}
        for model in MODELS:
            report = {}
            for horizon in HORIZONS:
                groups = build_trials(candles, signals[model], horizon, cutoff)
                report[str(horizon)] = {split: {side: summarize_side(rows, side) for side in ("LONG", "SHORT")} for split, rows in groups.items()}
            primary = report[str(PRIMARY_HORIZON)]["holdout"]
            evaluations[model] = {"horizons": report, "evidence": {side: evidence_status(primary[side]) for side in primary},
                                  "reaction_delay": reaction_delay(candles, signals[model], cutoff),
                                  "stability": stability([s for s in signals[model] if s["date"] >= cutoff])}
        latest = dict(signals[PRIMARY_MODEL][-1])
        age = (before - candles[-1].datetime.date()).days
        latest["data_age_days"] = age
        latest["raw_bias"] = latest["bias"]
        if age > 5:
            latest.update(bias="WAIT", reason="Dữ liệu cũ hơn 5 ngày; không dùng để chọn hướng hiện tại")
        latest["historical_evidence"] = evaluations[PRIMARY_MODEL]["evidence"].get(latest["raw_bias"], "no_direction")
        assets[symbol] = {"metadata": metadata[symbol], "latest": latest, "models": evaluations,
                          "history": [{"date": c.datetime.date().isoformat(), "close": c.close,
                                       **{model: signals[model][i] for model in MODELS}} for i, c in enumerate(candles)]}
    return {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "timeframe": "D1",
        "before": before.isoformat(), "holdout_start": cutoff, "primary_model": PRIMARY_MODEL,
        "primary_horizon": PRIMARY_HORIZON, "horizons": list(HORIZONS),
        "mode": "research_only", "applies_to_scanner": False, "assets": assets,
        "errors": errors, "metadata": metadata,
        "limitations": [
            "Kết quả chọn hướng, chưa phải lợi nhuận của setup sau phí/stop/target.",
            "Tín hiệu đóng nến T, đo từ open T+1 đến close T+h; chỉ dùng D1 đã hoàn tất.",
            "CI bootstrap theo block 40 nến; nhiều phép so sánh, không phải bảo đảm xác suất đúng.",
            "Giữ nguyên công thức sau khi mở holdout; promising là bằng chứng sơ bộ, chưa phải quyền giao dịch.",
            "Lịch phiên khác nhau giữa tài sản; proxy/spot/futures không được coi là cùng một sản phẩm.",
        ],
    }


def run_compass_research(
    out_dir: str | Path, period: str = "10y", config_path: str | Path | None = None,
    before: str | None = None, cache_path: str | Path | None = None, rrg_results: str | Path | None = None,
) -> Path:
    if config_path and cache_path:
        raise ValueError("Choose --config or --cache, not both")
    cutoff_date = date.fromisoformat(before) if before else datetime.now(timezone.utc).date()
    if cutoff_date > datetime.now(timezone.utc).date():
        raise ValueError("--before cannot be a future date")
    output_dir = Path(out_dir)
    data, metadata, errors = load_research_data(output_dir, period, config_path, cutoff_date, cache_path)
    if not data:
        raise ValueError(f"No usable D1 history. See {output_dir / 'candles.json'} for provider errors")
    payload = evaluate_compass(data, metadata, errors, cutoff_date)
    payload["implementation_sha256"] = {
        name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ("compass.py", "compass_research.py")
    }
    payload["runtime"] = {"python": sys.version.split()[0]}
    for package in ("yfinance", "pandas", "numpy"):
        try:
            payload["runtime"][package] = version(package)
        except PackageNotFoundError:
            pass
    if rrg_results:
        rrg_path = Path(rrg_results).resolve()
        rrg_payload = json.loads(rrg_path.read_text(encoding="utf-8"))
        payload["rrg_comparison"] = {"source": str(rrg_path), "generated_at": rrg_payload.get("generated_at"),
                                     "data_as_of": rrg_payload.get("data_as_of"),
                                     "reference": rrg_payload.get("rrg_reference", {}), "historical_ab_test": False}
    protocol_path = Path(__file__).resolve().parent.parent / "docs" / "market-compass-research.md"
    if protocol_path.exists():
        protocol = protocol_path.read_text(encoding="utf-8")
        (output_dir / "protocol.md").write_text(protocol, encoding="utf-8")
        payload["protocol_sha256"] = hashlib.sha256(protocol.encode()).hexdigest()
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    from .compass_report import write_compass_report

    write_compass_report(payload, output_dir / "index.html")
    return results_path
