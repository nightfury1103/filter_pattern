# Market RRG Overview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the crowded multi-market RRG summary with fixed representative status cards and a representative-only chart whose final arrow clearly shows observed direction.

**Architecture:** Keep provider identifiers and representative retrieval in `rrg_dashboard.py`, adding display aliases and explicit unavailable rows to its output contract. Normalize and aggregate those rows in `report.py`, where the generated HTML will render market cards, preserve the existing market drill-down, and apply the approved faded-tail/emphasized-arrow SVG treatment.

**Tech Stack:** Python 3.13, generated HTML/CSS/SVG, pytest 9, existing StockCharts/Fialda RRG adapters.

---

## File Structure

- Modify `filter_pattern/rrg_dashboard.py`: own the fixed representative configuration, internal-to-display symbol aliases, and complete representative rows including unavailable data.
- Modify `filter_pattern/report.py`: normalize representative rows, calculate market status, render the compact card grid, preserve filter-driven detailed charts, and render clearer SVG direction arrows.
- Modify `tests/test_rrg_dashboard.py`: verify representative configuration, D1 retrieval, display aliases, and non-blocking unavailable rows.
- Modify `tests/test_report_chart.py`: verify aggregation, simplified markup, unavailable states, representative-only charts, drill-down behavior, and arrow rendering.

No new runtime module is needed. The behavior belongs at the two existing boundaries: RRG data attachment and report rendering.

### Task 1: Make Representative Rows Complete and Display-Safe

**Files:**
- Modify: `filter_pattern/rrg_dashboard.py:75-84`
- Modify: `filter_pattern/rrg_dashboard.py:300-333`
- Test: `tests/test_rrg_dashboard.py:191-288`

- [ ] **Step 1: Write failing tests for the representative contract**

Add these tests beside the existing market-representative tests in `tests/test_rrg_dashboard.py`:

```python
def test_market_representative_configuration_and_display_labels_are_fixed() -> None:
    assert rrg_dashboard.RRG_MARKET_REPRESENTATIVES == {
        "US stock": ["SPY"],
        "Vietnam stock": ["VNINDEX"],
        "Crypto": ["BTCUSDT", "ETHUSDT"],
        "Forex": ["DXY"],
        "Index": ["US500"],
        "Commodity": ["XAUUSD"],
        "Commodity ETF": ["DBC"],
    }
    assert rrg_dashboard.RRG_MARKET_REPRESENTATIVE_LABELS == {
        ("Crypto", "BTCUSDT"): "BTCUSD",
        ("Crypto", "ETHUSDT"): "ETHUSD",
    }


def test_market_representative_rows_keep_internal_symbols_and_unavailable_slots() -> None:
    btc = RRGSelection(
        symbol="BTCUSDT",
        sector="Crypto",
        benchmark="$ONE",
        latest={"x": 101.4, "y": 101.2},
        intent={"quadrant": "LEADING", "dx1": 1.2, "dy1": 1.1},
        sector_latest={},
        sector_intent={},
        rrg_series=[{"x": 100.2, "y": 100.1}, {"x": 101.4, "y": 101.2}],
    )
    errors: list[str] = []

    rows = rrg_dashboard._market_representative_rrg_rows(
        {"Crypto": {"SOLUSDT"}},
        {"Crypto": lambda symbols: {"BTCUSDT": btc}},
        errors,
    )

    assert [(row["symbol"], row["display_symbol"]) for row in rows] == [
        ("BTCUSDT", "BTCUSD"),
        ("ETHUSDT", "ETHUSD"),
    ]
    assert rows[0]["evidence"]["status"] == "RRG_MARKET_REPRESENTATIVE"
    assert rows[0]["rrg"]["stock_intent"]["quadrant"] == "LEADING"
    assert rows[1]["evidence"]["status"] == "RRG_MARKET_UNAVAILABLE"
    assert rows[1]["rrg"] == {}
    assert errors == []


def test_market_representative_fetch_failure_keeps_unavailable_rows() -> None:
    def fail_fetch(_symbols: list[str]) -> dict[str, RRGSelection]:
        raise RuntimeError("provider offline")

    errors: list[str] = []
    rows = rrg_dashboard._market_representative_rrg_rows(
        {"US stock": {"AAPL"}},
        {"US stock": fail_fetch},
        errors,
    )

    assert len(rows) == 1
    assert rows[0]["symbol"] == "SPY"
    assert rows[0]["display_symbol"] == "SPY"
    assert rows[0]["evidence"]["status"] == "RRG_MARKET_UNAVAILABLE"
    assert errors == ["US stock representative: provider offline"]
```

