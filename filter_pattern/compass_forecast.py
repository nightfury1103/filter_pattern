"""Setup-independent, fixed-protocol D1 forecast experiment. Never a live gate.

Features use close T; labels use open T+1 through close T+h. Fit and probability
calibration use distinct calendar periods with purged boundary-crossing labels.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
from collections import Counter
from datetime import date, datetime, timezone
from importlib.metadata import version
from pathlib import Path
from statistics import fmean, stdev

from .compass import WARMUP, _atr, _ema, calculate_compass_series, efficiency_ratio, validate_candles
from .compass_research import load_research_data, outcome
from .models import Candle

FEATURE_NAMES = (
    "return_1_atr", "return_5_atr", "return_20_atr", "return_60_atr",
    "distance_ema20_atr", "trend_20_50_atr", "trend_change_5", "efficiency_20",
    "volatility_10_60", "range_position_20", "range_position_60",
    "distance_prior_high20_atr", "distance_prior_low20_atr", "body_atr", "close_location",
)
PROTOCOL = {
    "schema": 2, "timeframe": "D1", "primary_horizon": 10, "diagnostic_horizons": [5, 20],
    "data_quality": "exclude entire instrument if >14 calendar-day gap or >=20 consecutive unchanged zero-range bars",
    "quality_revision": "First run exposed an 812-day VN30_ETF gap. Original run invalidated and archived; models, thresholds, and time splits unchanged.",
    "calibration_start": "2022-01-01", "test_start": "2024-01-01",
    "threshold": .75, "primary_model": "boosted", "reference_model": "logistic",
    "label": "close(T+h) / open(T+1) - 1; Long > 0; Short < 0; exact flat is incorrect for both",
    "fit_flat_labels": "omit exact-zero 10-bar outcomes from fit and calibration only",
    "features": list(FEATURE_NAMES), "setup_dependency": False,
    "logistic": {"C": .1, "max_iter": 2000},
    "boosted": {"max_iter": 100, "max_depth": 2, "max_leaf_nodes": 4,
                "learning_rate": .05, "min_samples_leaf": 50, "l2_regularization": 10.,
                "early_stopping": False, "random_state": 17},
    "sigmoid_calibrator": {"C": 1., "max_iter": 2000},
    "weights": "equal total weight per instrument within each fitting period; no class rebalancing",
    "duplicate_exclusion": "SPY excluded from fitting and pooled scores when US500 is available; shown separately",
    "bootstrap": "500 moving-block resamples of 60 union calendar dates; same date draws across instruments",
    "evidence_gate": "coverage >= 10%, >= 100 fixed-schedule non-overlapping signals, 95% block CI lower >= 75%; no live promotion",
    "reuse_disclosure": "2024+ prices overlap a previously inspected experiment. Retrospective temporal validation, not a fresh untouched holdout.",
    "model_selection": "two predeclared models, fixed 0.75 threshold; no search on test results",
}


def audit_continuity(candles: list[Candle]) -> dict:
    """Conservative research eligibility; never bridge missing years as adjacent D1."""
    gaps = [{"from": a.datetime.date().isoformat(), "to": b.datetime.date().isoformat(),
             "calendar_days": (b.datetime.date() - a.datetime.date()).days}
            for a, b in zip(candles, candles[1:]) if (b.datetime.date() - a.datetime.date()).days > 14]
    longest = streak = 0
    previous_flat = None
    for c in candles:
        flat = c.open == c.high == c.low == c.close
        streak = (streak + 1 if previous_flat == c.close else 1) if flat else 0
        previous_flat = c.close if flat else None
        longest = max(longest, streak)
    return {"eligible": not gaps and longest < 20, "gaps_over_14_days": gaps,
            "longest_unchanged_zero_range_run": longest}


def feature_rows(candles: list[Candle]) -> list[dict]:
    """Scale-free features, all calculated from data available at close T."""
    validate_candles(candles)
    prices = [c.close for c in candles]
    ema20, ema50, atr = _ema(prices, 20), _ema(prices, 50), _atr(candles)
    returns = [0.] + [math.log(b / a) for a, b in zip(prices, prices[1:])]
    trends = [(a - b) / v if v else 0. for a, b, v in zip(ema20, ema50, atr)]
    rows = []
    for i in range(WARMUP, len(candles)):
        c, scale = candles[i], max(float(atr[i] or 0.), prices[i] * 1e-8)
        position = []
        for h in (20, 60):
            lo = min(x.low for x in candles[i - h + 1:i + 1])
            hi = max(x.high for x in candles[i - h + 1:i + 1])
            position.append((c.close - lo) / (hi - lo) if hi > lo else .5)
        features = [(c.close - prices[i - h]) / (scale * math.sqrt(h)) for h in (1, 5, 20, 60)]
        features += [(c.close - ema20[i]) / scale, trends[i], trends[i] - trends[i - 5],
                     efficiency_ratio(prices[i - 20:i + 1]),
                     stdev(returns[i - 9:i + 1]) / max(stdev(returns[i - 59:i + 1]), 1e-8),
                     *position,
                     (max(x.high for x in candles[i - 20:i]) - c.close) / scale,
                     (c.close - min(x.low for x in candles[i - 20:i])) / scale,
                     (c.close - c.open) / scale,
                     (c.close - c.low) / (c.high - c.low) if c.high > c.low else .5]
        rows.append({"index": i, "date": c.datetime.date().isoformat(), "features": features,
                     "close": c.close, "extension_atr": features[4]})
    return rows


def label_rows(candles: list[Candle], rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        outcomes = {str(h): outcome(candles, row["index"], h) for h in (5, 10, 20)
                    if row["index"] + h < len(candles)}
        result.append({**row, "outcomes": outcomes})
    return result


def split_rows(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {"train": [], "calibration": [], "test": []}
    for row in rows:
        label = row["outcomes"].get("10")
        if not label:
            continue
        day = row["date"]
        if day < PROTOCOL["calibration_start"]:
            if label["exit_date"] < PROTOCOL["calibration_start"]:
                groups["train"].append(row)
        elif day < PROTOCOL["test_start"]:
            if label["exit_date"] < PROTOCOL["test_start"]:
                groups["calibration"].append(row)
        else:
            groups["test"].append(row)
    return groups


def bias_from_probability(p_up: float, threshold: float = .75) -> str:
    if not math.isfinite(p_up) or not 0 <= p_up <= 1 or not .5 < threshold <= 1:
        raise ValueError("Invalid probability or confidence threshold")
    return "LONG" if p_up >= threshold else "SHORT" if p_up <= 1 - threshold else "WAIT"


def _fit_weights(rows: list[dict]) -> list[float]:
    counts = Counter(row["symbol"] for row in rows)
    return [len(rows) / (len(counts) * counts[row["symbol"]]) for row in rows]


def fit_models(groups: dict[str, list[dict]]) -> tuple[dict, dict]:
    """Neither model nor scaler nor calibrator receives any test rows."""
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    train = [r for r in groups["train"] if r["outcomes"]["10"]["return_pct"] != 0]
    calibration = [r for r in groups["calibration"] if r["outcomes"]["10"]["return_pct"] != 0]
    for name, rows in (("train", train), ("calibration", calibration)):
        if len(rows) < 200 or len({r["outcomes"]["10"]["return_pct"] > 0 for r in rows}) < 2:
            raise ValueError(f"Insufficient {name} data: need >=200 observations and both directions")
    x = np.array([r["features"] for r in train])
    y = np.array([r["outcomes"]["10"]["return_pct"] > 0 for r in train], dtype=int)
    cx = np.array([r["features"] for r in calibration])
    cy = np.array([r["outcomes"]["10"]["return_pct"] > 0 for r in calibration], dtype=int)
    weights, cweights = _fit_weights(train), _fit_weights(calibration)
    models = {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(**PROTOCOL["logistic"])),
        "boosted": HistGradientBoostingClassifier(**PROTOCOL["boosted"]),
    }
    fitted = {}
    for name, model in models.items():
        print(f"Fit {name}: {len(train)} training / {len(calibration)} calibration days", flush=True)
        kwargs = {"logisticregression__sample_weight": weights, "standardscaler__sample_weight": weights} if name == "logistic" else {"sample_weight": weights}
        model.fit(x, y, **kwargs)
        calibrator = LogisticRegression(**PROTOCOL["sigmoid_calibrator"])
        calibrator.fit(model.decision_function(cx).reshape(-1, 1), cy, sample_weight=cweights)
        fitted[name] = (model, calibrator)
    manifest = {name: {"rows": len(rows), "first": min(r["date"] for r in rows),
                       "last": max(r["date"] for r in rows), "symbols": dict(Counter(r["symbol"] for r in rows))}
                for name, rows in (("train", train), ("calibration", calibration))}
    return fitted, manifest


def predict_rows(models: dict, rows: list[dict]) -> list[dict]:
    import numpy as np
    if not rows:
        return []
    x = np.array([r["features"] for r in rows])
    probabilities = {name: calibrator.predict_proba(model.decision_function(x).reshape(-1, 1))[:, 1]
                     for name, (model, calibrator) in models.items()}
    return [{**{k: v for k, v in row.items() if k != "features"},
             "forecasts": {name: {"p_up": float(p[i]), "bias": bias_from_probability(float(p[i]), PROTOCOL["threshold"])}
                           for name, p in probabilities.items()}}
            for i, row in enumerate(rows)]


def _selected(rows: list[dict], model: str, side: str, horizon: int) -> tuple[list[dict], list[dict]]:
    eligible = [r for r in rows if str(horizon) in r["outcomes"]]
    chosen = [r for r in eligible if r["forecasts"][model]["bias"] in (("LONG", "SHORT") if side == "ALL" else (side,))]
    return eligible, chosen


def _correct(row: dict, model: str, horizon: int) -> bool:
    sign = 1 if row["forecasts"][model]["bias"] == "LONG" else -1
    return row["outcomes"][str(horizon)]["return_pct"] * sign > 0


def block_interval(rows: list[dict], model: str, side: str, horizon: int) -> list[float] | None:
    """Resample contiguous dates together across instruments, including WAIT days."""
    import numpy as np
    eligible, chosen = _selected(rows, model, side, horizon)
    if len(chosen) < 30:
        return None
    correct = sum(_correct(r, model, horizon) for r in chosen)
    if correct in (0, len(chosen)):
        # Resampling cannot infer unseen failures/successes. A degenerate [1,1]
        # (or [0,0]) interval would communicate certainty unsupported by data.
        return None
    days = sorted({r["date"] for r in eligible})
    if len(days) < 120:
        return None  # Less than two 60-date blocks cannot support this uncertainty estimate.
    positions = {day: i for i, day in enumerate(days)}
    totals, wins = np.zeros(len(days)), np.zeros(len(days))
    for r in chosen:
        p = positions[r["date"]]
        totals[p] += 1
        wins[p] += _correct(r, model, horizon)
    rng = np.random.default_rng(1709)
    scores = []
    for _ in range(500):
        starts = rng.integers(0, len(days) - 60 + 1, size=math.ceil(len(days) / 60))
        indices = np.concatenate([np.arange(s, s + 60) for s in starts])[:len(days)]
        total = totals[indices].sum()
        if total:
            scores.append(float(wins[indices].sum() / total))
    # Very sparse signals produce too many empty resamples to claim a usable interval.
    return [float(v) for v in np.quantile(scores, [.025, .975])] if len(scores) >= 450 else None


def summarize(rows: list[dict], model: str, side: str = "ALL", horizon: int = 10) -> dict:
    eligible, chosen = _selected(rows, model, side, horizon)
    wins = sum(_correct(r, model, horizon) for r in chosen)
    scheduled = [r for r in chosen if (r["index"] - WARMUP) % horizon == 0]
    ci = block_interval(rows, model, side, horizon)
    coverage = len(chosen) / len(eligible) if eligible else 0.
    adequate = coverage >= .1 and len(scheduled) >= 100 and ci is not None and ci[0] >= .75
    # Same-side unconditional baseline weighted by the model's actual Long/Short mix.
    baseline = None
    if eligible and chosen:
        up_rate = fmean(r["outcomes"][str(horizon)]["return_pct"] > 0 for r in eligible)
        down_rate = fmean(r["outcomes"][str(horizon)]["return_pct"] < 0 for r in eligible)
        long_weight = sum(r["forecasts"][model]["bias"] == "LONG" for r in chosen) / len(chosen)
        baseline = long_weight * up_rate + (1 - long_weight) * down_rate
    return {"eligible": len(eligible), "signals": len(chosen), "wins": wins, "false_signals": len(chosen) - wins,
            "accuracy": wins / len(chosen) if chosen else None, "coverage": coverage,
            "block_ci95": ci, "scheduled_signals": len(scheduled),
            "scheduled_accuracy": fmean(_correct(r, model, horizon) for r in scheduled) if scheduled else None,
            "side_mix_baseline": baseline, "evidence": "retrospective_candidate" if adequate else "not_demonstrated",
            "mean_abs_extension_at_signal": fmean(abs(r["extension_atr"]) for r in chosen) if chosen else None,
            "extended_over_2atr_fraction": fmean(abs(r["extension_atr"]) > 2 for r in chosen) if chosen else None}


def probability_diagnostics(rows: list[dict], model: str) -> dict:
    eligible = [r for r in rows if "10" in r["outcomes"]]
    if not eligible:
        return {"brier": None, "bins": []}
    bins = []
    for lo, hi in ((0, .25), (.25, .4), (.4, .5), (.5, .6), (.6, .75), (.75, 1.000001)):
        group = [r for r in eligible if lo <= r["forecasts"][model]["p_up"] < hi]
        bins.append({"range": [lo, min(hi, 1.)], "count": len(group),
                     "mean_p_up": fmean(r["forecasts"][model]["p_up"] for r in group) if group else None,
                     "actual_up": fmean(r["outcomes"]["10"]["return_pct"] > 0 for r in group) if group else None})
    return {"brier": fmean((r["forecasts"][model]["p_up"] - (r["outcomes"]["10"]["return_pct"] > 0)) ** 2 for r in eligible),
            "bins": bins}


def stability_summary(rows: list[dict], model: str) -> dict:
    states = [r["forecasts"][model]["bias"] for r in rows]
    switches = sum(a != b for a, b in zip(states, states[1:]))
    fast_reversals = sum(s != "WAIT" and any(t != "WAIT" and t != s for t in states[i + 1:i + 6])
                         for i, s in enumerate(states))
    return {"days": len(states), "state_switches": switches, "opposite_within_5_bars": fast_reversals}


def run_forecast_research(out: str | Path, cache: str | Path, before: str | None = None) -> Path:
    try:
        from threadpoolctl import threadpool_limits
        import joblib
        import sklearn  # noqa: F401 -- fail with actionable optional-dependency message
    except ImportError as exc:
        raise ValueError("Install forecast research dependencies: pip install '.[research]'") from exc

    output = Path(out)
    cutoff = date.fromisoformat(before) if before else datetime.now(timezone.utc).date()
    data, metadata, errors = load_research_data(output, cache_path=cache, before=cutoff)
    audits = {s: audit_continuity(c) for s, c in data.items()}
    for s, audit in audits.items():
        if not audit["eligible"]:
            errors[s] = f"Continuity audit failed: {json.dumps(audit)}; excluded entirely, no repair or gap bridging"
            del data[s]
    if not data:
        raise ValueError("No valid completed D1 data")
    # Written before model fitting/results, so the report records this exact experiment.
    protocol_text = json.dumps(PROTOCOL, ensure_ascii=False, sort_keys=True, indent=2)
    (output / "protocol.json").write_text(protocol_text, encoding="utf-8")
    rows_by_symbol = {s: [{**r, "symbol": s} for r in label_rows(c, feature_rows(c))] for s, c in data.items()}
    excluded = ["SPY"] if "US500" in data and "SPY" in data else []
    groups = split_rows([r for s, rows in rows_by_symbol.items() if s not in excluded for r in rows])
    with threadpool_limits(limits=2):
        models, fit_manifest = fit_models(groups)
        predictions = {s: predict_rows(models, [r for r in rows if r["date"] >= PROTOCOL["test_start"]])
                       for s, rows in rows_by_symbol.items()}
    # Persist local models for reproducibility only; scanner never loads them.
    joblib.dump(models, output / "research-models.joblib")
    for s, rows in predictions.items():
        old = calculate_compass_series(data[s])
        for row in rows:
            for name in ("ema", "ema_atr", "multi_horizon"):
                row["forecasts"][name] = {"bias": old[name][row["index"]]["bias"]}
            row["forecasts"]["always_long"] = {"bias": "LONG"}
    names = ("boosted", "logistic", "ema", "ema_atr", "multi_horizon", "always_long")
    summaries = {}
    all_rows = [r for s, rows in predictions.items() if s not in excluded for r in rows]
    for s, rows in {**predictions, "POOLED": all_rows}.items():
        summaries[s] = {m: {str(h): {side: summarize(rows, m, side, h) for side in ("ALL", "LONG", "SHORT")}
                             for h in (5, 10, 20)} for m in names}
    latest = {}
    for s, rows in predictions.items():
        if not rows:
            continue
        r = rows[-1]
        age = (cutoff - date.fromisoformat(r["date"])).days
        latest[s] = {"date": r["date"], "age_days": age, "experimental_forecasts": r["forecasts"],
                     "display_state": "STALE" if age > 5 else "RESEARCH_ONLY",
                     "validated_direction": "WAIT", "reason": "Retrospective research only; no prospective validation"}
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "protocol": PROTOCOL,
        "protocol_sha256": hashlib.sha256(protocol_text.encode()).hexdigest(),
        "implementation_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                  (Path(__file__), Path(__file__).with_name("compass.py"), Path(__file__).with_name("compass_research.py"))},
        "versions": {"python": platform.python_version(), **{p: version(p) for p in ("numpy", "scikit-learn", "scipy")}},
        "metadata": metadata, "errors": errors, "data_quality_audit": audits, "excluded_from_fit_and_pool": excluded,
        "fit_manifest": fit_manifest, "summaries": summaries, "latest": latest,
        "probability_diagnostics": {s: {m: probability_diagnostics(rows, m) for m in models}
                                    for s, rows in {**predictions, "POOLED": all_rows}.items()},
        "stability": {s: {m: stability_summary(rows, m) for m in names} for s, rows in predictions.items()},
        "history": predictions,
    }
    target = output / "results.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    from .compass_forecast_report import write_forecast_report
    write_forecast_report(payload, output / "index.html")
    return target
