# US-Stock Candle Freshness Implementation Plan

> Apply Ponytail full: use the existing workflow, payload, report, and shell tools; add no dependency or calendar abstraction.

**Goal:** Make every scheduled/manual Pages publication uniquely versioned and verifiably served, while keeping stale symbols visible with clear per-market freshness warnings.

**Architecture:** Schedule/manual events create a timestamp commit on `scanner-trigger` and dispatch the workflow at that ref; the dispatched run and normal `main` pushes perform the scan. The deployed artifact carries `deployment.json`, and the deploy job polls the public marker. Scanner rows are annotated by comparing each symbol's final candle with its market peers; payload/report code summarizes those warnings.

**Tech stack:** GitHub Actions YAML, Python 3.13, pytest, existing HTML renderer, curl.

## Task 1: Lock the workflow contract with failing tests

**Files:**
- Modify: `tests/test_workflow_config.py`
- Modify: `.github/workflows/scanner-pages-v2.yml`

1. Add tests asserting `scanner-trigger` is a push branch, schedule/manual runs have a trigger-only job, scan jobs are push-only, and the artifact writes then verifies `deployment.json` after deploy.
2. Run `pytest -q tests/test_workflow_config.py` and confirm the new tests fail.
3. Add the minimal `trigger_scan` job, event-sensitive concurrency, push-only scan conditions, marker creation, and post-deploy polling.
4. Re-run the workflow tests and commit.

## Task 2: Add peer freshness warnings test-first

**Files:**
- Modify: `tests/test_scanner.py`
- Modify: `filter_pattern/scanner.py`

1. Add a test with two symbols in one market where one ends earlier; assert both remain and only the older symbol receives a warning with both timestamps.
2. Run the focused test and confirm failure.
3. Add one helper to calculate `(market, symbol)` warnings and one helper to attach them to candidate/rejected rows; call them from both scan paths.
4. Re-run focused scanner tests and commit.

## Task 3: Expose market freshness in payload and report

**Files:**
- Modify: `tests/test_report_chart.py`
- Modify: `filter_pattern/report.py`
- Modify: `filter_pattern/scanner.py`

1. Add tests for `data_as_of_by_market`, `data_warnings_by_market`, header freshness tags, individual warning text, and the live-candle wording.
2. Run focused tests and confirm failure.
3. Derive per-market timestamps/warnings in `result_payload`, render them in the report header/card metadata, and replace “latest closed candle” with “latest candle.”
4. Re-run focused tests and commit.

## Task 4: Verify, integrate, and prove the live deployment

**Files:**
- Verify all modified files

1. Run `pytest -q`, `git diff --check`, and inspect the final diff for scope/minimality.
2. Merge the implementation branch into `main` and push.
3. Monitor the pushed Actions run through deployment.
4. Fetch public `deployment.json` and D1 `results.json`; verify the served run marker matches and report the US-stock market timestamp plus any retained stale-symbol warnings.
5. Update FP-5 with the verification evidence and completion status.