Update `test_rrg_reference_adds_btc_and_eth_crypto_market_representatives` so it asserts both identities:

```python
    assert [row["symbol"] for row in crypto_representatives] == ["BTCUSDT", "ETHUSDT"]
    assert [row["display_symbol"] for row in crypto_representatives] == ["BTCUSD", "ETHUSD"]
```

- [ ] **Step 2: Run the tests and verify the expected failures**

Run:

```bash
python -m pytest \
  tests/test_rrg_dashboard.py::test_market_representative_configuration_and_display_labels_are_fixed \
  tests/test_rrg_dashboard.py::test_market_representative_rows_keep_internal_symbols_and_unavailable_slots \
  tests/test_rrg_dashboard.py::test_market_representative_fetch_failure_keeps_unavailable_rows \
  tests/test_rrg_dashboard.py::test_rrg_reference_adds_btc_and_eth_crypto_market_representatives -q
```

Expected: FAIL because `RRG_MARKET_REPRESENTATIVE_LABELS` and `display_symbol` do not exist and missing selections are currently omitted.

- [ ] **Step 3: Add display aliases without changing fetch identifiers**

Immediately after `RRG_MARKET_REPRESENTATIVES` in `filter_pattern/rrg_dashboard.py`, add:

```python
RRG_MARKET_REPRESENTATIVE_LABELS = {
    ("Crypto", "BTCUSDT"): "BTCUSD",
    ("Crypto", "ETHUSDT"): "ETHUSD",
}
```

Replace `_market_representative_rrg_rows` and `_market_representative_display_symbol` with:

```python
def _market_representative_rrg_rows(
    symbols_by_market: dict[str, set[str]],
    fetchers: dict[str, Callable[[list[str]], dict[str, RRGSelection]]],
    errors: list[str],
) -> list[dict]:
    rows: list[dict] = []
    for market in sorted(symbols_by_market):
        symbols = RRG_MARKET_REPRESENTATIVES.get(market) or []
        if not symbols:
            continue
        try:
            selections = fetchers[market](symbols)
        except Exception as exc:  # Representative context must stay non-blocking.
            errors.append(f"{market} representative: {exc}")
            selections = {}
        for symbol in symbols:
            selected = selections.get(symbol)
            available = selected is not None
            rows.append(
                {
                    "symbol": symbol,
                    "display_symbol": _market_representative_display_symbol(market, symbol),
                    "market": market,
                    "timeframe": "D1",
                    "setup": "market",
                    "evidence": {
                        "status": "RRG_MARKET_REPRESENTATIVE" if available else "RRG_MARKET_UNAVAILABLE",
                        "score": 0,
                    },
                    "rrg": _rrg_json(selected) if selected is not None else {},
                }
            )
    return rows


def _market_representative_display_symbol(market: str, symbol: str) -> str:
    return RRG_MARKET_REPRESENTATIVE_LABELS.get((market, symbol), symbol)
```

This keeps `symbol` suitable for provider and payload identity while giving the report a dedicated label.

- [ ] **Step 4: Run the focused representative tests**

Run:

```bash
python -m pytest tests/test_rrg_dashboard.py -k "market_representative or adds_daily_market_representatives or adds_btc_and_eth" -q
```

