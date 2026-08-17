# Market RRG Representative Source Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unavailable Vietnam and dollar-index RRG lookups with provider-backed symbols while preserving the user-facing `E1VFVN30` and `DXY` identities.

**Architecture:** Keep the existing market-representative pipeline and provider adapters unchanged. Update the Vietnam representative configuration to request `E1VFVN30` from Fialda against its existing `VNINDEX` benchmark, and add an explicit Forex provider-symbol alias so a report row named `DXY` requests StockCharts `$USD` and maps the returned series back to `DXY`. DBC coverage remains unchanged and deferred.

**Tech Stack:** Python 3.13, pytest, Fialda RRG adapter, StockCharts RRG adapter

---

### Task 1: Use E1VFVN30 as the Vietnam market representative

**Files:**
- Modify: `filter_pattern/rrg_dashboard.py:76-85`
- Test: `tests/test_rrg_dashboard.py`

- [ ] **Step 1: Update the representative-contract assertion and add a Fialda adapter test**

Change the Vietnam entry in `test_market_representative_configuration_and_display_labels_are_fixed` and add this focused test after `test_fialda_rrg_series_uses_ratio_and_momentum_fields`:

```python
def test_vietnam_representative_uses_e1vfvn30_rrg_against_vnindex(monkeypatch) -> None:
    payload = {
        "result": [
            {"date": "20260811", "rrgdata": {"E1VFVN30": {"price": 20.0, "ratio": 98.8, "mom": 99.4}}},
            {"date": "20260812", "rrgdata": {"E1VFVN30": {"price": 20.2, "ratio": 99.1, "mom": 99.7}}},
            {"date": "20260813", "rrgdata": {"E1VFVN30": {"price": 20.4, "ratio": 99.5, "mom": 100.1}}},
            {"date": "20260814", "rrgdata": {"E1VFVN30": {"price": 20.7, "ratio": 99.9, "mom": 100.5}}},
        ]
    }

    def fake_fetch(symbols: list[str], icbs: list[str]) -> dict:
        assert symbols == ["E1VFVN30"]
        assert icbs == []
        return payload

    monkeypatch.setattr(rrg_dashboard, "_fetch_fialda_rrg", fake_fetch)
    monkeypatch.setattr(rrg_dashboard, "_safe_vn_sector_by_symbol", lambda _symbols: {})
    monkeypatch.setattr(rrg_dashboard.time, "sleep", lambda _seconds: None)

    selections = rrg_dashboard._vnstock_rrg_references(["E1VFVN30"])

    assert list(selections) == ["E1VFVN30"]
    assert selections["E1VFVN30"].benchmark == "VNINDEX"
    assert len(selections["E1VFVN30"].rrg_series) == 4
```

The updated representative assertion must be:

```python
assert rrg_dashboard.RRG_MARKET_REPRESENTATIVES == {
    "US stock": ["SPY"],
    "Vietnam stock": ["E1VFVN30"],
    "Crypto": ["BTCUSDT", "ETHUSDT"],
    "Forex": ["DXY"],
    "Index": ["US500"],
    "Commodity": ["XAUUSD"],
    "Commodity ETF": ["DBC"],
}
```

- [ ] **Step 2: Run the focused tests to verify the representative contract fails**

Run:

```bash
python -m pytest \
  tests/test_rrg_dashboard.py::test_market_representative_configuration_and_display_labels_are_fixed \
  tests/test_rrg_dashboard.py::test_vietnam_representative_uses_e1vfvn30_rrg_against_vnindex \
  -q
```

Expected: one failure showing the configured Vietnam representative is still `VNINDEX`, while the isolated Fialda adapter test passes.

- [ ] **Step 3: Update the Vietnam representative configuration**

Change only the Vietnam entry in `RRG_MARKET_REPRESENTATIVES`:

```python
RRG_MARKET_REPRESENTATIVES = {
    "US stock": ["SPY"],
    "Vietnam stock": ["E1VFVN30"],
    "Crypto": ["BTCUSDT", "ETHUSDT"],
    "Forex": ["DXY"],
    "Index": ["US500"],
    "Commodity": ["XAUUSD"],
    "Commodity ETF": ["DBC"],
}
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```bash
python -m pytest \
  tests/test_rrg_dashboard.py::test_market_representative_configuration_and_display_labels_are_fixed \
  tests/test_rrg_dashboard.py::test_vietnam_representative_uses_e1vfvn30_rrg_against_vnindex \
  -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit the Vietnam representative change**

```bash
git add filter_pattern/rrg_dashboard.py tests/test_rrg_dashboard.py
git commit -m "Use E1VFVN30 as Vietnam RRG representative"
```

### Task 2: Back DXY with the StockCharts dollar index symbol

**Files:**
- Modify: `filter_pattern/rrg_dashboard.py:86-110,1108-1110`
- Test: `tests/test_rrg_dashboard.py`

- [ ] **Step 1: Add failing provider-alias and report-identity tests**

