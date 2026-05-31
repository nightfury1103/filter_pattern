from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from .direction import (
    backtest_direction,
    build_market_context,
    calculate_direction,
    collect_direction_backtest_samples,
    direction_report_from_samples,
)
from .models import Candle
from .providers import load_yahoo_ohlcv_many
from .scanner import _download_market_data, _expand_crypto_if_supported, _filter_markets
from .universe import get_universe


def run_direction_backtest(
    out_dir: str | Path,
    timeframe: str = "D1",
    period: str = "5y",
    universe_name: str = "default",
    markets: str | None = "all",
    data_provider: str = "yahoo",
    limit: int | None = None,
    horizon: int = 20,
    step: int = 5,
    min_history: int = 220,
) -> Path:
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    universe = _filter_markets(get_universe(universe_name), markets)
    universe, crypto_settings = _expand_crypto_if_supported(universe, data_provider)
    if limit is not None:
        universe = universe[:limit]

    downloaded = _download_direction_data(universe, period, timeframe, data_provider)
    candles_by_symbol: dict[str, list[Candle]] = {}
    markets_by_symbol: dict[str, str] = {}
    data_errors: dict[str, str] = {}
    for item in universe:
        data = downloaded.get(item.yahoo_symbol)
        if isinstance(data, Exception):
            data_errors[item.symbol] = str(data)
            continue
        if not data:
            data_errors[item.symbol] = f"No data returned for {item.yahoo_symbol}"
            continue
        candles_by_symbol[item.symbol] = data
        markets_by_symbol[item.symbol] = item.market

    report = backtest_direction(
        candles_by_symbol,
        markets_by_symbol=markets_by_symbol,
        horizon=horizon,
        step=step,
        min_history=min_history,
    )
    market_reports = _backtests_by_market(candles_by_symbol, markets_by_symbol, horizon, step, min_history)
    latest_rows = _latest_direction_rows(candles_by_symbol, markets_by_symbol)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timeframe": timeframe,
        "period": period,
        "universe": universe_name,
        "markets": markets or "all",
        "data_provider": data_provider,
        "symbol_count": len(universe),
        "usable_symbol_count": len(candles_by_symbol),
        "data_errors": data_errors,
        "crypto_settings": crypto_settings,
        "backtest": report.to_json(),
        "backtests_by_market": market_reports,
        "latest_direction": latest_rows,
    }
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_direction_backtest_html(payload, output_dir / "index.html")
    return results_path


def _download_direction_data(universe, period: str, timeframe: str, data_provider: str) -> dict[str, list[Candle] | Exception]:
    provider = data_provider.lower()
    if provider == "yahoo":
        return load_yahoo_ohlcv_many([item.yahoo_symbol for item in universe], period=period, timeframe=timeframe)
    return _download_market_data(universe, period, timeframe, data_provider)


def _latest_direction_rows(candles_by_symbol: dict[str, list[Candle]], markets_by_symbol: dict[str, str]) -> list[dict]:
    rows = []
    context_cache = {}
    for symbol, candles in candles_by_symbol.items():
        market = markets_by_symbol.get(symbol, "")
        if market not in context_cache:
            context_cache[market] = build_market_context(candles_by_symbol, markets_by_symbol, market)
        context = context_cache[market]
        snapshot = calculate_direction(candles, market, context)
        row = {
            "symbol": symbol,
            "market": market,
            "last_date": candles[-1].datetime.date().isoformat() if candles else "",
            **snapshot.to_json(),
        }
        if context is not None:
            row["market_context"] = context.to_json()
        rows.append(row)
    rows.sort(key=lambda row: (row["bias"], -float(row["confidence"]), row["symbol"]))
    return rows


