# BTCUSDT.P Real-Data DD A/B Chart Design

## Goal

Replace the synthetic DD comparison with two review images built from the same real Binance `BTCUSDT.P` daily perpetual candles.

## Data and Selection

- Fetch Binance USDT-margined perpetual `BTC/USDT:USDT` D1 OHLCV through the project's existing CCXT dependency.
- Search historical rolling endpoints for a case where the pre-revision DD detector qualifies an interrupted/non-consecutive doji sequence and the revised detector rejects it.
- Do not alter, interpolate, or synthesize any candle.
- If no exact detector-difference case exists in the available Binance history, stop and report that fact instead of manufacturing one.

## Rendering

- Render A with detector commit `8401c4b3` and B with detector commit `6d9d6e33`.
- Feed both renderers the identical candle list, configuration, D1 chart window, image dimensions, and axis behavior.
- Label both charts with `BTCUSDT.P`, Binance perpetual, timeframe, and visible data-date range.
- A must show the old detector result; B must show the revised detector result and its rejection evidence.

## Output

- `reports/dd-ab-real-btcusdt/old/btcusdt-p-dd.jpg`
- `reports/dd-ab-real-btcusdt/new/btcusdt-p-dd.jpg`

## Verification

- Record the selected candle endpoint and SHA-256 hash of the shared OHLCV payload.
- Confirm both JPGs are 1920x1080 and visually readable.
- Confirm the old and new results differ for the intended consecutive-doji rule.
- Make no production detector or chart-code changes solely to create these images.