Add the DXY assertion to `test_cross_market_stockcharts_rrg_symbol_mapping`:

```python
assert rrg_dashboard._forex_stockcharts_symbol("DXY") == "$USD"
```

Add this focused test after `test_cross_market_stockcharts_rrg_symbol_mapping`:

```python
def test_dxy_rrg_uses_stockcharts_usd_symbol_but_keeps_dxy_identity(monkeypatch) -> None:
    payload = {
        "rrgdata": [
            {"rrgdata": {"$USD": {"jdkratio": 99.0, "jdkmom": 99.4, "price": 100.0}}},
            {"rrgdata": {"$USD": {"jdkratio": 99.3, "jdkmom": 99.7, "price": 100.2}}},
            {"rrgdata": {"$USD": {"jdkratio": 99.7, "jdkmom": 100.1, "price": 100.5}}},
            {"rrgdata": {"$USD": {"jdkratio": 100.1, "jdkmom": 100.4, "price": 100.8}}},
        ]
    }

    def fake_fetch(symbols: list[str], benchmark: str) -> dict:
        assert symbols == ["$USD"]
        assert benchmark == "$ONE"
        return payload

    monkeypatch.setattr(rrg_dashboard, "_fetch_stockcharts_rrg", fake_fetch)
    monkeypatch.setattr(rrg_dashboard.time, "sleep", lambda _seconds: None)

    selections = rrg_dashboard._forex_rrg_references(["DXY"])

    assert list(selections) == ["DXY"]
    assert selections["DXY"].benchmark == "$ONE"
    assert len(selections["DXY"].rrg_series) == 4
```

- [ ] **Step 2: Run the focused tests to verify they fail for the current `$DXY` mapping**

Run:

```bash
python -m pytest \
  tests/test_rrg_dashboard.py::test_cross_market_stockcharts_rrg_symbol_mapping \
  tests/test_rrg_dashboard.py::test_dxy_rrg_uses_stockcharts_usd_symbol_but_keeps_dxy_identity \
  -q
```

Expected: both tests fail because `_forex_stockcharts_symbol("DXY")` currently returns `$DXY`.

- [ ] **Step 3: Add the explicit Forex provider-symbol mapping**

Add this constant after `RRG_MARKET_REPRESENTATIVE_LABELS`:

```python
FOREX_STOCKCHARTS_SYMBOLS = {
    "DXY": "$USD",
}
```

Then replace `_forex_stockcharts_symbol` with:

```python
def _forex_stockcharts_symbol(symbol: str) -> str:
    cleaned = re.sub(r"[^A-Z]", "", str(symbol).upper())
    return FOREX_STOCKCHARTS_SYMBOLS.get(cleaned, f"${cleaned}" if cleaned else "")
```

The existing `display_by_stockcharts` mapping in `_forex_rrg_references` will map StockCharts `$USD` results back to report symbol `DXY`.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```bash
python -m pytest \
  tests/test_rrg_dashboard.py::test_cross_market_stockcharts_rrg_symbol_mapping \
  tests/test_rrg_dashboard.py::test_dxy_rrg_uses_stockcharts_usd_symbol_but_keeps_dxy_identity \
  -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit the DXY provider mapping**

```bash
git add filter_pattern/rrg_dashboard.py tests/test_rrg_dashboard.py
git commit -m "Map DXY to StockCharts dollar index"
```

### Task 3: Verify and deploy the combined change

**Files:**
- Verify: `filter_pattern/rrg_dashboard.py`
- Verify: `tests/test_rrg_dashboard.py`
- Verify: `tests/test_report_chart.py`

- [ ] **Step 1: Run the RRG and report-chart regression tests**

Run:

```bash
python -m pytest tests/test_rrg_dashboard.py tests/test_report_chart.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run the complete test suite**

Run:

```bash
python -m pytest -q
```

Expected: all tests pass with no failures.

- [ ] **Step 3: Inspect the final diff and commit graph**

Run:

```bash
git diff main...HEAD --check
git diff main...HEAD -- filter_pattern/rrg_dashboard.py tests/test_rrg_dashboard.py
git log --oneline --decorate -5
```

Expected: no whitespace errors; the runtime diff contains only the `E1VFVN30` configuration, the `DXY` provider alias, and their tests; the two implementation commits are at the branch tip.

- [ ] **Step 4: Fast-forward main and push the deployment branch**

From the primary checkout, fast-forward `main` to the implementation branch and run:

```bash
git push origin main
```

Expected: `origin/main` advances to the implementation branch tip and the deployment workflow starts.

- [ ] **Step 5: Verify the deployed report payload**

After the deployment workflow completes, fetch the deployed D1 report payload and inspect `rrg_reference.market_representatives`.

Expected: the Vietnam representative is `E1VFVN30` with an attached RRG quadrant, and the Forex representative remains labeled `DXY` with an attached RRG quadrant. DBC may remain absent because its coverage is explicitly deferred.
