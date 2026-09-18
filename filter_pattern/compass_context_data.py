"""Audited external D1 context; all cross-market joins are strictly lagged."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from bisect import bisect_left
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import fmean, stdev

from .compass import _ema, validate_candles
from .compass_forecast import audit_continuity
from .models import Candle

SECTORS = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")
ETF_SOURCES = ("RSP", "SPY", "HYG", "IEF", "TLT", *SECTORS)
CONTEXT_FEATURES = (
    "sector_above_ema50", "sector_breadth_change5", "sector_positive20",
    "sector_momentum_dispersion", "cyclical_minus_defensive20",
    "equal_weight_minus_cap20", "credit_minus_treasury5", "credit_minus_treasury20",
    "treasury_z20", "dollar_z20", "equity_z20", "vix_log_level", "vix_term_ratio", "vix_change5",
)


def validate_source(candles: list[Candle]) -> dict:
    validate_candles(candles)
    if len(candles) < 260:
        raise ValueError("Need >=260 D1 bars")
    audit = audit_continuity(candles)
    audit["tolerated_float_boundary_rows"] = sum(not c.low <= min(c.open, c.close) <= max(c.open, c.close) <= c.high for c in candles)
    if not audit["eligible"]:
        raise ValueError(f"Continuity failure: {json.dumps(audit)}")
    return audit


def fetch_context(output: Path, before: date, cache: str | Path | None = None) -> dict:
    """Cache exact responses; a cache run never silently fetches missing sources."""
    output.mkdir(parents=True, exist_ok=True)
    if cache:
        bundle = json.loads(Path(cache).read_text(encoding="utf-8"))
    else:
        import requests
        import yfinance as yf
        yf.set_tz_cache_location(str(output / "yahoo-cache"))
        bundle = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "sources": {}, "errors": {}}
        raw_dir = output / "raw-context"
        raw_dir.mkdir(exist_ok=True)
        for ticker in ETF_SOURCES:
            print(f"Context source: {ticker}", flush=True)
            try:
                frame = yf.download(ticker, start="2010-01-01", end=before.isoformat(), interval="1d",
                                    auto_adjust=True, progress=False, threads=False, timeout=30)
                if frame.empty:
                    raise ValueError("Empty Yahoo history")
                if getattr(frame.columns, "nlevels", 1) > 1:
                    frame.columns = frame.columns.get_level_values(0)
                raw = frame.to_csv()
                (raw_dir / f"{ticker}.csv").write_text(raw, encoding="utf-8")
                rows = [{"datetime": t.isoformat(), "open": float(r["Open"]), "high": float(r["High"]),
                         "low": float(r["Low"]), "close": float(r["Close"]), "volume": float(r["Volume"])}
                        for t, r in frame.iterrows()]
                bundle["sources"][ticker] = {"provider": "Yahoo Finance", "adjustment": "auto_adjust=True",
                    "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(), "candles": rows}
            except Exception as exc:
                bundle["errors"][ticker] = str(exc)
        for ticker in ("VIX", "VIX3M"):
            url = f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{ticker}_History.csv"
            print(f"Context source: Cboe {ticker}", flush=True)
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                raw = response.text
                (raw_dir / f"{ticker}.csv").write_text(raw, encoding="utf-8")
                rows = []
                for r in csv.DictReader(io.StringIO(raw)):
                    day = datetime.strptime(r["DATE"], "%m/%d/%Y")
                    if date(2010, 1, 1) <= day.date() < before:
                        rows.append({"datetime": day.isoformat(), **{k: float(r[k.upper()]) for k in ("open", "high", "low", "close")}, "volume": 0.})
                bundle["sources"][ticker] = {"provider": "Cboe", "url": url,
                    "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(), "candles": rows}
            except Exception as exc:
                bundle["errors"][ticker] = str(exc)
    (output / "context-sources.json").write_text(json.dumps(bundle, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return bundle


def audit_context(bundle: dict, before: date) -> tuple[dict, dict, dict]:
    accepted, metadata, errors = {}, {}, dict(bundle.get("errors", {}))
    for symbol, entry in bundle["sources"].items():
        try:
            candles = [Candle(**{**r, "datetime": datetime.fromisoformat(r["datetime"])}) for r in entry["candles"]
                       if datetime.fromisoformat(r["datetime"]).date() < before]
            audit = validate_source(candles)
            accepted[symbol] = candles
            metadata[symbol] = {k: v for k, v in entry.items() if k != "candles"}
            metadata[symbol].update({"bars": len(candles), "first": candles[0].datetime.date().isoformat(),
                                     "last": candles[-1].datetime.date().isoformat(), "audit": audit})
            errors.pop(symbol, None)
        except (ValueError, TypeError, KeyError) as exc:
            errors[symbol] = str(exc)
    return accepted, metadata, errors


def _series_features(candles: list[Candle]) -> dict:
    prices = [c.close for c in candles]
    ema = _ema(prices, 50)
    changes = [0.] + [math.log(b / a) for a, b in zip(prices, prices[1:])]
    return {candles[i].datetime.date().isoformat(): {
        "close": prices[i], "above": float(prices[i] > ema[i]),
        "r5": math.log(prices[i] / prices[i-5]), "r20": math.log(prices[i] / prices[i-20]),
        "z20": math.log(prices[i] / prices[i-20]) / (max(stdev(changes[i-59:i+1]), 1e-8)*math.sqrt(20))}
        for i in range(60, len(candles))}


def build_context(sources: dict[str, list[Candle]]) -> list[dict]:
    required = (*ETF_SOURCES, "VIX", "VIX3M", "DXY")
    missing = sorted(set(required)-sources.keys())
    if missing:
        raise ValueError("Missing validated context sources: " + ", ".join(missing))
    series = {s: _series_features(sources[s]) for s in required}
    common = sorted(set.intersection(*(set(v) for v in series.values())))
    if len(common) < 260:
        raise ValueError("Insufficient common context history")
    breadth = [fmean(series[s][d]["above"] for s in SECTORS) for d in common]
    rows = []
    for i in range(5, len(common)):
        d = common[i]
        v = {s: rows[d] for s, rows in series.items()}
        values = [breadth[i], breadth[i]-breadth[i-5], fmean(v[s]["r20"] > 0 for s in SECTORS),
                  stdev(v[s]["z20"] for s in SECTORS),
                  fmean(v[s]["r20"] for s in ("XLY", "XLI", "XLF"))-fmean(v[s]["r20"] for s in ("XLP", "XLU", "XLV")),
                  v["RSP"]["r20"]-v["SPY"]["r20"], v["HYG"]["r5"]-v["IEF"]["r5"],
                  v["HYG"]["r20"]-v["IEF"]["r20"], v["TLT"]["z20"], v["DXY"]["z20"],
                  v["SPY"]["z20"], math.log(v["VIX"]["close"]/20),
                  v["VIX"]["close"]/v["VIX3M"]["close"], v["VIX"]["r5"]]
        rows.append({"date": d, "values": dict(zip(CONTEXT_FEATURES, values))})
    return rows


def attach_context(rows: list[dict], context: list[dict]) -> list[dict]:
    dates = [r["date"] for r in context]
    result = []
    for row in rows:
        i = bisect_left(dates, row["date"]) - 1  # Strictly previous date, never same date.
        previous = context[i] if i >= 0 else None
        age = (date.fromisoformat(row["date"])-date.fromisoformat(previous["date"])).days if previous else None
        valid = age is not None and 1 <= age <= 5
        result.append({**row, "context_date": previous["date"] if previous else None,
                       "context_age_days": age, "context": previous["values"] if valid else None})
    return result
