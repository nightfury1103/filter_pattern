from __future__ import annotations

import io
import os
import time
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
from math import isnan

from .models import Candle


SUPPORTED_TIMEFRAMES = {"D1", "H4"}


def load_yahoo_ohlcv(symbol: str, period: str = "2y", timeframe: str = "D1") -> list[Candle]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is required for market scans. Run: python -m pip install -e '.[dev]'") from exc

    active_timeframe = _normalize_timeframe(timeframe)
    frame = yf.download(
        symbol,
        period=period,
        interval=_yahoo_interval(active_timeframe),
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    candles = _candles_from_frame(frame, symbol, active_timeframe)
    if active_timeframe == "H4":
        return _resample_to_h4(candles)
    return candles


def load_yahoo_ohlcv_many(
    symbols: list[str],
    period: str = "2y",
    timeframe: str = "D1",
) -> dict[str, list[Candle] | Exception]:
    active_timeframe = _normalize_timeframe(timeframe)
    unique_symbols = list(dict.fromkeys(symbols))
    if not unique_symbols:
        return {}
    if len(unique_symbols) == 1:
        symbol = unique_symbols[0]
        try:
            return {symbol: load_yahoo_ohlcv(symbol, period, active_timeframe)}
        except Exception as exc:  # noqa: BLE001 - returned per symbol for scanner reporting.
            return {symbol: exc}

    try:
        import yfinance as yf
    except ImportError as exc:
        return {symbol: RuntimeError("yfinance is required for market scans. Run: python -m pip install -e '.[dev]'") for symbol in unique_symbols}

    frame = yf.download(
        unique_symbols,
        period=period,
        interval=_yahoo_interval(active_timeframe),
        auto_adjust=False,
        group_by="ticker",
        progress=False,
        threads=True,
    )
    results: dict[str, list[Candle] | Exception] = {}
    for symbol in unique_symbols:
        try:
            if frame.empty:
                raise ValueError(f"No Yahoo Finance {active_timeframe} data returned for {symbol}")
            if not (hasattr(frame.columns, "nlevels") and frame.columns.nlevels > 1):
                raise ValueError(f"Yahoo Finance batch data missing ticker level for {symbol}")
            available = set(frame.columns.get_level_values(0))
            if symbol not in available:
                raise ValueError(f"No Yahoo Finance {active_timeframe} data returned for {symbol}")
            candles = _candles_from_frame(frame[symbol], symbol, active_timeframe)
            results[symbol] = _resample_to_h4(candles) if active_timeframe == "H4" else candles
        except Exception as exc:  # noqa: BLE001 - returned per symbol for scanner reporting.
            results[symbol] = exc
    return results


def load_ccxt_ohlcv_many(
    symbols: list[str],
    period: str = "2y",
    timeframe: str = "D1",
    exchange_id: str = "binance,bybit,okx",
) -> dict[str, list[Candle] | Exception]:
    active_timeframe = _normalize_timeframe(timeframe)
    unique_symbols = list(dict.fromkeys(symbols))
    if not unique_symbols:
        return {}

    try:
        import ccxt
    except ImportError as exc:
        return {
            symbol: RuntimeError("ccxt is required for crypto market scans. Run: python -m pip install -e '.[dev]'")
            for symbol in unique_symbols
        }

    results: dict[str, list[Candle] | Exception] = {}
    unresolved = set(unique_symbols)
    exchange_errors: list[str] = []
    ccxt_timeframe = _ccxt_timeframe(active_timeframe)
    limit = _ccxt_limit(period, active_timeframe)

    for active_exchange_id in _exchange_ids(exchange_id):
        if not unresolved:
            break
        exchange_class = getattr(ccxt, active_exchange_id, None)
        if exchange_class is None:
            exchange_errors.append(f"Unknown CCXT exchange: {active_exchange_id}")
            continue

        exchange = exchange_class({"enableRateLimit": True})
        try:
            exchange.load_markets()
        except Exception as exc:  # noqa: BLE001 - keep fallback exchanges available.
            exchange_errors.append(f"{active_exchange_id}: {exc}")
            close = getattr(exchange, "close", None)
            if callable(close):
                close()
            continue

        for raw_symbol in list(unresolved):
            try:
                ccxt_symbol = _ccxt_symbol(raw_symbol)
                if ccxt_symbol not in exchange.markets:
                    raise ValueError(f"{ccxt_symbol} is not available on CCXT exchange {active_exchange_id}")
                rows = exchange.fetch_ohlcv(ccxt_symbol, timeframe=ccxt_timeframe, limit=limit)
                if not rows:
                    raise ValueError(f"No CCXT {active_timeframe} data returned for {raw_symbol} on {active_exchange_id}")
                results[raw_symbol] = [_ccxt_candle(row) for row in rows]
                unresolved.remove(raw_symbol)
            except Exception as exc:  # noqa: BLE001 - returned per symbol for scanner reporting.
                results[raw_symbol] = exc
        close = getattr(exchange, "close", None)
        if callable(close):
            close()

    for raw_symbol in unresolved:
        last_error = results.get(raw_symbol)
        detail = str(last_error) if isinstance(last_error, Exception) else "; ".join(exchange_errors)
        results[raw_symbol] = ValueError(f"No CCXT {active_timeframe} data returned for {raw_symbol}. {detail}")
    return results


def load_vnstock_ohlcv_many(
    symbols: list[str],
    period: str = "2y",
    timeframe: str = "D1",
    source: str | None = None,
    requests_per_minute: int | None = None,
) -> dict[str, list[Candle] | Exception]:
    active_timeframe = _normalize_timeframe(timeframe)
    unique_symbols = list(dict.fromkeys(symbols))
    if not unique_symbols:
        return {}

    try:
        from vnstock import Quote
    except ImportError:
        return {
            symbol: RuntimeError("vnstock is required for Vietnam market scans. Run: python -m pip install -e .")
            for symbol in unique_symbols
        }

    active_source = (source or os.environ.get("VNSTOCK_SOURCE") or "VCI").upper()
    rpm = _vnstock_requests_per_minute(requests_per_minute)
    delay_seconds = 60.0 / rpm if rpm > 0 else 0.0
    results: dict[str, list[Candle] | Exception] = {}
    last_request_at: float | None = None

    for symbol in unique_symbols:
        if last_request_at is not None and delay_seconds > 0:
            elapsed = time.monotonic() - last_request_at
            if elapsed < delay_seconds:
                time.sleep(delay_seconds - elapsed)
        last_request_at = time.monotonic()
        try:
            results[symbol] = _load_vnstock_ohlcv(symbol, period, active_timeframe, active_source, Quote)
        except KeyboardInterrupt:
            raise
        except BaseException as exc:  # noqa: BLE001 - vnstock may raise SystemExit on rate-limit errors.
            results[symbol] = RuntimeError(f"VNStock {active_source} {active_timeframe} data failed for {symbol}: {exc}")
    return results


def _load_vnstock_ohlcv(symbol: str, period: str, timeframe: str, source: str, quote_class) -> list[Candle]:
    start, end = _period_date_range(period)
    interval = "1H" if timeframe == "H4" else "1D"
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        frame = quote_class(symbol=symbol, source=source).history(start=start, end=end, interval=interval)
    candles = _candles_from_vnstock_frame(frame, symbol, timeframe)
    if timeframe == "H4":
        candles = _resample_to_h4(candles)
    if not candles:
        raise ValueError(f"No usable VNStock {timeframe} candles for {symbol}")
    return candles


def _candles_from_frame(frame, symbol: str, timeframe: str) -> list[Candle]:
    if frame.empty:
        raise ValueError(f"No Yahoo Finance {timeframe} data returned for {symbol}")

    if hasattr(frame.columns, "nlevels") and frame.columns.nlevels > 1:
        frame.columns = frame.columns.get_level_values(0)

    candles: list[Candle] = []
    for timestamp, row in frame.iterrows():
        open_value = _row_value(row, "Open")
        high = _row_value(row, "High")
        low = _row_value(row, "Low")
        close = _row_value(row, "Close")
        volume = _row_value(row, "Volume", default=0.0)
        if any(_is_nan(value) for value in (open_value, high, low, close)):
            continue
        dt = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else datetime.fromisoformat(str(timestamp))
        candles.append(
            Candle(
                datetime=dt.replace(tzinfo=None),
                open=float(open_value),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=0.0 if _is_nan(volume) else float(volume),
            )
        )

    if not candles:
        raise ValueError(f"No usable Yahoo Finance {timeframe} candles for {symbol}")
    return candles


def _candles_from_vnstock_frame(frame, symbol: str, timeframe: str) -> list[Candle]:
    if frame is None or frame.empty:
        raise ValueError(f"No VNStock {timeframe} data returned for {symbol}")

    frame = frame.copy()
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    required = {"time", "open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"VNStock data missing columns for {symbol}: {', '.join(sorted(missing))}")

    frame = frame.sort_values("time").drop_duplicates(subset=["time"], keep="last")
    candles: list[Candle] = []
    for _, row in frame.iterrows():
        open_value = _row_value(row, "open")
        high = _row_value(row, "high")
        low = _row_value(row, "low")
        close = _row_value(row, "close")
        volume = _row_value(row, "volume", default=0.0)
        if any(_is_nan(value) for value in (open_value, high, low, close)):
            continue
        timestamp = row["time"]
        dt = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else datetime.fromisoformat(str(timestamp))
        candles.append(
            Candle(
                datetime=dt.replace(tzinfo=None),
                open=float(open_value),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=0.0 if _is_nan(volume) else float(volume),
            )
        )

    if not candles:
        raise ValueError(f"No usable VNStock {timeframe} candles for {symbol}")
    return candles


def _normalize_timeframe(timeframe: str) -> str:
    normalized = timeframe.upper()
    if normalized not in SUPPORTED_TIMEFRAMES:
        raise ValueError("supported timeframes are D1 and H4")
    return normalized


def _yahoo_interval(timeframe: str) -> str:
    if timeframe == "H4":
        return "1h"
    return "1d"


def _resample_to_h4(candles: list[Candle]) -> list[Candle]:
    grouped: dict[datetime, list[Candle]] = {}
    for candle in candles:
        bucket_hour = (candle.datetime.hour // 4) * 4
        bucket = candle.datetime.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)
        grouped.setdefault(bucket, []).append(candle)

    h4_candles: list[Candle] = []
    for bucket in sorted(grouped):
        items = sorted(grouped[bucket], key=lambda item: item.datetime)
        h4_candles.append(
            Candle(
                datetime=bucket,
                open=items[0].open,
                high=max(item.high for item in items),
                low=min(item.low for item in items),
                close=items[-1].close,
                volume=sum(item.volume for item in items),
            )
        )
    return h4_candles


def _ccxt_timeframe(timeframe: str) -> str:
    if timeframe == "H4":
        return "4h"
    return "1d"


def _ccxt_limit(period: str, timeframe: str) -> int:
    days = _period_to_days(period)
    if timeframe == "H4":
        return max(120, min(1000, days * 6))
    return max(120, min(1000, days))


def _period_to_days(period: str) -> int:
    cleaned = period.strip().lower()
    if not cleaned:
        return 730
    if cleaned.endswith("mo"):
        try:
            return int(cleaned[:-2]) * 30
        except ValueError:
            return 730
    try:
        value = int(cleaned[:-1])
    except ValueError:
        return 730
    unit = cleaned[-1]
    if unit == "d":
        return value
    if unit == "y":
        return value * 365
    return 730


def _period_date_range(period: str) -> tuple[str, str]:
    days = _period_to_days(period)
    end = date.today()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def _vnstock_requests_per_minute(requests_per_minute: int | None = None) -> int:
    if requests_per_minute is not None:
        return max(1, requests_per_minute)
    raw = os.environ.get("VNSTOCK_REQUESTS_PER_MINUTE", "18")
    try:
        return max(1, int(raw))
    except ValueError:
        return 18


def _ccxt_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "").replace("/", "")
    if normalized.endswith("USDT"):
        return f"{normalized[:-4]}/USDT"
    if normalized.endswith("USD"):
        return f"{normalized[:-3]}/USDT"
    return symbol


def _exchange_ids(exchange_id: str) -> list[str]:
    ids = [item.strip() for item in exchange_id.split(",") if item.strip()]
    return ids or ["binance"]


def _ccxt_candle(row: list[float]) -> Candle:
    timestamp_ms, open_value, high, low, close, volume = row[:6]
    return Candle(
        datetime=datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).replace(tzinfo=None),
        open=float(open_value),
        high=float(high),
        low=float(low),
        close=float(close),
        volume=float(volume),
    )


def _row_value(row, name: str, default: float | None = None) -> float:
    if name not in row:
        if default is None:
            raise ValueError(f"Yahoo Finance data missing {name}")
        return default
    value = row[name]
    return float(value)


def _is_nan(value: float) -> bool:
    try:
        return isnan(value)
    except TypeError:
        return False
