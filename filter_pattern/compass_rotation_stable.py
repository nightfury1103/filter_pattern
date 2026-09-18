"""Frozen smoothing and hysteresis experiment for absolute four-state rotation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import median

from .compass import WARMUP, _ema
from .compass_wave import wave_series
from .compass_rotation import quadrant, summarize_phases
from .compass_shared import weights
from .compass_forecast import summarize
from .models import Candle

PROTOCOL = {"version": "rotation-stable-1", "smoothing_x": 5, "smoothing_y": 3,
            "change_bars": 5, "trend_band": .10, "momentum_band": .05, "warmup": WARMUP,
            "x": "EMA5((EMA20[T]-EMA20[T-3])/ATR14[T])", "y": "EMA3(X[T]-X[T-5])",
            "states": "Each sign persists inside its symmetric deadband; change only strictly beyond boundary; initial 0; quadrant from confirmed signs",
            "plot": "Actual numeric X/Y; phase can differ from raw quadrant only inside plotted deadbands",
            "selection": "One configuration for all symbols; no tuning after results",
            "horizons": [5, 10, 20], "reuse": "Previously inspected retrospective 2024-2026, not fresh validation",
            "latency": "Alternating close breakouts of prior 20 closes; recognition within 10 bars; paired latency on same recognized events"}
MODELS = {"wave": "Bản ổn định — làm mượt + vùng đệm", "original": "Bản cũ — đổi ô tại 0"}


def hysteresis(previous: int, value: float, band: float) -> int:
    return 1 if value > band else -1 if value < -band else previous


def series(candles: list[Candle]) -> list[dict]:
    original = wave_series(candles)
    x = _ema([r["score"] for r in original], PROTOCOL["smoothing_x"])
    y = _ema([v-x[i-5] if i >= 5 else 0. for i,v in enumerate(x)], PROTOCOL["smoothing_y"])
    trend = momentum = 0
    result = []
    for i,r in enumerate(original):
        if i >= WARMUP:
            trend = hysteresis(trend, x[i], PROTOCOL["trend_band"])
            momentum = hysteresis(momentum, y[i], PROTOCOL["momentum_band"])
        result.append({"date": r["date"], "score": x[i], "momentum": y[i],
                       "trend_sign": trend, "momentum_sign": momentum,
                       "phase": quadrant(trend,momentum), "raw_phase": quadrant(x[i],y[i]),
                       "within_buffer": abs(x[i]) <= .10 or abs(y[i]) <= .05,
                       "original": {"score": r["score"], "momentum": r["momentum"],
                                    "phase": quadrant(r["score"],r["momentum"]),
                                    "trend_sign": 1 if r["score"]>0 else -1 if r["score"]<0 else 0}})
    return result


def stability(rows: list[dict], model: str) -> dict:
    states = [r["forecasts"][model]["phase"] for r in rows]
    lengths = []
    for i,state in enumerate(states):
        if i==0 or state != states[i-1]: lengths.append(1)
        else: lengths[-1] += 1
    return {"days":len(states), "changes":max(0,len(lengths)-1),
            "median_run":median(lengths) if lengths else None,
            "one_bar_runs":lengths.count(1),
            "back_next_day":sum(states[i-1]==states[i+1]!=states[i] for i in range(1,len(states)-1))}


def latency(candles: list[Candle], signals: list[dict], start: str) -> dict:
    previous = None
    events = []
    for i in range(WARMUP,len(candles)-10):
        prior = [c.close for c in candles[i-20:i]]
        direction = 1 if candles[i].close>max(prior) else -1 if candles[i].close<min(prior) else None
        if direction is None or direction == previous: continue
        previous = direction
        if signals[i]["date"] < start: continue
        delays = {}
        for model in MODELS:
            delays[model] = next((j for j in range(11)
                if (signals[i+j] if model=="wave" else signals[i+j]["original"])["trend_sign"]==direction),None)
        events.append({"date":signals[i]["date"], "direction":direction, "delays":delays})
    both = [e for e in events if all(v is not None for v in e["delays"].values())]
    return {"reference":"alternating_20_close_breakout", "events":events,
            "models":{m:{"events":len(events),
                "recognized_at_event":sum(e["delays"][m]==0 for e in events),
                "recognized_within10":sum(e["delays"][m] is not None for e in events),
                "missed":sum(e["delays"][m] is None for e in events),
                "paired_events":len(both),
                "paired_median_bars":median(e["delays"][m] for e in both) if both else None} for m in MODELS},
            "paired_median_extra_bars":median(e["delays"]["wave"]-e["delays"]["original"] for e in both) if both else None}


def model_rows(rows: list[dict], model: str) -> list[dict]:
    return [{**r,"forecasts":{"wave":r["forecasts"][model]}} for r in rows]


def direction_overview(rows: list[dict], model: str) -> dict:
    eligible = [r for r in rows if "10" in r["outcomes"]]
    w = weights(eligible)
    selected = [i for i,r in enumerate(eligible) if r["forecasts"][model]["trend_sign"] != 0]
    wins = [i for i in selected if eligible[i]["outcomes"]["10"]["return_pct"]*eligible[i]["forecasts"][model]["trend_sign"]>0]
    total = float(w[selected].sum())
    return {"signals":len(selected),"wins":len(wins),"accuracy":float(w[wins].sum()/total) if total else None,
            "coverage":float(total/w.sum()) if len(w) else 0.}


def run(cache: Path, source: Path, out: Path):
    out.mkdir(parents=True,exist_ok=True)
    (out/"protocol.json").write_text(json.dumps(PROTOCOL,indent=2),encoding="utf-8")
    old=json.loads(source.read_text(encoding="utf-8"))
    wave_source=next(Path(p) for p in old["hashes"] if Path(p).name=="results.json")
    assert hashlib.sha256(wave_source.read_bytes()).hexdigest()==old["hashes"][str(wave_source)]
    original_wave=json.loads(wave_source.read_text(encoding="utf-8"))
    cached=json.loads(cache.read_text(encoding="utf-8"))
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"before":old["before"],"groups":old["groups"],
             "models":MODELS,"protocol":PROTOCOL,"assets":{},"errors":old["errors"],
             "hashes":{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                       (cache,source,Path(__file__),Path(__file__).with_name("compass_wave.py"),
                        Path(__file__).with_name("compass_rotation.py"),Path(__file__).with_name("compass.py"))}}
    combined=[]
    for symbol,a in old["assets"].items():
        candles=[Candle(**{**c,"datetime":datetime.fromisoformat(c["datetime"])})
                 for c in cached["instruments"][symbol]["candles"] if c["datetime"][:10]<old["before"]]
        states=series(candles); rows=[]
        for r in a["history"]:
            f=states[r["index"]]
            assert f["date"]==r["date"] and candles[r["index"]].close==r["close"]
            assert f["original"]["score"]==r["forecasts"]["wave"]["score"]
            assert f["original"]["momentum"]==r["forecasts"]["wave"]["momentum"]
            rows.append({**r,"epochs":{m:"fixed" for m in MODELS},
                         "forecasts":{"wave":{k:v for k,v in f.items() if k not in ("original","date")},"original":f["original"]}})
        stats={m:{str(h):summarize_phases(model_rows(rows,m),h) for h in (5,10,20)} for m in MODELS}
        # Direction diagnosis is separate from the four-state display, never a phase-to-trade mapping.
        diagnostic=[{**r,"extension_atr":0.,"forecasts":{m:{"bias":"LONG" if f["trend_sign"]>0 else "SHORT" if f["trend_sign"]<0 else "WAIT"}
                    for m,f in r["forecasts"].items()}} for r in rows]
        directional={m:{str(h):summarize(diagnostic,m,"ALL",h) for h in (5,10,20)} for m in MODELS}
        for hs in directional.values():
            for value in hs.values():
                value.pop("mean_abs_extension_at_signal");value.pop("extended_over_2atr_fraction")
        payload["assets"][symbol]={"history":rows,"phase_stats":stats["wave"],"phase_stats_by_model":stats,
            "stability":{m:{"full":stability(rows,m),"last180":stability(rows[-180:],m)} for m in MODELS},
            "latency":latency(candles,states,rows[0]["date"]),"directional":directional}
        combined.extend(rows)
        print(symbol, payload["assets"][symbol]["stability"],flush=True)
    payload["phase_stats_by_model"]={m:{str(h):summarize_phases(model_rows(combined,m),h) for h in (5,10,20)} for m in MODELS}
    payload["phase_stats"]=payload["phase_stats_by_model"]["wave"]
    payload["direction_overview"]={m:direction_overview(combined,m) for m in MODELS}
    (out/"results.json").write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    from .compass_rotation_stable_report import write_report
    write_report(payload,original_wave,out/"index.html")
    return payload


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache",type=Path,default=Path("reports/compass-exact-d1/candles.json"))
    p.add_argument("--source",type=Path,default=Path("reports/compass-rotation-d1/results.json"))
    p.add_argument("--out",type=Path,default=Path("reports/compass-rotation-stable-d1"))
    a=p.parse_args();run(a.cache,a.source,a.out)


if __name__=="__main__":main()
