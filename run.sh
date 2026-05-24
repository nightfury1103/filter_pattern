#!/usr/bin/env bash
set -euo pipefail

# Automatic market scan.
#
# MODE:
# - fast = default cross-market universe. Faster and avoids loading S&P 500.
# - full = broad D1 universe, including S&P 500. Slower.
#
# Data provider:
# - mixed = Yahoo first, VNStock fallback for Vietnam stocks, CCXT exchange data for crypto. Recommended.
# - yahoo = Yahoo Finance for every market. Faster, but crypto symbols may not match TradingView USDT pairs.
# - ccxt = crypto only.
# - vnstock = Vietnam stock only.
# Crypto scan:
# - core = faster scan. Binance + Bybit + OKX, capped by CRYPTO_MAX_SYMBOLS.
# - wide = full scan. Binance + Bybit + OKX + MEXC, uncapped unless CRYPTO_MAX_SYMBOLS is set.
# - static = only the crypto symbols already listed in the static universe.
# - CRYPTO_MARKET_TYPE=perp matches crypto futures/perpetual TradingView symbols such as BTCUSDT.P.
# - CRYPTO_MARKET_TYPE=spot matches spot symbols such as BTCUSDT.
# Broker filter:
# - exness = only Exness-supported commodities/forex/US stocks, plus Vietnam/crypto.
# - all = every symbol in the selected universe.
MODE="${MODE:-fast}"
DATA_PROVIDER="${DATA_PROVIDER:-mixed}"
BROKER="${BROKER:-exness}"
RUN_D1="${RUN_D1:-1}"
RUN_H4="${RUN_H4:-1}"
NEAR_MATCH_CHART_LIMIT="${NEAR_MATCH_CHART_LIMIT:-5}"
export CRYPTO_MODE="${CRYPTO_MODE:-wide}"
export CRYPTO_MARKET_TYPE="${CRYPTO_MARKET_TYPE:-perp}"
if [[ -z "${CRYPTO_MAX_SYMBOLS+x}" ]]; then
  if [[ "$CRYPTO_MODE" == "core" ]]; then
    export CRYPTO_MAX_SYMBOLS="100"
  else
    export CRYPTO_MAX_SYMBOLS=""
  fi
fi
export CCXT_MAX_WORKERS="${CCXT_MAX_WORKERS:-8}"
export VNSTOCK_REQUEST_TIMEOUT_SECONDS="${VNSTOCK_REQUEST_TIMEOUT_SECONDS:-8}"
if [[ -z "${CRYPTO_EXCHANGES:-}" ]]; then
  if [[ "$CRYPTO_MODE" == "wide" ]]; then
    export CRYPTO_EXCHANGES="binance,bybit,okx,mexc"
  else
    export CRYPTO_EXCHANGES="binance,bybit,okx"
  fi
fi

D1_PERIOD="${D1_PERIOD:-180d}"
H4_PERIOD="${H4_PERIOD:-60d}"

case "$MODE" in
  fast)
    DEFAULT_D1_UNIVERSE="default"
    DEFAULT_H4_UNIVERSE="default"
    ;;
  full)
    DEFAULT_D1_UNIVERSE="broad"
    DEFAULT_H4_UNIVERSE="default"
    ;;
  *)
    echo "Unknown MODE=$MODE. Use MODE=fast or MODE=full." >&2
    exit 2
    ;;
esac

D1_UNIVERSE="${D1_UNIVERSE:-$DEFAULT_D1_UNIVERSE}"
H4_UNIVERSE="${H4_UNIVERSE:-$DEFAULT_H4_UNIVERSE}"
D1_MARKETS="${D1_MARKETS:-all}"

# H4 can include Vietnam stock through VNStock fallback, but it is rate-limited.
H4_MARKETS="${H4_MARKETS:-US stock,Commodity,Forex,Crypto}"

D1_OUT="${D1_OUT:-reports/market-d1}"
H4_OUT="${H4_OUT:-reports/market-h4}"
COMBINED_OUT="${COMBINED_OUT:-reports/market-all/index.html}"

COMBINE_INPUTS=()

if [[ "$RUN_D1" == "1" ]]; then
  echo "Scanning D1: mode=$MODE universe=$D1_UNIVERSE markets=$D1_MARKETS period=$D1_PERIOD provider=$DATA_PROVIDER broker=$BROKER crypto_mode=$CRYPTO_MODE crypto_market_type=$CRYPTO_MARKET_TYPE crypto_max=${CRYPTO_MAX_SYMBOLS:-unlimited} crypto_exchanges=$CRYPTO_EXCHANGES"
  D1_ARGS=(
    --timeframe D1 \
    --out "$D1_OUT" \
    --period "$D1_PERIOD" \
    --universe "$D1_UNIVERSE" \
    --broker "$BROKER" \
    --data-provider "$DATA_PROVIDER" \
    --markets "$D1_MARKETS" \
    --near-match-chart-limit "$NEAR_MATCH_CHART_LIMIT" \
    --previous-results "$D1_OUT/results.json"
  )
  if [[ -n "${D1_LIMIT:-}" ]]; then
    D1_ARGS+=(--limit "$D1_LIMIT")
  fi
  python -m filter_pattern.cli scan-all-market "${D1_ARGS[@]}"
  COMBINE_INPUTS+=("$D1_OUT/results.json")
fi

if [[ "$RUN_H4" == "1" ]]; then
  echo "Scanning H4: mode=$MODE universe=$H4_UNIVERSE markets=$H4_MARKETS period=$H4_PERIOD provider=$DATA_PROVIDER broker=$BROKER crypto_mode=$CRYPTO_MODE crypto_market_type=$CRYPTO_MARKET_TYPE crypto_max=${CRYPTO_MAX_SYMBOLS:-unlimited} crypto_exchanges=$CRYPTO_EXCHANGES"
  H4_ARGS=(
    --timeframe H4 \
    --out "$H4_OUT" \
    --period "$H4_PERIOD" \
    --universe "$H4_UNIVERSE" \
    --broker "$BROKER" \
    --data-provider "$DATA_PROVIDER" \
    --markets "$H4_MARKETS" \
    --near-match-chart-limit "$NEAR_MATCH_CHART_LIMIT" \
    --previous-results "$H4_OUT/results.json"
  )
  if [[ -n "${H4_LIMIT:-}" ]]; then
    H4_ARGS+=(--limit "$H4_LIMIT")
  fi
  python -m filter_pattern.cli scan-all-market "${H4_ARGS[@]}"
  COMBINE_INPUTS+=("$H4_OUT/results.json")
fi

if [[ "${#COMBINE_INPUTS[@]}" -eq 0 ]]; then
  echo "Nothing to scan. Set RUN_D1=1 or RUN_H4=1." >&2
  exit 2
fi

echo "Combining reports"
python -m filter_pattern.cli combine-report \
  --inputs "${COMBINE_INPUTS[@]}" \
  --out "$COMBINED_OUT"

echo "Done: $COMBINED_OUT"