Expected: all selected tests PASS, including the existing assertion that representative crypto fetches use D1 for an H4 report.

- [ ] **Step 5: Commit the representative contract**

```bash
git add filter_pattern/rrg_dashboard.py tests/test_rrg_dashboard.py
git commit -m "Add complete RRG market representatives"
```

### Task 2: Render One Status Card per Market

**Files:**
- Modify: `filter_pattern/report.py:736-890`
- Modify: `filter_pattern/report.py:1277-1423`
- Modify: `filter_pattern/report.py:2994-3115`
- Modify: `filter_pattern/report.py:3281-3325`
- Test: `tests/test_report_chart.py:120-294`

- [ ] **Step 1: Add a reusable representative fixture and failing status tests**

Add this helper near the RRG overview tests in `tests/test_report_chart.py`:

```python
def _overview_representative(
    symbol: str,
    market: str,
    quadrant: str | None,
    *,
    display_symbol: str | None = None,
    dx: float = 0.4,
    dy: float = 0.5,
) -> dict:
    if quadrant is None:
        return {
            "symbol": symbol,
            "display_symbol": display_symbol or symbol,
            "market": market,
            "timeframe": "D1",
            "setup": "market",
            "evidence": {"status": "RRG_MARKET_UNAVAILABLE", "score": 0},
            "rrg": {},
        }
    latest = {"x": 101.0 if quadrant in {"LEADING", "WEAKENING"} else 99.0,
              "y": 101.0 if quadrant in {"LEADING", "IMPROVING"} else 99.0}
    return {
        "symbol": symbol,
        "display_symbol": display_symbol or symbol,
        "market": market,
        "timeframe": "D1",
        "setup": "market",
        "evidence": {"status": "RRG_MARKET_REPRESENTATIVE", "score": 0},
        "rrg": {
            "latest": latest,
            "stock_intent": {"quadrant": quadrant, "dx1": dx, "dy1": dy},
            "rrg_series": [
                {"x": latest["x"] - dx, "y": latest["y"] - dy, "end": "2026-08-16"},
                {**latest, "end": "2026-08-17"},
            ],
        },
    }
```

Add these tests:

```python
def test_rrg_market_status_aggregates_same_mixed_partial_and_unavailable() -> None:
    btc = _overview_representative("BTCUSDT", "Crypto", "LEADING", display_symbol="BTCUSD")
    eth_leading = _overview_representative("ETHUSDT", "Crypto", "LEADING", display_symbol="ETHUSD")
    eth_lagging = _overview_representative("ETHUSDT", "Crypto", "LAGGING", display_symbol="ETHUSD")
    eth_missing = _overview_representative("ETHUSDT", "Crypto", None, display_symbol="ETHUSD")

    normalize = lambda rows: report._rrg_overview_items(rows, include_unavailable=True)
    assert report._rrg_market_status(normalize([btc, eth_leading])) == "LEADING"
    assert report._rrg_market_status(normalize([btc, eth_lagging])) == "MIXED"
    assert report._rrg_market_status(normalize([btc, eth_missing])) == "PARTIAL"
    assert report._rrg_market_status(normalize([eth_missing])) == "UNAVAILABLE"


def test_rrg_overview_renders_representative_status_cards_without_long_lists() -> None:
    representatives = [
        _overview_representative("SPY", "US stock", "LEADING", dx=0.8, dy=0.7),
        _overview_representative("BTCUSDT", "Crypto", "LEADING", display_symbol="BTCUSD"),
        _overview_representative("ETHUSDT", "Crypto", "WEAKENING", display_symbol="ETHUSD", dx=0.3, dy=-0.4),
        _overview_representative("DXY", "Forex", None),
    ]
    html = report._rrg_market_overview_section(
        {"rrg_reference": {"market_representatives": representatives}},
        [],
    )

    assert 'class="market-status-grid"' in html
    assert 'data-market-status="LEADING"' in html
    assert 'data-market-status="MIXED"' in html
    assert 'data-market-status="UNAVAILABLE"' in html
    assert "BTCUSD" in html
    assert "ETHUSD" in html
    assert "DXY" in html
    assert "4</strong><span>Representative trails" not in html
    assert "3</strong><span>Representative trails" in html
    assert 'class="quadrant-grid"' not in html
    assert 'class="market-rrg-grid"' not in html
```

