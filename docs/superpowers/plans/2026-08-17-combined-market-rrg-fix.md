# Combined Market RRG Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve fixed market RRG representative rows when GitHub Pages combines scanner shard results.

**Architecture:** Add one focused aggregation helper in `report.py` that collects shard-level `rrg_reference` objects, deduplicates representative rows by market and internal symbol, prefers usable RRG data, and carries the merged reference into the combined payload. Existing overview rendering remains unchanged because it already consumes the correct payload contract.

**Tech Stack:** Python 3.13, pytest, existing JSON report aggregation.

---

### Task 1: Preserve Market Representatives Across Shards

**Files:**
- Modify: `filter_pattern/report.py:1723-1765`
- Modify: `tests/test_report_chart.py:555`

- [ ] **Step 1: Write the failing regression test**

Add this test beside the existing combined-results tests in `tests/test_report_chart.py`:

```python
def test_combined_results_preserve_market_rrg_representatives() -> None:
    unavailable_spy = _overview_representative("SPY", "US stock", None)
    available_spy = _overview_representative("SPY", "US stock", "LEADING")
    btc = _overview_representative("BTCUSDT", "Crypto", "LEADING", display_symbol="BTCUSD")
    eth = _overview_representative("ETHUSDT", "Crypto", None, display_symbol="ETHUSD")
    first = result_payload([], [], {"timeframe": "D1"})
    first["rrg_reference"] = {
        "enabled": True,
        "status": "attached",
        "attached_count": 2,
        "errors": ["temporary provider warning"],
        "market_representatives": [unavailable_spy, btc],
    }
    second = result_payload([], [], {"timeframe": "D1"})
    second["rrg_reference"] = {
        "enabled": True,
        "status": "attached",
        "attached_count": 1,
        "errors": ["temporary provider warning", "second warning"],
        "market_representatives": [available_spy, eth],
    }

    combined = report._combined_payload([first, second], ["first.json", "second.json"])
    reference = combined["rrg_reference"]
    representatives = {
        (row["market"], row["symbol"]): row
        for row in reference["market_representatives"]
    }

    assert list(representatives) == [
        ("Crypto", "BTCUSDT"),
        ("Crypto", "ETHUSDT"),
        ("US stock", "SPY"),
    ]
    assert representatives[("US stock", "SPY")]["rrg"]["stock_intent"]["quadrant"] == "LEADING"
    assert representatives[("Crypto", "ETHUSDT")]["rrg"] == {}
    assert reference["attached_count"] == 3
    assert reference["errors"] == ["temporary provider warning", "second warning"]
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python -m pytest tests/test_report_chart.py::test_combined_results_preserve_market_rrg_representatives -q
```

Expected: FAIL because `_combined_payload` currently omits `rrg_reference`.

- [ ] **Step 3: Implement the minimal aggregation helper**

Add these helpers before `_combined_payload` in `filter_pattern/report.py`:

```python
def _combined_rrg_reference(payloads: list[dict]) -> dict | None:
    references = [payload.get("rrg_reference") for payload in payloads]
    references = [reference for reference in references if isinstance(reference, dict)]
    if not references:
        return None

    representatives: dict[tuple[str, str], dict] = {}
    errors: list[str] = []
    for reference in references:
        for error in reference.get("errors") or []:
            error_text = str(error)
            if error_text not in errors:
                errors.append(error_text)
        for row in reference.get("market_representatives") or []:
            if not isinstance(row, dict):
                continue
            key = (str(row.get("market") or ""), str(row.get("symbol") or ""))
            if not all(key):
                continue
            current = representatives.get(key)
            if current is None or (
                _usable_market_rrg_representative(row)
                and not _usable_market_rrg_representative(current)
            ):
                representatives[key] = row

    combined = dict(references[0])
    combined["enabled"] = any(bool(reference.get("enabled")) for reference in references)
    combined["status"] = "attached" if any(
        reference.get("status") == "attached" for reference in references
    ) else str(references[0].get("status") or "unavailable")
    combined["attached_count"] = sum(int(reference.get("attached_count") or 0) for reference in references)
    combined["errors"] = errors
    combined["market_representatives"] = [representatives[key] for key in sorted(representatives)]
    return combined


def _usable_market_rrg_representative(row: dict) -> bool:
    intent = ((row.get("rrg") or {}).get("stock_intent") or {})
    return str(intent.get("quadrant") or "").upper() in {
        "LEADING",
        "IMPROVING",
        "WEAKENING",
        "LAGGING",
    }
```

Then attach the helper result near the end of `_combined_payload`:

```python
    rrg_reference = _combined_rrg_reference(payloads)
    if rrg_reference is not None:
        payload["rrg_reference"] = rrg_reference
```

- [ ] **Step 4: Verify GREEN and report rendering**

Run:

```bash
python -m pytest tests/test_report_chart.py::test_combined_results_preserve_market_rrg_representatives tests/test_report_chart.py -k "rrg_overview or combined_results" -q
```

Expected: all selected tests PASS.

- [ ] **Step 5: Run the full suite and inspect the diff**

Run:

```bash
python -m pytest -q
git diff --check
```

Expected: all tests PASS and `git diff --check` produces no output.

- [ ] **Step 6: Commit, merge to main, and push**

Commit the spec amendment, plan, regression test, and implementation. Fast-forward `main`, rerun the focused regression on merged `main`, and push to trigger GitHub Pages.
