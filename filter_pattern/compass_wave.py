"""One fixed causal trend-state rule, evaluated separately from hindsight fit."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .compass import WARMUP, _atr, _ema, calculate_compass_series, validate_candles
from .compass_exact import GROUPS, SYMBOLS
from .compass_forecast import summarize, stability_summary
from .compass_shared import weights
from .models import Candle
from .rrg_comparison import quick, paired_comparison

NAMES = {"wave": "Sóng giá EMA20 + vùng đệm ATR", "ema": "EMA20/50 cũ",
         "adaptive": "Analog cập nhật / hướng mỗi ngày", "always_long": "Luôn Long"}
PROTOCOL = {"version": "wave-1", "ema": 20, "atr": 14, "slope_bars": 3,
            "band_atr": .5, "warmup": WARMUP, "horizon": 10, "diagnostic_horizons": [5, 20],
            "rule": "LONG close>EMA20+.5ATR and EMA20>EMA20[T-3]; SHORT symmetric; otherwise retain previous state, initial WAIT",
            "timing": "Signal after close T; evaluate open T+1 to close T+h; no future pivots or repaint",
            "recognition": "Agreement with sign(close T/close T-10 -1) is descriptive only, not forecast accuracy",
            "symbols": SYMBOLS, "reuse": "2024-2026 previously inspected; retrospective only",
            "selection": "One fixed configuration for all symbols, no tuning or live promotion"}


def advance(previous: str, close: float, ema: float, prior_ema: float, atr: float) -> str:
    if atr > 0:
        if close > ema + .5 * atr and ema > prior_ema:
            return "LONG"
        if close < ema - .5 * atr and ema < prior_ema:
            return "SHORT"
    return previous


def wave_series(candles: list[Candle]) -> list[dict]:
    validate_candles(candles)
    ema, atr = _ema([c.close for c in candles], 20), _atr(candles, 14)
    result, state = [], "WAIT"
    for i, c in enumerate(candles):
        scale = float(atr[i] or 0)
        score = (ema[i] - ema[i-3]) / scale if i >= 3 and scale > 0 else 0.
        if i >= WARMUP:
            state = advance(state, c.close, ema[i], ema[i-3], scale)
        result.append({"date": c.datetime.date().isoformat(), "bias": state, "p_up": None,
                       "score": score, "momentum": score - result[i-5]["score"] if i >= 5 else 0.,
                       "ema20": ema[i], "atr14": scale,
                       "upper": ema[i] + .5 * scale, "lower": ema[i] - .5 * scale})
    return result


def recognition(rows: list[dict], model: str) -> dict:
    chosen = [r for r in rows if r["forecasts"][model]["bias"] != "WAIT"]
    wins = sum(r["past_return10"] * (1 if r["forecasts"][model]["bias"] == "LONG" else -1) > 0 for r in chosen)
    return {"days": len(chosen), "aligned": wins, "agreement": wins/len(chosen) if chosen else None,
            "meaning": "same-time agreement with past 10 bars; not future accuracy"}


def overall(rows: list[dict]) -> dict:
    eligible = [r for r in rows if "10" in r["outcomes"]]
    w = weights(eligible)
    result = {}
    for m in NAMES:
        chosen = [i for i, r in enumerate(eligible) if r["forecasts"][m]["bias"] != "WAIT"]
        wins = [i for i in chosen if eligible[i]["outcomes"]["10"]["return_pct"] *
                (1 if eligible[i]["forecasts"][m]["bias"] == "LONG" else -1) > 0]
        total = float(w[chosen].sum())
        result[m] = {"signals": len(chosen), "wins": len(wins),
                     "accuracy": float(w[wins].sum()/total) if total else None,
                     "coverage": float(total/w.sum()) if len(w) else 0.,
                     "long": sum(eligible[i]["forecasts"][m]["bias"] == "LONG" for i in chosen),
                     "short": sum(eligible[i]["forecasts"][m]["bias"] == "SHORT" for i in chosen)}
    return result


def run(cache: Path, baseline: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    (out/"protocol.json").write_text(json.dumps(PROTOCOL, ensure_ascii=False, indent=2), encoding="utf-8")
    source = json.loads(cache.read_text(encoding="utf-8"))
    prior = json.loads(baseline.read_text(encoding="utf-8"))
    expected = {v for k, v in prior["hashes"].items() if Path(k).name == "candles.json"}
    if hashlib.sha256(cache.read_bytes()).hexdigest() not in expected:
        raise ValueError("Expected identical validated OHLC as baseline")
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "before": prior["before"],
               "models": NAMES, "groups": GROUPS, "protocol": PROTOCOL, "assets": {}, "errors": prior["errors"],
               "hashes": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                          (cache, baseline, Path(__file__), Path(__file__).with_name("compass.py"),
                           Path(__file__).with_name("compass_forecast.py"))}}
    combined = []
    for symbol in SYMBOLS:
        if symbol not in prior["assets"]:
            continue
        candles = [Candle(**{**c, "datetime": datetime.fromisoformat(c["datetime"])})
                   for c in source["instruments"][symbol]["candles"] if c["datetime"][:10] < prior["before"]]
        waves, ema = wave_series(candles), calculate_compass_series(candles)["ema"]
        rows = []
        old_history = prior["assets"][symbol]["history"]
        for j, old in enumerate(old_history):
            i = old["index"]
            assert candles[i].datetime.date().isoformat() == old["date"]
            assert candles[i].close == old["close"]
            raw = old["forecasts"]["raw75"]["p_up"]
            prev = old_history[j-5] if j >= 5 else None
            delta = raw - prev["forecasts"]["raw75"]["p_up"] if prev and prev["library_month"] == old["library_month"] else None
            forecasts = {"wave": waves[i],
                         "ema": {"bias": ema[i]["bias"], "p_up": None, "score": ema[i]["score"], "momentum": ema[i]["momentum"]},
                         "adaptive": {"bias": old["forecasts"]["raw_direction"]["bias"], "p_up": raw},
                         "always_long": {"bias": "LONG", "p_up": None}}
            if delta is not None:
                forecasts["adaptive"].update(score=(raw-.5)*10, momentum=delta*10)
            rows.append({"date": old["date"], "index": i, "close": old["close"], "symbol": symbol,
                         "outcomes": old["outcomes"], "extension_atr": old["extension_atr"],
                         "past_return10": (candles[i].close/candles[i-10].close-1)*100,
                         "forecasts": forecasts,
                         "epochs": {"wave": "fixed", "ema": "fixed", "adaptive": old["library_month"], "always_long": "fixed"}})
        summaries = {m: {str(h): {side: summarize(rows, m, side, h) for side in
                                  (("ALL", "LONG", "SHORT") if h == 10 else ("ALL",))}
                          for h in (5, 10, 20)} for m in NAMES}
        payload["assets"][symbol] = {"history": rows, "summaries": summaries,
            "recognition": {m: recognition(rows, m) for m in NAMES},
            "stability": {m: stability_summary(rows, m) for m in NAMES},
            "yearly": {str(y): {m: quick([r for r in rows if r["date"].startswith(str(y))], m) for m in NAMES} for y in (2024, 2025, 2026)},
            "paired": [paired_comparison(rows, "wave", m) for m in ("ema", "adaptive", "always_long")]}
        combined.extend(rows)
        print(symbol, "wave", summaries["wave"]["10"]["ALL"]["accuracy"],
              "past agreement", payload["assets"][symbol]["recognition"]["wave"]["agreement"], flush=True)
    payload["overview"] = overall(combined)
    (out/"results.json").write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    from .compass_wave_report import write_report
    write_report(payload, out/"index.html")
    return payload


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, default=Path("reports/compass-exact-d1/candles.json"))
    p.add_argument("--baseline", type=Path, default=Path("reports/compass-adaptive-d1/results.json"))
    p.add_argument("--out", type=Path, default=Path("reports/compass-wave-d1"))
    a = p.parse_args()
    run(a.cache, a.baseline, a.out)


if __name__ == "__main__":
    main()