Import the module at the top of the test file if it is not already imported:

```python
from filter_pattern import report
```

- [ ] **Step 2: Run the status tests and verify they fail**

Run:

```bash
python -m pytest \
  tests/test_report_chart.py::test_rrg_market_status_aggregates_same_mixed_partial_and_unavailable \
  tests/test_report_chart.py::test_rrg_overview_renders_representative_status_cards_without_long_lists -q
```

Expected: FAIL because `_rrg_market_status` and the market-status card grid do not exist, and `_rrg_market_overview_section` currently returns an empty string when only representative rows are supplied.

- [ ] **Step 3: Preserve unavailable items during normalization**

Change `_rrg_overview_items` to accept `include_unavailable` and to use the display label while retaining source identity:

```python
def _rrg_overview_items(rows: list[dict], include_unavailable: bool = False) -> list[dict]:
    by_symbol: dict[tuple[str, str, str], dict] = {}
    valid_quadrants = {"LEADING", "IMPROVING", "WEAKENING", "LAGGING"}
    for row in rows:
        rrg = row.get("rrg") or {}
        intent = rrg.get("stock_intent") or {}
        quadrant = str(intent.get("quadrant") or "").upper()
        available = quadrant in valid_quadrants
        if not available and not include_unavailable:
            continue
        source_symbol = str(row.get("symbol") or "").strip()
        symbol = str(row.get("display_symbol") or source_symbol).strip()
        if not source_symbol or not symbol:
            continue
        item = {
            "symbol": symbol,
            "source_symbol": source_symbol,
            "market": str(row.get("market") or "Unknown"),
            "timeframe": str(row.get("timeframe") or ""),
            "setup": str(row.get("setup") or ""),
            "status": str((row.get("evidence") or {}).get("status") or ""),
            "score": _score_value(row) or 0.0,
            "quadrant": quadrant if available else "UNAVAILABLE",
            "available": available,
            "x": _numeric((rrg.get("latest") or {}).get("x")) or _numeric(intent.get("x")) or 0.0,
            "y": _numeric((rrg.get("latest") or {}).get("y")) or _numeric(intent.get("y")) or 0.0,
            "dx": _numeric(intent.get("dx1")) or 0.0,
            "dy": _numeric(intent.get("dy1")) or 0.0,
            "series": _rrg_overview_series(rrg, intent) if available else [],
            "latest_date": _rrg_latest_date(rrg) if available else "",
        }
        key = (item["timeframe"], item["market"], source_symbol)
        if key not in by_symbol or _rrg_overview_rank(item) > _rrg_overview_rank(by_symbol[key]):
            by_symbol[key] = item
    return list(by_symbol.values())
```

Update `_rrg_market_representative_items` to use the complete form:

```python
def _rrg_market_representative_items(payload: dict, fallback_items: list[dict]) -> list[dict]:
    representatives = (payload.get("rrg_reference") or {}).get("market_representatives") or []
    items = _rrg_overview_items(representatives, include_unavailable=True)
    if items:
        return sorted(items, key=lambda item: (str(item.get("market") or ""), str(item.get("symbol") or "")))
    by_market = _rrg_items_by_market(fallback_items)
    return [
        sorted(market_items, key=_rrg_overview_rank, reverse=True)[0]
        for _market, market_items in sorted(by_market.items())
        if market_items
    ]
```

- [ ] **Step 4: Add status aggregation and compact card rendering**

Replace `_rrg_quadrant_card`, `_rrg_overview_symbol`, and `_rrg_market_card` with these focused helpers:

