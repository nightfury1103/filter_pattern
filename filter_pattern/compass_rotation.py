"""Four-state absolute price rotation using the frozen wave experiment axes."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from .compass_shared import weights

PHASES = ("LEADING", "WEAKENING", "LAGGING", "IMPROVING", "CENTER", "MISSING")
PROTOCOL = {"version": "rotation-1", "basis": "absolute price trend; not benchmark-relative JdK RRG",
            "x": "(EMA20[T]-EMA20[T-3])/ATR14[T]", "y": "x[T]-x[T-5]",
            "phases": list(PHASES), "boundaries": "exact zero on either axis => CENTER; absent/nonfinite => MISSING",
            "retuning": False, "forced_clockwise_rotation": False, "signal_mapping": None,
            "horizons": [5, 10, 20], "label": "open T+1 to close T+h return, grouped by state at close T",
            "reuse": "Previously inspected 2024-2026; descriptive retrospective, no 75% claim",
            "weights": "equal asset exposure, US500/SPY half each, calculated on eligible rows before phase selection"}


def quadrant(x: float | None, y: float | None) -> str:
    if x is None or y is None or not math.isfinite(x) or not math.isfinite(y):
        return "MISSING"
    if x == 0 or y == 0:
        return "CENTER"
    return ("LEADING" if y > 0 else "WEAKENING") if x > 0 else ("IMPROVING" if y > 0 else "LAGGING")


def phase_rows(history: list[dict]) -> list[dict]:
    result = []
    for r in history:
        f = r["forecasts"]["wave"]
        result.append({"date": r["date"], "index": r["index"], "symbol": r["symbol"], "close": r["close"],
                       "outcomes": r["outcomes"], "epochs": {"wave": "fixed"},
                       "forecasts": {"wave": {"score": f["score"], "momentum": f["momentum"],
                                             "phase": quadrant(f["score"], f["momentum"])}}})
    return result


def summarize_phases(rows: list[dict], horizon: int) -> dict:
    eligible = [r for r in rows if str(horizon) in r["outcomes"]]
    w = weights(eligible)
    result = {}
    for phase in PHASES:
        indices = [i for i, r in enumerate(eligible) if r["forecasts"]["wave"]["phase"] == phase]
        total = float(w[indices].sum())
        up = [i for i in indices if eligible[i]["outcomes"][str(horizon)]["return_pct"] > 0]
        down = [i for i in indices if eligible[i]["outcomes"][str(horizon)]["return_pct"] < 0]
        flat = [i for i in indices if eligible[i]["outcomes"][str(horizon)]["return_pct"] == 0]
        result[phase] = {"days": len(indices), "up": len(up), "down": len(down), "flat": len(flat),
                         "coverage": float(total/w.sum()) if len(w) else 0.,
                         "up_rate": float(w[up].sum()/total) if total else None,
                         "down_rate": float(w[down].sum()/total) if total else None,
                         "flat_rate": float(w[flat].sum()/total) if total else None,
                         "mean_return_pct": float(sum(w[i]*eligible[i]["outcomes"][str(horizon)]["return_pct"] for i in indices)/total) if total else None}
    return result


def run(source: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    (out/"protocol.json").write_text(json.dumps(PROTOCOL, ensure_ascii=False, indent=2), encoding="utf-8")
    old = json.loads(source.read_text(encoding="utf-8"))
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "before": old["before"],
               "groups": old["groups"], "models": {"wave": "Chu kỳ sóng giá — 4 trạng thái"},
               "assets": {}, "errors": old["errors"], "protocol": PROTOCOL,
               "hashes": {str(source): hashlib.sha256(source.read_bytes()).hexdigest(),
                          str(Path(__file__)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    combined = []
    for symbol, a in old["assets"].items():
        rows = phase_rows(a["history"])
        transitions = Counter((a["forecasts"]["wave"]["phase"], b["forecasts"]["wave"]["phase"])
                              for a,b in zip(rows,rows[1:]) if b["index"] == a["index"]+1)
        payload["assets"][symbol] = {"history": rows,
            "phase_stats": {str(h): summarize_phases(rows,h) for h in (5,10,20)},
            "transitions": [{"from": a, "to": b, "count": n} for (a,b),n in sorted(transitions.items())]}
        combined.extend(rows)
    payload["phase_stats"] = {str(h): summarize_phases(combined,h) for h in (5,10,20)}
    (out/"results.json").write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    from .compass_rotation_report import write_report
    write_report(payload, old, out/"index.html")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("reports/compass-wave-d1/results.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/compass-rotation-d1"))
    args=parser.parse_args()
    run(args.source,args.out)


if __name__ == "__main__":
    main()
