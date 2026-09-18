# D1 Market Compass: fixed first experiment

## Decision contract

The compass helps choose which D1 setups to investigate: LONG, SHORT, or WAIT.
Weak bullish evidence is not a short signal. Both sides use symmetric rules.
Direction is context, not an entry order, a probability, or a profitability claim.
Existing RRG, pattern qualification, and direction authority remain unchanged.

## Frozen candidates (before inspecting historical results)

All signals use completed D1 OHLC candles. First eligible observation is bar 201.

1. `ema`: EMA20 above/below EMA50. Always directional except exact equality.
2. `ema_atr`: (EMA20 - EMA50) / Wilder ATR14; LONG above +0.5 with
   positive five-bar change; SHORT below -0.5 with negative change; else WAIT.
3. `multi_horizon` (primary research candidate): log returns over 20/60/120 bars,
   each divided by trailing 60-bar daily log-return standard deviation times
   sqrt(horizon). All three must share a sign, their equally weighted score
   must exceed +/-0.5, and 20-bar efficiency ratio must be >=0.20. Otherwise WAIT.
   Efficiency = abs(net close change) / sum(abs(daily close changes)).

These thresholds are design assumptions, not fitted parameters. Momentum is
the five-bar change in the signed score; it is displayed separately and is
not an extra multi-horizon gate. Agreement is not a calibrated probability.
No threshold search or selection using final holdout results is allowed.

## Evaluation

- Primary horizon: 10 bars; also report 5 and 20 bars.
- Signal at close T; hypothetical observation starts at open T+1 and ends at
  close T+h. Record signed return and actual intervening high/low excursion.
- One shared chronological cutoff, approximately 70% through the union of
  eligible signal dates. Development rows whose outcomes cross the cutoff
  are excluded. Test signals start on/after the cutoff. No random split.
- Report each symbol, model, horizon and side separately; no pooled accuracy
  dominated by BTC's daily calendar or equity's positive historical drift.
- Daily observations are descriptive and overlap. Also compute independently
  scheduled observations every h bars, identical across models. These outcomes
  do not overlap within a symbol/horizon, but are not assumed IID.
- Show hit rate, false-direction rate, mean/median signed return, adverse and
  favorable excursion, directional coverage, state changes and rapid reversals.
- Compare directional returns with an always-same-side baseline on all eligible
  dates; compute moving-block-bootstrap 95% intervals for selected signed return
  and its difference from that baseline (fixed 40-bar blocks, fixed RNG seed).
  This is a descriptive screen, not proof of a causal benefit or multiple-test
  adjusted statistical significance.
- Separate chronological halves of the holdout are shown to expose instability.
- A side receives `promising` only at the primary horizon with >=30 scheduled
  non-overlapping observations, positive bootstrap lower bounds for both mean
  return and baseline lift, and positive signed mean in both holdout halves.
  Otherwise use `insufficient` or `not_demonstrated`. These labels never
  automatically authorize live trades or suppress scanner results.
- Historical setup-entry/stop/target performance is a later distinct test;
  forward direction returns do not establish setup profitability. Costs,
  funding and slippage are not included in these directional diagnostics.

## Data and reproducibility

Save candles, provenance, SHA256, dropped incomplete dates, actual date coverage,
errors and protocol in every output. Built-in Yahoo instruments are explicitly
named: S&P 500 index, SPY, BTC/ETH USD spot, gold futures proxy, EURUSD, USDJPY,
USD index, and attempted Vietnam ETF proxy. Never call a futures/ETF proxy the
native CFD/index. CSV config allows exact TradingView instruments.
Do not forward-fill market holidays or silently substitute missing assets.
Reject invalid OHLC, duplicate or unordered dates. Missing/stale current data
must not issue an actionable live direction. D1 bars have market-specific
session calendars: 20 crypto bars and 20 stock bars are not equal elapsed days.

Existing RRG history is externally computed and short. Optional existing RRG
report data can be displayed with its actual timestamp/benchmark, but is not
called a full historical A/B test. No invented RRG reconstruction.

## Deliverables

`compass-research` CLI, reproducible results/candles JSON, Vietnamese interactive
HTML with current direction, historical price/signal charts and model/horizon
comparisons. Optional `--rrg-results` keeps the supplied RRG overview alongside
the experiment without changing its rules. Unit tests cover causality, symmetry,
scale invariance, missing data, next-open timing, split boundaries and reporting.

## Research basis

- https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum
- https://www.aqr.com/Insights/Research/Alternative-Thinking/Key-Design-Choices-when-Building-a-Risk-Mitigating-Portfolio

Published trend-following evidence motivates the hypothesis, but does not
validate these shorter horizons, thresholds, instruments or setup filters.

## Reporting addendum (after first result inspection)

Add always-same-side hit rate beside conditional hit rate to expose directional
base rates. Add descriptive reaction delay relative to alternating 20-bar
closing-price breakouts: median time to matching bias within ten bars, plus
missed events. This reference is not a true-reversal label. Neither diagnostic
changes the frozen models, thresholds, cutoff, primary horizon or evidence gate.