```python
def _rrg_market_status(items: list[dict]) -> str:
    available = [item for item in items if item.get("available", True) and item.get("quadrant") != "UNAVAILABLE"]
    if not available:
        return "UNAVAILABLE"
    if len(available) < len(items):
        return "PARTIAL"
    quadrants = {str(item.get("quadrant") or "") for item in available}
    return next(iter(quadrants)) if len(quadrants) == 1 else "MIXED"


def _rrg_direction_arrow(item: dict) -> str:
    if not item.get("available", True):
        return "—"
    dx = float(item.get("dx") or 0.0)
    dy = float(item.get("dy") or 0.0)
    if dx >= 0 and dy > 0:
        return "↗"
    if dx < 0 and dy >= 0:
        return "↖"
    if dx > 0 and dy <= 0:
        return "↘"
    if dx <= 0 and dy < 0:
        return "↙"
    return "→"


def _rrg_market_status_card(market: str, items: list[dict]) -> str:
    status = _rrg_market_status(items)
    symbol_rows = []
    for item in items:
        quadrant = str(item.get("quadrant") or "UNAVAILABLE")
        if item.get("available", True):
            coordinates = f"RS {_fmt(item.get('x'))} · Mom {_fmt(item.get('y'))}"
            movement = f"{_rrg_direction_arrow(item)} dx {_fmt(item.get('dx'))} / dy {_fmt(item.get('dy'))}"
        else:
            coordinates = "RRG data unavailable"
            movement = "—"
        symbol_rows.append(
            '<div class="market-status-symbol">'
            f'<div><b>{escape(str(item.get("symbol") or ""))}</b><span>{escape(quadrant.title())}</span></div>'
            f'<div><span>{escape(coordinates)}</span><em>{escape(movement)}</em></div>'
            '</div>'
        )
    return (
        f'<article class="market-status-card status-{escape(status.lower())}" data-market-status="{escape(status)}">'
        f'<div class="market-status-head"><strong>{escape(market)}</strong><span>{escape(status.title())}</span></div>'
        f'<div class="market-status-symbols">{"".join(symbol_rows)}</div>'
        '</article>'
    )
```

- [ ] **Step 5: Rebuild the overview around representatives**

Refactor `_rrg_market_overview_section` so representatives drive the all-markets counts and cards while candidate items still drive detailed market charts:

```python
def _rrg_market_overview_section(payload: dict, rows: list[dict]) -> str:
    detail_items = _rrg_overview_items(rows)
    representative_items = _rrg_market_representative_items(payload, detail_items)
    if not representative_items:
        return ""

    available = [item for item in representative_items if item.get("available", True)]
    representative_by_market = _rrg_items_by_market(representative_items)
    supportive = sum(1 for item in available if item["quadrant"] in {"LEADING", "IMPROVING"})
    risk = sum(1 for item in available if item["quadrant"] in {"WEAKENING", "LAGGING"})
    ratio = f"{supportive}:{risk}"
    status_cards = "\n".join(
        _rrg_market_status_card(market, market_items)
        for market, market_items in sorted(representative_by_market.items())
    )

    all_chart = _rrg_overview_chart_svg(
        available,
        "all",
        "Market Representative RRG",
        "Fixed D1 representative trails",
    )
    if not all_chart:
        all_chart = (
            '<div class="rrg-chart-shell" data-rrg-market="all">'
            '<div class="rrg-chart-empty">Representative RRG data is unavailable for this report.</div>'
            '</div>'
        )
    charts = [all_chart]
    for market, market_items in sorted(_rrg_items_by_market(detail_items).items()):
        if market == "Crypto" and representative_by_market.get(market):
            market_items = [item for item in representative_by_market[market] if item.get("available", True)]
        market_chart = _rrg_overview_chart_svg(
            market_items,
            market,
            f"Daily RRG Chart - {market}",
            "Detailed daily RRG for the selected market",
            hidden=True,
        )
        if market_chart:
            charts.append(market_chart)

    return f"""
      <section class="rrg-overview">
        <div class="overview-head">
          <div>
            <h2>Market RRG Overview</h2>
            <p>Fixed D1 representatives show each market's current quadrant and observed movement.</p>
          </div>
          <div class="overview-score">
            <div><strong>{len(representative_by_market)}</strong><span>Markets</span></div>
            <div><strong>{len(available)}</strong><span>Representative trails</span></div>
            <div><strong>{escape(ratio)}</strong><span>Support / risk</span></div>
          </div>
        </div>
        <div class="market-status-grid">{status_cards}</div>
        <div id="rrgChartMode" class="filter-count">All markets: representative RRG trails</div>
        {"".join(charts)}
      </section>
"""
```

