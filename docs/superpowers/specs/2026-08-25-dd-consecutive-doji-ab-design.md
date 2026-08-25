# DD Consecutive-Doji Filter and A/B Review Design

## Purpose

Revise only the DD detector so it cannot qualify an interrupted or non-consecutive pair of dojis. Grok will implement the revision and generate two directly comparable charts. Codex will review the implementation, tests, and chart evidence; Codex will not implement the detector change.

## Theory Contract

A valid DD setup requires:

1. A clear directional impulse.
2. One controlled pullback toward EMA21.
3. Two consecutive signal candles that are both valid dojis near EMA21.
4. A combined signal level at the pair's high for long setups or low for short setups.
5. Either a near-signal `WAITING` state or an immediate next-candle `TRIGGERED` state.

The revision changes only item 3. Existing impulse, pullback, EMA, signal, stop, obstacle, scoring, long/short, and lifecycle rules remain unchanged.

## Confirmed Defect

The current detector searches clusters of two through four candles and accepts a cluster when any two candles pass the doji checks. This allows the sequence `valid doji -> non-doji -> valid doji` to qualify as DD even though the two valid dojis are not consecutive.

The current doji test also uses `max(cfg.doji_body_ratio, 0.35)`. With the default configured ratio of `0.30`, this silently widens the accepted body ratio to `0.35`.

## Revised Detection Rule

Keep the two existing DD candidate positions, but evaluate exactly one adjacent pair at each position:

- A pair ending on the latest candle.
- A pair ending one candle before the latest candle.

The existing `_dd_entry_status` result remains authoritative. A pair ending one candle before the latest candle may therefore remain `WAITING` or become `TRIGGERED`, `LATE`, or `FAILED` according to the latest candle; this revision must not alter that lifecycle behavior.

Both candles in the pair must independently satisfy all of these checks:

- Positive high-low range.
- `abs(close - open) / (high - low) <= cfg.doji_body_ratio`.
- Range no larger than 90% of the average range of the preceding eight candles.
- Range percentage no larger than `cfg.max_signal_range_pct`.
- Candle is near EMA21 under the existing distance rule.
- Candle does not violate the existing direction-specific wick rejection rule.

The candles are consecutive by position in the normalized candle series. Weekends and exchange holidays do not invalidate adjacency.

Three or more consecutive dojis are not automatically rejected: the detector evaluates the lifecycle-appropriate latest adjacent pair. A non-doji between the two valid dojis always rejects the DD pair.

When no pair qualifies, rejection evidence must include:

`DD requires two consecutive valid doji candles near EMA21`

## Minimal Implementation Boundary

Grok may modify:

- `filter_pattern/detector.py`
  - Restrict DD candidate length to two adjacent candles.
  - Require both candles to pass the DD candle predicate.
  - Respect `cfg.doji_body_ratio` exactly.
  - Emit the explicit consecutive-doji rejection reason.
- `filter_pattern/chart.py`
  - Change the DD annotation text from `2+ doji near EMA21` to `2 consecutive dojis near EMA21`.
- `tests/test_detector.py`
  - Add focused regression coverage described below.

Grok must not change setup scores, generic configuration defaults, other detectors, scanner/report filtering, market-data providers, RRG behavior, or live-candle handling.

No new dependency, detector class, compatibility layer, or retained legacy DD implementation is allowed.

## Regression Fixture

Add a deterministic helper based on `make_bullish_dd_series(triggered=False)` that creates this final signal area:

1. Valid doji: `open=104.25, high=105.05, low=103.75, close=104.35`.
2. Invalid interruption candle: `open=103.95, high=105.05, low=103.75, close=104.75`.
3. Valid doji: retain the existing `open=104.35, high=105.10, low=103.85, close=104.45` candle.
4. Replace the latest waiting candle with `open=104.10, high=105.00, low=103.95, close=104.70`. It remains below and near the signal, but its body is deliberately too large to be a doji.

Use the original timestamps and volume values from the base fixture. On the current baseline this input qualifies as long `WAITING` DD with a three-candle cluster. After the revision it must be rejected: the older adjacent pair contains candle 2, while the latest adjacent pair contains candle 4, so neither pair contains two valid dojis.

## Required Tests

Grok must follow red-green TDD and record the failing baseline result before changing production code.

1. `test_dd_rejects_interrupted_nonconsecutive_doji_pair`
   - Uses the regression fixture above.
   - Expects `qualified is False`, status `rejected`, and the consecutive-doji rejection reason.
2. Existing bullish DD waiting test remains green.
3. Existing bullish DD triggered test remains green.
4. `test_dd_respects_configured_doji_body_ratio`
   - Starts from `make_bullish_dd_series(triggered=False)` with `doji_body_ratio=0.30`.
   - Replaces the second explicit doji with `open=104.05, high=105.10, low=103.85, close=104.45`, whose body ratio is `0.32`.
   - Expects rejection, proving the detector no longer widens the configured threshold.

The existing bullish waiting fixture also protects the rule that an older additional small/doji candle does not invalidate the lifecycle-appropriate latest pair; do not add a duplicate test for that behavior.

Run at minimum:

```bash
pytest tests/test_detector.py -q
```

Then run the complete suite. Network-dependent universe failures must be reported separately and must not be presented as DD failures.

## A/B Chart Deliverables

Generate exactly two full-resolution JPG images from the same regression candles, timeframe, configuration, chart window, dimensions, and axis limits:

- `reports/dd-ab/old/dd-interrupted-pair.jpg`
- `reports/dd-ab/new/dd-interrupted-pair.jpg`

Generation order:

1. Before modifying production code, render the old image from the current `main` detector and preserve it.
2. Implement and test the revision.
3. Render the new image from the revised detector using the identical candle list.

The old chart must visibly show:

- DD `WAITING`/qualified state.
- The current three-candle DD cluster annotation.
- The valid-doji, interruption-candle, valid-doji sequence.

The new chart must visibly show:

- DD `rejected` state.
- Rejection subtitle containing `DD requires two consecutive valid doji candles near EMA21`.
- The identical candle sequence and EMA21 line.

The new chart does not need a rejected-cluster rectangle. Keeping the candles identical and showing the explicit rejection reason is sufficient for visual review.

Do not overwrite the old image after the detector changes. Do not use two different symbols, fixtures, date windows, or price scales.

## Grok Handoff Requirements

Grok must return:

- The implementation commit hash.
- The red test command and expected failure observed before the fix.
- The green targeted and full-suite test results after the fix.
- Absolute paths to both A/B JPG files.
- A short diff summary limited to DD behavior.

## Codex Review Checklist

Codex will reject the implementation if any item fails:

- The regression test was not observed failing before production changes.
- A non-consecutive pair can still qualify.
- The configured `doji_body_ratio` is still widened.
- Existing valid waiting or triggered DD fixtures regress.
- Other setup detectors or scoring rules changed.
- The old and new pictures use different candle data or chart scales.
- The old picture is regenerated using revised logic.
- The new rejection reason is not visible in the new picture.

## Acceptance Criteria

- The known interrupted pair qualifies on the old baseline and is rejected by the revised detector.
- Two adjacent valid dojis still qualify under the existing surrounding DD rules.
- Waiting and triggered lifecycle behavior remains unchanged.
- The configured doji ratio is honored exactly.
- The two A/B images let the user compare the same candles before and after the rule change.
- Only DD detector behavior and its chart wording change.
