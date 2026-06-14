# Reviewable Filter Patterns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep strict pattern candidates unchanged while surfacing promising rejected VCP setups for manual review.

**Architecture:** Add partial scoring to rejected original VCP evidence and adjust report reviewability for VCP rows with near-trigger context. The scanner/report pipeline already carries rejected rows into `near_matches` and `review_setups`, so no JSON schema change is needed.

**Tech Stack:** Python dataclasses, existing pytest suite, existing report payload helpers.

---

### Task 1: VCP Partial Score

**Files:**
- Modify: `filter_pattern/detector.py`
- Test: `tests/test_detector.py`

- [ ] **Step 1: Write the failing test**

Add a test in `tests/test_detector.py` that builds a VCP-like series with near-pivot price but missing strict prior-uptrend confirmation. Assert `qualified` is false and `score > 0`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_detector.py::test_rejected_vcp_keeps_partial_score_for_reviewable_near_pivot_base -q`
Expected: FAIL because rejected VCP score is currently `0.0`.

- [ ] **Step 3: Implement partial scoring**

Update `_score()` in `filter_pattern/detector.py` so rejected VCP evidence receives bounded partial points from contractions, proximity, volume evidence, and prior trend evidence. Preserve the current score formula for qualified setups.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_detector.py::test_rejected_vcp_keeps_partial_score_for_reviewable_near_pivot_base -q`
Expected: PASS.

### Task 2: Reviewable VCP Rows

**Files:**
- Modify: `filter_pattern/report.py`
- Test: `tests/test_report_chart.py`

- [ ] **Step 1: Write the failing test**

Add a test in `tests/test_report_chart.py` that sends a rejected VCP row with pivot/current close, close distance, and low detector score through `result_payload()`. Assert the row appears in `review_setups`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_report_chart.py::test_payload_includes_near_pivot_vcp_rejects_as_review_setups -q`
Expected: FAIL because current VCP reviewability requires score at least `50`.

- [ ] **Step 3: Implement reviewability rule**

Update `_is_reviewable_setup()` in `filter_pattern/report.py` so VCP-family rows with trigger context and `abs(distance_to_pivot_pct) <= 5.0` are reviewable even with lower scores.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_report_chart.py::test_payload_includes_near_pivot_vcp_rejects_as_review_setups -q`
Expected: PASS.

### Task 3: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused suite**

Run: `python3 -m pytest tests/test_detector.py tests/test_report_chart.py tests/test_scanner.py -q`
Expected: all tests pass.
