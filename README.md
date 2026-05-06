# filter_pattern

D1/H4 pattern scanner and proof-report generator for TradingView-compatible OHLCV CSV exports.

The first version is intentionally TradingView-first and correctness-first:

- Input: CSV candles with `datetime` or TradingView `time`, plus `open`, `high`, `low`, `close`, `volume`.
- Scan target: D1 and H4.
- Pattern: configurable Minervini-style VCP defaults.
- Output: `results.json`, annotated PNG charts, and an HTML report.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Configure Symbols

Create `config.yml`, then point each `csv_path` at your exported TradingView D1 or H4 CSV file.

```bash
filter-pattern init-config --out config.yml
```

```yaml
timeframe: D1
technique: minervini-vcp
setup: all
symbols:
  - symbol: AAPL
    market: US stock
    tradingview_symbol: NASDAQ:AAPL
    csv_path: data/AAPL_D1.csv
```

Each CSV should contain:

```csv
datetime,open,high,low,close,volume
2025-01-01,100,105,99,104,1200000
```

TradingView exports using `time` are accepted too:

```csv
time,open,high,low,close,Volume
2026-01-01T04:00:00,100,105,99,104,1200000
```

## Run

Scan your own TradingView CSV exports:

```bash
filter-pattern scan --config config.yml --timeframe D1 --out reports/latest
```

Scan your TradingView CSV exports across every implemented setup in one report:

```bash
filter-pattern scan-all --config config.yml --timeframe D1 --out reports/tradingview-d1
filter-pattern scan-all --config config.yml --timeframe H4 --out reports/tradingview-h4
```

Choose the pattern technique:

```bash
filter-pattern scan --config config.yml --timeframe D1 --out reports/latest --technique minervini-vcp
filter-pattern scan --config config.yml --timeframe D1 --out reports/latest --technique nhathoai --setup rb
filter-pattern scan-market --config config.yml --timeframe D1 --out reports/setup-filter --universe broad --broker exness --technique nhathoai --setup all
filter-pattern scan --config config.yml --timeframe D1 --out reports/latest --technique experimental-ema21-compression
```

You can also set `technique` and `setup` in `config.yml`. CLI flags override the config values when provided.
For `--technique nhathoai`, `--setup all` writes one report with separate evaluations for `DD`, `FB`, `SB`, `BB`, `RB`, `IRB`, `ARB`, and Nhật Hoài `VCP`; use the report's setup filter to inspect one setup at a time.

Download and scan the built-in cross-market universe with Yahoo Finance data:

```bash
filter-pattern scan-market --config config.yml --timeframe D1 --out reports/market
```

Use the broader S&P 500 + cross-market universe:

```bash
filter-pattern scan-market --config config.yml --timeframe D1 --out reports/market --universe broad
```

Filter commodities, forex, and US stocks to symbols supported by Exness:

```bash
filter-pattern scan-market --config config.yml --timeframe D1 --out reports/market --universe broad --broker exness --technique minervini-vcp
```

Use exchange data for crypto instead of Yahoo Finance:

```bash
filter-pattern scan-all-market --timeframe H4 --out reports/market-h4 --period 60d --universe default --data-provider mixed
```

Provider options:

- `--data-provider mixed`: recommended, uses Yahoo Finance first, VNStock as a Vietnam-stock fallback when Yahoo is missing/too short, and CCXT exchange data for crypto.
- `--data-provider yahoo`: uses Yahoo Finance for every market. This is faster, but crypto candles may not match TradingView `BINANCE:*USDT` charts.
- `--data-provider ccxt`: crypto-only data source; non-crypto symbols are reported as unsupported for this provider.
- `--data-provider vnstock`: Vietnam-stock-only source for direct VNStock testing.

For crypto, CCXT tries Binance first, then Bybit, then OKX. This keeps the scanner closer to TradingView USDT-pair charts than Yahoo's `*-USD` crypto data.
VNStock guest access is rate-limited, so the scanner throttles fallback calls with `VNSTOCK_REQUESTS_PER_MINUTE=18` by default. Use a lower value if the API rejects requests, or a higher value only if your VNStock account allows it.

Technique behavior:

- `minervini-vcp` is the existing Minervini-style VCP scanner. `vcp` is kept as a backward-compatible alias.
- `nhathoai` scans the Nhật Hoài / Bob Volman style setup set: `dd`, `fb`, `sb`, `bb`, `rb`, `irb`, `arb`, and `vcp`.
- `experimental-ema21-compression` is the old rough EMA21 compression detector. It is kept separate so it cannot be mistaken for an exact Nhật Hoài setup.

The HTML report shows every attempted symbol grouped by market, plus data-unavailable counts by market. This matters because Yahoo Finance does not cover every Vietnam, crypto, forex, or commodity symbol that TradingView can display.

If your shell has both conda Python and Apple system Python, prefer `python` while your conda or virtual environment is active. `python3` may point to `/Library/Developer/...` and miss installed dev tools like `pytest`.

This writes:

- `reports/latest/results.json`
- `reports/latest/index.html`
- `reports/latest/charts/{symbol}.png`

Regenerate only the HTML report:

```bash
filter-pattern report --input reports/latest/results.json --out reports/latest/index.html
```

Combine multiple scan outputs into one filterable HTML report:

```bash
filter-pattern combine-report \
  --inputs reports/candidate-check-vcp/results.json reports/candidate-check-ema21/results.json reports/nhathoai-rules/results.json \
  --out reports/combined/index.html
```

You can also run without installing the console script:

```bash
python -m filter_pattern.cli scan --config config.yml --timeframe D1 --out reports/latest
```

## VCP Rules In V1

The detector checks:

- prior uptrend before the base.
- 2 to 4 contractions.
- progressively tightening contraction depth.
- volume dry-up in the late contraction.
- current close below pivot and within the configured near-pivot zone.

Defaults live in `examples/config.example.yml` and can be tuned per scan.

## Test

```bash
python -m pytest
```

## Deploy To GitHub Pages

This repo includes `.github/workflows/scanner-pages.yml` for scheduled website deployment.

Recommended first run:

1. Push the repo to GitHub.
2. In GitHub, open **Settings -> Pages** and choose **GitHub Actions** as the source.
3. Open **Actions -> Scanner Pages -> Run workflow**.
4. Choose `timeframe = all` for the first deployment.

After that, the workflow refreshes:

- H4 every 4 hours.
- D1 once per weekday after the US daily candle is normally available.

The published site keeps the previous D1 or H4 report between runs by saving generated output to the `gh-pages` branch, then deploying the static `public/` folder to GitHub Pages.

Each scan compares the new qualified watchlist with the previous `results.json` for the same timeframe. The report marks candidates as:

- `New`
- `Triggered change`
- `Improved`
- `Weaker`
- `Status changed`
- `Unchanged`
- `Dropped`

Use the report's **All changes** filter to review only symbols that changed since the last run.

The workflow uses these defaults:

```text
DATA_PROVIDER=mixed
BROKER=exness
D1_PERIOD=180d
H4_PERIOD=60d
D1_UNIVERSE=default
H4_UNIVERSE=default
D1_MARKETS=all
H4_MARKETS=US stock,Commodity,Forex,Crypto
```
