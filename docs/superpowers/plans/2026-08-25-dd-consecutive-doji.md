# DD Consecutive-Doji Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the DD detector accept only two adjacent valid dojis at the configured body ratio, then prove the change with tests and identical-input old/new JPG charts.

**Architecture:** Keep the two existing DD candidate positions (`cluster_end` on the latest candle and one candle before it). Evaluate exactly one adjacent pair at each position. Both candles must pass the existing doji/range/EMA/wick checks, using `cfg.doji_body_ratio` exactly. `_dd_entry_status` remains the lifecycle authority. Scoring weights stay unchanged.

**Tech Stack:** Python 3.11+, pytest, matplotlib chart renderer, existing `nhathoai` DD detector.

## Global Constraints

- Modify only `filter_pattern/detector.py`, `filter_pattern/chart.py`, and `tests/test_detector.py`.
- Do not change setup scores, generic config defaults, other detectors, scanner/report filtering, market-data providers, RRG behavior, or live-candle handling.
- No new dependency, detector class, compatibility layer, or retained legacy DD implementation.
- Follow red-green TDD: record the failing baseline before production changes.
- Render `reports/dd-ab/old/dd-interrupted-pair.jpg` from the current detector before production changes; do not overwrite it afterward.
- Render `reports/dd-ab/new/dd-interrupted-pair.jpg` from the revised detector using the identical candle list, timeframe, configuration, chart window, dimensions, and axis limits.

---

### Task 1: Failing regression tests

**Files:**
- Modify: `tests/test_detector.py`

**Interfaces:**
- Consumes: `make_bullish_dd_series(triggered: bool, sharp_pullback: bool = False) -> list[Candle]`, `make_config() -> VCPConfig`, `detect_pattern(...)`
- Produces: `make_interrupted_nonconsecutive_dd_series() -> list[Candle]`, `test_dd_rejects_interrupted_nonconsecutive_doji_pair`, `test_dd_respects_configured_doji_body_ratio`

- [ ] **Step 1: Write the failing tests**

Add `from dataclasses import replace` and this helper plus tests next to the existing bullish DD tests:

```python
def make_interrupted_nonconsecutive_dd_series() -> list[Candle]:
    candles = make_bullish_dd_series(triggered=False)
    first_doji, second_doji, waiting = candles[-3], candles[-2], candles[-1]
    interruption = replace(first_doji, open=103.95, high=105.05, low=103.75, close=104.75)
    latest = replace(waiting, open=104.10, high=105.00, low=103.95, close=104.70)
    return [*candles[:-3], first_doji, interruption, second_doji, latest]


def test_dd_rejects_interrupted_nonconsecutive_doji_pair() -> None:
    candles = make_interrupted_nonconsecutive_dd_series()

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="dd")

    assert evidence.qualified is False
    assert evidence.status == "rejected"
    assert any(
        "DD requires two consecutive valid doji candles near EMA21" in failure
        for failure in evidence.failures
    )


def test_dd_respects_configured_doji_body_ratio() -> None:
    candles = make_bullish_dd_series(triggered=False)
    second_doji = candles[-2]
    candles[-2] = replace(second_doji, open=104.05, high=105.10, low=103.85, close=104.45)
    config = replace(make_config(), doji_body_ratio=0.30)

    evidence = detect_pattern(candles, "nhathoai", config, setup="dd")

    assert evidence.qualified is False
    assert evidence.status == "rejected"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/huypham/miniconda3/bin/python3.13 -m pytest tests/test_detector.py::test_dd_rejects_interrupted_nonconsecutive_doji_pair tests/test_detector.py::test_dd_respects_configured_doji_body_ratio -q`

Expected: FAIL because the current detector still qualifies both fixtures.

- [ ] **Step 3: Render the old A/B chart before production changes**

Generate `reports/dd-ab/old/dd-interrupted-pair.jpg` from the current detector using `make_interrupted_nonconsecutive_dd_series()`, timeframe `D1`, `make_config()`, and `render_chart`. Lock price-axis limits from the plotted candle window so the later new chart can reuse them. Do not overwrite this file after detector changes.

---

### Task 2: Consecutive-pair detector and chart wording

**Files:**
- Modify: `filter_pattern/detector.py:3324-3602`
- Modify: `filter_pattern/detector.py:3778-3786`
- Modify: `filter_pattern/chart.py:454`

**Interfaces:**
- Consumes: existing `_score_dd_cluster`, `_dd_entry_status`, `cfg.doji_body_ratio`
- Produces: DD pairs of length 2 only; rejection evidence containing `DD requires two consecutive valid doji candles near EMA21`

- [ ] **Step 1: Restrict DD candidates to one adjacent pair per lifecycle position**

In `_score_dd_direction`, replace `for cluster_len in range(2, 5)` with a fixed adjacent pair:

```python
    best = _empty_dd(direction, ["DD requires two consecutive valid doji candles near EMA21"])
    n = len(candles)
    for cluster_end in (n - 2, n - 1):
        if cluster_end < 5:
            continue
        cluster_start = cluster_end - 1
        if cluster_start < 10:
            continue
        cluster = candles[cluster_start : cluster_end + 1]
```

- [ ] **Step 2: Require both candles to pass the DD candle predicate at `cfg.doji_body_ratio`**

In `_score_dd_cluster`, require every candle in the pair to have a positive range, `body_ratio <= cfg.doji_body_ratio`, range `<= 90%` of the prior-eight average, range percentage `<= cfg.max_signal_range_pct`, EMA21 proximity, and no direction-specific wick rejection. On failure, return:

```python
    return 0, [], ["DD requires two consecutive valid doji candles near EMA21"]
```

Put that same sentence in the first three `_dd_reject_lines` entries so the chart subtitle can show it. Keep cluster score at 15 when the pair passes.

- [ ] **Step 3: Update chart annotation text**

In `_draw_dd_annotations`, change `2+ doji near EMA21` to `2 consecutive dojis near EMA21`.

- [ ] **Step 4: Run targeted tests to verify they pass**

Run: `/Users/huypham/miniconda3/bin/python3.13 -m pytest tests/test_detector.py -q`

Expected: PASS, including existing bullish waiting and triggered DD tests.

- [ ] **Step 5: Render the new A/B chart from the identical candles**

Generate `reports/dd-ab/new/dd-interrupted-pair.jpg` with the same candle list, timeframe, config, chart window, figure size, and axis limits as the old image. Confirm the new title/status is rejected and the subtitle contains `DD requires two consecutive valid doji candles near EMA21`.

- [ ] **Step 6: Run the complete suite and commit**

Run: `/Users/huypham/miniconda3/bin/python3.13 -m pytest -q`

Report network-dependent universe failures separately if they occur. Commit the DD-only implementation.