def _backtests_by_market(
    candles_by_symbol: dict[str, list[Candle]],
    markets_by_symbol: dict[str, str],
    horizon: int,
    step: int,
    min_history: int,
) -> dict[str, dict]:
    market_symbols: dict[str, dict[str, list[Candle]]] = {}
    for symbol, candles in candles_by_symbol.items():
        market = markets_by_symbol.get(symbol, "Unknown")
        market_symbols.setdefault(market, {})[symbol] = candles
    reports = {}
    for market, market_candles in sorted(market_symbols.items()):
        samples = collect_direction_backtest_samples(
            market_candles,
            markets_by_symbol={symbol: market for symbol in market_candles},
            horizon=horizon,
            step=step,
            min_history=min_history,
        )
        report = direction_report_from_samples(samples, horizon=horizon, step=step, min_history=min_history).to_json()
        train_samples, test_samples = _walk_forward_split(samples)
        report["walk_forward"] = {
            "train": direction_report_from_samples(train_samples, horizon=horizon, step=step, min_history=min_history).to_json(),
            "test": direction_report_from_samples(test_samples, horizon=horizon, step=step, min_history=min_history).to_json(),
            "test_sample_ratio": round(len(test_samples) / len(samples), 4) if samples else 0.0,
        }
        report["validation"] = _market_validation(report)
        reports[market] = report
    return reports


def _walk_forward_split(samples: list) -> tuple[list, list]:
    if len(samples) < 10:
        return samples, []
    ordered = sorted(samples, key=lambda item: (item.date, item.symbol))
    split_index = max(1, int(len(ordered) * 0.70))
    return ordered[:split_index], ordered[split_index:]


def _market_validation(report: dict) -> dict:
    test = report.get("walk_forward", {}).get("test", {})
    return {
        "long_authority": _authority_status(test.get("long_allowed", {})),
        "short_authority": _authority_status(test.get("short_allowed", {})),
        "rule": "validated only when holdout samples >= 30, hit_rate >= 55%, average > 0, and median > 0",
    }


def _authority_status(bucket: dict) -> str:
    if int(bucket.get("sample_count", 0)) < 30:
        return "not_enough_samples"
    if float(bucket.get("hit_rate", 0.0)) < 0.55:
        return "failed_hit_rate"
    if float(bucket.get("average_return_pct", 0.0)) <= 0:
        return "failed_average_return"
    if float(bucket.get("median_return_pct", 0.0)) <= 0:
        return "failed_median_return"
    return "validated"


