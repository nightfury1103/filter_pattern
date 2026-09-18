"""Bounded, causal monthly refresh of the shared analog D1 experiment."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from .compass import calculate_compass_series
from .compass_analog import fit_library, probabilities
from .compass_context_data import validate_source
from .compass_exact import GROUPS, SYMBOLS
from .compass_forecast import (
    bias_from_probability, probability_diagnostics, stability_summary, summarize,
)
from .compass_research import load_research_data
from .compass_shared import prepare, weights
from .rrg_comparison import paired_comparison, quick, signed_bias

THRESHOLDS = {f"raw{int(t * 100)}": t for t in (.60, .65, .70, .75, .80)}
NAMES = {
    "selected": "La bàn cập nhật: qua xác nhận",
    "calibrated": "Cập nhật + hiệu chỉnh / 75%",
    **{m: f"Cập nhật tháng / ngưỡng {t:.0%}" for m, t in THRESHOLDS.items()},
    "raw_direction": "Cập nhật tháng / hướng mỗi ngày",
    "calibrated_direction": "Sau hiệu chỉnh / hướng mỗi ngày",
    "old75": "Bản cũ 25 analog / 75%",
    "old_direction": "Bản cũ / hướng mỗi ngày",
    "ema": "EMA", "always_long": "Luôn Long",
}
PROTOCOL = {
    "version": "adaptive-1", "symbols": SYMBOLS, "years": [2024, 2025, 2026],
    "horizon": 10, "neighbors": 25, "lookback_years": 4, "refresh": "calendar month",
    "features": "Unchanged 12 features/scaler/vote from compass_analog",
    "library": "Reference date >= month minus four years; 10-bar label exit strictly before month; every 10 bars; at least 100 references",
    "calibration": "Logistic(C=1) on logit of causal raw votes in Y-2; purged at Y-1; no class balancing; >=200 rows and both classes; frozen in Y-1 and Y",
    "validation": "Fixed calibrated threshold .75 on Y-1; labels strictly before Y; no threshold selection",
    "gate": "accuracy>=.75, coverage>=.10, >=100 signals, >=20 Long and >=20 Short; otherwise selected WAIT",
    "diagnostics": {"raw_thresholds": THRESHOLDS, "daily_direction_threshold": .5},
    "label": "close(T+h)/open(T+1)-1; primary h=10; diagnostics h=5,20; flat incorrect both directions",
    "reuse": "Previously inspected 2024-2026, retrospective only; updates can use matured earlier test labels by fixed monthly rule",
    "evidence": "coverage>=10%, >=100 fixed-schedule samples, block CI95 lower>=75%, all seven symbols; no live promotion",
}


def library_rows(rows: list[dict], month: str) -> list[dict]:
    """Strict calendar cutoff protects all markets from same-date timing leaks."""
    start = f"{int(month[:4]) - PROTOCOL['lookback_years']}{month[4:]}"
    return [r for r in rows if start <= r["date"] < month
            and "10" in r["outcomes"]
            and r["outcomes"]["10"]["exit_date"] < month
            and r["outcomes"]["10"]["return_pct"] != 0]


def monthly_stream(rows: list[dict], start: str = "2022-01-01"):
    history, libraries, manifests = [], {}, {}
    months = sorted({r["date"][:7] + "-01" for r in rows if r["date"] >= start})
    for month in months:
        train = library_rows(rows, month)
        library, manifest = fit_library(train)
        queries = sorted([r for r in rows if r["date"][:7] == month[:7]],
                         key=lambda r: (r["date"], r["symbol"]))
        ps = probabilities(queries, library).get("analog25")
        history.extend({**r, "raw_p": float(ps[i]) if ps is not None else None,
                        "library_month": month} for i, r in enumerate(queries))
        libraries[month] = library
        manifests[month] = {**manifest, "cutoff_exclusive": month,
                            "window_start": f"{int(month[:4])-PROTOCOL['lookback_years']}{month[4:]}",
                            "query_rows": len(queries)}
    return history, libraries, manifests


def logit(ps):
    import numpy as np
    p = np.clip(np.asarray(ps, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p)).reshape(-1, 1)


def calibration_rows(stream: list[dict], year: int) -> list[dict]:
    start, end = f"{year-2}-01-01", f"{year-1}-01-01"
    return [r for r in stream if start <= r["date"] < end and r["raw_p"] is not None
            and "10" in r["outcomes"] and r["outcomes"]["10"]["exit_date"] < end
            and r["outcomes"]["10"]["return_pct"] != 0]


def fit_calibrator(rows: list[dict]):
    from sklearn.linear_model import LogisticRegression
    y = [r["outcomes"]["10"]["return_pct"] > 0 for r in rows]
    if len(rows) < 200 or len(set(y)) < 2:
        return None
    model = LogisticRegression(C=1., max_iter=2000)
    model.fit(logit([r["raw_p"] for r in rows]), y, sample_weight=weights(rows))
    return model


def calibrated_probabilities(rows: list[dict], calibrator):
    result = [None] * len(rows)
    valid = [i for i, r in enumerate(rows) if r["raw_p"] is not None]
    if calibrator is not None and valid:
        values = calibrator.predict_proba(logit([rows[i]["raw_p"] for i in valid]))[:, 1]
        for i, p in zip(valid, values):
            result[i] = float(p)
    return result


def validate_gate(rows: list[dict], ps: list[float | None]) -> dict:
    """One fixed decision rule. Missing scores remain in the coverage denominator."""
    import numpy as np
    assert len(rows) == len(ps)
    w = weights(rows)
    states = [bias_from_probability(p) if p is not None else "WAIT" for p in ps]
    chosen = np.array([s != "WAIT" for s in states], dtype=bool)
    correct = np.array([r["outcomes"]["10"]["return_pct"] * (1 if s == "LONG" else -1) > 0
                        and s != "WAIT" for r, s in zip(rows, states)], dtype=bool)
    count = int(chosen.sum())
    accuracy = float(w[correct].sum() / w[chosen].sum()) if count else None
    coverage = float(w[chosen].sum() / w.sum()) if len(w) else 0.
    longs, shorts = states.count("LONG"), states.count("SHORT")
    passed = count >= 100 and longs >= 20 and shorts >= 20 and coverage >= .1 and accuracy >= .75
    return {"model": "calibrated", "threshold": .75 if passed else None,
            "proposed_threshold": .75, "status": "active" if passed else "validation_gate_failed",
            "signals": count, "accuracy": accuracy, "coverage": coverage,
            "long": longs, "short": shorts, "trials": []}


def span(rows: list[dict]) -> dict:
    return {"rows": len(rows), "first": min((r["date"] for r in rows), default=None),
            "last": max((r["date"] for r in rows), default=None),
            "last_label_exit": max((r["outcomes"]["10"]["exit_date"] for r in rows), default=None)}


def forecast(rows, calibrator, gate):
    result = []
    for r, p in zip(rows, calibrated_probabilities(rows, calibrator)):
        raw = r["raw_p"]
        predictions = {m: {"p_up": raw, "bias": bias_from_probability(raw, t) if raw is not None else "WAIT"}
                       for m, t in THRESHOLDS.items()}
        predictions["calibrated"] = {"p_up": p, "bias": bias_from_probability(p) if p is not None else "WAIT"}
        predictions["selected"] = {"p_up": p, "bias": predictions["calibrated"]["bias"] if gate["threshold"] else "WAIT"}
        for name, value in (("raw_direction", raw), ("calibrated_direction", p)):
            predictions[name] = {"p_up": value, "bias": signed_bias(value, .5) if value is not None else "WAIT"}
        result.append({**r, "forecasts": predictions,
                       "epochs": {m: r["library_month"] for m in predictions},
                       "selected_model": "calibrated", "selected_threshold": gate["threshold"],
                       "gate_status": gate["status"]})
    return result


def run(cache: Path, baseline: Path, out: Path, before: str):
    import joblib
    from threadpoolctl import threadpool_limits

    out.mkdir(parents=True, exist_ok=True)
    (out / "protocol.json").write_text(json.dumps(PROTOCOL, ensure_ascii=False, indent=2), encoding="utf-8")
    old = json.loads(baseline.read_text(encoding="utf-8"))
    baseline_cache_hashes = {value for key, value in old["hashes"].items()
                             if Path(key).name == "candles.json"}
    if hashlib.sha256(cache.read_bytes()).hexdigest() not in baseline_cache_hashes:
        raise ValueError("Baseline must use the identical validated OHLC cache")
    data, metadata, errors = load_research_data(out, cache_path=cache, before=date.fromisoformat(before))
    rows = []
    for symbol in SYMBOLS:
        if symbol in data:
            validate_source(data[symbol])
            rows.extend(prepare(data[symbol], symbol))
    print("Build causal monthly analog stream", flush=True)
    with threadpool_limits(limits=2):
        stream, libraries, manifests = monthly_stream(rows)
    (out / "monthly-manifest.json").write_text(json.dumps(manifests, indent=2), encoding="utf-8")
    folds, calibrators = {}, {}
    history = {s: [] for s in SYMBOLS if s in data}
    for year in PROTOCOL["years"]:
        calibration = calibration_rows(stream, year)
        validation = [r for r in stream if f"{year-1}-01-01" <= r["date"] < f"{year}-01-01"
                      and "10" in r["outcomes"] and r["outcomes"]["10"]["exit_date"] < f"{year}-01-01"]
        test = [r for r in stream if r["date"].startswith(str(year))]
        calibrator = fit_calibrator(calibration)
        gate = validate_gate(validation, calibrated_probabilities(validation, calibrator))
        train = library_rows(rows, f"{year}-01-01")
        folds[str(year)] = {"train": span(train), "calibration": span(calibration),
                            "validation": span(validation), "selection": gate,
                            "status": "fitted" if calibrator is not None else "insufficient_calibration",
                            "calibration_slope": float(calibrator.coef_[0, 0]) if calibrator is not None else None,
                            "calibration_intercept": float(calibrator.intercept_[0]) if calibrator is not None else None}
        calibrators[str(year)] = calibrator
        for r in forecast(test, calibrator, gate):
            history[r["symbol"]].append(r)
        print(f"Adaptive/{year}: {gate}", flush=True)

    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "before": before,
               "protocol": PROTOCOL, "groups": GROUPS, "models": NAMES, "shared_folds": folds,
               "availability_model": "raw75", "assets": {}, "monthly_manifest": manifests,
               "chart_models": {"selected": NAMES["selected"], "calibrated": NAMES["calibrated"],
                                "raw75": NAMES["raw75"], "old75": NAMES["old75"]},
               "errors": {s: errors.get(s, "Missing validated exact-symbol history") for s in SYMBOLS if s not in data},
               "hashes": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                          [cache, baseline, Path(__file__), Path(__file__).with_name("compass_analog.py"),
                           Path(__file__).with_name("compass_shared.py"), Path(__file__).with_name("compass_forecast.py")]}}
    for symbol, rs in history.items():
        previous = {r["date"]: r for r in old["assets"].get(symbol, {}).get("history", [])}
        ema = calculate_compass_series(data[symbol])["ema"]
        for r in rs:
            prior = previous.get(r["date"])
            if prior:
                assert r["outcomes"] == prior["outcomes"], (symbol, r["date"], "Outcome mismatch")
            r["forecasts"]["old75"] = prior["forecasts"]["analog25"] if prior else {"p_up": None, "bias": "WAIT"}
            r["forecasts"]["old_direction"] = prior["forecasts"]["analog25_direction"] if prior else {"bias": "WAIT"}
            r["forecasts"].update(ema={"bias": ema[r["index"]]["bias"]}, always_long={"bias": "LONG"})
            r["epochs"]["old75"] = r["date"][:4]
        matched = [r for r in rs if all(r["forecasts"][m]["p_up"] is not None for m in ("raw75", "calibrated", "old75"))]
        # This run must compare every forecast date, not silently discard hard dates.
        if len(matched) != len(rs):
            raise ValueError(f"{symbol}: incomplete matched predictions: {len(matched)}/{len(rs)}")
        print(f"Evaluate adaptive {symbol}: {len(matched)} matched dates", flush=True)
        summaries = {m: {str(h): {side: summarize(matched, m, side, h)
                                 for side in (("ALL", "LONG", "SHORT") if h == 10 else ("ALL",))}
                         for h in (5, 10, 20)} for m in NAMES}
        payload["assets"][symbol] = {
            "metadata": metadata[symbol], "benchmark": "thư viện cập nhật dùng chung", "folds": folds,
            "history": [{k: v for k, v in r.items() if k not in ("features", "weekly_features")} for r in rs],
            "matched_dates": {"first": matched[0]["date"], "last": matched[-1]["date"], "count": len(matched)},
            "summaries": summaries, "rule_full_period": {},
            "yearly": {str(y): {m: quick([r for r in matched if r["date"].startswith(str(y))], m) for m in NAMES}
                       for y in PROTOCOL["years"]},
            "diagnostics": {m: probability_diagnostics(matched, m) for m in ("raw75", "calibrated", "old75")},
            "stability": {m: stability_summary(matched, m) for m in NAMES},
            "price_clean_sensitivity": {m: quick(matched, m) for m in NAMES},
            "paired": [paired_comparison(matched, a, b) for a, b in
                       (("raw75", "old75"), ("raw_direction", "old_direction"),
                        ("calibrated_direction", "old_direction"), ("selected", "always_long"))],
        }
    joblib.dump({"libraries": libraries, "calibrators": calibrators}, out / "research-models.joblib")
    (out / "stream-calibration.json").write_text(json.dumps([
        {k: r[k] for k in ("symbol", "date", "raw_p", "library_month", "outcomes")}
        for r in stream if r["date"] < "2024-01-01"], allow_nan=False), encoding="utf-8")
    (out / "results.json").write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    from .compass_adaptive_report import write_report
    write_report(payload, out / "index.html")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("reports/compass-exact-d1/candles.json"))
    parser.add_argument("--baseline", type=Path, default=Path("reports/compass-analog-d1/results.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/compass-adaptive-d1"))
    parser.add_argument("--before", default="2026-09-17")
    args = parser.parse_args()
    run(args.cache, args.baseline, args.out, args.before)


if __name__ == "__main__":
    main()
