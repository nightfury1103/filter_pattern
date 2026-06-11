from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
from os.path import relpath
from pathlib import Path
from urllib.parse import quote

from .exness import is_exness_supported_symbol


TRIGGER_WARNING_DISTANCE_PCT = 5.0
REVIEW_SETUP_LIMIT = 750


def write_html_report(results_path: str | Path, output_path: str | Path) -> Path:
    results_file = Path(results_path)
    output_file = Path(output_path)
    payload = json.loads(results_file.read_text())
    return write_html_payload(payload, output_file)


def apply_watchlist_changes(payload: dict, previous_results_path: str | Path | None) -> dict:
    if previous_results_path is None:
        _mark_first_run(payload)
        refresh_trigger_warnings(payload)
        return payload

    previous_path = Path(previous_results_path)
    if not previous_path.exists():
        _mark_first_run(payload)
        refresh_trigger_warnings(payload)
        return payload

    previous_payload = json.loads(previous_path.read_text())
    previous_candidates = previous_payload.get("candidates", [])
    previous_by_key = {_watchlist_key(item): item for item in previous_candidates}
    current_keys: set[tuple[str, ...]] = set()
    counts: dict[str, int] = defaultdict(int)

    for candidate in payload.get("candidates", []):
        key = _watchlist_key(candidate)
        current_keys.add(key)
        previous = previous_by_key.get(key)
        change = _candidate_change(candidate, previous)
        candidate["watchlist_change"] = change
        if previous is not None:
            candidate["previous_score"] = previous.get("evidence", {}).get("score")
            candidate["previous_status"] = previous.get("evidence", {}).get("status")
        counts[change] += 1

    dropped = []
    for key, previous in previous_by_key.items():
        if key in current_keys:
            continue
        dropped_item = _dropped_watchlist_item(previous)
        dropped.append(dropped_item)
        counts["DROPPED"] += 1

    dropped.sort(key=lambda item: (str(item.get("timeframe", "")), str(item.get("symbol", "")), str(item.get("setup", ""))))
    payload["watchlist_dropped"] = dropped
    payload["watchlist_changes"] = {
        "previous_results": str(previous_path),
        "previous_available": True,
        "counts": dict(sorted(counts.items())),
    }
    refresh_trigger_warnings(payload)
    return payload


def refresh_trigger_warnings(payload: dict) -> dict:
    near_matches = payload.get("near_matches") or _near_matches(payload.get("rejected", []))
    review_setups = payload.get("review_setups") or _review_setups(payload.get("rejected", []))
    payload["trigger_warnings"] = _trigger_warnings(payload.get("candidates", []) + near_matches + review_setups)
    return payload


def write_combined_html_report(results_paths: list[str | Path], output_path: str | Path, copy_assets: bool = False) -> Path:
    payload = combined_result_payload(results_paths)
    if copy_assets:
        materialize_combined_assets(payload, Path(output_path).parent)
    return write_html_payload(payload, output_path)


def write_combined_results_json(
    results_paths: list[str | Path],
    output_path: str | Path,
    copy_assets: bool = False,
    asset_root: str | Path | None = None,
) -> Path:
    output_file = Path(output_path)
    payload = combined_result_payload(results_paths)
    if copy_assets:
        materialize_combined_assets(payload, Path(asset_root) if asset_root is not None else output_file.parent)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2))
    return output_file


def write_combined_outputs(
    results_paths: list[str | Path],
    html_output_path: str | Path,
    results_output_path: str | Path | None = None,
    copy_assets: bool = False,
) -> tuple[Path, Path | None]:
    html_output = Path(html_output_path)
    payload = combined_result_payload(results_paths)
    if copy_assets:
        materialize_combined_assets(payload, html_output.parent)
    results_output = None
    if results_output_path is not None:
        results_output = Path(results_output_path)
        results_output.parent.mkdir(parents=True, exist_ok=True)
        results_output.write_text(json.dumps(payload, indent=2))
    return write_html_payload(payload, html_output), results_output


def combined_result_payload(results_paths: list[str | Path]) -> dict:
    payloads = []
    for results_path in results_paths:
        results_file = Path(results_path)
        if not results_file.exists():
            raise FileNotFoundError(f"Results file not found: {results_file}")
        payloads.append(json.loads(results_file.read_text()))
    if not payloads:
        raise ValueError("at least one results.json input is required")
    return _combined_payload(payloads, results_paths)


