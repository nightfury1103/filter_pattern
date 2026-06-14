# Reviewable Filter Patterns Design

## Goal

Preserve the current strict candidate list while making promising rejected setups visible for manual review.

## Scope

This first pass focuses on VCP-style false negatives like tight near-pivot bases that fail one or more strict gates. Strict `qualified` behavior must not loosen. The report should instead surface these rows in review/near-match areas with meaningful partial scores.

## Design

Original VCP scoring should no longer collapse every rejected setup to `0.0`. A rejected setup can earn partial evidence points for useful chart traits: near trigger, controlled base depth, detected contractions, dry-up evidence, and prior trend evidence. Hard failures still keep `qualified=False`.

The report review filter should treat VCP rows with trigger context and close proximity as reviewable even when their detector score is below the current generic threshold. This keeps the final candidate list clean while making discretionary chart reads inspectable.

## Non-Goals

- Do not promote rejected setups to candidates.
- Do not loosen SB/FB timing windows in this first pass.
- Do not change RRG or broker gating in this first pass.
- Do not add a new lifecycle enum yet.

## Testing

Add regression tests that prove:

- a strict VCP reject can receive a nonzero partial score when it is near pivot and has useful supporting evidence;
- a low-scoring near-pivot VCP row is included in `review_setups`;
- existing strict detector and scanner tests remain green.
