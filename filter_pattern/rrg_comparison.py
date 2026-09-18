"""Offline, matched-date audit of actual provider RRG versus saved forecasts.

This module does not estimate proprietary JdK coordinates or modify live RRG.
Run: python -m filter_pattern.rrg_comparison --help
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, median

from .compass_forecast import summarize, stability_summary
from .rrg_dashboard import _series_from_fialda, _series_from_stockcharts, rrg_intent

SOURCES = {
    "XAUUSD": ("one", "$GOLD", "$ONE"),
    "BTCUSD": ("crypto", "$BTCUSD", "$ONE"),
    "ETHUSD": ("crypto", "$ETHUSD", "$ONE"),
    "DXY": ("forex", "$USD", "$ONE"),
    "US500": ("index", "$SPX", "$ONE"),
    "SPY": ("spy", "SPY", "SPY"),
    "E1VFVN30": ("fialda", "E1VFVN30", "VNINDEX"),
}
NAMES = {
    "rrg_y": "RRG: hướng trục Y",
    "rrg_x": "RRG: sức mạnh trục X",
    "rrg_intent": "RRG: xác nhận Long gốc",
    "price_direction": "Compass chỉ giá: hướng mỗi ngày",
    "context_direction": "Compass bối cảnh: hướng mỗi ngày",
    "price_only": "Compass chỉ giá: ngưỡng 75%",
    "context": "Compass bối cảnh: ngưỡng 75%",
    "ema": "EMA",
    "always_long": "Luôn Long",
}


def signed_bias(value: float, center: float) -> str:
    return "LONG" if value > center else "SHORT" if value < center else "WAIT"


def normalize_points(points: list[dict], before: str) -> list[dict]:
    """Require unique finite daily observations; never invent missing dates."""
    result, seen = [], set()
    for raw in points:
        stamp = raw.get("date") or str(raw.get("start", ""))[:10]
        day = date.fromisoformat(stamp).isoformat()
        if day >= before:
            continue
        if day in seen:
            raise ValueError(f"Duplicate RRG date: {day}")
        seen.add(day)
        x, y = float(raw["x"]), float(raw["y"])
        price = float(raw["price"]) if raw.get("price") is not None else None
        if not all(math.isfinite(v) for v in (x, y)) or (price is not None and (not math.isfinite(price) or price <= 0)):
            raise ValueError(f"Invalid RRG observation: {day}")
        if raw.get("end") and str(raw["end"])[:10] != day:
            raise ValueError(f"Non-daily RRG observation: {day}")
        result.append({"date": day, "x": x, "y": y, "price": price})
    return sorted(result, key=lambda p: p["date"])


def make_signals(points: list[dict]) -> dict[str, dict]:
    result = {}
    for i, p in enumerate(points):
        # Identical production function, supplied only data available through T.
        intent = rrg_intent(points[max(0, i-9):i+1])
        result[p["date"]] = {"point": p, "rrg_y": signed_bias(p["y"], 100),
            "rrg_x": signed_bias(p["x"], 100),
            "rrg_intent": "LONG" if intent["accepted"] else "WAIT"}
    return result


def matched_rows(history: list[dict], points: list[dict], closes: dict[str, float], price_scale: float = 1.) -> tuple[list[dict], dict]:
    signals = make_signals(points)
    rows, mismatches, deviations = [], [], []
    available = [r for r in history if all(r["forecasts"][m].get("p_up") is not None for m in ("price_only", "context"))]
    for original in available:
        signal = signals.get(original["date"])
        if signal is None:
            continue
        row = copy.deepcopy(original)
        for model in ("rrg_y", "rrg_x", "rrg_intent"):
            row["forecasts"][model] = {"bias": signal[model]}
        for source, target in (("price_only", "price_direction"), ("context", "context_direction")):
            row["forecasts"][target] = {"bias": signed_bias(row["forecasts"][source]["p_up"], .5)}
        point = signal["point"]
        deviation = abs(point["price"]*price_scale/closes[row["date"]]-1) if point["price"] is not None else None
        row["rrg"] = {**point, "price_deviation_fraction": deviation}
        if deviation is not None:
            deviations.append(deviation)
            if deviation > .01:
                mismatches.append({"date": row["date"], "relative_difference": deviation})
        rows.append(row)
    audit = {"compass_available_days": len(available), "matched_days": len(rows),
        "missing_rrg_dates": [r["date"] for r in available if r["date"] not in signals],
        "first": rows[0]["date"] if rows else None, "last": rows[-1]["date"] if rows else None,
        "rrg_first": points[0]["date"] if points else None, "rrg_last": points[-1]["date"] if points else None,
        "rrg_points": len(points), "price_deviation_median": median(deviations) if deviations else None,
        "price_deviation_max": max(deviations) if deviations else None, "price_mismatches_over_1pct": mismatches,
        "center_points": sum(r["rrg"]["x"] == 100 and r["rrg"]["y"] == 100 for r in rows)}
    return rows, audit


def paired_comparison(rows: list[dict], a: str, b: str, horizon: int = 10) -> dict:
    """Conditional paired accuracy difference, preserving date blocks and WAITs."""
    import numpy as np
    eligible = [r for r in rows if str(horizon) in r["outcomes"]]
    mask, differences, wins_a, wins_b = [], [], 0, 0
    for r in eligible:
        sa, sb = (r["forecasts"][m]["bias"] for m in (a, b))
        chosen = sa != "WAIT" and sb != "WAIT"
        ret = r["outcomes"][str(horizon)]["return_pct"]
        wa = int(chosen and ret*(1 if sa == "LONG" else -1) > 0)
        wb = int(chosen and ret*(1 if sb == "LONG" else -1) > 0)
        mask.append(int(chosen))
        differences.append(wa-wb)
        wins_a += wa
        wins_b += wb
    n = sum(mask)
    result = {"a": a, "b": b, "shared_signals": n, "wins_a": wins_a, "wins_b": wins_b,
        "accuracy_a": wins_a/n if n else None, "accuracy_b": wins_b/n if n else None,
        "difference_a_minus_b": (wins_a-wins_b)/n if n else None, "block_ci95_difference": None}
    if n < 30 or len(eligible) < 120:
        return result
    # Identical correctness on every shared date is descriptive, not proof of equivalence.
    if not any(differences):
        return result
    mask, differences = np.array(mask), np.array(differences)
    rng, draws = np.random.default_rng(1709), []
    for _ in range(500):
        starts = rng.integers(0, len(eligible)-60+1, size=math.ceil(len(eligible)/60))
        indices = np.concatenate([np.arange(s, s+60) for s in starts])[:len(eligible)]
        count = mask[indices].sum()
        if count:
            draws.append(float(differences[indices].sum()/count))
    if len(draws) >= 450:
        result["block_ci95_difference"] = [float(v) for v in np.quantile(draws, [.025, .975])]
    return result


def quick(rows: list[dict], model: str, horizon: int = 10) -> dict:
    eligible = [r for r in rows if str(horizon) in r["outcomes"]]
    chosen = [r for r in eligible if r["forecasts"][model]["bias"] != "WAIT"]
    wins = sum(r["outcomes"][str(horizon)]["return_pct"]*(1 if r["forecasts"][model]["bias"] == "LONG" else -1) > 0 for r in chosen)
    return {"eligible": len(eligible), "signals": len(chosen), "wins": wins, "false_signals": len(chosen)-wins,
        "accuracy": wins/len(chosen) if chosen else None, "coverage": len(chosen)/len(eligible) if eligible else 0}


def run_comparison(source_dir: Path, compass_path: Path, candle_path: Path, out: Path) -> dict:
    compass = json.loads(compass_path.read_text(encoding="utf-8"))
    candles = json.loads(candle_path.read_text(encoding="utf-8"))["instruments"]
    cutoff = compass["before"]
    result = {"generated_at": datetime.now(timezone.utc).isoformat(), "before": cutoff,
        "protocol": "docs/rrg-comparison-protocol.md", "models": NAMES, "assets": {}, "errors": {},
        "input_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (compass_path, candle_path)},
        "overlap_checks": {}}
    for symbol, (filename, code, benchmark) in SOURCES.items():
        source = source_dir/f"{filename}-raw.json"
        if not source.exists():
            result["errors"][symbol] = "Missing actual provider RRG history"
            continue
        raw = json.loads(source.read_text(encoding="utf-8"))
        parser = _series_from_fialda if filename == "fialda" else _series_from_stockcharts
        points = normalize_points(parser(raw, [code]).get(code, []), cutoff)
        result["input_sha256"][str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
        if symbol not in compass["history"] or symbol not in candles:
            result["errors"][symbol] = f"RRG has {len(points)} points; no validated matching OHLC/Compass forecasts"
            continue
        if not points:
            result["errors"][symbol] = "Provider returned no valid coordinates"
            continue
        closes = {c["datetime"][:10]: c["close"] for c in candles[symbol]["candles"]}
        rows, audit = matched_rows(compass["history"][symbol], points, closes, 1000 if filename == "fialda" else 1)
        if not rows:
            result["errors"][symbol] = "No exact-date matched observations"
            continue
        print(f"Evaluate {symbol}: {len(rows)} matched dates", flush=True)
        clean = [r for r in rows if r["rrg"]["price_deviation_fraction"] is not None and r["rrg"]["price_deviation_fraction"] <= .01]
        result["assets"][symbol] = {"benchmark": benchmark, "audit": audit, "history": rows,
            "summaries": {m: {str(h): {side: summarize(rows,m,side,h) for side in (("ALL","LONG","SHORT") if h==10 else ("ALL",))} for h in (5,10,20)} for m in NAMES},
            "yearly": {str(y): {m: quick([r for r in rows if r["date"].startswith(str(y))],m) for m in NAMES} for y in (2024,2025,2026)},
            "price_clean_sensitivity": {m: quick(clean,m) for m in NAMES},
            "stability": {m: stability_summary(rows,m) for m in NAMES},
            "paired": [paired_comparison(rows,a,b) for a in ("rrg_y","rrg_x","rrg_intent") for b in ("price_direction","context_direction","price_only","context","ema","always_long")]}
        check_path = source_dir/f"{filename}-check-raw.json"
        if check_path.exists():
            short = normalize_points(parser(json.loads(check_path.read_text(encoding="utf-8")),[code]).get(code,[]),cutoff)
            long_by_day = {p["date"]:p for p in points}
            overlap = [p for p in short if p["date"] in long_by_day]
            result["overlap_checks"][symbol] = {"days":len(overlap), "max_coordinate_difference":max((abs(p[k]-long_by_day[p["date"]][k]) for p in overlap for k in ("x","y")),default=None)}
    out.mkdir(parents=True,exist_ok=True)
    (out/"results.json").write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    write_report(result,out/"index.html")
    return result


def write_report(payload: dict, path: Path) -> None:
    data = json.dumps(payload,ensure_ascii=False).replace("<","\\u003c")
    page = '''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RRG và Market Compass — kiểm tra cùng ngày</title><style>
body{background:#0c1321;color:#e1e8f2;font:15px system-ui;margin:0;padding:24px}main{max-width:1280px;margin:auto}h1{font-size:24px}h2{font-size:18px;margin-top:28px}p{line-height:1.6;color:#b9c6da}.notice{padding:16px;background:#322819;border:1px solid #8a693b;border-radius:8px}select{background:#182439;color:white;padding:9px;border:1px solid #526783;border-radius:5px;margin:4px 16px 4px 4px}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:10px;border-bottom:1px solid #29364b;white-space:nowrap}th{color:#9fb4d2}a{color:#70c9ff}.positive{color:#74dfb1}#source{font-size:13px}details{margin-top:24px}summary{cursor:pointer;font-size:17px}button{cursor:pointer}@media(max-width:600px){body{padding:12px}}
</style><main><h1>RRG hiện tại so với Market Compass D1</h1>
<p class="notice">Dùng tọa độ RRG thật từ đúng nguồn của ứng dụng, ghép cùng ngày với dự báo Compass đã lưu. Đây là kiểm tra hồi cứu, chưa xác nhận hiệu quả live hoặc độ chính xác 75%. Không sửa RRG và không huấn luyện lại Compass.</p>
<p>Quy tắc chính: RRG nửa trên → Long, nửa dưới → Short; đúng tâm trục → Chưa rõ. Quy tắc trục X và xác nhận Long gốc được báo riêng. Compass “hướng mỗi ngày” đọc xác suất trên/dưới 50%; ngưỡng 75% giữ nhiều ngày Chưa rõ.</p>
<label>Mã <select id="symbol"></select></label><label>Sau <select id="horizon"><option>5</option><option selected>10</option><option>20</option></select> nến</label>
<p id="source"></p><h2>Tỷ lệ đúng và tần suất có hướng — cùng tập ngày có dữ liệu</h2>
<div class="scroll"><table><thead><tr><th>Phép đọc</th><th>Đúng / tín hiệu</th><th>Tỷ lệ đúng</th><th>Độ phủ</th><th>Số sai</th><th>CI 95%</th><th>Mẫu lịch cố định</th></tr></thead><tbody id="metrics"></tbody></table></div>
<p>Độ phủ là tỷ lệ ngày có Long/Short trên ngày đủ kết quả. Số tín hiệu là số ngày, không phải số giao dịch độc lập. CI dùng block bootstrap; mẫu quá ít không có CI. SPY so với chính SPY nên tọa độ 100/100 được coi là trung tính.</p>
<h2>So sánh trực tiếp — chỉ ngày cả hai cùng đưa ra hướng, sau 10 nến</h2>
<div class="scroll"><table><thead><tr><th>RRG</th><th>Đối chiếu</th><th>Ngày chung</th><th>RRG đúng</th><th>Đối chiếu đúng</th><th>Chênh lệch RRG</th><th>CI chênh lệch</th></tr></thead><tbody id="paired"></tbody></table></div>
<p>Chênh lệch dương có lợi cho RRG. CI chứa 0 chưa cho thấy bên nào hơn rõ ràng; các phép so sánh là thăm dò, chưa hiệu chỉnh cho thử nhiều giả thuyết. Dữ liệu giá lịch sử đã được xem ở các vòng trước.</p>
<details><summary>Long / Short riêng và từng năm — chân trời 10 nến</summary><div class="scroll"><table><thead><tr><th>Mô hình</th><th>Hướng</th><th>Đúng / tín hiệu</th><th>Tỷ lệ đúng</th></tr></thead><tbody id="sides"></tbody></table><table><thead><tr><th>Năm</th><th>Mô hình</th><th>Đúng / tín hiệu</th><th>Tỷ lệ đúng</th><th>Độ phủ</th></tr></thead><tbody id="years"></tbody></table></div></details>
<details><summary>Ổn định và độ nhạy chất lượng giá</summary><p>Đổi trạng thái tính trên các ngày chung, có thể cách nhau cuối tuần/ngày nghỉ. Ít đổi do luôn WAIT không chứng minh hướng ổn định. Số đảo hướng trong 5 quan sát kế tiếp không nhất thiết là 5 nến crypto.</p><div class="scroll"><table><thead><tr><th>Mô hình</th><th>Số đổi trạng thái</th><th>Đảo hướng trong 5 quan sát</th><th>Loại ngày lệch giá >1%: đúng / tín hiệu</th><th>Tỷ lệ đúng</th></tr></thead><tbody id="stability"></tbody></table></div></details>
<details><summary>Nguồn và giới hạn</summary><p id="audit"></p><p id="errors"></p><p>StockCharts: BTC/ETH/DXY/US500/XAU so với $ONE; SPY so với SPY. Fialda: E1VFVN30 so với VNINDEX. Crypto RRG thiếu cuối tuần: không forward-fill. Giá kết quả lấy từ cùng cache OHLC của Compass; có khác biệt feed/phiên với nguồn RRG. Tọa độ hồi cứu có thể đã được nhà cung cấp cập nhật.</p></details>
<p><a href="../compass-exact-d1/index.html">Mở Market Compass</a> · <a href="results.json">Số liệu đầy đủ</a></p></main>
<script>const D=__DATA__;const $=id=>document.getElementById(id);const pct=v=>v==null?'—':(100*v).toFixed(1)+'%';const ci=v=>v?v.map(pct).join(' đến '):'Chưa đủ bằng chứng';function row(id,values){const tr=document.createElement('tr');for(const v of values){const td=document.createElement('td');td.textContent=v??'—';tr.append(td)}$(id).append(tr)}
for(const s of Object.keys(D.assets))$('symbol').add(new Option(s,s));$('symbol').value=D.assets.US500?'US500':Object.keys(D.assets)[0];
function draw(){const s=$('symbol').value,a=D.assets[s],h=$('horizon').value;for(const id of ['metrics','paired','sides','years','stability'])$(id).replaceChildren();
$('source').textContent=s+' · Benchmark RRG: '+a.benchmark+' · '+a.audit.first+' đến '+a.audit.last+' · '+a.audit.matched_days+' ngày chung / '+a.audit.compass_available_days+' ngày Compass · '+a.audit.center_points+' điểm tại tâm 100/100';
for(const[m,name]of Object.entries(D.models)){const r=a.summaries[m][h].ALL;row('metrics',[name,r.wins+' / '+r.signals,pct(r.accuracy),pct(r.coverage),r.false_signals,ci(r.block_ci95),r.scheduled_signals]);for(const side of ['LONG','SHORT']){const t=a.summaries[m]['10'][side];row('sides',[name,side,t.wins+' / '+t.signals,pct(t.accuracy)])}const st=a.stability[m],cl=a.price_clean_sensitivity[m];row('stability',[name,st.state_switches,st.opposite_within_5_bars,cl.wins+' / '+cl.signals,pct(cl.accuracy)])}
for(const p of a.paired)row('paired',[D.models[p.a],D.models[p.b],p.shared_signals,pct(p.accuracy_a),pct(p.accuracy_b),pct(p.difference_a_minus_b),ci(p.block_ci95_difference)]);
for(const[y,models]of Object.entries(a.yearly))for(const[m,r]of Object.entries(models))row('years',[y,D.models[m],r.wins+' / '+r.signals,pct(r.accuracy),pct(r.coverage)]);
$('audit').textContent='RRG nguồn: '+a.audit.rrg_first+' → '+a.audit.rrg_last+'. Lệch giá trung vị: '+pct(a.audit.price_deviation_median)+'. Ngày lệch >1%: '+JSON.stringify(a.audit.price_mismatches_over_1pct)+'. Kiểm tra cửa sổ ngắn/dài: '+JSON.stringify(D.overlap_checks[s]??'Không có phép đối chiếu riêng');
$('errors').textContent=Object.entries(D.errors).map(([s,e])=>s+': '+e).join(' · ')}
$('symbol').addEventListener('change',draw);$('horizon').addEventListener('change',draw);draw();</script></html>'''
    path.write_text(page.replace("__DATA__",data),encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources",type=Path,default=Path("reports/rrg-comparison-d1"))
    parser.add_argument("--compass",type=Path,default=Path("reports/compass-exact-d1/results.json"))
    parser.add_argument("--candles",type=Path,default=Path("reports/compass-exact-d1/candles.json"))
    parser.add_argument("--out",type=Path,default=Path("reports/rrg-comparison-d1"))
    args=parser.parse_args()
    run_comparison(args.sources,args.compass,args.candles,args.out)


if __name__ == "__main__":
    main()