def materialize_combined_assets(payload: dict, output_dir: str | Path) -> dict:
    base_dir = Path(output_dir)
    for container, key, path_value in _payload_asset_paths(payload):
        source = Path(str(path_value))
        if not source.exists():
            continue
        destination = _combined_asset_destination(source, base_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        preview = _preview_path(str(source))
        if preview is not None and preview.exists():
            preview_destination = destination.parent / "preview" / destination.name
            preview_destination.parent.mkdir(parents=True, exist_ok=True)
            if preview.resolve() != preview_destination.resolve():
                shutil.copy2(preview, preview_destination)
        container[key] = str(destination)
    return payload


def write_html_payload(payload: dict, output_path: str | Path) -> Path:
    output_file = Path(output_path)
    candidates = payload.get("candidates", [])
    near_matches = payload.get("near_matches") or _near_matches(payload.get("rejected", []))
    review_setups = payload.get("review_setups") or _review_setups(payload.get("rejected", []))
    trigger_warnings = _trigger_warnings(candidates + near_matches + review_setups)
    not_configured = _not_configured_rows(payload.get("rejected", []))
    dropped = payload.get("watchlist_dropped", [])
    watchlist_changes = payload.get("watchlist_changes", {})
    change_counts = watchlist_changes.get("counts", {})
    scanned_by_market = payload.get("scanned_symbols_by_market") or _scanned_symbols_by_market(
        candidates + payload.get("rejected", [])
    )
    data_errors_by_market = payload.get("data_errors_by_market") or _data_errors_by_market(payload.get("rejected", []))
    markets = sorted(scanned_by_market)
    market_options = "\n".join(f'<option value="{escape(market)}">{escape(market)}</option>' for market in markets)
    technique_options = "\n".join(
        f'<option value="{escape(technique_name)}">{escape(technique_name)}</option>'
        for technique_name in _techniques_in_rows(
            candidates + near_matches + review_setups + trigger_warnings + not_configured + payload.get("rejected", [])
        )
    )
    setup_options = "\n".join(
        f'<option value="{escape(setup_name)}">{escape(setup_name.upper())}</option>'
        for setup_name in _setups_in_rows(
            candidates + near_matches + review_setups + trigger_warnings + not_configured + payload.get("rejected", [])
        )
    )
    timeframe_options = "\n".join(
        f'<option value="{escape(timeframe)}">{escape(timeframe)}</option>'
        for timeframe in _timeframes_in_rows(
            candidates + near_matches + review_setups + trigger_warnings + not_configured + payload.get("rejected", []), payload
        )
    )
    change_options = "\n".join(
        f'<option value="{escape(change)}">{escape(_change_label(change))}</option>'
        for change in _changes_in_rows(candidates, dropped)
    )

    rows = "\n".join(_candidate_card(candidate, output_file.parent) for candidate in candidates)
    setup = payload.get("config", {}).get("setup", "all")
    timeframe = str(payload.get("timeframe") or payload.get("config", {}).get("timeframe", "D1"))
    if not rows:
        rows = (
            f'<section class="empty">No qualified {escape(timeframe)} {escape(str(payload.get("config", {}).get("technique", "vcp")))} '
            f'candidate(s) found.</section>'
        )
    near_rows = "\n".join(_near_match_card(candidate, output_file.parent) for candidate in near_matches)
    if near_rows:
        near_rows = f"""
    <h2>Near Matches</h2>
    <p class="section-note">These are not qualified entry setups. They passed many checks but failed at least one strict setup rule.</p>
    {near_rows}
"""
    review_rows = "\n".join(_review_setup_card(candidate, output_file.parent) for candidate in review_setups)
    if review_rows:
        review_rows = f"""
    <h2>Continue Watching</h2>
    <p class="section-note">These rejected, failed, late, or already-triggered structures still have recognizable pattern context. Keep them visible for manual lifecycle review because a setup can rebuild and trigger again.</p>
    {review_rows}
"""
    warning_rows = "\n".join(_trigger_warning_card(item, output_file.parent) for item in trigger_warnings)
    if warning_rows:
        warning_rows = f"""
    <h2>Near Break / Trigger Warnings</h2>
    <p class="section-note">Symbols whose current price is close to the trigger/pivot, or whose setup has just triggered. Strict-failed rows remain manual-review only.</p>
    {warning_rows}
"""
    not_configured_rows = "\n".join(_not_configured_card(item) for item in not_configured)
    if not_configured_rows:
        not_configured_rows = f"""
    <h2>Not Configured</h2>
    <p class="section-note">These setup buckets were evaluated as placeholders. They are shown so setup filtering is visible before exact rules are implemented.</p>
    {not_configured_rows}
"""
    coverage_rows = _coverage_section(scanned_by_market, data_errors_by_market)
    dropped_rows = "\n".join(_dropped_card(item) for item in dropped)
    if dropped_rows:
        dropped_rows = f"""
    <h2>Dropped Since Last Run</h2>
    <p class="section-note">These were qualified in the previous run but are no longer on the active watchlist.</p>
    {dropped_rows}
"""
    broker_filter = payload.get("config", {}).get("broker_filter", "all")
    technique = payload.get("config", {}).get("technique", "vcp")
    data_errors = sum(data_errors_by_market.values())
    exness_count = _exness_supported_count(candidates)
    avg_score = _average_candidate_score(candidates)
    triggered = sum(1 for item in candidates if str(item.get("evidence", {}).get("status", "")).upper() == "TRIGGERED")
    waiting = sum(
        1
        for item in candidates
        if str(item.get("evidence", {}).get("status", "")).upper() in {"WAITING", "NEAR_PIVOT", "READY_NEAR_PIVOT"}
    )
    setup_panel = _setup_distribution_panel(candidates)
    market_panel = _market_distribution_panel(scanned_by_market, data_errors_by_market)
    rrg_overview = _rrg_market_overview_section(candidates + trigger_warnings + review_setups + near_matches)
    new_count = int(change_counts.get("NEW", 0))
    dropped_count = len(dropped)
    changed_count = sum(int(change_counts.get(key, 0)) for key in ("NEW", "TRIGGERED", "IMPROVED", "WEAKER", "STATUS_CHANGED"))

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(timeframe)} Pattern Scanner Report</title>
  <style>
    :root {{
      color-scheme: light;
      --text: #e7ecf3;
      --muted: #8d98aa;
      --line: #2a3242;
      --line-strong: #3d4658;
      --panel: #ffffff;
      --dark-panel: #111722;
      --dark-panel-2: #0c111a;
      --chrome: #151922;
      --bg: #0f1218;
      --accent: #2563eb;
      --good: #15803d;
      --warn: #b45309;
      --bad: #b91c1c;
      --shadow: 0 16px 40px rgba(0, 0, 0, 0.28);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    .app {{
      min-height: 100vh;
      display: block;
    }}
    aside.nav {{
      display: none;
      background: #101827;
      color: #e5e7eb;
      padding: 22px 18px;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 22px;
    }}
    .mark {{
      width: 34px;
      height: 34px;
      border: 2px solid #93c5fd;
      border-radius: 8px;
      display: grid;
      place-items: center;
      color: #bfdbfe;
      font-weight: 800;
    }}
    .brand strong {{ display: block; font-size: 15px; }}
    .brand span {{ display: block; color: #9ca3af; font-size: 12px; }}
    .side-section {{
      border-top: 1px solid rgba(229, 231, 235, 0.14);
      padding-top: 16px;
      margin-top: 16px;
    }}
    .side-label {{
      font-size: 11px;
      text-transform: uppercase;
      color: #94a3b8;
      font-weight: 800;
      margin-bottom: 10px;
    }}
    .nav-pill {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 34px;
      padding: 0 10px;
      border-radius: 7px;
      color: #d1d5db;
      font-size: 13px;
      margin: 4px 0;
    }}
    .nav-pill.active {{
      background: #1e293b;
      color: #ffffff;
      outline: 1px solid rgba(147, 197, 253, 0.25);
    }}
    .count {{
      font-size: 11px;
      color: #cbd5e1;
      background: rgba(255, 255, 255, 0.08);
      padding: 2px 7px;
      border-radius: 999px;
    }}
    .page {{
      min-width: 0;
      padding: 0 14px 18px;
      max-width: none;
      margin: 0 auto;
    }}
    header {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: start;
      margin: 0 -14px 0;
      padding: 10px 14px;
      background: var(--chrome);
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 30;
    }}
    h1 {{ margin: 0 0 6px; font-size: 24px; letter-spacing: 0; }}
    .summary {{ color: var(--muted); font-size: 13px; }}
    .run-meta {{
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
      max-width: 520px;
    }}
    .tag {{
      border: 1px solid var(--line);
      background: #0f141e;
      color: #cbd5e1;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      white-space: nowrap;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(10, minmax(104px, 1fr));
      gap: 10px;
      margin: 12px 0 10px;
    }}
    .stat {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #0f141e;
      min-height: 76px;
    }}
    .stat strong {{ display: block; color: #ffffff; font-size: 24px; line-height: 1; margin-bottom: 8px; }}
    .stat span {{ color: var(--muted); font-size: 13px; }}
    .toolbar {{
      display: grid;
      grid-template-columns: minmax(280px, 2fr) repeat(4, minmax(132px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
      position: sticky;
      top: 58px;
      z-index: 20;
      background: rgba(15, 18, 24, 0.98);
      padding: 14px 0 12px;
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--line);
    }}
    input, select {{
      width: 100%;
      height: 38px;
      border: 1px solid var(--line-strong);
      border-radius: 7px;
      padding: 0 10px;
      background: #0f141e;
      color: var(--text);
      font: inherit;
      font-size: 13px;
    }}
    .filter-count {{
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 13px;
    }}
    .rrg-overview {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #101723;
      margin: 12px 0 14px;
      padding: 14px;
    }}
    .overview-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      margin-bottom: 12px;
    }}
    .overview-head h2 {{
      margin: 0 0 4px;
      font-size: 18px;
      color: #f8fafc;
    }}
    .overview-head p {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .overview-score {{
      display: grid;
      grid-template-columns: repeat(3, minmax(86px, 1fr));
      gap: 8px;
      min-width: 300px;
    }}
    .overview-score div {{
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 8px;
      background: #0f141e;
    }}
    .overview-score strong {{
      display: block;
      color: #ffffff;
      font-size: 20px;
      line-height: 1;
      margin-bottom: 5px;
    }}
    .overview-score span {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .rrg-chart-shell {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0f141e;
      padding: 10px;
      margin-bottom: 12px;
    }}
    .rrg-chart-title {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: #cbd5e1;
      font-size: 12px;
      font-weight: 800;
      margin: 0 0 8px;
    }}
    .rrg-chart-title span {{
      color: var(--muted);
      font-weight: 700;
    }}
    .rrg-svg {{
      width: 100%;
      height: auto;
      display: block;
      border-radius: 6px;
      background: #0b1220;
    }}
    .rrg-axis {{ stroke: #e5e7eb; stroke-width: 1.4; opacity: .86; }}
    .rrg-gridline {{ stroke: #334155; stroke-width: .8; opacity: .55; }}
    .rrg-tail {{ fill: none; stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; opacity: .92; }}
    .rrg-dot {{ stroke: #f8fafc; stroke-width: 1.8; }}
    .rrg-label {{ fill: #f8fafc; font-size: 12px; font-weight: 800; paint-order: stroke; stroke: #0b1220; stroke-width: 3px; stroke-linejoin: round; }}
    .rrg-small-label {{ fill: #cbd5e1; font-size: 11px; font-weight: 700; }}
    .rrg-legend {{ fill: #cbd5e1; font-size: 11px; font-weight: 700; }}
    .quadrant-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }}
    .quadrant-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0f141e;
      overflow: hidden;
      min-height: 178px;
    }}
    .quadrant-card.leading {{ border-top: 4px solid #22c55e; }}
    .quadrant-card.improving {{ border-top: 4px solid #38bdf8; }}
    .quadrant-card.weakening {{ border-top: 4px solid #f97316; }}
    .quadrant-card.lagging {{ border-top: 4px solid #ef4444; }}
    .quadrant-head {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      padding: 10px;
      border-bottom: 1px solid var(--line);
    }}
    .quadrant-head strong {{ color: #ffffff; }}
    .quadrant-head span {{ color: var(--muted); font-size: 12px; }}
    .quadrant-count {{
      min-width: 32px;
      height: 32px;
      display: grid;
      place-items: center;
      border-radius: 7px;
      background: #172033;
      color: #ffffff;
      font-weight: 800;
    }}
    .quadrant-list {{
      display: grid;
      gap: 6px;
      padding: 10px;
    }}
    .overview-symbol {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      border: 1px solid rgba(148, 163, 184, 0.18);
      border-radius: 7px;
      padding: 7px;
      background: #111a29;
      font-size: 12px;
    }}
    .overview-symbol b {{ color: #f8fafc; overflow-wrap: anywhere; }}
    .overview-symbol span {{ color: #9ca3af; display: block; margin-top: 2px; }}
    .overview-symbol em {{ color: #cbd5e1; font-style: normal; font-variant-numeric: tabular-nums; }}
    .market-rrg-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 8px;
      margin-top: 12px;
    }}
    .market-rrg {{
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #0f141e;
      padding: 9px;
      font-size: 12px;
    }}
    .market-rrg strong {{ color: #f8fafc; display: block; margin-bottom: 7px; }}
    .market-bars {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 3px;
    }}
    .market-bars span {{
      min-height: 22px;
      display: grid;
      place-items: center;
      border-radius: 5px;
      color: #ffffff;
      font-size: 11px;
      font-weight: 800;
    }}
    .market-bars .leading {{ background: #15803d; }}
    .market-bars .improving {{ background: #0369a1; }}
    .market-bars .weakening {{ background: #c2410c; }}
    .market-bars .lagging {{ background: #b91c1c; }}
    .layout {{ display: block; }}
    .main-column {{ min-width: 0; }}
    .side-panel {{
      display: grid;
      gap: 12px;
      position: sticky;
      top: 112px;
      max-height: calc(100vh - 126px);
      overflow: auto;
    }}
    .panel {{
      background: var(--dark-panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .panel h3 {{ margin: 0 0 12px; font-size: 14px; }}
    .dist-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      min-height: 30px;
      font-size: 12px;
      border-bottom: 1px solid var(--line);
    }}
    .dist-row:last-child {{ border-bottom: 0; }}
    .bar {{
      height: 7px;
      background: #e2e8f0;
      border-radius: 999px;
      overflow: hidden;
      margin-top: 4px;
    }}
    .bar span {{ display: block; height: 100%; background: var(--accent); border-radius: inherit; }}
    article {{
      background: var(--dark-panel);
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      margin-bottom: 22px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 11px 14px;
      border-bottom: 1px solid var(--line);
      background: #111722;
    }}
    .symbol {{ font-size: 19px; font-weight: 800; }}
    .meta, .reasons, .metrics {{ color: var(--muted); font-size: 13px; }}
    .score {{
      min-width: 70px;
      height: 54px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      background: #eff6ff;
      color: #1d4ed8;
      border: 1px solid #bfdbfe;
      font-size: 18px;
      font-weight: 800;
      text-align: center;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 700;
      background: #eff6ff;
      color: #1d4ed8;
      margin-left: 8px;
    }}
    .badge.near-badge {{ background: #fffbeb; color: var(--warn); }}
    .badge.warning-badge {{ background: #fef3c7; color: #92400e; border: 1px solid #f59e0b; }}
    .badge.triggered {{ background: #ecfdf5; color: var(--good); }}
    .badge.waiting {{ background: #fffbeb; color: var(--warn); }}
    .badge.short {{ background: #fef2f2; color: var(--bad); }}
    .badge.long {{ background: #eff6ff; color: #1d4ed8; }}
    .badge.change-new {{ background: #ecfdf5; color: var(--good); }}
    .badge.change-triggered {{ background: #eff6ff; color: #1d4ed8; }}
    .badge.change-improved {{ background: #f0fdf4; color: #166534; }}
    .badge.change-weaker {{ background: #fff7ed; color: #c2410c; }}
    .badge.change-dropped {{ background: #fef2f2; color: var(--bad); }}
    .badge.change-unchanged, .badge.change-first_run {{ background: #f8fafc; color: #475569; }}
    .card-content {{
      display: block;
      background: #ffffff;
    }}
    .card-content.no-chart {{
      grid-template-columns: 1fr;
    }}
    .chart-frame {{
      background: #ffffff;
      border-bottom: 1px solid #cbd5e1;
      min-width: 0;
    }}
    .chart-frame img {{
      display: block;
      width: 100%;
      height: auto;
      background: #ffffff;
    }}
    .lazy-chart {{
      aspect-ratio: 16 / 9;
      object-fit: contain;
    }}
    .chart-pair {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 14px;
      padding: 14px;
      align-items: start;
    }}
    .chart-tile {{
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      overflow: hidden;
      background: #ffffff;
    }}
    .chart-tile strong {{
      display: block;
      padding: 8px 10px;
      border-bottom: 1px solid #e5e7eb;
      background: #f8fafc;
      color: #334155;
      font-size: 12px;
      text-transform: uppercase;
    }}
    .chart-tile img {{
      border: 0;
    }}
    .rrg-reference {{
      border: 1px solid #dbeafe;
      border-radius: 8px;
      background: #f8fbff;
      padding: 10px;
      margin-bottom: 12px;
      color: #1f2937;
    }}
    .rrg-reference .reasons {{
      color: #1f2937;
      font-weight: 800;
      margin-bottom: 8px;
    }}
    .rrg-reference .meta {{
      color: #64748b;
      font-size: 12px;
    }}
    .body {{
      padding: 14px;
      min-width: 0;
      background: #ffffff;
      color: #111827;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 12px;
    }}
    .metric {{
      border: 1px solid #e5e7eb;
      border-radius: 7px;
      padding: 8px;
      background: #fbfdff;
      min-height: 54px;
    }}
    .metric strong {{ display: block; color: var(--text); margin-top: 4px; }}
    details.lower-tf-review {{
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      background: #f8fafc;
      margin-top: 14px;
      overflow: hidden;
    }}
    details.lower-tf-review summary {{
      cursor: pointer;
      padding: 10px 12px;
      font-weight: 800;
      color: #1f2937;
      background: #ffffff;
      border-bottom: 1px solid #e5e7eb;
    }}
    details.lower-tf-review[open] summary {{ border-bottom-color: #cbd5e1; }}
    .lower-tf-body {{
      padding: 12px;
      display: grid;
      gap: 12px;
    }}
    .lower-tf-card {{
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      background: #ffffff;
      overflow: hidden;
    }}
    .lower-tf-head {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 8px;
      padding: 10px 12px;
      border-bottom: 1px solid #e5e7eb;
      font-size: 13px;
    }}
    .lower-tf-head strong {{ color: var(--text); }}
    .lower-tf-note {{
      padding: 10px 12px;
      color: var(--muted);
      font-size: 13px;
      border-bottom: 1px solid #e5e7eb;
    }}
    .lower-tf-card img {{ border-bottom: 0; }}
    ul {{ margin: 8px 0 0; padding-left: 20px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .empty {{
      background: var(--dark-panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 24px;
      color: var(--muted);
    }}
    h2 {{ margin: 36px 0 8px; font-size: 22px; }}
    .main-column h2 {{ color: #f8fafc; }}
    .main-column > h2:first-child {{ margin-top: 0; }}
    .section-note {{ margin: 0 0 16px; color: var(--muted); }}
    .near {{
      overflow: hidden;
    }}
    .near .failures {{ color: #991b1b; }}
    details.coverage {{
      background: var(--dark-panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px 20px;
      margin-bottom: 24px;
    }}
    details.coverage summary {{
      cursor: pointer;
      font-weight: 700;
    }}
    .coverage-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-top: 16px;
    }}
    .coverage-market {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .coverage-market h3 {{
      margin: 0 0 8px;
      font-size: 15px;
    }}
    .symbols {{
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      line-height: 1.6;
      overflow-wrap: anywhere;
    }}
    .symbol-chip {{
      display: inline-block;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      padding: 2px 6px;
      margin: 2px;
      background: #0f141e;
      color: #cbd5e1;
    }}
    .data-errors {{
      margin-top: 12px;
      color: #991b1b;
      font-size: 13px;
    }}
    @media (max-width: 1180px) {{
      .app {{ grid-template-columns: 1fr; }}
      aside.nav {{ position: static; height: auto; }}
      .layout {{ display: block; }}
      .side-panel {{ position: static; }}
      .stats {{ grid-template-columns: repeat(4, 1fr); }}
      .toolbar {{ grid-template-columns: repeat(2, 1fr); }}
      .overview-head {{ display: block; }}
      .overview-score {{ min-width: 0; margin-top: 12px; }}
      .quadrant-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .card-content {{ grid-template-columns: 1fr; }}
      .chart-pair {{ grid-template-columns: 1fr; }}
      .chart-frame {{ border-bottom: 1px solid #cbd5e1; }}
    }}
    @media (max-width: 720px) {{
      .page {{ padding: 16px; }}
      header {{ grid-template-columns: 1fr; }}
      .run-meta {{ justify-content: flex-start; }}
      .toolbar {{ grid-template-columns: 1fr; position: static; }}
      .card-head {{ flex-direction: column; }}
      .score {{ text-align: left; }}
      .overview-score, .quadrant-grid {{ grid-template-columns: 1fr; }}
      .stats, .metrics {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="nav">
      <div class="brand"><div class="mark">FP</div><div><strong>Filter Pattern</strong><span>{escape(timeframe)} multi-setup scanner</span></div></div>
      <div class="side-section">
        <div class="side-label">Report</div>
        <div class="nav-pill active"><span>All Qualified</span><span class="count">{len(candidates)}</span></div>
        <div class="nav-pill"><span>Triggered</span><span class="count">{triggered}</span></div>
        <div class="nav-pill"><span>Waiting</span><span class="count">{waiting}</span></div>
      <div class="nav-pill"><span>Warnings</span><span class="count">{len(trigger_warnings)}</span></div>
      <div class="nav-pill"><span>Continue Watching</span><span class="count">{len(review_setups)}</span></div>
      <div class="nav-pill"><span>Near Match</span><span class="count">{len(near_matches)}</span></div>
      <div class="nav-pill"><span>Exness Supported</span><span class="count">{exness_count}</span></div>
      </div>
      <div class="side-section">
        <div class="side-label">Setups</div>
        {_setup_nav_items(candidates)}
      </div>
      <div class="side-section">
        <div class="side-label">Markets</div>
        {_market_nav_items(scanned_by_market)}
      </div>
    </aside>
    <main class="page">
      <header>
        <div>
          <h1>All Pattern Scanner Report</h1>
          <div class="summary">
            {escape(timeframe)} Scanner Report · Generated {escape(payload.get("generated_at", ""))} ·
            Technique: {escape(technique)} · Setup: {escape(setup)}
          </div>
        </div>
        <div class="run-meta">
          <span class="tag">Universe: {escape(str(payload.get("config", {}).get("universe", "csv")))}</span>
          <span class="tag">Timeframe: {escape(timeframe)}</span>
          <span class="tag">Broker: {escape(broker_filter)}</span>
          <span class="tag">Source: {escape(str(payload.get("config", {}).get("data_source", "CSV")))}</span>
        </div>
      </header>
      <section class="stats">
        <div class="stat"><strong>{escape(str(payload.get("scanned_symbols", 0)))}</strong><span>Scanned</span></div>
        <div class="stat"><strong>{escape(str(len(candidates)))}</strong><span>Qualified</span></div>
        <div class="stat"><strong>{escape(str(len(trigger_warnings)))}</strong><span>Near break warnings</span></div>
        <div class="stat"><strong>{escape(str(triggered))}</strong><span>Triggered</span></div>
        <div class="stat"><strong>{escape(str(waiting))}</strong><span>Waiting / near pivot</span></div>
        <div class="stat"><strong>{escape(str(new_count))}</strong><span>New since last run</span></div>
        <div class="stat"><strong>{escape(str(changed_count))}</strong><span>Changed</span></div>
        <div class="stat"><strong>{escape(str(dropped_count))}</strong><span>Dropped</span></div>
        <div class="stat"><strong>{escape(avg_score)}</strong><span>Average score</span></div>
        <div class="stat"><strong>{escape(str(data_errors))}</strong><span>Data unavailable</span></div>
      </section>
      {rrg_overview}
      <div class="toolbar">
        <input id="search" type="search" placeholder="Search symbol, setup, market, TradingView id">
        <select id="timeframeFilter"><option value="all">All timeframes</option>{timeframe_options}</select>
        <select id="marketFilter"><option value="all">All markets</option>{market_options}</select>
        <select id="brokerFilter"><option value="all">All broker support</option><option value="exness">Exness supported</option><option value="not-exness">Not Exness supported</option></select>
        <select id="statusFilter">
          <option value="all">All statuses</option>
          <option value="warning">Near break warning</option>
          <option value="qualified">Qualified</option>
          <option value="review">Continue watching</option>
          <option value="near">Near match</option>
          <option value="dropped">Dropped</option>
          <option value="not_configured">Not configured</option>
          <option value="coverage">Coverage</option>
        </select>
        <select id="techniqueFilter"><option value="all">All techniques</option>{technique_options}</select>
        <select id="setupFilter"><option value="all">All setups</option>{setup_options}</select>
        <select id="directionFilter"><option value="all">Long + Short</option><option value="long">Long</option><option value="short">Short</option></select>
        <select id="changeFilter"><option value="all">All changes</option>{change_options}</select>
        <select id="scoreFilter"><option value="0">Score 0+</option><option value="80">Score 80+</option><option value="85">Score 85+</option><option value="90">Score 90+</option><option value="95">Score 95+</option></select>
      </div>
      <div id="filterCount" class="filter-count"></div>
      <div class="layout">
        <section class="main-column">
          {coverage_rows}
          {warning_rows}
          <h2>Candidates</h2>
          {rows}
          {dropped_rows}
          {review_rows}
          {near_rows}
          {not_configured_rows}
        </section>
      </div>
    </main>
  </div>
  <script>
    const search = document.getElementById('search');
    const timeframeFilter = document.getElementById('timeframeFilter');
    const marketFilter = document.getElementById('marketFilter');
    const brokerFilter = document.getElementById('brokerFilter');
    const statusFilter = document.getElementById('statusFilter');
    const techniqueFilter = document.getElementById('techniqueFilter');
    const setupFilter = document.getElementById('setupFilter');
    const directionFilter = document.getElementById('directionFilter');
    const changeFilter = document.getElementById('changeFilter');
    const scoreFilter = document.getElementById('scoreFilter');
    const filterCount = document.getElementById('filterCount');
    const coverageSection = document.getElementById('coverageSection');
    const filterable = Array.from(document.querySelectorAll('[data-filterable="true"]'));
    const deferredImages = Array.from(document.querySelectorAll('img[data-src]'));

    function loadDeferredImage(image) {{
      const src = image.dataset.src;
      if (!src) {{
        return;
      }}
      image.src = src;
      image.removeAttribute('data-src');
    }}

    if ('IntersectionObserver' in window) {{
      const imageObserver = new IntersectionObserver((entries, observer) => {{
        for (const entry of entries) {{
          if (entry.isIntersecting) {{
            loadDeferredImage(entry.target);
            observer.unobserve(entry.target);
          }}
        }}
      }}, {{ rootMargin: '800px 0px' }});
      for (const image of deferredImages) {{
        imageObserver.observe(image);
      }}
    }} else {{
      for (const image of deferredImages) {{
        loadDeferredImage(image);
      }}
    }}

    function applyFilters() {{
      const text = search.value.trim().toLowerCase();
      const timeframe = timeframeFilter.value;
      const market = marketFilter.value;
      const broker = brokerFilter.value;
      const status = statusFilter.value;
      const technique = techniqueFilter.value;
      const setup = setupFilter.value;
      const direction = directionFilter.value;
      const change = changeFilter.value;
      const minimumScore = Number(scoreFilter.value || '0');
      const filtersActive = Boolean(text) || timeframe !== 'all' || market !== 'all' || broker !== 'all' || status !== 'all' || technique !== 'all' || setup !== 'all' || direction !== 'all' || change !== 'all' || minimumScore > 0;
      let visibleResults = 0;
      for (const node of filterable) {{
        const nodeTimeframe = node.dataset.timeframe || '';
        const nodeMarket = node.dataset.market || '';
        const nodeStatus = node.dataset.status || '';
        const nodeExness = node.dataset.exness || '';
        const nodeTechnique = node.dataset.technique || '';
        const nodeSetup = node.dataset.setup || '';
        const nodeDirection = node.dataset.direction || '';
        const nodeChange = node.dataset.change || '';
        const nodeScore = Number(node.dataset.score || '0');
        const haystack = (node.dataset.symbols || node.textContent || '').toLowerCase();
        const matchesTimeframe = timeframe === 'all' || nodeStatus === 'coverage' || nodeTimeframe === timeframe;
        const matchesMarket = market === 'all' || nodeMarket === market;
        const matchesBroker = broker === 'all' || nodeStatus === 'coverage' || (broker === 'exness' && nodeExness === 'true') || (broker === 'not-exness' && nodeExness !== 'true');
        const matchesStatus = status === 'all' || nodeStatus === status;
        const matchesTechnique = technique === 'all' || nodeStatus === 'coverage' || nodeTechnique === technique;
        const matchesSetup = setup === 'all' || nodeStatus === 'coverage' || nodeSetup === setup;
        const matchesDirection = direction === 'all' || nodeStatus === 'coverage' || nodeDirection === direction;
        const matchesChange = change === 'all' || nodeStatus === 'coverage' || nodeChange === change;
        const matchesScore = nodeStatus === 'coverage' || nodeScore >= minimumScore;
        const matchesText = !text || haystack.includes(text);
        const visible = matchesTimeframe && matchesMarket && matchesBroker && matchesStatus && matchesTechnique && matchesSetup && matchesDirection && matchesChange && matchesScore && matchesText;
        node.style.display = visible ? '' : 'none';
        if (visible && node.classList.contains('result-card')) {{
          visibleResults += 1;
        }}
      }}
      if (coverageSection) {{
        coverageSection.style.display = status === 'coverage' || !filtersActive ? '' : 'none';
      }}
      filterCount.textContent = `${{visibleResults}} result card(s) visible`;
    }}

    search.addEventListener('input', applyFilters);
    timeframeFilter.addEventListener('change', applyFilters);
    marketFilter.addEventListener('change', applyFilters);
    brokerFilter.addEventListener('change', applyFilters);
    statusFilter.addEventListener('change', applyFilters);
    techniqueFilter.addEventListener('change', applyFilters);
    setupFilter.addEventListener('change', applyFilters);
    directionFilter.addEventListener('change', applyFilters);
    changeFilter.addEventListener('change', applyFilters);
    scoreFilter.addEventListener('change', applyFilters);
    applyFilters();
  </script>
</body>
</html>
"""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html)
    return output_file


def result_payload(candidates: list[dict], rejected: list[dict], config: dict) -> dict:
    near_matches = _near_matches(rejected)
    review_setups = _review_setups(rejected)
    scanned = candidates + rejected
    scanned_by_market = _scanned_symbols_by_market(scanned)
    trigger_warnings = _trigger_warnings(candidates + near_matches + review_setups)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timeframe": config.get("timeframe", "D1"),
        "scanned_symbols": sum(len(symbols) for symbols in scanned_by_market.values()),
        "evaluation_count": len(scanned),
        "qualified_count": len(candidates),
        "candidates": candidates,
        "near_matches": near_matches,
        "review_setups": review_setups,
        "trigger_warnings": trigger_warnings,
        "scanned_symbols_by_market": scanned_by_market,
        "data_errors_by_market": _data_errors_by_market(rejected),
        "rejected": rejected,
        "config": config,
    }


def _combined_payload(payloads: list[dict], source_paths: list[str | Path]) -> dict:
    candidates: list[dict] = []
    rejected: list[dict] = []
    dropped: list[dict] = []
    explicit_near_matches: list[dict] = []
    explicit_review_setups: list[dict] = []
    for payload in payloads:
        candidates.extend(payload.get("candidates", []))
        rejected.extend(payload.get("rejected", []))
        dropped.extend(payload.get("watchlist_dropped", []))
        explicit_near_matches.extend(payload.get("near_matches", []))
        explicit_review_setups.extend(payload.get("review_setups", []))

    timeframes = sorted(
        {
            str(item.get("timeframe", payload.get("timeframe", payload.get("config", {}).get("timeframe", "D1"))))
            for payload in payloads
            for item in payload.get("candidates", []) + payload.get("rejected", [])
        }
    )
    config = {
        "timeframe": "Mixed" if len(timeframes) > 1 else (timeframes[0] if timeframes else "D1"),
        "technique": "combined",
        "setup": "all",
        "report_sources": [str(path) for path in source_paths],
        "source_count": len(source_paths),
    }
    payload = result_payload(candidates, rejected, config)
    payload["near_matches"] = _combined_near_matches(explicit_near_matches, rejected)
    payload["review_setups"] = _combined_review_setups(explicit_review_setups, rejected)
    _attach_lower_timeframe_reviews(payload)
    payload["trigger_warnings"] = _trigger_warnings(candidates + payload["near_matches"] + payload["review_setups"])
    payload["watchlist_dropped"] = dropped
    payload["watchlist_changes"] = _watchlist_change_summary(candidates, dropped)
    return payload


def _combined_near_matches(explicit_rows: list[dict], rejected: list[dict]) -> list[dict]:
    rows = [dict(row) for row in explicit_rows] or _near_matches(rejected, limit=50)
    rows.sort(key=lambda item: _numeric(item.get("near_match_score")) or 0.0, reverse=True)
    return rows[:50]


def _combined_review_setups(explicit_rows: list[dict], rejected: list[dict]) -> list[dict]:
    rows = [dict(row) for row in explicit_rows] or _review_setups(rejected)
    rows.sort(
        key=lambda item: (
            _numeric(item.get("review_score")) or 0.0,
            _score_value(item) or 0.0,
            str(item.get("market", "")),
            str(item.get("symbol", "")),
            str(item.get("setup", "")),
        ),
        reverse=True,
    )
    return rows[:REVIEW_SETUP_LIMIT]


def _payload_asset_paths(value: object):
    if isinstance(value, dict):
        for key in ("chart_path", "rrg_chart_path"):
            path_value = value.get(key)
            if path_value:
                yield value, key, path_value
        for child in value.values():
            yield from _payload_asset_paths(child)
    elif isinstance(value, list):
        for item in value:
            yield from _payload_asset_paths(item)


def _combined_asset_destination(source: Path, output_dir: Path) -> Path:
    try:
        source.resolve().relative_to(output_dir.resolve())
        return source
    except ValueError:
        pass
    parts = source.parts
    for marker in ("d1-shards", "h4-shards"):
        if marker not in parts:
            continue
        index = parts.index(marker)
        relative = Path(*parts[index + 1 :])
        return output_dir / "assets" / relative
    return output_dir / "assets" / source.name


def _attach_lower_timeframe_reviews(payload: dict) -> None:
    candidates = payload.get("candidates", [])
    near_matches = payload.get("near_matches", [])
    review_setups = payload.get("review_setups", [])
    reviewable_rows = candidates + near_matches + review_setups
    lower_rows = [
        item
        for item in reviewable_rows
        if str(item.get("timeframe", "")).upper() == "H4"
        and item.get("chart_path")
    ]
    if not lower_rows:
        return

    for item in reviewable_rows:
        if str(item.get("timeframe", "")).upper() != "D1":
            continue
        reviews = _best_lower_timeframe_reviews(item, lower_rows)
        if not reviews:
            continue
        item["lower_timeframe_reviews"] = reviews

        evidence = item.get("evidence", {})
        status = str(evidence.get("status", "")).upper()
        if status not in {"WAITING", "NEAR_PIVOT", "READY_NEAR_PIVOT", "FORMING"}:
            continue
        distance = _numeric(evidence.get("distance_to_pivot_pct"))
        if distance is None or abs(distance) > TRIGGER_WARNING_DISTANCE_PCT:
            continue
        confirmation = next((review for review in reviews if review.get("volume_confirmed")), None)
        if confirmation is not None:
            item["lower_timeframe_confirmation"] = confirmation


def _best_lower_timeframe_reviews(item: dict, lower_rows: list[dict], limit: int = 3) -> list[dict]:
    direction = _direction_from_evidence(item.get("evidence", {}))
    matches = []
    for candidate in lower_rows:
        if str(candidate.get("symbol")) != str(item.get("symbol")):
            continue
        candidate_direction = _direction_from_evidence(candidate.get("evidence", {}))
        if direction and candidate_direction and candidate_direction != direction:
            continue
        if not _lower_timeframe_is_same_price_area(item, candidate):
            continue
        matches.append(candidate)
    if not matches:
        return []

    def rank(candidate: dict) -> tuple[int, int, int, float]:
        evidence = candidate.get("evidence", {})
        exact_setup = (
            str(candidate.get("technique")) == str(item.get("technique"))
            and str(candidate.get("setup")) == str(item.get("setup"))
        )
        volume_confirmed = _prefixed_evidence_line(evidence.get("reasons", []), "Trigger volume confirmed:") is not None
        triggered = str(evidence.get("status", "")).upper() == "TRIGGERED"
        return (1 if exact_setup else 0, 1 if volume_confirmed else 0, 1 if triggered else 0, _score_value(candidate) or 0.0)

    ranked = sorted(matches, key=rank, reverse=True)
    return [_lower_timeframe_review_payload(item) for item in ranked[:limit]]


def _lower_timeframe_is_same_price_area(higher_item: dict, lower_item: dict) -> bool:
    higher_evidence = higher_item.get("evidence", {})
    lower_evidence = lower_item.get("evidence", {})
    anchors = [
        _numeric(higher_evidence.get("pivot")),
        _numeric(higher_evidence.get("current_close")),
    ]
    lower_values = [
        _numeric(lower_evidence.get("pivot")),
        _numeric(lower_evidence.get("current_close")),
    ]
    anchors = [value for value in anchors if value and value > 0]
    lower_values = [value for value in lower_values if value and value > 0]
    if not anchors or not lower_values:
        return False
    for anchor in anchors:
        for value in lower_values:
            if abs(value - anchor) / anchor * 100 <= TRIGGER_WARNING_DISTANCE_PCT:
                return True
    return False


def _lower_timeframe_review_payload(item: dict) -> dict:
    evidence = item.get("evidence", {})
    volume_confirmed = _prefixed_evidence_line(evidence.get("reasons", []), "Trigger volume confirmed:")
    volume_not_confirmed = _prefixed_evidence_line(evidence.get("reasons", []), "Trigger volume not confirmed:")
    pre_trigger_building = _prefixed_evidence_line(evidence.get("reasons", []), "Pre-trigger volume building:")
    pre_trigger_watch = _prefixed_evidence_line(evidence.get("reasons", []), "Pre-trigger volume watch:")
    volume_detail = volume_confirmed or volume_not_confirmed or pre_trigger_building or pre_trigger_watch
    if volume_confirmed:
        volume_label = "Trigger volume confirmed"
    elif volume_not_confirmed:
        volume_label = "Trigger volume not confirmed"
    elif pre_trigger_building:
        volume_label = "Pre-trigger volume building"
    elif pre_trigger_watch:
        volume_label = "Pre-trigger volume watch"
    else:
        volume_label = "Volume not available"
    return {
        "timeframe": str(item.get("timeframe", "")),
        "technique": str(item.get("technique", "")),
        "setup": str(item.get("setup", "")),
        "status": str(evidence.get("status", "")),
        "score": evidence.get("score"),
        "trigger_level": evidence.get("pivot"),
        "current_price": evidence.get("current_close"),
        "distance_to_pivot_pct": evidence.get("distance_to_pivot_pct"),
        "chart_path": item.get("chart_path"),
        "volume_label": volume_label,
        "volume_detail": volume_detail,
        "volume_confirmed": volume_confirmed is not None,
        "note": (
            f"{item.get('timeframe')} {item.get('technique')} / {item.get('setup')} is triggered and latest closed candle "
            f"has confirmed volume: {volume_confirmed}"
            if volume_confirmed
            else ""
        ),
    }


def _mark_first_run(payload: dict) -> None:
    counts: dict[str, int] = defaultdict(int)
    for candidate in payload.get("candidates", []):
        candidate["watchlist_change"] = "FIRST_RUN"
        counts["FIRST_RUN"] += 1
    payload["watchlist_dropped"] = []
    payload["watchlist_changes"] = {
        "previous_results": None,
        "previous_available": False,
        "counts": dict(sorted(counts.items())),
    }


def _watchlist_change_summary(candidates: list[dict], dropped: list[dict]) -> dict:
    counts: dict[str, int] = defaultdict(int)
    previous_available = False
    for candidate in candidates:
        change = str(candidate.get("watchlist_change") or "UNKNOWN")
        counts[change] += 1
        if change != "FIRST_RUN":
            previous_available = True
    if dropped:
        previous_available = True
        counts["DROPPED"] += len(dropped)
    return {
        "previous_results": "combined source reports",
        "previous_available": previous_available,
        "counts": dict(sorted(counts.items())),
    }


def _watchlist_key(item: dict) -> tuple[str, ...]:
    evidence = item.get("evidence", {})
    return (
        str(item.get("timeframe", "")),
        str(item.get("market", "")),
        str(item.get("symbol", "")),
        str(item.get("technique", "")),
        str(item.get("setup", "")),
        _direction_from_evidence(evidence),
    )


def _candidate_change(candidate: dict, previous: dict | None) -> str:
    if previous is None:
        return "NEW"
    current_status = str(candidate.get("evidence", {}).get("status", "")).upper()
    previous_status = str(previous.get("evidence", {}).get("status", "")).upper()
    if current_status == "TRIGGERED" and previous_status != "TRIGGERED":
        return "TRIGGERED"

    current_score = _score_value(candidate)
    previous_score = _score_value(previous)
    if current_score is not None and previous_score is not None:
        delta = current_score - previous_score
        if delta >= 5:
            return "IMPROVED"
        if delta <= -5:
            return "WEAKER"
    if current_status != previous_status:
        return "STATUS_CHANGED"
    return "UNCHANGED"


def _score_value(item: dict) -> float | None:
    score = item.get("evidence", {}).get("score")
    if isinstance(score, int | float):
        return float(score)
    return None


def _numeric(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _dropped_watchlist_item(previous: dict) -> dict:
    evidence = previous.get("evidence", {})
    return {
        "symbol": previous.get("symbol", ""),
        "market": previous.get("market", ""),
        "tradingview_symbol": previous.get("tradingview_symbol", ""),
        "timeframe": previous.get("timeframe", ""),
        "technique": previous.get("technique", ""),
        "setup": previous.get("setup", ""),
        "direction": _direction_from_evidence(evidence),
        "previous_score": evidence.get("score"),
        "previous_status": evidence.get("status"),
        "watchlist_change": "DROPPED",
    }


def _average_candidate_score(candidates: list[dict]) -> str:
    scores = [
        item.get("evidence", {}).get("score")
        for item in candidates
        if isinstance(item.get("evidence", {}).get("score"), int | float)
    ]
    if not scores:
        return "n/a"
    return f"{sum(scores) / len(scores):.0f}"


def _setup_nav_items(candidates: list[dict]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for item in candidates:
        counts[_display_setup(item)] += 1
    return "".join(
        f'<div class="nav-pill"><span>{escape(setup)}</span><span class="count">{counts.get(setup, 0)}</span></div>'
        for setup in _all_setup_labels()
    )


def _market_nav_items(scanned_by_market: dict[str, list[str]]) -> str:
    return "".join(
        f'<div class="nav-pill"><span>{escape(market)}</span><span class="count">{len(symbols)}</span></div>'
        for market, symbols in sorted(scanned_by_market.items())
    )


def _setup_distribution_panel(candidates: list[dict]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for item in candidates:
        counts[_display_setup(item)] += 1
    maximum = max(counts.values() or [1])
    return "".join(
        f"""<div class="dist-row"><div>{escape(setup)}<div class="bar"><span style="width: {max(3, counts.get(setup, 0) / maximum * 100):.0f}%"></span></div></div><strong>{counts.get(setup, 0)}</strong></div>"""
        for setup in _all_setup_labels()
    )


def _market_distribution_panel(scanned_by_market: dict[str, list[str]], data_errors_by_market: dict[str, int]) -> str:
    if not scanned_by_market:
        return '<div class="dist-row"><span>No symbols</span><strong>0</strong></div>'
    return "".join(
        f"""<div class="dist-row"><span>{escape(market)}</span><strong>{len(symbols)} scanned{_data_error_suffix(data_errors_by_market.get(market, 0))}</strong></div>"""
        for market, symbols in sorted(scanned_by_market.items())
    )


def _data_error_suffix(count: int) -> str:
    return "" if count <= 0 else f" / {count} errors"


def _exness_supported_count(rows: list[dict]) -> int:
    return sum(1 for row in rows if _is_row_exness_supported(row))


def _is_row_exness_supported(row: dict) -> bool:
    market = str(row.get("market", ""))
    if market not in {"Commodity", "Forex", "US stock"}:
        return False
    return is_exness_supported_symbol(str(row.get("symbol", "")), market)


def _all_setup_labels() -> tuple[str, ...]:
    return (
        "Original VCP",
        "VCP 1C",
        "VCP 2C",
        "VCP 3C",
        "NH VCP",
        "ARB",
        "DD",
        "SB",
        "BB",
        "RB",
        "IRB",
        "Compression",
        "FB",
    )


def _chart_img(src: str, alt: str) -> str:
    alt_text = escape(alt)
    return (
        f'<img class="lazy-chart" data-src="{src}" alt="{alt_text}" loading="lazy" decoding="async" width="1920" height="1080">'
        f'<noscript><img src="{src}" alt="{alt_text}"></noscript>'
    )


def _chart_frame_html(item: dict, report_dir: Path, alt: str, label: str) -> str:
    chart_path = item.get("chart_path") or ""
    if not chart_path:
        return ""
    chart_src, chart_preview_src = _chart_sources(str(chart_path), report_dir)
    rrg = item.get("rrg") or {}
    rrg_chart = rrg.get("rrg_chart_path")
    if not rrg_chart:
        return f'<div class="chart-frame"><a class="chart-tile" href="{chart_src}">{_chart_img(chart_preview_src, alt)}</a></div>'

    rrg_src, rrg_preview_src = _chart_sources(str(rrg_chart), report_dir)
    confidence = rrg.get("confidence") or {}
    confidence_label = str(confidence.get("label") or "RRG Reference")
    return f"""<div class="chart-frame">
      <div class="chart-pair">
        <a class="chart-tile" href="{chart_src}"><strong>{escape(label)}</strong>{_chart_img(chart_preview_src, alt)}</a>
        <a class="chart-tile" href="{rrg_src}"><strong>RRG Confidence</strong>{_chart_img(rrg_preview_src, f'{item.get("symbol", "")} RRG confidence chart')}</a>
      </div>
      <div class="rrg-reference" style="margin:0 10px 10px;">
        <div class="reasons">{escape(confidence_label)}</div>
        <div class="meta">{escape(_rrg_reference_meta(rrg))}</div>
      </div>
    </div>"""


def _rrg_reference_panel(item: dict) -> str:
    rrg = item.get("rrg") or {}
    if not rrg:
        return ""
    confidence = rrg.get("confidence") or {}
    intent = rrg.get("stock_intent") or {}
    return f"""
      <div class="rrg-reference">
        <div class="reasons">RRG Confidence: {escape(str(confidence.get("label") or "RRG Reference"))}</div>
        <div class="metrics">
          <div class="metric"><span>Benchmark</span><strong>{escape(str(rrg.get("benchmark") or "-"))}</strong></div>
          <div class="metric"><span>Quadrant</span><strong>{escape(str(intent.get("quadrant") or "-"))}</strong></div>
          <div class="metric"><span>Head dx</span><strong>{escape(_fmt(intent.get("dx1")))}</strong></div>
          <div class="metric"><span>Head dy</span><strong>{escape(_fmt(intent.get("dy1")))}</strong></div>
        </div>
        <div class="meta">{escape(str(confidence.get("note") or "RRG is shown as reference only and does not block the pattern."))}</div>
      </div>"""


def _rrg_reference_meta(rrg: dict) -> str:
    confidence = rrg.get("confidence") or {}
    intent = rrg.get("stock_intent") or {}
    sector = str(rrg.get("sector") or "").strip()
    benchmark = str(rrg.get("benchmark") or "").strip()
    relation = f"{sector} vs {benchmark}" if sector and benchmark else (benchmark or sector or "RRG")
    quadrant = str(intent.get("quadrant") or "-")
    dx = _fmt(intent.get("dx1"))
    dy = _fmt(intent.get("dy1"))
    note = str(confidence.get("note") or "Reference only.")
    return f"{relation} · {quadrant} · head dx {dx} · head dy {dy}. {note}"


def _candidate_card(candidate: dict, report_dir: Path) -> str:
    evidence = candidate["evidence"]
    tv_symbol = candidate["tradingview_symbol"]
    chart_html = _chart_frame_html(candidate, report_dir, f'{candidate["symbol"]} proof chart', "Current Setup Pattern")
    reasons = "".join(f"<li>{escape(reason)}</li>" for reason in _clean_evidence_lines(evidence.get("reasons", []))[:8])
    tv_url = f"https://www.tradingview.com/chart/?symbol={quote(tv_symbol)}"
    pivot = _fmt(evidence.get("pivot"))
    close = _fmt(evidence.get("current_close"))
    distance = _fmt(evidence.get("distance_to_pivot_pct"), suffix="%")
    volume_ratio = _fmt(evidence.get("volume_dry_up_ratio"))
    lower_timeframe_confirmation = _lower_timeframe_confirmation_html(candidate, report_dir)
    direction_authority = _direction_authority_html(candidate)
    rrg_reference = _rrg_reference_panel(candidate)
    technique = candidate.get("technique", "vcp")
    setup = candidate.get("setup", "all")
    timeframe = str(candidate.get("timeframe", "D1"))
    status = str(evidence.get("status", "qualified"))
    direction = _direction_from_evidence(evidence)
    direction_badge = f'<span class="badge {escape(direction)}">{escape(direction.title())}</span>' if direction else ""
    status_class = "triggered" if status.upper() == "TRIGGERED" else "waiting"
    display_setup = _display_setup(candidate)
    change = str(candidate.get("watchlist_change", "FIRST_RUN"))
    change_badge = _change_badge(change)
    previous_score = candidate.get("previous_score")
    previous_status = candidate.get("previous_status")
    previous_text = ""
    if previous_score is not None or previous_status is not None:
        previous_text = f' · Previous: {escape(_fmt(previous_score))} / {escape(str(previous_status or "n/a"))}'

    exness_supported = _is_row_exness_supported(candidate)

    return f"""<article class="result-card" data-filterable="true" data-status="qualified" data-timeframe="{escape(timeframe)}" data-market="{escape(candidate["market"])}" data-technique="{escape(technique)}" data-setup="{escape(setup)}" data-direction="{escape(direction)}" data-change="{escape(change)}" data-score="{escape(str(evidence.get("score", 0)))}" data-exness="{str(exness_supported).lower()}" data-symbols="{escape(candidate["symbol"] + " " + candidate["tradingview_symbol"] + " " + candidate["market"] + " " + timeframe + " " + technique + " " + setup + " " + display_setup + " " + direction + " " + change + " " + ("exness" if exness_supported else ""))}">
  <div class="card-head">
    <div>
      <div class="symbol">{escape(candidate["symbol"])} <span class="badge">{escape(display_setup)}</span>{direction_badge}<span class="badge {status_class}">{escape(status)}</span>{change_badge}{_exness_badge(exness_supported)}</div>
      <div class="meta">{escape(candidate["market"])} · {escape(timeframe)} · {escape(technique)} / {escape(setup)}{previous_text} · <a href="{tv_url}" target="_blank" rel="noreferrer">{escape(tv_symbol)}</a></div>
    </div>
    <div class="score">{escape(str(evidence.get("score", 0)))}</div>
  </div>
  <div class="card-content">
    {chart_html}
    <div class="body">
      <div class="metrics">
        <div class="metric"><span>Trigger / pivot</span><strong>{pivot}</strong></div>
        <div class="metric"><span>Current</span><strong>{close}</strong></div>
        <div class="metric"><span>Distance</span><strong>{distance}</strong></div>
        <div class="metric"><span>Volume ratio</span><strong>{volume_ratio}</strong></div>
      </div>
      {rrg_reference}
      {direction_authority}
      <div class="reasons">Candidate evidence:</div>
      <ul>{reasons}</ul>
      {lower_timeframe_confirmation}
    </div>
  </div>
</article>"""


def _lower_timeframe_confirmation_html(item: dict, report_dir: Path) -> str:
    reviews = item.get("lower_timeframe_reviews") or []
    confirmation = item.get("lower_timeframe_confirmation")
    if not reviews and not confirmation:
        return ""

    if not reviews and confirmation:
        reviews = [confirmation]
    summary = "Review lower timeframe"
    if confirmation:
        summary = f"Review lower timeframe: {escape(str(confirmation.get('timeframe') or 'lower TF'))} volume confirmed"

    cards = []
    for review in reviews:
        timeframe = str(review.get("timeframe") or "Lower TF")
        technique = str(review.get("technique") or "")
        setup = str(review.get("setup") or "")
        status = str(review.get("status") or "n/a")
        score = _fmt(review.get("score"))
        trigger = _fmt(review.get("trigger_level"))
        current = _fmt(review.get("current_price"))
        distance = _fmt(review.get("distance_to_pivot_pct"), suffix="%")
        volume_label = str(review.get("volume_label") or "Volume")
        volume_detail = str(review.get("volume_detail") or "Review volume on the lower timeframe chart.")
        chart_path = str(review.get("chart_path") or "")
        chart_html = ""
        if chart_path:
            chart_src, chart_preview_src = _chart_sources(chart_path, report_dir)
            chart_html = f'<a class="chart-tile" href="{chart_src}">{_chart_img(chart_preview_src, f"{timeframe} lower timeframe review chart")}</a>'
        cards.append(
            f"""<div class="lower-tf-card">
        <div class="lower-tf-head">
          <span><strong>{escape(timeframe)}</strong> · {escape(technique)} / {escape(setup)} · {escape(status)}</span>
          <span>score {escape(score)} · trigger {escape(trigger)} · current {escape(current)} · distance {escape(distance)}</span>
        </div>
        <div class="lower-tf-note"><strong>{escape(volume_label)}:</strong> {escape(volume_detail)}</div>
        {chart_html}
      </div>"""
        )
    cards_html = "\n".join(cards)
    return f"""
    <details class="lower-tf-review">
      <summary>{summary}</summary>
      <div class="lower-tf-body">
        <div class="lower-tf-note">Use this lower-timeframe chart for manual review only. Ignore the candidate if the lower timeframe is not compressed enough, has too much empty space, or does not agree with the higher-timeframe setup.</div>
        {cards_html}
      </div>
    </details>"""


def _direction_authority_html(item: dict) -> str:
    authority = item.get("direction_authority") or {}
    if not authority:
        return ""
    decision = str(authority.get("decision_label") or authority.get("decision") or "Watch only")
    bias = str(authority.get("bias") or "n/a")
    phase = str(authority.get("phase") or "n/a")
    confidence = _fmt(authority.get("confidence"))
    trend = _fmt(authority.get("trend_score"))
    momentum = _fmt(authority.get("momentum_score"))
    trade_filter = str(authority.get("trade_filter") or "")
    reasons = authority.get("reasons") or []
    reason_text = " · ".join(str(reason) for reason in reasons[:2])
    return f"""
      <div class="direction-authority">
        <div class="reasons">Direction authority:</div>
        <div class="metrics">
          <div class="metric"><span>Decision</span><strong>{escape(decision)}</strong></div>
          <div class="metric"><span>Phase</span><strong>{escape(phase)}</strong></div>
          <div class="metric"><span>Bias</span><strong>{escape(bias)}</strong></div>
          <div class="metric"><span>Confidence</span><strong>{escape(confidence)}</strong></div>
          <div class="metric"><span>Trend</span><strong>{escape(trend)}</strong></div>
          <div class="metric"><span>Momentum</span><strong>{escape(momentum)}</strong></div>
        </div>
        <ul><li>{escape(trade_filter)}</li>{f"<li>{escape(reason_text)}</li>" if reason_text else ""}</ul>
      </div>"""


def _near_match_card(candidate: dict, report_dir: Path) -> str:
    evidence = candidate["evidence"]
    tv_symbol = candidate["tradingview_symbol"]
    tv_url = f"https://www.tradingview.com/chart/?symbol={quote(tv_symbol)}"
    chart_html = _chart_frame_html(candidate, report_dir, f'{candidate["symbol"]} near-match VCP chart', "Near-Match Pattern")
    content_class = "card-content" if chart_html else "card-content no-chart"
    reasons = "".join(f"<li>{escape(reason)}</li>" for reason in _clean_evidence_lines(evidence.get("reasons", []))[:8])
    failures = "".join(f"<li>{escape(failure)}</li>" for failure in evidence.get("failures", [])[:4])
    distance = _fmt(evidence.get("distance_to_pivot_pct"), suffix="%")
    score = _fmt(candidate.get("near_match_score"))
    technique = candidate.get("technique", "vcp")
    setup = candidate.get("setup", "all")
    timeframe = str(candidate.get("timeframe", "D1"))
    direction = _direction_from_evidence(evidence)
    display_setup = _display_setup(candidate)
    change = str(candidate.get("watchlist_change", ""))
    lower_timeframe_confirmation = _lower_timeframe_confirmation_html(candidate, report_dir)
    direction_authority = _direction_authority_html(candidate)
    rrg_reference = _rrg_reference_panel(candidate)

    exness_supported = _is_row_exness_supported(candidate)

    return f"""<article class="near result-card" data-filterable="true" data-status="near" data-timeframe="{escape(timeframe)}" data-market="{escape(candidate["market"])}" data-technique="{escape(technique)}" data-setup="{escape(setup)}" data-direction="{escape(direction)}" data-change="{escape(change)}" data-score="{escape(str(evidence.get("score", 0)))}" data-exness="{str(exness_supported).lower()}" data-symbols="{escape(candidate["symbol"] + " " + candidate["tradingview_symbol"] + " " + candidate["market"] + " " + timeframe + " " + technique + " " + setup + " " + display_setup + " " + direction + " " + change + " " + ("exness" if exness_supported else ""))}">
  <div class="card-head">
    <div>
      <div class="symbol">{escape(candidate["symbol"])} <span class="badge near-badge">Near</span><span class="badge">{escape(display_setup)}</span>{_exness_badge(exness_supported)}</div>
      <div class="meta">{escape(candidate["market"])} · {escape(timeframe)} · {escape(technique)} / {escape(setup)} · <a href="{tv_url}" target="_blank" rel="noreferrer">{escape(tv_symbol)}</a></div>
    </div>
    <div class="score">{score}</div>
  </div>
  <div class="{content_class}">
    {chart_html}
    <div class="body">
      <div class="metrics">
        <div class="metric"><span>Distance</span><strong>{distance}</strong></div>
        <div class="metric"><span>Status</span><strong>Near</strong></div>
      </div>
      {rrg_reference}
      {direction_authority}
      <div class="reasons">Passed checks:</div>
      <ul>{reasons}</ul>
      <div class="reasons failures">Failed checks:</div>
      <ul class="failures">{failures}</ul>
      {lower_timeframe_confirmation}
    </div>
  </div>
</article>"""


def _review_setup_card(candidate: dict, report_dir: Path) -> str:
    evidence = candidate["evidence"]
    tv_symbol = candidate["tradingview_symbol"]
    tv_url = f"https://www.tradingview.com/chart/?symbol={quote(tv_symbol)}"
    chart_html = _chart_frame_html(candidate, report_dir, f'{candidate["symbol"]} lifecycle review chart', "Lifecycle Pattern")
    content_class = "card-content" if chart_html else "card-content no-chart"
    reasons = "".join(f"<li>{escape(reason)}</li>" for reason in _clean_evidence_lines(evidence.get("reasons", []))[:8])
    failures = "".join(f"<li>{escape(failure)}</li>" for failure in evidence.get("failures", [])[:5])
    trigger = _fmt(evidence.get("pivot"))
    current = _fmt(evidence.get("current_close"))
    distance = _fmt(evidence.get("distance_to_pivot_pct"), suffix="%")
    score = _fmt(candidate.get("review_score"))
    technique = candidate.get("technique", "vcp")
    setup = candidate.get("setup", "all")
    timeframe = str(candidate.get("timeframe", "D1"))
    status = str(evidence.get("status", "review"))
    direction = _direction_from_evidence(evidence)
    display_setup = _display_setup(candidate)
    change = str(candidate.get("watchlist_change", ""))
    lower_timeframe_confirmation = _lower_timeframe_confirmation_html(candidate, report_dir)
    direction_authority = _direction_authority_html(candidate)
    rrg_reference = _rrg_reference_panel(candidate)
    exness_supported = _is_row_exness_supported(candidate)

    return f"""<article class="near result-card" data-filterable="true" data-status="review" data-timeframe="{escape(timeframe)}" data-market="{escape(candidate["market"])}" data-technique="{escape(technique)}" data-setup="{escape(setup)}" data-direction="{escape(direction)}" data-change="{escape(change)}" data-score="{escape(str(evidence.get("score", 0)))}" data-exness="{str(exness_supported).lower()}" data-symbols="{escape(candidate["symbol"] + " " + candidate["tradingview_symbol"] + " " + candidate["market"] + " " + timeframe + " " + technique + " " + setup + " " + display_setup + " " + direction + " " + change + " " + ("exness" if exness_supported else ""))}">
  <div class="card-head">
    <div>
      <div class="symbol">{escape(candidate["symbol"])} <span class="badge near-badge">Review</span><span class="badge">{escape(display_setup)}</span><span class="badge">{escape(status)}</span>{_exness_badge(exness_supported)}</div>
      <div class="meta">{escape(candidate["market"])} · {escape(timeframe)} · {escape(technique)} / {escape(setup)} · <a href="{tv_url}" target="_blank" rel="noreferrer">{escape(tv_symbol)}</a></div>
    </div>
    <div class="score">{score}</div>
  </div>
  <div class="{content_class}">
    {chart_html}
    <div class="body">
      <div class="metrics">
        <div class="metric"><span>Trigger / pivot</span><strong>{trigger}</strong></div>
        <div class="metric"><span>Current</span><strong>{current}</strong></div>
        <div class="metric"><span>Distance</span><strong>{distance}</strong></div>
        <div class="metric"><span>Status</span><strong>{escape(status)}</strong></div>
      </div>
      {rrg_reference}
      {direction_authority}
      <div class="reasons">Detected structure:</div>
      <ul>{reasons}</ul>
      <div class="reasons failures">Why it is not qualified:</div>
      <ul class="failures">{failures}</ul>
      {lower_timeframe_confirmation}
    </div>
  </div>
</article>"""


def _trigger_warning_card(item: dict, report_dir: Path) -> str:
    evidence = item["evidence"]
    warning = item.get("trigger_warning", {})
    tv_symbol = item["tradingview_symbol"]
    tv_url = f"https://www.tradingview.com/chart/?symbol={quote(tv_symbol)}"
    chart_html = _chart_frame_html(item, report_dir, f'{item["symbol"]} near break warning chart', "Near-Break Pattern")
    content_class = "card-content" if chart_html else "card-content no-chart"
    technique = item.get("technique", "vcp")
    setup = item.get("setup", "all")
    timeframe = str(item.get("timeframe", "D1"))
    direction = _direction_from_evidence(evidence)
    display_setup = _display_setup(item)
    exness_supported = _is_row_exness_supported(item)
    score = _fmt(evidence.get("score"))
    trigger = _fmt(warning.get("trigger_level") or evidence.get("pivot"))
    current = _fmt(evidence.get("current_close"))
    distance = _fmt(warning.get("distance_pct"), suffix="%")
    warning_label = str(warning.get("label") or "Near break")
    note = str(warning.get("note") or "Price is close to the trigger/pivot.")
    lower_timeframe_confirmation = _lower_timeframe_confirmation_html(item, report_dir)
    direction_authority = _direction_authority_html(item)
    rrg_reference = _rrg_reference_panel(item)
    reasons = "".join(f"<li>{escape(reason)}</li>" for reason in _clean_evidence_lines(evidence.get("reasons", []))[:4])
    failures = "".join(f"<li>{escape(failure)}</li>" for failure in evidence.get("failures", [])[:3])
    failure_html = ""
    if failures:
        failure_html = f"""
    <div class="reasons failures">Strict warning:</div>
    <ul class="failures">{failures}</ul>"""
    return f"""<article class="near result-card" data-filterable="true" data-status="warning" data-timeframe="{escape(timeframe)}" data-market="{escape(item["market"])}" data-technique="{escape(technique)}" data-setup="{escape(setup)}" data-direction="{escape(direction)}" data-change="{escape(str(item.get("watchlist_change", "")))}" data-score="{escape(str(evidence.get("score", 0)))}" data-exness="{str(exness_supported).lower()}" data-symbols="{escape(item["symbol"] + " " + item["tradingview_symbol"] + " " + item["market"] + " " + timeframe + " " + technique + " " + setup + " " + display_setup + " " + direction + " warning near break triggered " + ("exness" if exness_supported else ""))}">
  <div class="card-head">
    <div>
      <div class="symbol">{escape(item["symbol"])} <span class="badge warning-badge">{escape(warning_label)}</span><span class="badge">{escape(display_setup)}</span>{_exness_badge(exness_supported)}</div>
      <div class="meta">{escape(item["market"])} · {escape(timeframe)} · {escape(technique)} / {escape(setup)} · <a href="{tv_url}" target="_blank" rel="noreferrer">{escape(tv_symbol)}</a></div>
    </div>
    <div class="score">{score}</div>
  </div>
  <div class="{content_class}">
    {chart_html}
    <div class="body">
      <div class="metrics">
        <div class="metric"><span>Trigger / pivot</span><strong>{trigger}</strong></div>
        <div class="metric"><span>Current</span><strong>{current}</strong></div>
        <div class="metric"><span>Distance</span><strong>{distance}</strong></div>
        <div class="metric"><span>Warning</span><strong>{escape(warning_label)}</strong></div>
      </div>
      {rrg_reference}
      <div class="reasons">Warning reason:</div>
      <ul><li>{escape(note)}</li>{reasons}</ul>
      {direction_authority}
      {lower_timeframe_confirmation}
      {failure_html}
    </div>
  </div>
</article>"""


def _not_configured_card(item: dict) -> str:
    evidence = item.get("evidence", {})
    tv_symbol = item["tradingview_symbol"]
    tv_url = f"https://www.tradingview.com/chart/?symbol={quote(tv_symbol)}"
    technique = item.get("technique", "unknown")
    setup = item.get("setup", "all")
    timeframe = str(item.get("timeframe", "D1"))
    failures = "".join(f"<li>{escape(failure)}</li>" for failure in evidence.get("failures", [])[:4])

    exness_supported = _is_row_exness_supported(item)

    return f"""<article class="near result-card" data-filterable="true" data-status="not_configured" data-timeframe="{escape(timeframe)}" data-market="{escape(item["market"])}" data-technique="{escape(technique)}" data-setup="{escape(setup)}" data-direction="" data-score="0" data-exness="{str(exness_supported).lower()}" data-symbols="{escape(item["symbol"] + " " + item["tradingview_symbol"] + " " + item["market"] + " " + timeframe + " " + technique + " " + setup + " " + ("exness" if exness_supported else ""))}">
  <div class="card-head">
    <div>
      <div class="symbol">{escape(item["symbol"])} <span class="badge near-badge">Not Configured</span></div>
      <div class="meta">{escape(item["market"])} · {escape(timeframe)} · {escape(technique)} / {escape(setup)} · <a href="{tv_url}" target="_blank" rel="noreferrer">{escape(tv_symbol)}</a></div>
    </div>
    <div class="score">Setup {escape(setup.upper())}</div>
  </div>
  <div class="body">
    <div class="metrics">
      <span><strong>Status</strong> not configured</span>
    </div>
    <div class="reasons failures">Reason:</div>
    <ul class="failures">{failures}</ul>
  </div>
</article>"""


def _exness_badge(supported: bool) -> str:
    if not supported:
        return ""
    return '<span class="badge">Exness</span>'


def _change_badge(change: str) -> str:
    if not change:
        return ""
    label = _change_label(change)
    css = change.lower().replace("_", "-")
    return f'<span class="badge change-{escape(css)}">{escape(label)}</span>'


def _change_label(change: str) -> str:
    labels = {
        "FIRST_RUN": "First run",
        "NEW": "New",
        "TRIGGERED": "Triggered change",
        "IMPROVED": "Improved",
        "WEAKER": "Weaker",
        "STATUS_CHANGED": "Status changed",
        "UNCHANGED": "Unchanged",
        "DROPPED": "Dropped",
    }
    return labels.get(change, change.replace("_", " ").title())


def _changes_in_rows(candidates: list[dict], dropped: list[dict]) -> list[str]:
    preferred = ["NEW", "TRIGGERED", "IMPROVED", "WEAKER", "STATUS_CHANGED", "UNCHANGED", "DROPPED", "FIRST_RUN"]
    present = {str(item.get("watchlist_change", "")) for item in candidates + dropped if item.get("watchlist_change")}
    return [change for change in preferred if change in present]


def _dropped_card(item: dict) -> str:
    tv_symbol = str(item.get("tradingview_symbol", ""))
    tv_url = f"https://www.tradingview.com/chart/?symbol={quote(tv_symbol)}"
    technique = str(item.get("technique", ""))
    setup = str(item.get("setup", ""))
    timeframe = str(item.get("timeframe", ""))
    market = str(item.get("market", ""))
    direction = str(item.get("direction", ""))
    symbol = str(item.get("symbol", ""))
    exness_supported = _is_row_exness_supported(item)
    display_setup = _display_setup(item)
    score = _fmt(item.get("previous_score"))
    status = str(item.get("previous_status") or "n/a")
    change = str(item.get("watchlist_change", "DROPPED"))
    return f"""<article class="near result-card" data-filterable="true" data-status="dropped" data-timeframe="{escape(timeframe)}" data-market="{escape(market)}" data-technique="{escape(technique)}" data-setup="{escape(setup)}" data-direction="{escape(direction)}" data-change="{escape(change)}" data-score="{escape(str(item.get("previous_score") or 0))}" data-exness="{str(exness_supported).lower()}" data-symbols="{escape(symbol + " " + tv_symbol + " " + market + " " + timeframe + " " + technique + " " + setup + " " + display_setup + " " + direction + " DROPPED " + ("exness" if exness_supported else ""))}">
  <div class="card-head">
    <div>
      <div class="symbol">{escape(symbol)} <span class="badge">{escape(display_setup)}</span>{_change_badge(change)}{_exness_badge(exness_supported)}</div>
      <div class="meta">{escape(market)} · {escape(timeframe)} · {escape(technique)} / {escape(setup)} · <a href="{tv_url}" target="_blank" rel="noreferrer">{escape(tv_symbol)}</a></div>
    </div>
    <div class="score">{score}</div>
  </div>
  <div class="body">
    <div class="metrics">
      <div class="metric"><span>Previous status</span><strong>{escape(status)}</strong></div>
      <div class="metric"><span>Previous score</span><strong>{score}</strong></div>
    </div>
    <div class="reasons failures">Dropped reason:</div>
    <ul class="failures"><li>Qualified in the previous run, but not qualified in the current run.</li></ul>
  </div>
</article>"""


def _near_matches(rejected: list[dict], limit: int = 20) -> list[dict]:
    scored = []
    for item in rejected:
        evidence = item.get("evidence", {})
        if evidence.get("status") == "data_error":
            continue
        score = _near_match_score(evidence)
        if score <= 0:
            continue
        enriched = dict(item)
        enriched["near_match_score"] = round(score, 2)
        scored.append(enriched)
    scored.sort(key=lambda item: item["near_match_score"], reverse=True)
    return scored[:limit]


def _review_setups(rejected: list[dict], limit: int = REVIEW_SETUP_LIMIT) -> list[dict]:
    scored = []
    for item in rejected:
        evidence = item.get("evidence", {})
        status = str(evidence.get("status", "")).lower()
        if status in {"data_error", "not_configured"}:
            continue
        if not _is_reviewable_setup(item):
            continue
        score = _review_setup_score(item)
        if score <= 0:
            continue
        enriched = dict(item)
        enriched["near_match_score"] = round(max(0.0, _near_match_score(evidence)), 2)
        enriched["review_score"] = round(score, 2)
        scored.append(enriched)
    scored.sort(
        key=lambda item: (
            item["review_score"],
            _score_value(item) or 0.0,
            str(item.get("market", "")),
            str(item.get("symbol", "")),
            str(item.get("setup", "")),
        ),
        reverse=True,
    )
    return scored[:limit]


def _is_reviewable_setup(item: dict) -> bool:
    evidence = item.get("evidence", {})
    if evidence.get("qualified"):
        return False
    if _has_structural_chart_evidence(evidence):
        return True
    if evidence.get("contractions"):
        return evidence.get("pivot") is not None and evidence.get("current_close") is not None
    setup = str(item.get("setup", "")).lower()
    if setup not in {
        "original-vcp",
        "vcp-1c",
        "vcp-2c",
        "vcp-3c",
        "vcp",
        "compression",
        "fb",
        "sb",
        "bb",
        "rb",
        "irb",
        "arb",
    }:
        return False
    score = _numeric(evidence.get("score")) or 0.0
    distance = _numeric(evidence.get("distance_to_pivot_pct"))
    has_trigger_context = evidence.get("pivot") is not None and evidence.get("current_close") is not None
    near_enough = distance is not None and abs(distance) <= 10.0
    return has_trigger_context and score >= 50 and near_enough


def _has_structural_chart_evidence(evidence: dict) -> bool:
    structural_prefixes = (
        "Range description:",
        "Build-up description:",
        "Inner buildup/block description:",
        "Context/range:",
        "Compression zone:",
        "Pivot line values:",
        "Entry trigger level:",
        "Breakout boundary:",
        "Trigger level:",
        "Target boundary:",
        "Stop-loss area:",
    )
    for line in evidence.get("reasons", []) + evidence.get("failures", []):
        text = str(line).strip()
        if text.startswith(structural_prefixes):
            return True
    return False


def _review_setup_score(item: dict) -> float:
    evidence = item.get("evidence", {})
    detector_score = _numeric(evidence.get("score")) or 0.0
    near_score = max(0.0, _near_match_score(evidence))
    structure_bonus = 80.0 if _has_structural_chart_evidence(evidence) else 0.0
    contraction_bonus = 30.0 if evidence.get("contractions") else 0.0
    distance = _numeric(evidence.get("distance_to_pivot_pct"))
    distance_bonus = max(0.0, 20.0 - abs(distance) * 2.0) if distance is not None else 0.0
    status = str(evidence.get("status", "")).upper()
    lifecycle_bonus = 20.0 if status in {"REJECTED", "REJECT", "FAILED", "LATE", "DEVELOPING", "FORMING", "TRIGGERED"} else 0.0
    return detector_score + near_score + structure_bonus + contraction_bonus + distance_bonus + lifecycle_bonus


def _trigger_warnings(rows: list[dict], limit: int = 60) -> list[dict]:
    warnings = []
    for row in rows:
        warning = _trigger_warning(row)
        if warning is None:
            continue
        enriched = dict(row)
        enriched["trigger_warning"] = warning
        warnings.append(enriched)
    warnings.sort(
        key=lambda item: (
            item["trigger_warning"]["priority"],
            abs(float(item["trigger_warning"].get("distance_pct") or 999)),
            -(_score_value(item) or 0.0),
            str(item.get("market", "")),
            str(item.get("symbol", "")),
        )
    )
    return warnings[:limit]


def _trigger_warning(row: dict) -> dict | None:
    evidence = row.get("evidence", {})
    status = str(evidence.get("status", "")).upper()
    if status in {"DATA_ERROR", "NOT_CONFIGURED", "LATE", "FAILED"}:
        return None

    trigger = _numeric(evidence.get("pivot"))
    current = _numeric(evidence.get("current_close"))
    distance = _numeric(evidence.get("distance_to_pivot_pct"))
    if distance is None and trigger and current is not None:
        distance = ((trigger - current) / trigger) * 100
    if trigger is None or current is None or distance is None:
        return None

    if status == "TRIGGERED":
        volume_confirmed = _prefixed_evidence_line(evidence.get("reasons", []), "Trigger volume confirmed:")
        volume_not_confirmed = _prefixed_evidence_line(evidence.get("reasons", []), "Trigger volume not confirmed:")
        label = "Triggered"
        note = "Second trigger / pivot break has already closed and price is still being tracked."
        if volume_confirmed:
            label = "Triggered, volume confirmed"
            note = f"Trigger candle volume confirms the break: {volume_confirmed}"
        elif volume_not_confirmed:
            label = "Triggered, volume not confirmed"
            note = f"Trigger candle closed, but volume is not confirmed: {volume_not_confirmed}"
        return {
            "label": label,
            "note": note,
            "distance_pct": round(distance, 2),
            "trigger_level": trigger,
            "priority": 0,
        }

    active_wait_statuses = {"WAITING", "NEAR_PIVOT", "READY_NEAR_PIVOT", "FORMING"}
    near_strict_failure = row.get("near_match_score") is not None
    if (status in active_wait_statuses or near_strict_failure) and abs(distance) <= TRIGGER_WARNING_DISTANCE_PCT:
        lower_confirmation = row.get("lower_timeframe_confirmation") or {}
        volume_building = _prefixed_evidence_line(evidence.get("reasons", []), "Pre-trigger volume building:")
        volume_watch = _prefixed_evidence_line(evidence.get("reasons", []), "Pre-trigger volume watch:")
        label = "Near break"
        note = f"Current price is within {TRIGGER_WARNING_DISTANCE_PCT:.1f}% of the trigger/pivot."
        priority = 1
        if lower_confirmation:
            label = f"Near break + {lower_confirmation.get('timeframe', 'lower TF')} volume"
            note = (
                f"Current price is within {TRIGGER_WARNING_DISTANCE_PCT:.1f}% of the higher-timeframe trigger/pivot. "
                f"{lower_confirmation.get('note', 'Lower timeframe trigger volume is confirmed.')}"
            )
            priority = 0.5
        elif volume_building:
            label = "Near break, volume building"
            note = (
                f"Current price is within {TRIGGER_WARNING_DISTANCE_PCT:.1f}% of the trigger/pivot. "
                f"Pre-trigger clue only, not confirmation: {volume_building}"
            )
        elif volume_watch:
            note = (
                f"Current price is within {TRIGGER_WARNING_DISTANCE_PCT:.1f}% of the trigger/pivot. "
                f"Pre-trigger volume watch: {volume_watch}"
            )
        if near_strict_failure:
            label = "Near break, strict-failed"
            note = (
                f"Current price is within {TRIGGER_WARNING_DISTANCE_PCT:.1f}% of the trigger/pivot, "
                "but at least one strict setup rule failed."
            )
            priority = 2
        return {
            "label": label,
            "note": note,
            "distance_pct": round(distance, 2),
            "trigger_level": trigger,
            "priority": priority,
        }

    return None


def _prefixed_evidence_line(lines: list, prefix: str) -> str | None:
    for line in lines:
        text = str(line).strip()
        if text.startswith(prefix):
            return text.removeprefix(prefix).strip()
    return None


def _not_configured_rows(rejected: list[dict]) -> list[dict]:
    return [item for item in rejected if item.get("evidence", {}).get("status") == "not_configured"]


def _rrg_market_overview_section(rows: list[dict]) -> str:
    items = _rrg_overview_items(rows)
    if not items:
        return ""

    quadrants = ["LEADING", "IMPROVING", "WEAKENING", "LAGGING"]
    by_quadrant = {quadrant: [] for quadrant in quadrants}
    by_market: dict[str, dict[str, int]] = defaultdict(lambda: {quadrant: 0 for quadrant in quadrants})
    for item in items:
        quadrant = item["quadrant"]
        by_quadrant[quadrant].append(item)
        by_market[item["market"]][quadrant] += 1

    for quadrant in quadrants:
        by_quadrant[quadrant].sort(key=_rrg_overview_rank, reverse=True)

    supportive = len(by_quadrant["LEADING"]) + len(by_quadrant["IMPROVING"])
    risk = len(by_quadrant["WEAKENING"]) + len(by_quadrant["LAGGING"])
    ratio = f"{supportive}:{risk}" if risk else f"{supportive}:0"
    chart = _rrg_overview_chart_svg(items)
    quadrant_cards = "\n".join(_rrg_quadrant_card(quadrant, by_quadrant[quadrant]) for quadrant in quadrants)
    market_cards = "\n".join(_rrg_market_card(market, counts) for market, counts in sorted(by_market.items()))
    return f"""
      <section class="rrg-overview">
        <div class="overview-head">
          <div>
            <h2>Market RRG Overview</h2>
            <p>Reference map for symbols with RRG data. Pattern quality still comes from the price chart.</p>
          </div>
          <div class="overview-score">
            <div><strong>{len(items)}</strong><span>RRG symbols</span></div>
            <div><strong>{supportive}</strong><span>Leading + improving</span></div>
            <div><strong>{escape(ratio)}</strong><span>Support / risk</span></div>
          </div>
        </div>
        {chart}
        <div class="quadrant-grid">{quadrant_cards}</div>
        <div class="market-rrg-grid">{market_cards}</div>
      </section>
"""


def _rrg_overview_items(rows: list[dict]) -> list[dict]:
    by_symbol: dict[tuple[str, str], dict] = {}
    for row in rows:
        rrg = row.get("rrg") or {}
        intent = rrg.get("stock_intent") or {}
        quadrant = str(intent.get("quadrant") or "").upper()
        if quadrant not in {"LEADING", "IMPROVING", "WEAKENING", "LAGGING"}:
            continue
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        item = {
            "symbol": symbol,
            "market": str(row.get("market") or "Unknown"),
            "timeframe": str(row.get("timeframe") or ""),
            "setup": str(row.get("setup") or ""),
            "status": str((row.get("evidence") or {}).get("status") or ""),
            "score": _score_value(row) or 0.0,
            "quadrant": quadrant,
            "x": _numeric((rrg.get("latest") or {}).get("x")) or _numeric(intent.get("x")) or 0.0,
            "y": _numeric((rrg.get("latest") or {}).get("y")) or _numeric(intent.get("y")) or 0.0,
            "dx": _numeric(intent.get("dx1")) or 0.0,
            "dy": _numeric(intent.get("dy1")) or 0.0,
            "series": _rrg_overview_series(rrg, intent),
            "latest_date": _rrg_latest_date(rrg),
        }
        key = (item["timeframe"], symbol)
        if key not in by_symbol or _rrg_overview_rank(item) > _rrg_overview_rank(by_symbol[key]):
            by_symbol[key] = item
    return list(by_symbol.values())


def _rrg_overview_rank(item: dict) -> tuple[float, float, float]:
    quadrant_bonus = {
        "LEADING": 4.0,
        "IMPROVING": 3.0,
        "WEAKENING": 2.0,
        "LAGGING": 1.0,
    }.get(str(item.get("quadrant")), 0.0)
    return (
        quadrant_bonus,
        float(item.get("dy") or 0.0) + float(item.get("dx") or 0.0),
        float(item.get("score") or 0.0),
    )


def _rrg_overview_series(rrg: dict, intent: dict) -> list[tuple[float, float]]:
    series = []
    for point in rrg.get("rrg_series") or rrg.get("series") or []:
        x = _numeric((point or {}).get("x"))
        y = _numeric((point or {}).get("y"))
        if x is not None and y is not None:
            series.append((x, y))
    if len(series) >= 2:
        return series[-10:]

    latest = rrg.get("latest") or {}
    x = _numeric(latest.get("x")) or _numeric(intent.get("x"))
    y = _numeric(latest.get("y")) or _numeric(intent.get("y"))
    dx = _numeric(intent.get("dx1")) or 0.0
    dy = _numeric(intent.get("dy1")) or 0.0
    if x is None or y is None:
        return []
    if dx or dy:
        return [(x - dx, y - dy), (x, y)]
    return [(x, y)]


def _rrg_overview_chart_svg(items: list[dict]) -> str:
    points = [point for item in items for point in item.get("series", [])]
    if not points:
        return ""

    xs = [float(point[0]) for point in points] + [100.0]
    ys = [float(point[1]) for point in points] + [100.0]
    x_min, x_max = _rrg_axis_bounds(xs)
    y_min, y_max = _rrg_axis_bounds(ys)
    width = 1000
    height = 560
    left = 72
    right = 38
    top = 44
    bottom = 58
    plot_w = width - left - right
    plot_h = height - top - bottom

    def sx(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_w

    def sy(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_h

    x100 = sx(100.0)
    y100 = sy(100.0)
    grid_lines = []
    for value in _rrg_tick_values(x_min, x_max):
        x = sx(value)
        grid_lines.append(f'<line class="rrg-gridline" x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height - bottom}"/>')
        grid_lines.append(f'<text class="rrg-small-label" x="{x:.1f}" y="{height - 24}" text-anchor="middle">{_fmt(value)}</text>')
    for value in _rrg_tick_values(y_min, y_max):
        y = sy(value)
        grid_lines.append(f'<line class="rrg-gridline" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>')
        grid_lines.append(f'<text class="rrg-small-label" x="18" y="{y + 4:.1f}">{_fmt(value)}</text>')

    latest_dates = sorted({str(item.get("latest_date")) for item in items if item.get("latest_date")})
    latest_text = f" · Latest RRG row: {latest_dates[-1]}" if latest_dates else ""
    sorted_items = sorted(items, key=_rrg_overview_rank, reverse=True)
    label_symbols = {str(item.get("symbol")) for item in sorted_items[:24]}
    paths = []
    for item in sorted_items:
        series = item.get("series") or [(item.get("x", 100.0), item.get("y", 100.0))]
        if not series:
            continue
        color = _rrg_quadrant_color(str(item.get("quadrant")))
        coords = [(sx(float(x)), sy(float(y))) for x, y in series]
        if len(coords) >= 2:
            path = " ".join(f"{'M' if index == 0 else 'L'} {x:.1f} {y:.1f}" for index, (x, y) in enumerate(coords))
            paths.append(f'<path class="rrg-tail" d="{path}" stroke="{color}"><title>{escape(str(item.get("symbol")))} daily RRG tail</title></path>')
        x, y = coords[-1]
        symbol = str(item.get("symbol"))
        paths.append(f'<circle class="rrg-dot" cx="{x:.1f}" cy="{y:.1f}" r="5.2" fill="{color}"><title>{escape(symbol)} current</title></circle>')
        if symbol in label_symbols:
            label_x = min(width - right - 4, x + 8)
            label_y = max(top + 12, y - 8)
            paths.append(f'<text class="rrg-label" x="{label_x:.1f}" y="{label_y:.1f}">{escape(symbol)}</text>')

    return f"""
        <div class="rrg-chart-shell">
          <div class="rrg-chart-title"><strong>Daily RRG Chart</strong><span>Tail: older -> current · center line = 100{escape(latest_text)}</span></div>
          <svg class="rrg-svg" viewBox="0 0 {width} {height}" role="img" aria-label="Daily RRG overview chart">
            <rect x="{left}" y="{top}" width="{max(0, x100 - left):.1f}" height="{max(0, y100 - top):.1f}" fill="#123251" opacity=".54"/>
            <rect x="{x100:.1f}" y="{top}" width="{max(0, width - right - x100):.1f}" height="{max(0, y100 - top):.1f}" fill="#12391f" opacity=".58"/>
            <rect x="{left}" y="{y100:.1f}" width="{max(0, x100 - left):.1f}" height="{max(0, height - bottom - y100):.1f}" fill="#3b1518" opacity=".58"/>
            <rect x="{x100:.1f}" y="{y100:.1f}" width="{max(0, width - right - x100):.1f}" height="{max(0, height - bottom - y100):.1f}" fill="#3a240d" opacity=".58"/>
            {''.join(grid_lines)}
            <line class="rrg-axis" x1="{left}" y1="{y100:.1f}" x2="{width - right}" y2="{y100:.1f}"/>
            <line class="rrg-axis" x1="{x100:.1f}" y1="{top}" x2="{x100:.1f}" y2="{height - bottom}"/>
            <text class="rrg-label" x="{left + 14}" y="{top + 24}">IMPROVING</text>
            <text class="rrg-label" x="{width - right - 14}" y="{top + 24}" text-anchor="end">LEADING</text>
            <text class="rrg-label" x="{left + 14}" y="{height - bottom - 14}">LAGGING</text>
            <text class="rrg-label" x="{width - right - 14}" y="{height - bottom - 14}" text-anchor="end">WEAKENING</text>
            {''.join(paths)}
            <text class="rrg-legend" x="{left}" y="{height - 8}">JdK RS-Ratio</text>
            <text class="rrg-legend" x="{width - 12}" y="{top}" transform="rotate(90 {width - 12} {top})">JdK RS-Momentum</text>
          </svg>
        </div>
"""


def _rrg_axis_bounds(values: list[float]) -> tuple[float, float]:
    low = min(values)
    high = max(values)
    low = min(low, 96.0)
    high = max(high, 104.0)
    padding = max((high - low) * 0.14, 0.8)
    return low - padding, high + padding


def _rrg_tick_values(low: float, high: float) -> list[float]:
    start = int(low)
    end = int(high) + 1
    return [float(value) for value in range(start, end + 1) if value % 2 == 0]


def _rrg_quadrant_color(quadrant: str) -> str:
    return {
        "LEADING": "#22c55e",
        "IMPROVING": "#38bdf8",
        "WEAKENING": "#f97316",
        "LAGGING": "#ef4444",
    }.get(quadrant, "#cbd5e1")


def _rrg_latest_date(rrg: dict) -> str:
    for point in reversed(rrg.get("rrg_series") or rrg.get("series") or []):
        for key in ("end", "date", "start"):
            value = (point or {}).get(key)
            if value:
                return str(value)
    latest = rrg.get("latest") or {}
    for key in ("end", "date", "start"):
        value = latest.get(key)
        if value:
            return str(value)
    return ""


def _rrg_quadrant_card(quadrant: str, items: list[dict], limit: int = 8) -> str:
    label = quadrant.title()
    detail = {
        "LEADING": "Strong relative strength",
        "IMPROVING": "Momentum turning up",
        "WEAKENING": "Momentum cooling",
        "LAGGING": "Weak relative strength",
    }[quadrant]
    rows = "\n".join(_rrg_overview_symbol(item) for item in items[:limit])
    if not rows:
        rows = '<div class="overview-symbol"><div><b>No symbols</b><span>Nothing currently mapped here</span></div><em>-</em></div>'
    extra = len(items) - limit
    if extra > 0:
        rows += f'<div class="overview-symbol"><div><b>+{extra} more</b><span>Use filters below to inspect the full list</span></div><em></em></div>'
    return f"""
          <div class="quadrant-card {escape(quadrant.lower())}">
            <div class="quadrant-head"><div><strong>{escape(label)}</strong><span>{escape(detail)}</span></div><div class="quadrant-count">{len(items)}</div></div>
            <div class="quadrant-list">{rows}</div>
          </div>
"""


def _rrg_overview_symbol(item: dict) -> str:
    movement = f"dx {_fmt(item.get('dx'))} / dy {_fmt(item.get('dy'))}"
    meta = f"{item.get('market')} · {item.get('timeframe')} · {item.get('setup')} · {item.get('status')}"
    return (
        '<div class="overview-symbol">'
        f'<div><b>{escape(str(item.get("symbol")))}</b><span>{escape(meta)}</span></div>'
        f"<em>{escape(movement)}</em>"
        "</div>"
    )


def _rrg_market_card(market: str, counts: dict[str, int]) -> str:
    return f"""
          <div class="market-rrg">
            <strong>{escape(market)}</strong>
            <div class="market-bars">
              <span class="leading" title="Leading">{counts.get("LEADING", 0)}</span>
              <span class="improving" title="Improving">{counts.get("IMPROVING", 0)}</span>
              <span class="weakening" title="Weakening">{counts.get("WEAKENING", 0)}</span>
              <span class="lagging" title="Lagging">{counts.get("LAGGING", 0)}</span>
            </div>
          </div>
"""


def _coverage_section(scanned_by_market: dict[str, list[str]], data_errors_by_market: dict[str, int]) -> str:
    total = sum(len(symbols) for symbols in scanned_by_market.values())
    markets = []
    for market, symbols in sorted(scanned_by_market.items()):
        symbol_text = "".join(f'<span class="symbol-chip">{escape(symbol)}</span>' for symbol in symbols)
        data_errors = data_errors_by_market.get(market, 0)
        data_error_text = ""
        if data_errors:
            data_error_text = f'<div class="data-errors">Data unavailable for {data_errors} symbol(s) from this provider.</div>'
        markets.append(
            f"""<div class="coverage-market" data-filterable="true" data-status="coverage" data-timeframe="" data-market="{escape(market)}" data-technique="" data-setup="" data-symbols="{escape(" ".join(symbols) + " " + market)}">
  <h3>{escape(market)} ({len(symbols)})</h3>
  <div class="symbols">{symbol_text}</div>
  {data_error_text}
</div>"""
        )
    return f"""<details id="coverageSection" class="coverage" open>
  <summary>Scanned Universe ({total} symbols)</summary>
  <div class="coverage-grid">
    {"".join(markets)}
  </div>
</details>"""


def _scanned_symbols_by_market(rows: list[dict]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        grouped[row.get("market", "unknown")].append(row.get("symbol", "unknown"))
    return {market: sorted(set(symbols)) for market, symbols in sorted(grouped.items())}


def _setups_in_rows(rows: list[dict]) -> list[str]:
    setups = sorted({str(row.get("setup", "all")) for row in rows if row.get("setup")})
    return [setup for setup in setups if setup != "all"]


def _techniques_in_rows(rows: list[dict]) -> list[str]:
    return sorted({str(row.get("technique", "unknown")) for row in rows if row.get("technique")})


def _timeframes_in_rows(rows: list[dict], payload: dict) -> list[str]:
    fallback = str(payload.get("timeframe") or payload.get("config", {}).get("timeframe", "D1"))
    timeframes = sorted({str(row.get("timeframe", fallback)) for row in rows if row.get("timeframe", fallback)})
    return timeframes or [fallback]


def _data_errors_by_market(rejected: list[dict]) -> dict[str, int]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in rejected:
        if row.get("evidence", {}).get("status") == "data_error":
            grouped[row.get("market", "unknown")].add(row.get("symbol", "unknown"))
    return {market: len(symbols) for market, symbols in sorted(grouped.items())}


def _display_setup(row: dict) -> str:
    technique = str(row.get("technique", ""))
    setup = str(row.get("setup", "all"))
    if technique == "minervini-vcp":
        if setup == "vcp-1c":
            return "VCP 1C"
        if setup == "vcp-2c":
            return "VCP 2C"
        if setup == "vcp-3c":
            return "VCP 3C"
        return "Original VCP"
    if technique == "experimental-ema21-compression" or setup == "compression":
        return "Compression"
    if setup == "vcp" and technique == "nhathoai":
        return "NH VCP"
    if setup and setup != "all":
        return setup.upper()
    return technique or "unknown"


def _direction_from_evidence(evidence: dict) -> str:
    lines = evidence.get("reasons", []) + evidence.get("failures", [])
    direction = _line_value(lines, "Direction:")
    if direction:
        normalized = direction.strip().lower()
        if normalized in {"long", "short"}:
            return normalized
    status = str(evidence.get("status", "")).lower()
    if "_long" in status:
        return "long"
    if "_short" in status:
        return "short"
    return ""


def _clean_evidence_lines(lines: list[str]) -> list[str]:
    cleaned = []
    skip_prefixes = (
        "Pattern:",
        "Direction:",
        "Status:",
        "Score:",
        "Reason:",
        "Manual review note:",
    )
    for line in lines:
        stripped = str(line).strip()
        if not stripped or stripped.startswith(skip_prefixes):
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        cleaned.append(stripped)
    return cleaned


def _line_value(lines: list[str], prefix: str) -> str | None:
    for line in lines:
        stripped = str(line).strip()
        if stripped.startswith(prefix):
            return stripped.removeprefix(prefix).strip()
    return None


def _near_match_score(evidence: dict) -> float:
    reasons = evidence.get("reasons", [])
    failures = evidence.get("failures", [])
    distance = evidence.get("distance_to_pivot_pct")
    proximity_bonus = 0.0
    if isinstance(distance, int | float):
        proximity_bonus = max(0.0, 10 - abs(distance))
    return len(reasons) * 10 - len(failures) * 5 + proximity_bonus


def _relative_path(path: str, report_dir: Path) -> str:
    if not path:
        return ""
    path_obj = Path(path)
    if path_obj.is_absolute():
        return relpath(path_obj, report_dir.resolve())
    resolved = path_obj.resolve()
    if resolved.exists():
        return relpath(resolved, report_dir.resolve())
    try:
        return str(resolved.relative_to(report_dir.resolve()))
    except ValueError:
        return path


def _chart_sources(path: str, report_dir: Path) -> tuple[str, str]:
    full_src = escape(_relative_path(path, report_dir))
    preview_path = _preview_path(path)
    if preview_path is not None and preview_path.exists():
        return full_src, escape(_relative_path(str(preview_path), report_dir))
    return full_src, full_src


def _preview_path(path: str) -> Path | None:
    if not path:
        return None
    path_obj = Path(path)
    return path_obj.parent / "preview" / path_obj.name


def _fmt(value: object, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"
