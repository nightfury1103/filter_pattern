"""Predeclared cross-market context experiment with purged yearly walk-forward."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from importlib.metadata import version
from pathlib import Path
from statistics import fmean

from .compass import calculate_compass_series
from .compass_context_data import CONTEXT_FEATURES, attach_context, audit_context, build_context, fetch_context, validate_source
from .compass_forecast import (
    FEATURE_NAMES, PROTOCOL as V2_PROTOCOL, bias_from_probability, feature_rows,
    label_rows, probability_diagnostics, stability_summary, summarize,
)
from .compass_research import load_research_data

TARGETS = ("US500", "BTCUSD", "ETHUSD", "GOLD_FUTURES", "DXY")
MODEL_NAMES = ("context", "price_only", "confirmation", "ema", "always_long")
PROTOCOL = {
    "version": 3, "timeframe": "D1", "targets": TARGETS, "primary_horizon": 10,
    "diagnostic_horizons": [5, 20], "years": [2022, 2023, 2024, 2025, 2026],
    "primary_evaluation_start": "2024-01-01", "threshold": .75,
    "fit": "Separate model per target/year. Train before previous calendar year; calibrate previous year; test current year. Purge crossing 10-bar labels.",
    "matched_ablation": "price_only and context fit and calibrate on identical eligible rows",
    "features_price": FEATURE_NAMES, "features_context": CONTEXT_FEATURES,
    "model": V2_PROTOCOL["boosted"], "calibrator": V2_PROTOCOL["sigmoid_calibrator"],
    "context_timing": "Strictly earlier source date, max 5 calendar days old. Same-date cross-market data prohibited.",
    "source_quality": "Positive finite consistent OHLC; >=260 bars; no >14-day gap or >=20 unchanged zero-range bars. Entire source rejected.",
    "rule": "Own 5-bar momentum same direction and abs(EMA20 distance)<=2 ATR; equity/crypto breadth>=2/3+credit5>0+VIXterm<1 for Long, opposite breadth<=1/3+credit5<0+term>1 for Short; gold USD20<0+TLT20>0 Long, inverse Short; dollar TLT20<0+credit5<0 Long, inverse Short. Rule assigns no probability.",
    "evidence_gate": V2_PROTOCOL["evidence_gate"],
    "test_reuse": "Retrospective research; target history previously inspected. New context sources and walk-forward do not constitute fresh untouched validation.",
    "no_optimization": "Three predeclared candidates; no threshold/hyperparameter search on outcomes",
}


def fold_split(rows: list[dict], year: int) -> dict[str, list[dict]]:
    cal_start, test_start, test_end = f"{year-1}-01-01", f"{year}-01-01", f"{year+1}-01-01"
    groups: dict[str, list[dict]] = {"train": [], "calibration": [], "test": []}
    for row in rows:
        if test_start <= row["date"] < test_end:
            groups["test"].append(row)  # Includes pending outcomes and missing context.
            continue
        label = row["outcomes"].get("10")
        if row.get("context") is None or not label or label["return_pct"] == 0:
            continue
        if row["date"] < cal_start and label["exit_date"] < cal_start:
            groups["train"].append(row)
        elif cal_start <= row["date"] < test_start and label["exit_date"] < test_start:
            groups["calibration"].append(row)
    return groups


def confirmation_rule(row: dict, symbol: str) -> str:
    c = row.get("context")
    if c is None or abs(row["extension_atr"]) > 2:
        return "WAIT"
    momentum = row["features"][1]
    if symbol in ("US500", "BTCUSD", "ETHUSD"):
        up = c["sector_above_ema50"] >= 2/3 and c["credit_minus_treasury5"] > 0 and c["vix_term_ratio"] < 1
        down = c["sector_above_ema50"] <= 1/3 and c["credit_minus_treasury5"] < 0 and c["vix_term_ratio"] > 1
    elif symbol == "GOLD_FUTURES":
        up = c["dollar_z20"] < 0 and c["treasury_z20"] > 0
        down = c["dollar_z20"] > 0 and c["treasury_z20"] < 0
    elif symbol == "DXY":
        up = c["treasury_z20"] < 0 and c["credit_minus_treasury5"] < 0
        down = c["treasury_z20"] > 0 and c["credit_minus_treasury5"] > 0
    else:
        return "WAIT"
    return "LONG" if up and momentum > 0 else "SHORT" if down and momentum < 0 else "WAIT"


def _x(rows: list[dict], context: bool):
    import numpy as np
    return np.array([r["features"] + ([r["context"][f] for f in CONTEXT_FEATURES] if context else []) for r in rows])


def fit_fold(groups: dict) -> tuple[dict, dict]:
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    manifest = {}
    for split in ("train", "calibration"):
        rows = groups[split]
        labels = [int(r["outcomes"]["10"]["return_pct"] > 0) for r in rows]
        manifest[split] = {"rows": len(rows), "up": sum(labels),
                           "first": min((r["date"] for r in rows), default=None),
                           "last": max((r["date"] for r in rows), default=None),
                           "last_label_exit": max((r["outcomes"]["10"]["exit_date"] for r in rows), default=None)}
        if len(rows) < 200 or len(set(labels)) < 2:
            return {}, {**manifest, "status": f"insufficient_{split}"}
    y = np.array([r["outcomes"]["10"]["return_pct"] > 0 for r in groups["train"]], dtype=int)
    cy = np.array([r["outcomes"]["10"]["return_pct"] > 0 for r in groups["calibration"]], dtype=int)
    fitted = {}
    for name in ("price_only", "context"):
        external = name == "context"
        model = HistGradientBoostingClassifier(**PROTOCOL["model"])
        model.fit(_x(groups["train"], external), y)
        calibrator = LogisticRegression(**PROTOCOL["calibrator"])
        calibrator.fit(model.decision_function(_x(groups["calibration"], external)).reshape(-1, 1), cy)
        fitted[name] = (model, calibrator)
        manifest[name] = {"calibration_slope": float(calibrator.coef_[0, 0]), "calibration_intercept": float(calibrator.intercept_[0])}
    return fitted, {**manifest, "status": "fitted"}


def predict_fold(rows: list[dict], models: dict, symbol: str) -> list[dict]:
    valid = [r for r in rows if r.get("context") is not None]
    probs = {}
    for name, (model, calibrator) in models.items():
        if valid:
            values = calibrator.predict_proba(model.decision_function(_x(valid, name == "context")).reshape(-1, 1))[:, 1]
            probs[name] = {r["date"]: float(p) for r, p in zip(valid, values)}
    result = []
    for row in rows:
        forecasts = {}
        for name in ("price_only", "context"):
            p = probs.get(name, {}).get(row["date"])
            forecasts[name] = {"p_up": p, "bias": bias_from_probability(p) if p is not None else "WAIT",
                               "reason": "forecast" if p is not None else "missing_context_or_insufficient_fit"}
        forecasts["confirmation"] = {"bias": confirmation_rule(row, symbol)}
        result.append({**{k: v for k, v in row.items() if k != "features"}, "forecasts": forecasts})
    return result


def quick_metrics(rows: list[dict], model: str, horizon: int = 10) -> dict:
    eligible = [r for r in rows if str(horizon) in r["outcomes"]]
    signals = [r for r in eligible if r["forecasts"][model]["bias"] != "WAIT"]
    wins = sum(r["outcomes"][str(horizon)]["return_pct"] * (1 if r["forecasts"][model]["bias"] == "LONG" else -1) > 0 for r in signals)
    return {"eligible": len(eligible), "signals": len(signals), "wins": wins,
            "accuracy": wins/len(signals) if signals else None, "coverage": len(signals)/len(eligible) if eligible else 0.}


def _diagnostics(rows: list[dict], model: str) -> dict:
    available = [r for r in rows if r["forecasts"][model].get("p_up") is not None]
    result = probability_diagnostics(available, model)
    p = [r["forecasts"][model]["p_up"] for r in available if "10" in r["outcomes"]]
    return {**result, "probability_range": [min(p), max(p)] if p else None, "predicted_rows": len(p)}


def run_context_research(out: str | Path, cache: str | Path, context_cache: str | Path | None = None,
                         before: str | None = None) -> Path:
    try:
        from threadpoolctl import threadpool_limits
        import joblib
        import sklearn  # noqa: F401
    except ImportError as exc:
        raise ValueError("Install research dependencies: pip install '.[research]'") from exc
    output = Path(out)
    output.mkdir(parents=True, exist_ok=True)
    cutoff = date.fromisoformat(before) if before else datetime.now(timezone.utc).date()
    protocol_text = json.dumps(PROTOCOL, ensure_ascii=False, sort_keys=True, indent=2)
    (output / "protocol.json").write_text(protocol_text, encoding="utf-8")
    data, metadata, errors = load_research_data(output, cache_path=cache, before=cutoff)
    audits = {}
    for s in list(data):
        try:
            audits[s] = validate_source(data[s])
        except ValueError as exc:
            errors[s] = str(exc)
            del data[s]
    bundle = fetch_context(output, cutoff, context_cache)
    sources, source_meta, source_errors = audit_context(bundle, cutoff)
    if "DXY" in data:
        sources["DXY"] = data["DXY"]
        source_meta["DXY"] = {"provider": "target_cache", **metadata["DXY"]}
    audit_path = output / "data-audit.json"
    audit_path.write_text(json.dumps({"targets": audits, "target_errors": errors, "context": source_meta,
                                      "context_errors": source_errors}, ensure_ascii=False, indent=2), encoding="utf-8")
    context = build_context(sources)  # Clear failure if any required source is invalid/missing.
    history, manifests, artifacts = {}, {}, {}
    for s in TARGETS:
        if s not in data:
            errors.setdefault(s, "Missing validated target data")
            continue
        rows = attach_context([{**r, "symbol": s} for r in label_rows(data[s], feature_rows(data[s]))], context)
        old = calculate_compass_series(data[s])
        predicted, manifests[s] = [], {}
        for year in PROTOCOL["years"]:
            groups = fold_split(rows, year)
            if not groups["test"]:
                continue
            print(f"Walk-forward {s} / {year}: train={len(groups['train'])}, calibration={len(groups['calibration'])}", flush=True)
            with threadpool_limits(limits=2):
                models, manifest = fit_fold(groups)
                predicted.extend(predict_fold(groups["test"], models, s))
            manifests[s][str(year)] = manifest
            artifacts[f"{s}/{year}"] = models
        for row in predicted:
            row["forecasts"]["ema"] = {"bias": old["ema"][row["index"]]["bias"]}
            row["forecasts"]["always_long"] = {"bias": "LONG"}
        history[s] = predicted
    if not history:
        raise ValueError("No targets with walk-forward test history")
    joblib.dump(artifacts, output / "research-models.joblib")
    primary = {s: [r for r in rows if r["date"] >= PROTOCOL["primary_evaluation_start"]] for s, rows in history.items()}
    primary["POOLED"] = [r for rows in primary.values() for r in rows]
    summaries, diagnostics = {}, {}
    for s, rows in primary.items():
        print(f"Evaluate {s}", flush=True)
        summaries[s] = {m: {"10": {side: summarize(rows, m, side, 10) for side in ("ALL", "LONG", "SHORT")},
                            **{str(h): {"ALL": summarize(rows, m, "ALL", h)} for h in (5, 20)}} for m in MODEL_NAMES}
        diagnostics[s] = {m: _diagnostics(rows, m) for m in ("context", "price_only")}
    latest = {s: {"date": rows[-1]["date"], "context_date": rows[-1]["context_date"],
                  "data_age_days": (cutoff-date.fromisoformat(rows[-1]["date"])).days,
                  "experimental_forecasts": rows[-1]["forecasts"], "validated_direction": "WAIT"}
              for s, rows in history.items() if rows}
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "protocol": PROTOCOL,
        "protocol_sha256": hashlib.sha256(protocol_text.encode()).hexdigest(), "metadata": metadata,
        "target_errors": errors, "context_errors": source_errors, "source_metadata": source_meta,
        "context_retrieved_at": bundle["retrieved_at"], "target_audits": audits,
        "versions": {p: version(p) for p in ("numpy", "scikit-learn", "scipy")},
        "implementation_sha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                  for name in ("compass_context.py", "compass_context_data.py", "compass_forecast.py", "compass.py", "compass_research.py")},
        "folds": manifests, "summaries": summaries, "probability_diagnostics": diagnostics,
        "yearly": {s: {str(y): {m: quick_metrics([r for r in rows if r["date"].startswith(str(y))], m)
                                 for m in MODEL_NAMES} for y in PROTOCOL["years"]} for s, rows in history.items()},
        "stability": {s: {m: stability_summary(rows, m) for m in MODEL_NAMES} for s, rows in primary.items() if s != "POOLED"},
        "missing_context_days": {s: sum(r["context"] is None for r in rows) for s, rows in primary.items()},
        "latest": latest, "history": history,
    }
    target = output / "results.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    (output / "latest-research-snapshot.json").write_text(json.dumps({"generated_at": payload["generated_at"],
        "protocol_sha256": payload["protocol_sha256"], "latest": latest,
        "status": "Research snapshot generated after historical bars; not a time-verified prospective signal or evidence of 75% accuracy"},
        ensure_ascii=False, indent=2), encoding="utf-8")
    from .compass_context_report import write_context_report
    write_context_report(payload, output / "index.html")
    return target