Keep `updateRrgOverview` unchanged so a selected market continues to activate its detailed shell and falls back to the all-markets shell if no detailed chart exists.

- [ ] **Step 6: Replace obsolete CSS with responsive status-card CSS**

Delete selectors for `.quadrant-grid`, `.quadrant-card`, `.quadrant-head`, `.quadrant-count`, `.quadrant-list`, `.overview-symbol`, `.market-rrg-grid`, `.market-rrg`, and `.market-bars`. Add:

```css
    .market-status-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 10px;
      margin: 0 0 12px;
    }
    .market-status-card {
      border: 1px solid var(--line);
      border-top: 4px solid var(--line-strong);
      border-radius: 8px;
      background: var(--soft);
      padding: 10px;
    }
    .market-status-card.status-leading { border-top-color: #16a34a; }
    .market-status-card.status-improving { border-top-color: #2563eb; }
    .market-status-card.status-weakening { border-top-color: #ea580c; }
    .market-status-card.status-lagging { border-top-color: #dc2626; }
    .market-status-card.status-mixed { border-top-color: #8b5cf6; }
    .market-status-card.status-partial,
    .market-status-card.status-unavailable { border-top-color: #94a3b8; }
    .market-status-head,
    .market-status-symbol,
    .market-status-symbol > div {
      display: flex;
      justify-content: space-between;
      gap: 8px;
    }
    .market-status-head { align-items: center; margin-bottom: 8px; }
    .market-status-head span {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 7px;
      font-size: 10px;
      font-weight: 800;
      text-transform: uppercase;
    }
    .market-status-symbols { display: grid; gap: 6px; }
    .market-status-symbol {
      align-items: end;
      border-top: 1px solid var(--line);
      padding-top: 6px;
      font-size: 11px;
    }
    .market-status-symbol > div { flex-direction: column; }
    .market-status-symbol > div:last-child { text-align: right; }
    .market-status-symbol b { color: var(--text); font-size: 14px; }
    .market-status-symbol span { color: var(--muted); }
    .market-status-symbol em { color: var(--text); font-style: normal; font-weight: 700; }
    .rrg-chart-empty { padding: 36px 16px; text-align: center; color: var(--muted); }
```

In the dark-mode color list, replace `.overview-symbol em` with `.market-status-symbol em`. In the responsive blocks, replace `.quadrant-grid` with `.market-status-grid`; use two columns under 1180px and one column under 720px.

- [ ] **Step 7: Run the focused overview tests**

In the manual `market_representatives` fixture inside `test_report_rrg_overview_uses_representatives_and_switches_market_charts`, add the approved labels without changing the source symbols:

```python
            {
                "symbol": "BTCUSDT",
                "display_symbol": "BTCUSD",
                "market": "Crypto",
                "timeframe": "D1",
            },
            {
                "symbol": "ETHUSDT",
                "display_symbol": "ETHUSD",
                "market": "Crypto",
                "timeframe": "D1",
            },
```

Insert `display_symbol` between each existing `symbol` and `market` field; leave each existing `rrg` dictionary unchanged. Change only the generated-HTML assertions for those two representatives to `BTCUSD` and `ETHUSD`. Keep the payload and fetch-contract assertions on `BTCUSDT` and `ETHUSDT`.