def _write_direction_backtest_html(payload: dict, output_path: Path) -> Path:
    bt = payload["backtest"]
    cards = "\n".join(
        [
            _bucket_card("LONG ALLOWED", bt["long_allowed"]),
            _bucket_card("SHORT ALLOWED", bt["short_allowed"]),
            _bucket_card("WATCH / BLOCKED", bt["watch_only"]),
        ]
    )
    rows = "\n".join(_latest_row(row) for row in payload.get("latest_direction", []))
    market_rows = "\n".join(_market_backtest_row(market, report) for market, report in payload.get("backtests_by_market", {}).items())
    errors = payload.get("data_errors", {})
    error_note = f"{len(errors)} data error(s)" if errors else "No data errors"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Direction Authority Backtest</title>
  <style>
    body {{ margin: 0; background: #0f172a; color: #e5e7eb; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; letter-spacing: 0; }}
    header {{ padding: 26px 32px; background: #111827; border-bottom: 1px solid rgba(255,255,255,.12); }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    header p {{ margin: 0; color: #9ca3af; line-height: 1.5; }}
    main {{ padding: 26px 32px 42px; }}
    section {{ background: #fff; color: #0f172a; border: 1px solid #dbe3ef; border-radius: 8px; padding: 20px; margin-bottom: 22px; }}
    h2 {{ margin: 0 0 12px; font-size: 20px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }}
    .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; }}
    .card strong {{ display: block; font-size: 13px; color: #475569; }}
    .card span {{ display: block; font-size: 24px; font-weight: 800; margin-top: 3px; }}
    .muted {{ color: #64748b; line-height: 1.5; }}
    .table-wrap {{ overflow: auto; border: 1px solid #e2e8f0; border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 10px 11px; border-bottom: 1px solid #e2e8f0; text-align: left; vertical-align: top; }}
    th {{ background: #f1f5f9; color: #334155; position: sticky; top: 0; }}
    .num {{ text-align: right; white-space: nowrap; }}
  </style>
</head>
<body>
  <header>
    <h1>Direction Authority Backtest</h1>
    <p>Generated {escape(payload["generated_at"])} · timeframe {escape(str(payload["timeframe"]))} · horizon {escape(str(bt["horizon"]))} bars · step {escape(str(bt["step"]))} · usable symbols {escape(str(payload["usable_symbol_count"]))}/{escape(str(payload["symbol_count"]))} · {escape(error_note)}</p>
  </header>
  <main>
    <section>
      <h2>Validation Summary</h2>
      <p class="muted">Allowed long returns are measured as forward return. Allowed short returns are inverted so positive means the short direction was correct. Watch/blocked rows are not trade signals; they show what the model refused to force.</p>
      <div class="cards">{cards}</div>
    </section>
    <section>
      <h2>Market-Level Validation</h2>
      <p class="muted">Use this section first. A market should earn authority on its own before it is mixed into a global summary.</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Market</th><th>Long Authority</th><th>Short Authority</th><th>Samples</th><th>Holdout Long</th><th>Holdout Hit</th><th>Holdout Avg</th><th>Holdout Median</th><th>Short Samples</th><th>Watch Samples</th></tr></thead>
          <tbody>{market_rows}</tbody>
        </table>
      </div>
    </section>
    <section>
      <h2>Latest Direction State</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Symbol</th><th>Market</th><th>Date</th><th>Bias</th><th>Phase</th><th>Trend</th><th>Momentum</th><th>Confidence</th><th>Filter</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _bucket_card(label: str, bucket: dict) -> str:
    return f"""<div class="card">
  <strong>{escape(label)}</strong>
  <span>{escape(str(round(bucket.get("hit_rate", 0) * 100, 1)))}%</span>
  <div class="muted">samples {escape(str(bucket.get("sample_count", 0)))} · avg {escape(str(bucket.get("average_return_pct", 0)))}% · median {escape(str(bucket.get("median_return_pct", 0)))}% · adverse {escape(str(bucket.get("average_adverse_return_pct", 0)))}%</div>
</div>"""


def _market_backtest_row(market: str, report: dict) -> str:
    validation = report.get("validation", {})
    test = report.get("walk_forward", {}).get("test", {})
    long_bucket = test.get("long_allowed", {})
    short_bucket = report.get("short_allowed", {})
    watch_bucket = report.get("watch_only", {})
    return f"""<tr>
  <td><strong>{escape(str(market))}</strong></td>
  <td>{escape(str(validation.get("long_authority", "unknown")))}</td>
  <td>{escape(str(validation.get("short_authority", "unknown")))}</td>
  <td class="num">{escape(str(report.get("sample_count", 0)))}</td>
  <td class="num">{escape(str(long_bucket.get("sample_count", 0)))}</td>
  <td class="num">{escape(str(round(long_bucket.get("hit_rate", 0) * 100, 1)))}%</td>
  <td class="num">{escape(str(long_bucket.get("average_return_pct", 0)))}%</td>
  <td class="num">{escape(str(long_bucket.get("median_return_pct", 0)))}%</td>
  <td class="num">{escape(str(short_bucket.get("sample_count", 0)))}</td>
  <td class="num">{escape(str(watch_bucket.get("sample_count", 0)))}</td>
</tr>"""


def _latest_row(row: dict) -> str:
    return f"""<tr>
  <td><strong>{escape(str(row["symbol"]))}</strong></td>
  <td>{escape(str(row.get("market", "")))}</td>
  <td>{escape(str(row["last_date"]))}</td>
  <td>{escape(str(row["bias"]))}</td>
  <td>{escape(str(row["phase"]))}</td>
  <td class="num">{escape(str(row["trend_score"]))}</td>
  <td class="num">{escape(str(row["momentum_score"]))}</td>
  <td class="num">{escape(str(row["confidence"]))}</td>
  <td>{escape(str(row["trade_filter"]))}</td>
</tr>"""
