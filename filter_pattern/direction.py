from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite, tanh
from statistics import mean
from typing import Iterable

from .models import Candle


class DirectionBias(StrEnum):
    LONG_ALLOWED = "LONG ALLOWED"
    SHORT_ALLOWED = "SHORT ALLOWED"
    WATCH_LONG = "WATCH LONG"
    WATCH_SHORT = "WATCH SHORT"
    WATCH_ONLY = "WATCH ONLY"
    NO_TRADE = "NO TRADE"


@dataclass(frozen=True)
class DirectionSnapshot:
    bias: DirectionBias
    phase: str
    trend_score: float
    momentum_score: float
    confidence: float
    allows_long: bool
    allows_short: bool
    trade_filter: str
    reasons: tuple[str, ...]

    def to_json(self) -> dict:
        return {
            "bias": self.bias.value,
            "phase": self.phase,
            "trend_score": round(self.trend_score, 1),
            "momentum_score": round(self.momentum_score, 1),
            "confidence": round(self.confidence, 1),
            "allows_long": self.allows_long,
            "allows_short": self.allows_short,
            "trade_filter": self.trade_filter,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class DirectionMarketContext:
    market: str
    long_allowed: bool
    short_allowed: bool
    label: str
    reasons: tuple[str, ...]

    def to_json(self) -> dict:
        return {
            "market": self.market,
            "long_allowed": self.long_allowed,
            "short_allowed": self.short_allowed,
            "label": self.label,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class DirectionBacktestBucket:
    sample_count: int
    hit_count: int
    hit_rate: float
    average_return_pct: float
    median_return_pct: float
    average_adverse_return_pct: float

    def to_json(self) -> dict:
        return {
            "sample_count": self.sample_count,
            "hit_count": self.hit_count,
            "hit_rate": round(self.hit_rate, 4),
            "average_return_pct": round(self.average_return_pct, 2),
            "median_return_pct": round(self.median_return_pct, 2),
            "average_adverse_return_pct": round(self.average_adverse_return_pct, 2),
        }


@dataclass(frozen=True)
class DirectionBacktestReport:
    sample_count: int
    horizon: int
    step: int
    min_history: int
    long_allowed: DirectionBacktestBucket
    short_allowed: DirectionBacktestBucket
    watch_only: DirectionBacktestBucket

    def to_json(self) -> dict:
        return {
            "sample_count": self.sample_count,
            "horizon": self.horizon,
            "step": self.step,
            "min_history": self.min_history,
            "long_allowed": self.long_allowed.to_json(),
            "short_allowed": self.short_allowed.to_json(),
            "watch_only": self.watch_only.to_json(),
        }


@dataclass(frozen=True)
class DirectionBacktestSample:
    symbol: str
    market: str
    date: str
    bias: DirectionBias
    forward_return_pct: float
    scored_return_pct: float


def calculate_direction(
    candles: list[Candle],
    market: str = "",
    context: DirectionMarketContext | None = None,
) -> DirectionSnapshot:
    closes = [float(candle.close) for candle in candles if candle.close > 0]
    if len(closes) < 120:
        return DirectionSnapshot(
            bias=DirectionBias.NO_TRADE,
            phase="Insufficient Data",
            trend_score=0.0,
            momentum_score=0.0,
            confidence=0.0,
            allows_long=False,
            allows_short=False,
            trade_filter="No trade: need at least 120 candles for direction authority",
            reasons=[f"Usable candles: {len(closes)}"],
        )

    close = closes[-1]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma100 = _sma(closes, 100)
    sma200 = _sma(closes, 200)
    r20 = _return(closes, 20)
    r60 = _return(closes, 60)
    r120 = _return(closes, 120)
    slope50 = _sma_slope(closes, 50, 20)
    adx, plus_di, minus_di = _adx_dmi(candles)
    di_edge = _di_edge(plus_di, minus_di)

    dist50 = _distance(close, sma50)
    dist100 = _distance(close, sma100)
    dist200 = _distance(close, sma200)
    stack50_200 = _distance(sma50, sma200)

    trend = _clamp(
        22 * _squash(dist50, 0.045)
        + 20 * _squash(dist100, 0.07)
        + 22 * _squash(dist200, 0.10)
        + 18 * _squash(stack50_200, 0.07)
        + 12 * _squash(r60, 0.16)
        + 10 * _squash(slope50, 0.045)
        + 12 * di_edge
    )
    acceleration = r20 - (r60 / 3 if _finite(r60) else 0.0)
    momentum = _clamp(
        38 * _squash(r20, 0.075)
        + 30 * _squash(acceleration, 0.06)
        + 16 * _squash(r60, 0.16)
        + 16 * di_edge
    )
    phase, bias, trade_filter = _classify_phase(trend, momentum, dist200, r20, r60, r120)
    conflict = _conflicting_scores(trend, momentum)
    confidence = _confidence(trend, momentum, adx, conflict)
    if confidence < 35 and bias in {DirectionBias.LONG_ALLOWED, DirectionBias.SHORT_ALLOWED}:
        bias = DirectionBias.WATCH_ONLY
        phase = "Chop / No Edge"
        trade_filter = "Low confidence: keep setup visible but do not force direction"
    if bias == DirectionBias.LONG_ALLOWED and confidence < 70:
        bias = DirectionBias.WATCH_LONG
        phase = "Markup / Long Needs Stronger Confirmation"
        trade_filter = "Watch long: trend agrees, but confidence is below real-money authority threshold"
    if bias == DirectionBias.SHORT_ALLOWED:
        bias = DirectionBias.WATCH_SHORT
        phase = "Markdown / Short Needs Confirmation"
        trade_filter = "Block shorts: price-only direction needs extra confirmation before real-money short authority"
    if context is not None and _same_market(market, context.market):
        if bias == DirectionBias.LONG_ALLOWED and not context.long_allowed:
            bias = DirectionBias.WATCH_LONG
            phase = f"{phase} / Market Context Blocked"
            trade_filter = f"Watch long: stock trend agrees, but market context is not aligned ({context.label})"
        if bias == DirectionBias.SHORT_ALLOWED and not context.short_allowed:
            bias = DirectionBias.WATCH_SHORT
            phase = f"{phase} / Market Context Blocked"
            trade_filter = f"Watch short: stock trend agrees, but market context is not aligned ({context.label})"
    bias, phase, trade_filter = _apply_market_authority_gate(str(market), bias, phase, trade_filter)

    allows_long = bias == DirectionBias.LONG_ALLOWED
    allows_short = bias == DirectionBias.SHORT_ALLOWED
    reasons = (
        f"Close vs SMA50: {_fmt_pct(dist50)}",
        f"Close vs SMA200: {_fmt_pct(dist200)}",
        f"20-bar return: {_fmt_pct(r20)}",
        f"60-bar return: {_fmt_pct(r60)}",
        f"120-bar return: {_fmt_pct(r120)}",
        f"ADX: {adx:.1f}, +DI {plus_di:.1f}, -DI {minus_di:.1f}",
    )
    return DirectionSnapshot(
        bias=bias,
        phase=phase,
        trend_score=round(trend, 1),
        momentum_score=round(momentum, 1),
        confidence=round(confidence, 1),
        allows_long=allows_long,
        allows_short=allows_short,
        trade_filter=trade_filter,
        reasons=reasons,
    )


def build_market_context(
    candles_by_symbol: dict[str, list[Candle]],
    markets_by_symbol: dict[str, str],
    market: str,
    end_index: int | None = None,
) -> DirectionMarketContext | None:
    normalized = str(market).strip().lower()
    if normalized != "us stock":
        return None
    rows = []
    for symbol, candles in candles_by_symbol.items():
        if markets_by_symbol.get(symbol, "").strip().lower() != "us stock":
            continue
        active = candles if end_index is None else candles[:end_index]
        closes = [float(candle.close) for candle in active if candle.close > 0]
        if len(closes) < 220:
            continue
        rows.append((symbol, closes, closes[-1] > _sma(closes, 50), closes[-1] > _sma(closes, 200)))
    if not rows:
        return DirectionMarketContext("US stock", False, False, "US equity context unavailable", ("Need at least 220 candles",))

    breadth50 = sum(row[2] for row in rows) / len(rows)
    breadth200 = sum(row[3] for row in rows) / len(rows)
    spy_ok = _benchmark_long_ok(rows, "SPY")
    qqq_ok = _benchmark_long_ok(rows, "QQQ")
    long_allowed = spy_ok and qqq_ok and breadth50 >= 0.55 and breadth200 >= 0.50
    label = "US equity risk-on" if long_allowed else "US equity context not aligned"
    reasons = (
        f"SPY aligned: {spy_ok}",
        f"QQQ aligned: {qqq_ok}",
        f"Breadth above SMA50: {breadth50:.0%}",
        f"Breadth above SMA200: {breadth200:.0%}",
    )
    return DirectionMarketContext(
        market="US stock",
        long_allowed=long_allowed,
        short_allowed=False,
        label=label,
        reasons=reasons,
    )


def setup_direction_from_evidence(evidence: dict, technique: str = "", setup: str = "") -> str:
    for line in [*evidence.get("reasons", []), *evidence.get("failures", [])]:
        text = str(line).strip()
        if not text.lower().startswith("direction:"):
            continue
        direction = text.split(":", 1)[1].strip().lower()
        if direction in {"long", "short"}:
            return direction
    status = str(evidence.get("status", "")).lower()
    if "_long" in status:
        return "long"
    if "_short" in status:
        return "short"
    normalized_technique = str(technique).lower()
    normalized_setup = str(setup).lower()
    if normalized_technique == "minervini-vcp" or normalized_setup == "vcp":
        return "long"
    return ""


def annotate_result_with_direction_authority(
    result: dict,
    candles: list[Candle],
    context: DirectionMarketContext | None = None,
) -> dict:
    annotated = dict(result)
    evidence = dict(annotated.get("evidence", {}))
    setup_direction = setup_direction_from_evidence(evidence, str(annotated.get("technique", "")), str(annotated.get("setup", "")))
    snapshot = calculate_direction(candles, str(annotated.get("market", "")), context)
    authority = snapshot.to_json()
    if context is not None:
        authority["market_context"] = context.to_json()
    authority["setup_direction"] = setup_direction or "unknown"
    authority["decision"] = _direction_decision(snapshot, setup_direction)
    authority["decision_label"] = _direction_decision_label(authority["decision"])
    annotated["direction_authority"] = authority
    return annotated


def backtest_direction(
    candles_by_symbol: dict[str, list[Candle]],
    markets_by_symbol: dict[str, str] | None = None,
    horizon: int = 20,
    step: int = 5,
    min_history: int = 220,
) -> DirectionBacktestReport:
    return direction_report_from_samples(
        collect_direction_backtest_samples(
            candles_by_symbol,
            markets_by_symbol=markets_by_symbol,
            horizon=horizon,
            step=step,
            min_history=min_history,
        ),
        horizon=horizon,
        step=step,
        min_history=min_history,
    )


def collect_direction_backtest_samples(
    candles_by_symbol: dict[str, list[Candle]],
    markets_by_symbol: dict[str, str] | None = None,
    horizon: int = 20,
    step: int = 5,
    min_history: int = 220,
) -> list[DirectionBacktestSample]:
    samples: list[DirectionBacktestSample] = []
    markets = markets_by_symbol or {}
    context_cache: dict[tuple[str, int], DirectionMarketContext | None] = {}
    for symbol, candles in candles_by_symbol.items():
        market = markets.get(symbol, "")
        if len(candles) <= min_history + horizon:
            continue
        for end in range(min_history, len(candles) - horizon, max(1, step)):
            sample = candles[:end]
            entry = candles[end - 1].close
            exit_price = candles[end + horizon - 1].close
            if entry <= 0 or exit_price <= 0:
                continue
            context_key = (market, end)
            if context_key not in context_cache:
                context_cache[context_key] = build_market_context(candles_by_symbol, markets, market, end)
            context = context_cache[context_key]
            snapshot = calculate_direction(sample, market, context)
            raw_return = (exit_price / entry - 1) * 100
            if snapshot.bias == DirectionBias.SHORT_ALLOWED:
                scored_return = -raw_return
            else:
                scored_return = raw_return
            samples.append(
                DirectionBacktestSample(
                    symbol=symbol,
                    market=market,
                    date=candles[end - 1].datetime.date().isoformat(),
                    bias=snapshot.bias,
                    forward_return_pct=raw_return,
                    scored_return_pct=scored_return,
                )
            )
    return samples


def direction_report_from_samples(
    samples: list[DirectionBacktestSample],
    horizon: int = 20,
    step: int = 5,
    min_history: int = 220,
) -> DirectionBacktestReport:
    long_returns: list[float] = []
    short_returns: list[float] = []
    watch_returns: list[float] = []
    for sample in samples:
        if sample.bias == DirectionBias.LONG_ALLOWED:
            long_returns.append(sample.forward_return_pct)
        elif sample.bias == DirectionBias.SHORT_ALLOWED:
            short_returns.append(sample.scored_return_pct)
        elif sample.bias in {DirectionBias.WATCH_LONG, DirectionBias.WATCH_SHORT, DirectionBias.WATCH_ONLY, DirectionBias.NO_TRADE}:
            watch_returns.append(sample.forward_return_pct)
    sample_count = len(long_returns) + len(short_returns) + len(watch_returns)
    return DirectionBacktestReport(
        sample_count=sample_count,
        horizon=horizon,
        step=step,
        min_history=min_history,
        long_allowed=_bucket(long_returns),
        short_allowed=_bucket(short_returns),
        watch_only=_bucket(watch_returns),
    )


def _direction_decision(snapshot: DirectionSnapshot, setup_direction: str) -> str:
    if setup_direction == "long":
        if snapshot.allows_long:
            return "ALLOW_LONG"
        if snapshot.bias == DirectionBias.WATCH_SHORT:
            return "BLOCK_LONG_DISTRIBUTION_RISK"
        if snapshot.bias == DirectionBias.SHORT_ALLOWED:
            return "BLOCK_LONG_MARKDOWN"
        return "WATCH_ONLY"
    if setup_direction == "short":
        if snapshot.allows_short:
            return "ALLOW_SHORT"
        if snapshot.bias == DirectionBias.WATCH_LONG:
            return "BLOCK_SHORT_ACCUMULATION_RISK"
        if snapshot.bias == DirectionBias.LONG_ALLOWED:
            return "BLOCK_SHORT_MARKUP"
        return "WATCH_ONLY"
    return "WATCH_ONLY"


def _direction_decision_label(decision: str) -> str:
    labels = {
        "ALLOW_LONG": "Long allowed",
        "ALLOW_SHORT": "Short allowed",
        "BLOCK_LONG_DISTRIBUTION_RISK": "Block long: distribution/cooling risk",
        "BLOCK_LONG_MARKDOWN": "Block long: markdown regime",
        "BLOCK_SHORT_ACCUMULATION_RISK": "Block short: accumulation/recovery risk",
        "BLOCK_SHORT_MARKUP": "Block short: markup regime",
        "WATCH_ONLY": "Watch only",
    }
    return labels.get(decision, "Watch only")


def _same_market(left: str, right: str) -> bool:
    return str(left).strip().lower() == str(right).strip().lower()


def _benchmark_long_ok(rows: list[tuple[str, list[float], bool, bool]], symbol: str) -> bool:
    for row_symbol, closes, above50, above200 in rows:
        if row_symbol != symbol:
            continue
        return above50 and above200 and _return(closes, 20) >= 0 and _return(closes, 60) >= 0
    return False


def _apply_market_authority_gate(
    market: str,
    bias: DirectionBias,
    phase: str,
    trade_filter: str,
) -> tuple[DirectionBias, str, str]:
    normalized = str(market).strip().lower()
    if normalized in {"crypto", "commodity", "forex"} and bias != DirectionBias.NO_TRADE:
        return (
            DirectionBias.WATCH_ONLY,
            f"{phase} / Context Only",
            f"Context only for {market or 'market'}: price-only direction is not validated enough to block trades",
        )
    if normalized == "us stock" and bias == DirectionBias.WATCH_SHORT:
        return (
            DirectionBias.WATCH_ONLY,
            f"{phase} / Context Only",
            "Context only: equity cooling warnings are not reliable enough to block longs without index/sector breadth",
        )
    return bias, phase, trade_filter


def _classify_phase(
    trend: float,
    momentum: float,
    dist200: float,
    r20: float,
    r60: float,
    r120: float,
) -> tuple[str, DirectionBias, str]:
    if momentum >= 22 and (trend < 65) and (dist200 < 0 or r120 < 0):
        return "Accumulation / Recovery", DirectionBias.WATCH_LONG, "Block shorts: improving from weak state"
    if momentum <= -22 and (trend > -65) and (dist200 > 0 or r120 > 0):
        return "Distribution / Cooling", DirectionBias.WATCH_SHORT, "Block longs: momentum deteriorating"
    if trend >= 55 and momentum >= 35 and dist200 > 0 and r20 >= 0 and r60 >= 0 and r120 >= 0:
        return "Markup", DirectionBias.LONG_ALLOWED, "Long allowed: trend is positive and momentum is not breaking down"
    if trend <= -30 and momentum <= -22 and dist200 <= 0 and r20 <= 0 and r60 <= 0 and r120 <= 0:
        return "Markdown", DirectionBias.SHORT_ALLOWED, "Short allowed: trend is negative and momentum is not recovering"
    if trend < 25 and momentum >= 22:
        return "Accumulation / Recovery", DirectionBias.WATCH_LONG, "Block shorts: improving from weak state"
    if trend > -25 and momentum <= -22:
        return "Distribution / Cooling", DirectionBias.WATCH_SHORT, "Block longs: momentum deteriorating"
    return "Chop / No Edge", DirectionBias.WATCH_ONLY, "Watch only: mixed trend and momentum"


def _confidence(trend: float, momentum: float, adx: float, conflict: bool) -> float:
    score = 0.42 * abs(trend) + 0.34 * abs(momentum) + 0.55 * min(max(adx, 0.0), 40.0)
    if conflict:
        score -= 18.0
    return round(max(5.0, min(100.0, score)), 1)


def _conflicting_scores(trend: float, momentum: float) -> bool:
    strongest = max(abs(trend), abs(momentum))
    if strongest <= 20:
        return True
    return trend * momentum < 0 and min(abs(trend), abs(momentum)) > strongest * 0.35


def _adx_dmi(candles: list[Candle], period: int = 14) -> tuple[float, float, float]:
    if len(candles) < period + 2:
        return 0.0, 0.0, 0.0
    trs: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for previous, current in zip(candles, candles[1:], strict=False):
        up_move = current.high - previous.high
        down_move = previous.low - current.low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        trs.append(max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close)))
    alpha = 2 / (period + 1)
    atr = trs[0]
    plus_smooth = plus_dm[0]
    minus_smooth = minus_dm[0]
    adx = 0.0
    plus_di = 0.0
    minus_di = 0.0
    for tr, plus, minus in zip(trs[1:], plus_dm[1:], minus_dm[1:], strict=True):
        atr = atr + alpha * (tr - atr)
        plus_smooth = plus_smooth + alpha * (plus - plus_smooth)
        minus_smooth = minus_smooth + alpha * (minus - minus_smooth)
        if atr <= 0:
            continue
        plus_di = 100 * plus_smooth / atr
        minus_di = 100 * minus_smooth / atr
        if plus_di + minus_di > 0:
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx if adx == 0.0 else adx + alpha * (dx - adx)
    denominator = plus_di + minus_di
    if denominator <= 0:
        return adx, plus_di, minus_di
    return adx, plus_di, minus_di