Run:

```bash
python -m pytest \
  tests/test_report_chart.py::test_rrg_market_status_aggregates_same_mixed_partial_and_unavailable \
  tests/test_report_chart.py::test_rrg_overview_renders_representative_status_cards_without_long_lists \
  tests/test_report_chart.py::test_report_renders_market_rrg_overview \
  tests/test_report_chart.py::test_report_rrg_overview_uses_representatives_and_switches_market_charts -q
```

Expected: all four tests PASS. The representative chart uses `BTCUSD`/`ETHUSD`; the assertions about `SOLUSDT` exclusion, `updateRrgOverview`, and market shells remain.

- [ ] **Step 8: Commit the market-status overview**

```bash
git add filter_pattern/report.py tests/test_report_chart.py
git commit -m "Simplify market RRG overview status"
```

### Task 3: Emphasize the Final RRG Direction Arrow

**Files:**
- Modify: `filter_pattern/report.py:816-824`
- Modify: `filter_pattern/report.py:3140-3235`
- Test: `tests/test_report_chart.py:173-294`

- [ ] **Step 1: Write failing SVG direction tests**

Add these tests in `tests/test_report_chart.py`:

```python
def test_rrg_chart_fades_history_and_emphasizes_only_the_final_arrow() -> None:
    item = report._rrg_overview_items(
        [_overview_representative("SPY", "US stock", "LEADING", dx=0.8, dy=0.7)]
    )[0]
    item["series"] = [(99.2, 99.1), (100.0, 100.2), (101.0, 101.0)]

    html = report._rrg_overview_chart_svg([item])

    assert html.count('class="rrg-tail rrg-history-tail"') == 1
    assert html.count('class="rrg-tail rrg-direction-head"') == 1
    assert html.count("marker-end=") == 1
    assert 'markerWidth="7.2"' in html
    assert 'markerHeight="7.2"' in html
    assert "SPY direction: previous to current" in html


def test_rrg_chart_single_point_has_endpoint_without_direction_arrow() -> None:
    item = report._rrg_overview_items(
        [_overview_representative("SPY", "US stock", "LEADING")]
    )[0]
    item["series"] = [(101.0, 101.0)]

    html = report._rrg_overview_chart_svg([item])

    assert 'class="rrg-dot"' in html
    assert 'class="rrg-tail rrg-history-tail"' not in html
    assert 'class="rrg-tail rrg-direction-head"' not in html
    assert "marker-end=" not in html
```

- [ ] **Step 2: Run the SVG tests and verify they fail**

Run:

```bash
python -m pytest \
  tests/test_report_chart.py::test_rrg_chart_fades_history_and_emphasizes_only_the_final_arrow \
  tests/test_report_chart.py::test_rrg_chart_single_point_has_endpoint_without_direction_arrow -q
```

Expected: FAIL because the current chart uses one fully opaque full-tail path, the old `rrg-arrow-segment` class, and a 4.8 marker.

- [ ] **Step 3: Split historical and final SVG segments**

Inside the item loop in `_rrg_overview_chart_svg`, replace marker construction and path construction with:

```python
        marker_defs.append(
            f'<marker id="{escape(marker_id)}" viewBox="0 0 10 10" refX="8.5" refY="5" '
            'markerWidth="7.2" markerHeight="7.2" orient="auto-start-reverse">'
            f'<path class="rrg-arrow-head" d="M 0 0 L 10 5 L 0 10 z" style="color:{color}"></path>'
            '</marker>'
        )
        history_coords = coords[:-1]
        if len(history_coords) >= 2:
            history_path = " ".join(
                f"{'M' if point_index == 0 else 'L'} {x:.1f} {y:.1f}"
                for point_index, (x, y) in enumerate(history_coords)
            )
            paths.append(
                f'<path class="rrg-tail rrg-history-tail" d="{history_path}" stroke="{color}">'
                f'<title>{escape(str(item.get("symbol")))} historical RRG tail</title></path>'
            )
        x, y = coords[-1]
        symbol = str(item.get("symbol"))
        paths.append(
            f'<circle class="rrg-dot" cx="{x:.1f}" cy="{y:.1f}" r="5.6" fill="{color}">'
            f'<title>{escape(symbol)} current</title></circle>'
        )
        if len(coords) >= 2:
            start_x, start_y = coords[-2]
            arrow_path = f"M {start_x:.1f} {start_y:.1f} L {x:.1f} {y:.1f}"
            paths.append(
                f'<path class="rrg-tail rrg-direction-head" d="{arrow_path}" stroke="{color}" '
                f'marker-end="url(#{escape(marker_id)})">'
                f'<title>{escape(symbol)} direction: previous to current</title></path>'
            )
```

Leave the current symbol-label block immediately after this code. The endpoint remains present for a one-point series, while arrow markup is generated only for two or more points.

- [ ] **Step 4: Apply the approved opacity and width hierarchy**

Replace the current tail and arrow-segment CSS with:

```css
    .rrg-tail { fill: none; stroke-linecap: round; stroke-linejoin: round; }
    .rrg-history-tail { stroke-width: 2; opacity: .28; }
    .rrg-direction-head { stroke-width: 4.5; opacity: 1; }
```

Retain `.rrg-arrow-head { fill: currentColor; }`, `.rrg-dot`, and label styles.

- [ ] **Step 5: Update the existing ordering assertion and run chart tests**

In `test_report_rrg_overview_uses_representatives_and_switches_market_charts`, replace the old class assertion with:

```python
    assert 'class="rrg-tail rrg-direction-head"' in html
    assert html.index('class="rrg-tail rrg-history-tail"') < html.index('class="rrg-tail rrg-direction-head"')
```

Run:

```bash
python -m pytest tests/test_report_chart.py -k "rrg_overview or rrg_chart" -q
```

Expected: all selected tests PASS. Each multi-point trail has one emphasized final arrow, and a single-point trail has only its endpoint.

- [ ] **Step 6: Commit the direction treatment**

```bash
git add filter_pattern/report.py tests/test_report_chart.py
git commit -m "Clarify RRG trail direction arrows"
```

### Task 4: Regression Verification and Tracker Handoff

**Files:**
- Verify: `filter_pattern/rrg_dashboard.py`
- Verify: `filter_pattern/report.py`
- Verify: `tests/test_rrg_dashboard.py`
- Verify: `tests/test_report_chart.py`

- [ ] **Step 1: Run the focused RRG and report suites**

Run:

```bash
python -m pytest tests/test_rrg_dashboard.py tests/test_report_chart.py -q
```

Expected: all tests PASS with no warnings introduced by this change.

- [ ] **Step 2: Run scanner integration tests**

Run:

```bash
python -m pytest tests/test_scanner.py tests/test_cli.py -q
```

Expected: all tests PASS, confirming representative retrieval remains non-blocking and no CLI contract changed.

- [ ] **Step 3: Run the full suite**

Run:

```bash
python -m pytest -q
```

Expected: the complete suite PASS.

- [ ] **Step 4: Inspect the final diff and generated selectors**

Run:

```bash
git diff --check
rg -n "quadrant-grid|market-rrg-grid|rrg-arrow-segment" filter_pattern/report.py tests/test_report_chart.py
git status --short
```

Expected: `git diff --check` prints nothing; `rg` prints nothing; `git status --short` shows only intentional implementation or tracker changes, if any remain uncommitted.

- [ ] **Step 5: Request tracker completion approval**

Report the verification results and ask the user to approve moving `FP-4` from In Progress to Done with a comment naming the changed files and test commands. Apply that board update only after approval, using the Jira tracker CLI so `.jira/board.html` is regenerated.
