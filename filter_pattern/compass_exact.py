"""Bounded per-symbol model selection for the user's exact screenshot roster."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from .compass import calculate_compass_series
from .compass_context import _diagnostics, _x, quick_metrics
from .compass_context_data import attach_context, audit_context, build_context, validate_source
from .compass_forecast import bias_from_probability, feature_rows, label_rows, summarize
from .compass_research import load_research_data

GROUPS = (("Commodity", ("XAUUSD",)), ("Crypto", ("BTCUSD", "ETHUSD")),
          ("Forex", ("DXY",)), ("Index", ("US500",)), ("US stock", ("SPY",)),
          ("Vietnam stock", ("E1VFVN30",)))
SYMBOLS = tuple(s for _, members in GROUPS for s in members)
PROTOCOL = {"version": "exact-symbols-1", "symbols": SYMBOLS, "years": [2024, 2025, 2026],
    "horizon": 10, "threshold": .75, "candidates": ["logistic", "tree2", "tree3"],
    "selection": "inner train before Y-2; choose minimum uncalibrated Brier on year Y-2; refit before Y-1; sigmoid calibrate year Y-1; test year Y",
    "label": "close(T+h)/open(T+1)-1; h=10 primary, 5/20 diagnostic; zero incorrect for both directions",
    "purge": "all training/selection/calibration labels must exit before next stage starts",
    "context": "strictly earlier date, <=5 calendar days old; US context is a hypothesis for other markets",
    "reuse": "Retrospective research; portions of test target history previously inspected. No prospective validation claim.",
    "evidence": "coverage>=10%, >=100 fixed-schedule non-overlapping signals, block CI95 lower>=75%; no live promotion",
    "model_parameters": {"logistic_C": .1, "tree_iterations": 100, "tree_learning_rate": .05,
                         "tree_min_samples_leaf": 50, "tree_l2": 10, "sigmoid_C": 1.}}


def stages(rows: list[dict], year: int) -> dict[str, list[dict]]:
    validation, calibration, test, end = (f"{y}-01-01" for y in (year-2, year-1, year, year+1))
    groups = {key: [] for key in ("inner_train", "validation", "refit", "calibration", "test")}
    for r in rows:
        if test <= r["date"] < end:
            groups["test"].append(r)
            continue
        label = r["outcomes"].get("10")
        if r.get("context") is None or not label or label["return_pct"] == 0:
            continue
        if r["date"] < validation and label["exit_date"] < validation:
            groups["inner_train"].append(r)
        if validation <= r["date"] < calibration and label["exit_date"] < calibration:
            groups["validation"].append(r)
        if r["date"] < calibration and label["exit_date"] < calibration:
            groups["refit"].append(r)
        if calibration <= r["date"] < test and label["exit_date"] < test:
            groups["calibration"].append(r)
    return groups


def new_candidate(name: str):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    if name == "logistic":
        return make_pipeline(StandardScaler(), LogisticRegression(C=.1, max_iter=2000))
    if name not in ("tree2", "tree3"):
        raise ValueError("Unknown candidate")
    return HistGradientBoostingClassifier(max_depth=2 if name == "tree2" else 3, max_leaf_nodes=4 if name == "tree2" else 8,
        max_iter=100, learning_rate=.05, min_samples_leaf=50, l2_regularization=10., early_stopping=False, random_state=17)


def fit_selected(groups: dict) -> tuple[dict, dict]:
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    manifest = {k: {"rows": len(rows), "first": min((r["date"] for r in rows), default=None),
                    "last": max((r["date"] for r in rows), default=None),
                    "last_label_exit": max((r["outcomes"]["10"]["exit_date"] for r in rows), default=None)}
                for k, rows in groups.items() if k != "test"}
    labels = {k: np.array([r["outcomes"]["10"]["return_pct"] > 0 for r in rows], dtype=int)
              for k, rows in groups.items() if k != "test"}
    for k in labels:
        if len(labels[k]) < (200 if k in ("inner_train", "refit") else 120) or len(set(labels[k])) < 2:
            return {}, {**manifest, "status": "insufficient_"+k}
    models = {}
    for mode in ("price_only", "context"):
        external = mode == "context"
        x = {k: _x(groups[k], external) for k in labels}
        scores = {}
        for name in PROTOCOL["candidates"]:
            candidate = new_candidate(name)
            candidate.fit(x["inner_train"], labels["inner_train"])
            scores[name] = float(np.mean((candidate.predict_proba(x["validation"])[:, 1]-labels["validation"])**2))
        winner = min(PROTOCOL["candidates"], key=lambda n: scores[n])
        model = new_candidate(winner)
        model.fit(x["refit"], labels["refit"])
        calibrator = LogisticRegression(C=1., max_iter=2000)
        calibrator.fit(model.decision_function(x["calibration"]).reshape(-1, 1), labels["calibration"])
        models[mode] = model, calibrator
        manifest[mode] = {"selected": winner, "validation_brier": scores,
                          "calibration_slope": float(calibrator.coef_[0, 0])}
    return models, {**manifest, "status": "fitted"}


def predict(rows: list[dict], models: dict) -> list[dict]:
    valid = [r for r in rows if r.get("context") is not None]
    probabilities = {}
    for mode, (model, calibrator) in models.items():
        if valid:
            p = calibrator.predict_proba(model.decision_function(_x(valid, mode == "context")).reshape(-1, 1))[:, 1]
            probabilities[mode] = {r["date"]: float(value) for r, value in zip(valid, p)}
    result = []
    for row in rows:
        forecasts = {}
        for mode in ("price_only", "context"):
            p = probabilities.get(mode, {}).get(row["date"])
            forecasts[mode] = {"p_up": p, "bias": bias_from_probability(p) if p is not None else "WAIT"}
        result.append({**{k: v for k, v in row.items() if k != "features"}, "forecasts": forecasts})
    return result


def run_exact(out: str | Path, cache: str | Path, context_cache: str | Path, before: str | None = None) -> Path:
    from threadpoolctl import threadpool_limits
    import joblib
    from importlib.metadata import version
    output = Path(out)
    output.mkdir(parents=True, exist_ok=True)
    cutoff = date.fromisoformat(before) if before else datetime.now(timezone.utc).date()
    protocol_text = json.dumps(PROTOCOL, ensure_ascii=False, sort_keys=True, indent=2)
    (output/"protocol.json").write_text(protocol_text, encoding="utf-8")
    data, metadata, all_errors = load_research_data(output, cache_path=cache, before=cutoff)
    errors = {s: e for s, e in all_errors.items() if s in SYMBOLS}
    data = {s: c for s, c in data.items() if s in SYMBOLS}
    for s in list(data):
        try:
            metadata[s]["audit"] = validate_source(data[s])
        except ValueError as exc:
            errors[s] = str(exc)
            del data[s]
    for s in SYMBOLS:
        if s not in data:
            errors.setdefault(s, "Missing exact-instrument validated D1 history; no proxy substituted")
    bundle = json.loads(Path(context_cache).read_text(encoding="utf-8"))
    sources, source_metadata, source_errors = audit_context(bundle, cutoff)
    if "DXY" not in data:
        raise ValueError("Validated DXY required for context")
    sources["DXY"] = data["DXY"]
    context = build_context(sources)
    history, manifests, saved = {}, {}, {}
    for s in SYMBOLS:
        if s not in data:
            continue
        rows = attach_context([{**r, "symbol": s} for r in label_rows(data[s], feature_rows(data[s]))], context)
        old = calculate_compass_series(data[s])
        history[s], manifests[s] = [], {}
        for year in PROTOCOL["years"]:
            groups = stages(rows, year)
            if not groups["test"]:
                continue
            print(f"Select models {s}/{year}: train={len(groups['inner_train'])}, validation={len(groups['validation'])}", flush=True)
            with threadpool_limits(limits=2):
                models, manifests[s][str(year)] = fit_selected(groups)
                history[s].extend(predict(groups["test"], models))
            saved[f"{s}/{year}"] = models
        for r in history[s]:
            r["forecasts"]["ema"] = {"bias": old["ema"][r["index"]]["bias"]}
            r["forecasts"]["always_long"] = {"bias": "LONG"}
    joblib.dump(saved, output/"research-models.joblib")
    summaries = {}
    for s, rows in history.items():
        print(f"Evaluate {s}", flush=True)
        summaries[s] = {m: {str(h): {side: summarize(rows, m, side, h) for side in (("ALL", "LONG", "SHORT") if h==10 else ("ALL",))}
                            for h in (5, 10, 20)} for m in ("context", "price_only", "ema", "always_long")}
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "before": cutoff.isoformat(), "protocol": PROTOCOL,
        "protocol_sha256": hashlib.sha256(protocol_text.encode()).hexdigest(), "groups": GROUPS,
        "metadata": {s: metadata.get(s, {}) for s in SYMBOLS}, "errors": errors,
        "source_metadata": source_metadata, "context_errors": source_errors,
        "versions": {p: version(p) for p in ("numpy", "scikit-learn", "scipy")},
        "source_context_sha256": hashlib.sha256(Path(context_cache).read_bytes()).hexdigest(),
        "implementation_sha256": {n: hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in
            ("compass_exact.py", "compass_context.py", "compass_context_data.py", "compass_forecast.py", "compass.py")},
        "history": history, "folds": manifests, "summaries": summaries,
        "yearly": {s: {str(y): {m: quick_metrics([r for r in rows if r["date"].startswith(str(y))],m)
            for m in ("context", "price_only", "ema")} for y in PROTOCOL["years"]} for s,rows in history.items()},
        "probability_diagnostics": {s: {m: _diagnostics(rows,m) for m in ("context", "price_only")} for s,rows in history.items()}}
    result = output/"results.json"
    result.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False),encoding="utf-8")
    from .compass_exact_report import write_exact_report
    write_exact_report(payload, output/"index.html")
    return result