def _ema_last(values: list[float], period: int) -> float:
    clean = [float(value) for value in values if _finite(value)]
    if not clean:
        return 0.0
    alpha = 2 / (period + 1)
    value = clean[0]
    for item in clean[1:]:
        value = value + alpha * (item - value)
    return value


def _sma(values: list[float], period: int) -> float:
    clean = [value for value in values if _finite(value)]
    if not clean:
        return 0.0
    window = clean[-min(period, len(clean)) :]
    return mean(window)


def _sma_slope(values: list[float], period: int, lookback: int) -> float:
    if len(values) <= lookback + period:
        return 0.0
    current = _sma(values, period)
    previous = _sma(values[: -lookback], period)
    if previous <= 0:
        return 0.0
    return current / previous - 1


def _return(values: list[float], lookback: int) -> float:
    if len(values) <= lookback:
        return 0.0
    previous = values[-lookback - 1]
    if previous <= 0:
        return 0.0
    return values[-1] / previous - 1


def _distance(value: float, reference: float) -> float:
    if reference <= 0:
        return 0.0
    return value / reference - 1


def _di_edge(plus_di: float, minus_di: float) -> float:
    denominator = plus_di + minus_di
    if denominator <= 0:
        return 0.0
    return (plus_di - minus_di) / denominator


def _squash(value: float, scale: float) -> float:
    if not _finite(value) or scale <= 0:
        return 0.0
    return tanh(value / scale)


def _clamp(value: float, low: float = -100.0, high: float = 100.0) -> float:
    if not _finite(value):
        return 0.0
    return max(low, min(high, value))


def _bucket(returns: list[float]) -> DirectionBacktestBucket:
    if not returns:
        return DirectionBacktestBucket(0, 0, 0.0, 0.0, 0.0, 0.0)
    ordered = sorted(returns)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        median = ordered[middle]
    else:
        median = (ordered[middle - 1] + ordered[middle]) / 2
    adverse = [value for value in returns if value < 0]
    return DirectionBacktestBucket(
        sample_count=len(returns),
        hit_count=sum(1 for value in returns if value > 0),
        hit_rate=sum(1 for value in returns if value > 0) / len(returns),
        average_return_pct=mean(returns),
        median_return_pct=median,
        average_adverse_return_pct=mean(adverse) if adverse else 0.0,
    )


def _fmt_pct(value: float) -> str:
    if not _finite(value):
        return "n/a"
    return f"{value * 100:+.1f}%"


def _finite(value: float) -> bool:
    return isfinite(value)
