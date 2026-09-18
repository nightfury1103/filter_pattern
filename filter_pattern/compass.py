"""Causal, symmetric D1 direction candidates; independent of scanner/RRG gates."""
from __future__ import annotations

from math import isfinite, log, sqrt, ulp
from statistics import fmean, stdev

from .models import Candle

MODELS = ("ema", "ema_atr", "multi_horizon")
PRIMARY_MODEL = "multi_horizon"
WARMUP = 200
HORIZONS = (5, 10, 20)
PRIMARY_HORIZON = 10


def validate_candles(candles: list[Candle]) -> None:
    previous = None
    for candle in candles:
        day = candle.datetime.date()
        if previous is not None and day <= previous:
            raise ValueError("D1 candles must have unique dates in ascending order")
        prices = (candle.open, candle.high, candle.low, candle.close)
        if not all(isfinite(p) and p > 0 for p in prices):
            raise ValueError(f"Invalid positive finite OHLC at {day}")
        # Adjusted OHLC multiplication can differ by one floating-point ULP at
        # equal boundaries. Tolerate representation error, never change prices.
        tolerance = 8 * ulp(max(prices))
        if candle.low > min(candle.open, candle.close) + tolerance or candle.high < max(candle.open, candle.close) - tolerance or candle.low > candle.high + tolerance:
            raise ValueError(f"Inconsistent OHLC at {day}")
        previous = day


def _ema(values: list[float], period: int) -> list[float]:
    result = []
    for value in values:
        result.append(value if not result else result[-1] + 2 / (period + 1) * (value - result[-1]))
    return result


def _atr(candles: list[Candle], period: int = 14) -> list[float | None]:
    ranges = []
    result: list[float | None] = []
    for index, candle in enumerate(candles):
        previous = candles[index - 1].close if index else candle.close
        ranges.append(max(candle.high - candle.low, abs(candle.high - previous), abs(candle.low - previous)))
        if index < period - 1:
            result.append(None)
        elif index == period - 1:
            result.append(fmean(ranges))
        else:
            result.append((float(result[-1]) * (period - 1) + ranges[-1]) / period)
    return result


def efficiency_ratio(values: list[float]) -> float:
    travel = sum(abs(b - a) for a, b in zip(values, values[1:]))
    return abs(values[-1] - values[0]) / travel if travel else 0.0


def calculate_compass_series(candles: list[Candle]) -> dict[str, list[dict]]:
    """Each row uses only its prefix. No full-sample normalization or fitting."""
    validate_candles(candles)
    prices = [c.close for c in candles]
    ema20, ema50, atr14 = _ema(prices, 20), _ema(prices, 50), _atr(candles)
    returns = [0.0] + [log(b / a) for a, b in zip(prices, prices[1:])] if prices else []
    results: dict[str, list[dict]] = {model: [] for model in MODELS}
    for index, candle in enumerate(candles):
        available = index >= WARMUP
        atr = atr14[index]
        ema_score = (ema20[index] - ema50[index]) / atr if atr else 0.0
        er = efficiency_ratio(prices[max(0, index - 20): index + 1])
        components = []
        if index >= 120:
            volatility = max(stdev(returns[index - 59:index + 1]), 1e-8)
            components = [log(prices[index] / prices[index - h]) / (volatility * sqrt(h)) for h in (20, 60, 120)]
        multi_score = fmean(components) if components else 0.0
        for model in MODELS:
            score = multi_score if model == "multi_horizon" else ema_score
            past = results[model][index - 5]["score"] if index >= 5 else score
            momentum = score - past
            bias = "WAIT"
            if available:
                if model == "ema":
                    bias = "LONG" if ema_score > 0 else "SHORT" if ema_score < 0 else "WAIT"
                elif model == "ema_atr":
                    if ema_score > 0.5 and momentum > 0:
                        bias = "LONG"
                    elif ema_score < -0.5 and momentum < 0:
                        bias = "SHORT"
                elif components and er >= 0.20:
                    if min(components) > 0 and multi_score > 0.5:
                        bias = "LONG"
                    elif max(components) < 0 and multi_score < -0.5:
                        bias = "SHORT"
            reason = "Chưa đủ 201 nến D1" if not available else "Xu hướng chưa đồng thuận hoặc còn nhiễu"
            if available and bias != "WAIT":
                reason = "Ưu tiên nghiên cứu setup Long" if bias == "LONG" else "Ưu tiên nghiên cứu setup Short"
            results[model].append({
                "date": candle.datetime.date().isoformat(), "available": available,
                "bias": bias, "score": score, "momentum": momentum,
                "efficiency": er, "components": components if model == "multi_horizon" else [],
                "reason": reason,
            })
    return results


def setup_alignment(bias: str, setup_direction: str) -> str:
    """Research annotation only. Never changes detector qualification."""
    if bias not in {"LONG", "SHORT"} or setup_direction.lower() not in {"long", "short"}:
        return "WAIT"
    return "ALIGNED" if bias.lower() == setup_direction.lower() else "AGAINST"
