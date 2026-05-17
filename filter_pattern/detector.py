from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import mean

from .models import Candle, Contraction, VCPConfig, VCPEvidence
from .techniques import MINERVINI_VCP_SCAN_SETUPS, normalize_setup, normalize_technique


def detect_pattern(
    candles: list[Candle],
    technique: str = "vcp",
    config: VCPConfig | None = None,
    setup: str = "all",
) -> VCPEvidence:
    normalized = normalize_technique(technique)
    normalized_setup = normalize_setup(setup)
    if normalized == "minervini-vcp":
        return detect_minervini_vcp_setup(candles, normalized_setup, config)
    if normalized == "experimental-ema21-compression":
        return detect_ema21_compression(candles, config)
    if normalized == "nhathoai":
        return detect_nhathoai_setup(candles, normalized_setup, config)
    raise ValueError("unknown technique. Choose one of: minervini-vcp, nhathoai, experimental-ema21-compression")


def detect_minervini_vcp_setup(
    candles: list[Candle],
    setup: str = "all",
    config: VCPConfig | None = None,
) -> VCPEvidence:
    cfg = config or VCPConfig()
    if setup in {"all", "original-vcp"}:
        return detect_vcp(candles, cfg)
    contraction_targets = {
        "vcp-1c": 1,
        "vcp-2c": 2,
        "vcp-3c": 3,
    }
    if setup not in contraction_targets:
        return _not_qualified(
            "Choose one original VCP setup: " + ", ".join(("original-vcp", *MINERVINI_VCP_SCAN_SETUPS[1:]))
        )
    target = contraction_targets[setup]
    variant_cfg = replace(cfg, min_contractions=target, max_contractions=target)
    evidence = detect_vcp(candles, variant_cfg)
    label = f"Original VCP {target}C"
    if evidence.qualified:
        return replace(
            evidence,
            status=f"ready_vcp_{target}c",
            reasons=[f"Pattern: {label}", *evidence.reasons],
        )
    return replace(
        evidence,
        failures=[f"Pattern: {label}", *evidence.failures],
    )


def detect_vcp(candles: list[Candle], config: VCPConfig | None = None) -> VCPEvidence:
    cfg = config or VCPConfig()
    failures: list[str] = []
    reasons: list[str] = []

    if len(candles) < cfg.min_history_days:
        return _not_qualified(f"Need at least {cfg.min_history_days} candles, got {len(candles)}")

    avg_recent_volume = mean(c.volume for c in candles[-50:])
    if avg_recent_volume < cfg.min_avg_volume:
        failures.append(
            f"Average recent volume {avg_recent_volume:,.0f} is below minimum {cfg.min_avg_volume:,.0f}"
        )

    base_end = len(candles) - 1
    base_start = max(0, len(candles) - cfg.max_base_days)
    pre_start = max(0, base_start - cfg.pre_base_days)
    base = candles[base_start:]
    pre_base = candles[pre_start:base_start]

    prior_uptrend_pct = _prior_uptrend_pct(pre_base, base)
    if prior_uptrend_pct is None or prior_uptrend_pct < cfg.min_prior_uptrend_pct:
        failures.append(
            f"Prior uptrend is {prior_uptrend_pct or 0:.1f}%, below {cfg.min_prior_uptrend_pct:.1f}%"
        )
    else:
        reasons.append(f"Prior uptrend confirmed: {prior_uptrend_pct:.1f}% before the base")

    contractions = _detect_contractions(candles, base_start, replace(cfg, min_contractions=1, max_contractions=8))
    pivot_contractions = _vcp_pivot_contractions(contractions, cfg)
    pivot = max((item.high for item in pivot_contractions), default=max(c.high for c in base[:-1] or base))
    current_close = candles[-1].close
    distance_to_pivot_pct = ((pivot - current_close) / pivot) * 100

    if current_close >= pivot:
        failures.append("Current close is already at or above pivot, so this is not a near-pivot watch setup")
    elif distance_to_pivot_pct > cfg.near_pivot_pct:
        failures.append(
            f"Current close is {distance_to_pivot_pct:.2f}% below pivot, above near-pivot limit {cfg.near_pivot_pct:.2f}%"
        )
    else:
        reasons.append(f"Current close is {distance_to_pivot_pct:.2f}% below pivot, inside entry watch zone")

    if len(contractions) < cfg.min_contractions:
        failures.append(f"Found {len(contractions)} valid contractions, need at least {cfg.min_contractions}")
    elif len(contractions) > cfg.max_contractions:
        contractions = contractions[-cfg.max_contractions :]

    if len(contractions) >= cfg.min_contractions:
        if _is_tightening(contractions, cfg.depth_tolerance_pct):
            reasons.append(
                "Contractions tighten progressively: "
                + " -> ".join(f"{item.depth_pct:.1f}%" for item in contractions)
            )
        else:
            failures.append(
                "Contractions are not tightening: "
                + " -> ".join(f"{item.depth_pct:.1f}%" for item in contractions)
            )

        if _has_rising_lows(contractions, cfg.low_tolerance_pct):
            reasons.append("Contraction lows hold higher or near-flat support")
        else:
            failures.append(
                "Contraction lows are not rising: "
                + " -> ".join(f"{item.low:.2f}" for item in contractions)
            )

        pivot_spread_pct = _pivot_spread_pct(pivot_contractions)
        if pivot_spread_pct <= cfg.max_pivot_spread_pct:
            reasons.append(f"Right-side pivot area is compact: contraction highs span {pivot_spread_pct:.1f}%")
        else:
            failures.append(
                f"Right-side pivot area is too wide: contraction highs span {pivot_spread_pct:.1f}%, "
                f"above {cfg.max_pivot_spread_pct:.1f}%"
            )

        final_depth = contractions[-1].depth_pct
        if final_depth <= cfg.max_final_contraction_depth_pct:
            reasons.append(f"Final contraction is tight at {final_depth:.1f}%")
        else:
            failures.append(
                f"Final contraction is {final_depth:.1f}%, above tightness limit "
                f"{cfg.max_final_contraction_depth_pct:.1f}%"
            )

    base_depth_pct = _base_depth_pct(base)
    if base_depth_pct > cfg.max_base_depth_pct:
        failures.append(f"Base depth is {base_depth_pct:.1f}%, above {cfg.max_base_depth_pct:.1f}%")
    else:
        reasons.append(f"Base depth is controlled at {base_depth_pct:.1f}%")

    volume_ratio = _volume_dry_up_ratio(candles, base_start, contractions)
    if volume_ratio is None:
        failures.append("Volume dry-up cannot be confirmed")
    elif volume_ratio > cfg.volume_dry_up_ratio + 0.05:
        failures.append(
            f"Late contraction volume ratio {volume_ratio:.2f} is above dry-up limit {cfg.volume_dry_up_ratio:.2f}"
        )
    elif volume_ratio > cfg.volume_dry_up_ratio:
        reasons.append(
            f"Volume dry-up is acceptable: late/base volume ratio {volume_ratio:.2f} is near limit {cfg.volume_dry_up_ratio:.2f}"
        )
    else:
        reasons.append(f"Volume dry-up confirmed: late/base volume ratio {volume_ratio:.2f}")

    qualified = not failures
    score = _score(qualified, contractions, distance_to_pivot_pct, volume_ratio, prior_uptrend_pct, cfg)
    status = "ready_near_pivot" if qualified else "rejected"

    return VCPEvidence(
        qualified=qualified,
        status=status,
        score=score,
        pivot=pivot,
        current_close=current_close,
        distance_to_pivot_pct=distance_to_pivot_pct,
        contractions=contractions,
        reasons=reasons,
        failures=failures,
        base_start_index=base_start,
        base_end_index=base_end,
        volume_dry_up_ratio=volume_ratio,
        prior_uptrend_pct=prior_uptrend_pct,
    )


def detect_nhathoai_setup(candles: list[Candle], setup: str = "all", config: VCPConfig | None = None) -> VCPEvidence:
    normalized = normalize_setup(setup)
    if normalized == "all":
        return _not_qualified("Choose one Nhật Hoài setup: DD, FB, SB, BB, RB, IRB, ARB, VCP, or Compression")
    if normalized == "compression":
        return detect_ema21_compression(candles, config)
    if normalized == "vcp":
        return _detect_nhathoai_vcp_setup(candles, config)
    if normalized == "arb":
        return _detect_arb_setup(candles, config)
    if normalized == "dd":
        return _detect_dd_setup(candles, config)
    if normalized == "fb":
        return _detect_fb_setup(candles, config)
    if normalized == "sb":
        return _detect_sb_setup(candles, config)
    if normalized == "bb":
        return _detect_bb_setup(candles, config)
    if normalized == "rb":
        return _detect_rb_setup(candles, config)
    if normalized == "irb":
        return _detect_irb_setup(candles, config)
    return _detect_nhathoai_price_action(candles, normalized, config)


def detect_ema21_compression(candles: list[Candle], config: VCPConfig | None = None) -> VCPEvidence:
    cfg = config or VCPConfig()
    min_needed = max(cfg.min_history_days, cfg.ema_period + cfg.setup_lookback + cfg.ema_slope_lookback)
    if len(candles) < min_needed:
        return _not_qualified(f"Need at least {min_needed} candles, got {len(candles)}")

    closes = [c.close for c in candles]
    ema_values = _ema(closes, cfg.ema_period)
    setup_start = max(0, len(candles) - cfg.setup_lookback)
    candidates = [
        _score_pivot_ema21_compression(candles, cfg, ema_values, "long", "Horizontal", setup_start),
        _score_pivot_ema21_compression(candles, cfg, ema_values, "short", "Horizontal", setup_start),
        _score_pivot_ema21_compression(candles, cfg, ema_values, "long", "Diagonal", setup_start),
        _score_pivot_ema21_compression(candles, cfg, ema_values, "short", "Diagonal", setup_start),
    ]
    result = max(candidates, key=lambda item: (_compression_status_rank(item.status), item.score))
    qualified = result.score >= 80 and result.status in {"WAITING", "TRIGGERED"} and not result.failures

    return VCPEvidence(
        qualified=qualified,
        status=result.status if qualified else "rejected",
        score=result.score,
        pivot=result.trigger,
        current_close=candles[-1].close,
        distance_to_pivot_pct=result.distance_to_trigger_pct,
        contractions=[],
        reasons=_compression_output_lines(result, candles) if qualified else [],
        failures=[] if qualified else _compression_reject_lines(result),
        base_start_index=result.compression_start_index,
        base_end_index=len(candles) - 1,
        volume_dry_up_ratio=result.volume_ratio,
        prior_uptrend_pct=None,
    )


@dataclass(frozen=True)
class _CompressionSetup:
    direction: str
    pivot_type: str
    status: str
    score: float
    pivot_start_index: int | None
    pivot_end_index: int | None
    pivot_start_value: float | None
    pivot_end_value: float | None
    compression_start_index: int | None
    compression_end_index: int | None
    zone_low: float | None
    zone_high: float | None
    trigger: float | None
    stop: float | None
    distance_to_trigger_pct: float | None
    latest_gap_atr: float | None
    volume_ratio: float | None
    reasons: list[str]
    failures: list[str]


def _score_pivot_ema21_compression(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
    pivot_type: str,
    setup_start: int,
) -> _CompressionSetup:
    pivot = _compression_pivot(candles, cfg, direction, pivot_type, setup_start)
    if pivot is None:
        return _empty_compression(
            direction,
            pivot_type,
            [f"Reject reason: no clear {pivot_type.lower()} pivot line with at least two reactions"],
        )

    pivot_start, pivot_end, pivot_start_value, pivot_end_value = pivot
    n = len(candles)
    latest = n - 1
    compression_len = min(max(6, cfg.compression_lookback), latest - setup_start)
    compression_start = max(setup_start, n - compression_len - 1)
    compression_end = latest - 1
    compression = candles[compression_start : compression_end + 1]
    if len(compression) < 5:
        return _empty_compression(direction, pivot_type, ["Reject reason: not enough recent candles for compression"])

    latest_pivot = _compression_line_value(pivot_start, pivot_start_value, pivot_end, pivot_end_value, latest)
    prior_pivot = _compression_line_value(
        pivot_start,
        pivot_start_value,
        pivot_end,
        pivot_end_value,
        compression_start,
    )
    atr = _atr(candles, 14)
    atr = atr if atr and atr > 0 else max(candles[-1].close * 0.02, 0.0001)
    latest_gap = abs(latest_pivot - ema_values[-1])
    early_gap = abs(prior_pivot - ema_values[compression_start])
    latest_gap_atr = latest_gap / atr
    volume_ratio = _window_volume_ratio(candles, compression_start)
    current = candles[-1]

    if direction == "long":
        trigger = latest_pivot
        stop = min(min(c.low for c in compression), min(ema_values[compression_start:latest]))
        distance_to_trigger_pct = ((trigger - current.close) / trigger) * 100 if trigger else None
        status = _compression_long_status(current, trigger, stop, cfg)
    else:
        trigger = latest_pivot
        stop = max(max(c.high for c in compression), max(ema_values[compression_start:latest]))
        distance_to_trigger_pct = ((current.close - trigger) / trigger) * 100 if trigger else None
        status = _compression_short_status(current, trigger, stop, cfg)

    pivot_points, pivot_reason, pivot_failure = _score_compression_pivot(
        candles,
        cfg,
        direction,
        pivot_type,
        pivot_start,
        pivot_end,
        pivot_start_value,
        pivot_end_value,
        setup_start,
    )
    ema_points, ema_reason, ema_failure = _score_compression_ema(
        candles,
        cfg,
        ema_values,
        direction,
        compression_start,
        compression_end,
    )
    inside_points, inside_reason, inside_failure = _score_compression_inside_zone(
        candles,
        ema_values,
        direction,
        pivot_start,
        pivot_start_value,
        pivot_end,
        pivot_end_value,
        compression_start,
        compression_end,
    )
    gap_points, gap_reason, gap_failure = _score_compression_gap(latest_gap_atr, early_gap, latest_gap, cfg)
    tight_points, tight_reason, tight_failure = _score_compression_candles(candles, compression_start, compression_end, atr)
    trigger_points, trigger_reason, trigger_failure = _score_compression_trigger(status, distance_to_trigger_pct, cfg)
    stop_points, stop_reason, stop_failure = _score_compression_stop(current.close, stop, atr, direction)

    score = (
        pivot_points
        + ema_points
        + inside_points
        + gap_points
        + tight_points
        + trigger_points
        + stop_points
    )
    reasons = [
        item
        for item in [
            pivot_reason,
            ema_reason,
            inside_reason,
            gap_reason,
            tight_reason,
            trigger_reason,
            stop_reason,
            _compression_volume_reason(volume_ratio),
        ]
        if item
    ]
    failures = [
        item
        for item in [
            pivot_failure,
            ema_failure,
            inside_failure,
            gap_failure,
            tight_failure,
            trigger_failure,
            stop_failure,
        ]
        if item
    ]

    if status not in {"WAITING", "TRIGGERED"}:
        failures.append(f"Status is {status}, not an active pivot-EMA21 compression entry candidate")
    if score < 80:
        failures.append(f"Score {score:.0f} is below required compression threshold 80")

    return _CompressionSetup(
        direction=direction,
        pivot_type=pivot_type,
        status=status,
        score=min(100.0, score),
        pivot_start_index=pivot_start,
        pivot_end_index=pivot_end,
        pivot_start_value=pivot_start_value,
        pivot_end_value=pivot_end_value,
        compression_start_index=compression_start,
        compression_end_index=latest,
        zone_low=min(c.low for c in candles[compression_start:latest + 1]),
        zone_high=max(c.high for c in candles[compression_start:latest + 1]),
        trigger=trigger,
        stop=stop,
        distance_to_trigger_pct=distance_to_trigger_pct,
        latest_gap_atr=latest_gap_atr,
        volume_ratio=volume_ratio,
        reasons=reasons,
        failures=failures,
    )


def _compression_pivot(
    candles: list[Candle],
    cfg: VCPConfig,
    direction: str,
    pivot_type: str,
    setup_start: int,
) -> tuple[int, int, float, float] | None:
    latest = len(candles) - 1
    setup = candles[setup_start:latest]
    if len(setup) < 10:
        return None
    if pivot_type == "Horizontal":
        if direction == "long":
            pivot = max(c.high for c in setup)
            touches = _boundary_touches(setup, pivot, cfg.boundary_touch_tolerance_pct)
            if touches < cfg.min_boundary_touches:
                return None
        else:
            pivot = min(c.low for c in setup)
            touches = _support_touches(setup, pivot, cfg.boundary_touch_tolerance_pct)
            if touches < cfg.min_boundary_touches:
                return None
        return setup_start, latest, pivot, pivot

    swings = _swing_points(candles, setup_start, latest - 1, cfg.swing_window)
    swing_type = "high" if direction == "long" else "low"
    relevant = [(index, price) for index, kind, price in swings if kind == swing_type]
    best: tuple[int, int, float, float] | None = None
    best_score = -1.0
    for first_pos, (first_index, first_price) in enumerate(relevant):
        for second_index, second_price in relevant[first_pos + 1 :]:
            if second_index - first_index < 4:
                continue
            if direction == "long" and second_price >= first_price * (1 - 0.002):
                continue
            if direction == "short" and second_price <= first_price * (1 + 0.002):
                continue
            line_latest = _compression_line_value(first_index, first_price, second_index, second_price, latest)
            current = candles[-1].close
            if direction == "long":
                if line_latest <= 0 or current > line_latest * (1 + cfg.max_boundary_distance_pct / 100):
                    continue
                distance = abs(line_latest - current) / line_latest
            else:
                if line_latest <= 0 or current < line_latest * (1 - cfg.max_boundary_distance_pct / 100):
                    continue
                distance = abs(current - line_latest) / line_latest
            recency = second_index / latest
            score = recency - distance
            if score > best_score:
                best_score = score
                best = (first_index, second_index, first_price, second_price)
    return best


def _compression_line_value(
    start_index: int,
    start_value: float,
    end_index: int,
    end_value: float,
    target_index: int,
) -> float:
    span = end_index - start_index
    if span == 0:
        return end_value
    slope = (end_value - start_value) / span
    return start_value + slope * (target_index - start_index)


def _score_compression_pivot(
    candles: list[Candle],
    cfg: VCPConfig,
    direction: str,
    pivot_type: str,
    pivot_start: int,
    pivot_end: int,
    pivot_start_value: float,
    pivot_end_value: float,
    setup_start: int,
) -> tuple[float, str, str]:
    if pivot_type == "Horizontal":
        setup = candles[setup_start:-1]
        touches = (
            _boundary_touches(setup, pivot_end_value, cfg.boundary_touch_tolerance_pct)
            if direction == "long"
            else _support_touches(setup, pivot_end_value, cfg.boundary_touch_tolerance_pct)
        )
        if touches >= cfg.min_boundary_touches:
            return 20, f"Pivot line: horizontal {'resistance' if direction == 'long' else 'support'} has {touches} reactions", ""
        return 0, "", f"Pivot line has {touches} reactions, need {cfg.min_boundary_touches}"

    slope = (pivot_end_value - pivot_start_value) / max(1, pivot_end - pivot_start)
    if (direction == "long" and slope < 0) or (direction == "short" and slope > 0):
        return 20, f"Pivot line: diagonal {'descending resistance' if direction == 'long' else 'ascending support'} connects two reactions", ""
    return 0, "", "Diagonal pivot slope contradicts the compression direction"


def _score_compression_ema(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
    start: int,
    end: int,
) -> tuple[float, str, str]:
    recent = candles[start : end + 1]
    emas = ema_values[start : end + 1]
    if not recent:
        return 0, "", "EMA21 cannot be checked without compression candles"
    if direction == "long":
        side_ratio = sum(1 for candle, ema in zip(recent, emas, strict=True) if candle.close >= ema) / len(recent)
        slope_ok = ema_values[-1] >= ema_values[-1 - cfg.ema_slope_lookback]
        if side_ratio >= 0.70 and slope_ok:
            return 20, f"EMA{cfg.ema_period} is below/supportive for {side_ratio:.0%} of compression candles", ""
        return 0, "", f"EMA{cfg.ema_period} is not a clean lower wall for the compression"
    side_ratio = sum(1 for candle, ema in zip(recent, emas, strict=True) if candle.close <= ema) / len(recent)
    slope_ok = ema_values[-1] <= ema_values[-1 - cfg.ema_slope_lookback]
    if side_ratio >= 0.70 and slope_ok:
        return 20, f"EMA{cfg.ema_period} is above/rejecting for {side_ratio:.0%} of compression candles", ""
    return 0, "", f"EMA{cfg.ema_period} is not a clean upper wall for the compression"


def _score_compression_inside_zone(
    candles: list[Candle],
    ema_values: list[float],
    direction: str,
    pivot_start: int,
    pivot_start_value: float,
    pivot_end: int,
    pivot_end_value: float,
    start: int,
    end: int,
) -> tuple[float, str, str]:
    total = max(1, end - start + 1)
    inside = 0
    for index in range(start, end + 1):
        pivot = _compression_line_value(pivot_start, pivot_start_value, pivot_end, pivot_end_value, index)
        ema = ema_values[index]
        candle = candles[index]
        if direction == "long":
            if candle.close <= pivot * 1.003 and candle.close >= ema * 0.997:
                inside += 1
        else:
            if candle.close >= pivot * 0.997 and candle.close <= ema * 1.003:
                inside += 1
    ratio = inside / total
    if ratio >= 0.75:
        return 20, f"Compression zone: {ratio:.0%} of recent closes stay between pivot and EMA21", ""
    return 0, "", f"Candles are not consistently trapped between pivot and EMA21 ({ratio:.0%} inside)"


def _score_compression_gap(
    latest_gap_atr: float,
    early_gap: float,
    latest_gap: float,
    cfg: VCPConfig,
) -> tuple[float, str, str]:
    narrowing = latest_gap <= early_gap
    if latest_gap_atr <= 1.5:
        return 15, f"Pivot-EMA21 distance is tight at {latest_gap_atr:.2f} ATR", ""
    if narrowing and latest_gap_atr <= 2.2:
        return 12, f"Pivot-EMA21 distance is narrowing and now {latest_gap_atr:.2f} ATR", ""
    return 0, "", f"Pivot-EMA21 distance is too wide at {latest_gap_atr:.2f} ATR"


def _score_compression_candles(
    candles: list[Candle],
    start: int,
    end: int,
    atr: float,
) -> tuple[float, str, str]:
    recent = candles[start : end + 1]
    prior = candles[max(0, start - len(recent)) : start]
    if not recent:
        return 0, "", "No compression candles found"
    recent_ranges = [c.high - c.low for c in recent]
    prior_ranges = [c.high - c.low for c in prior] or recent_ranges
    avg_recent_range = mean(recent_ranges)
    avg_prior_range = mean(prior_ranges)
    avg_close = mean(c.close for c in recent)
    if avg_close > 0 and avg_recent_range / avg_close < 0.0003:
        return 0, "", "Candles are too stale/flat to prove real compression"
    overlap_count = sum(
        1
        for prev, curr in zip(recent, recent[1:], strict=False)
        if min(prev.high, curr.high) >= max(prev.low, curr.low)
    )
    overlap_ratio = overlap_count / max(1, len(recent) - 1)
    recent_depth = _base_depth_pct(recent)
    if (
        avg_recent_range <= atr * 1.15
        and avg_recent_range <= avg_prior_range * 1.10
        and (overlap_ratio >= 0.45 or recent_depth <= 4.0)
    ):
        return 10, f"Candle tightness: average range is {avg_recent_range / atr:.2f} ATR with {overlap_ratio:.0%} overlap", ""
    return 0, "", "Candles are not tight/overlapping enough for a clean squeeze"


def _score_compression_trigger(
    status: str,
    distance_to_trigger_pct: float | None,
    cfg: VCPConfig,
) -> tuple[float, str, str]:
    if status == "TRIGGERED":
        return 10, "Breakout trigger: price just closed through the pivot line", ""
    if status == "WAITING":
        return 10, f"Breakout trigger: price is {distance_to_trigger_pct or 0:.2f}% from pivot and waiting", ""
    if status == "FORMING":
        return 4, "Breakout trigger: compression is forming but price is not close enough", ""
    if status == "LATE":
        return 0, "", "Breakout already moved too far from the pivot"
    if status == "FAILED":
        return 0, "", "Compression failed by breaking the wrong side or returning inside"
    return 0, "", "Trigger level is unclear"


def _score_compression_stop(
    current_close: float,
    stop: float,
    atr: float,
    direction: str,
) -> tuple[float, str, str]:
    risk = current_close - stop if direction == "long" else stop - current_close
    risk_atr = risk / atr if atr else 99.0
    if 0 < risk_atr <= 1.7:
        return 5, f"Stop-loss area is logical and close at {risk_atr:.2f} ATR", ""
    return 0, "", f"Stop-loss is too wide or illogical at {risk_atr:.2f} ATR"


def _compression_long_status(candle: Candle, trigger: float, stop: float, cfg: VCPConfig) -> str:
    if candle.close > trigger:
        distance = ((candle.close - trigger) / trigger) * 100
        return "TRIGGERED" if distance <= cfg.max_boundary_distance_pct else "LATE"
    if candle.close < stop:
        return "FAILED"
    distance = ((trigger - candle.close) / trigger) * 100
    return "WAITING" if 0 <= distance <= cfg.max_boundary_distance_pct else "FORMING"


def _compression_short_status(candle: Candle, trigger: float, stop: float, cfg: VCPConfig) -> str:
    if candle.close < trigger:
        distance = ((trigger - candle.close) / trigger) * 100
        return "TRIGGERED" if distance <= cfg.max_boundary_distance_pct else "LATE"
    if candle.close > stop:
        return "FAILED"
    distance = ((candle.close - trigger) / trigger) * 100
    return "WAITING" if 0 <= distance <= cfg.max_boundary_distance_pct else "FORMING"


def _compression_volume_reason(volume_ratio: float | None) -> str:
    if volume_ratio is None:
        return "Volume behavior: unavailable or too sparse; confidence is price-action only"
    if volume_ratio <= 0.90:
        return f"Volume dry-up confirmed: recent compression volume ratio {volume_ratio:.2f}"
    return f"Volume behavior: recent volume ratio {volume_ratio:.2f}; not used as a hard reject"


def _compression_status_rank(status: str) -> int:
    return {
        "TRIGGERED": 6,
        "WAITING": 5,
        "FORMING": 4,
        "LATE": 3,
        "FAILED": 2,
        "REJECT": 1,
    }.get(status, 0)


def _empty_compression(direction: str, pivot_type: str, failures: list[str]) -> _CompressionSetup:
    return _CompressionSetup(
        direction=direction,
        pivot_type=pivot_type,
        status="REJECT",
        score=0.0,
        pivot_start_index=None,
        pivot_end_index=None,
        pivot_start_value=None,
        pivot_end_value=None,
        compression_start_index=None,
        compression_end_index=None,
        zone_low=None,
        zone_high=None,
        trigger=None,
        stop=None,
        distance_to_trigger_pct=None,
        latest_gap_atr=None,
        volume_ratio=None,
        reasons=[],
        failures=failures,
    )


def _compression_output_lines(result: _CompressionSetup, candles: list[Candle]) -> list[str]:
    direction = "Long" if result.direction == "long" else "Short"
    return [
        "Pattern: Pivot-EMA21 Compression",
        f"Direction: {direction}",
        f"Pivot type: {result.pivot_type}",
        f"Status: {result.status}",
        f"Score: {result.score:.0f}",
        "",
        f"Pivot line description: {_compression_pivot_description(result, candles)}",
        f"Pivot line values: {_compression_pivot_values(result, candles)}",
        f"EMA21 condition: {result.reasons[1] if len(result.reasons) > 1 else 'n/a'}",
        f"Compression zone: {_date_span(candles, result.compression_start_index, result.compression_end_index)}; area {_fmt_range(result.zone_low, result.zone_high)}",
        f"Distance between pivot and EMA21: {result.latest_gap_atr:.2f} ATR" if result.latest_gap_atr is not None else "Distance between pivot and EMA21: n/a",
        f"Candle tightness: {_first_line_containing(result.reasons, 'Candle tightness') or 'tightness evidence present'}",
        f"Trigger level: {_fmt_price(result.trigger)}",
        f"Current price: {_fmt_price(result.current_price if hasattr(result, 'current_price') else candles[-1].close)}",
        f"Stop-loss area: {_fmt_price(result.stop)}",
        f"Volume behavior: {_compression_volume_reason(result.volume_ratio)}",
        f"Risk comment: stop is placed on the other side of the compression wall",
        "",
        "Reason:",
        *_bullet_lines(result.reasons[:4]),
        "",
        "Manual review note:",
        "- Check that the pivot line is genuinely respected, EMA21 is the opposite wall, and the breakout is fresh rather than extended.",
    ]


def _compression_reject_lines(result: _CompressionSetup) -> list[str]:
    failures = result.failures or ["Reject reason: pivot-EMA21 compression story is incomplete or unclear"]
    return [
        "Pattern: Pivot-EMA21 Compression",
        "Status: REJECT",
        f"Score: {result.score:.0f}",
        "",
        "Reject reason:",
        *_bullet_lines(failures[:3]),
    ]


def _compression_pivot_description(result: _CompressionSetup, candles: list[Candle]) -> str:
    if result.pivot_start_index is None or result.pivot_end_index is None:
        return "n/a"
    return (
        f"{result.pivot_type.lower()} pivot from "
        f"{candles[result.pivot_start_index].datetime.date()} {_fmt_price(result.pivot_start_value)} "
        f"to {candles[result.pivot_end_index].datetime.date()} {_fmt_price(result.pivot_end_value)}"
    )


def _compression_pivot_values(result: _CompressionSetup, candles: list[Candle]) -> str:
    if result.pivot_start_index is None or result.pivot_end_index is None:
        return "n/a"
    return (
        f"{candles[result.pivot_start_index].datetime.date()} {_fmt_price(result.pivot_start_value)} -> "
        f"{candles[result.pivot_end_index].datetime.date()} {_fmt_price(result.pivot_end_value)}"
    )


def _first_line_containing(lines: list[str], needle: str) -> str | None:
    for line in lines:
        if needle in line:
            return line
    return None


def _fmt_price(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _fmt_range(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "n/a"
    return f"{low:.2f} - {high:.2f}"


def _date_span(candles: list[Candle], start: int | None, end: int | None) -> str:
    if start is None or end is None:
        return "n/a"
    start = max(0, min(start, len(candles) - 1))
    end = max(0, min(end, len(candles) - 1))
    return f"{candles[start].datetime.date()} -> {candles[end].datetime.date()}"


def _bullet_lines(lines: list[str]) -> list[str]:
    return [line if line.startswith("- ") else f"- {line}" for line in lines]


@dataclass(frozen=True)
class _NhathoaiContext:
    cfg: VCPConfig
    closes: list[float]
    ema_values: list[float]
    setup_start: int
    setup: list[Candle]
    compression_start: int
    compression: list[Candle]
    current_close: float
    current_ema: float
    previous_ema: float


def _detect_nhathoai_price_action(
    candles: list[Candle],
    setup_name: str,
    config: VCPConfig | None = None,
) -> VCPEvidence:
    cfg = config or VCPConfig()
    context = _nhathoai_context(candles, cfg)
    if isinstance(context, VCPEvidence):
        return context
    return _detect_bob_volman_setup(context, setup_name)


@dataclass(frozen=True)
class _BVSetup:
    name: str
    direction: str
    score: float
    trigger: float | None
    stop: float | None
    base_start: int
    reasons: list[str]
    failures: list[str]


@dataclass(frozen=True)
class _NhathoaiVCPSetup:
    status: str
    score: float
    pivot: float | None
    current_close: float | None
    distance_to_pivot_pct: float | None
    stop: float | None
    base_start_index: int | None
    base_end_index: int | None
    contractions: list[Contraction]
    volume_ratio: float | None
    prior_uptrend_pct: float | None
    reasons: list[str]
    failures: list[str]


@dataclass(frozen=True)
class _ARBSetup:
    direction: str
    arb_type: str
    status: str
    score: float
    old_high: float | None
    old_low: float | None
    boundary: float | None
    first_break_index: int | None
    area_start_index: int | None
    area_end_index: int | None
    area_low: float | None
    area_high: float | None
    trigger: float | None
    stop: float | None
    base_start: int | None
    reasons: list[str]
    failures: list[str]


@dataclass(frozen=True)
class _DDSetup:
    direction: str
    status: str
    score: float
    impulse_start_index: int | None
    impulse_end_index: int | None
    pullback_start_index: int | None
    pullback_end_index: int | None
    cluster_start_index: int | None
    cluster_end_index: int | None
    cluster_low: float | None
    cluster_high: float | None
    signal: float | None
    stop: float | None
    obstacle: float | None
    reasons: list[str]
    failures: list[str]


@dataclass(frozen=True)
class _SBSetup:
    direction: str
    status: str
    score: float
    impulse_start_index: int | None
    impulse_end_index: int | None
    pullback_start_index: int | None
    pullback_end_index: int | None
    first_break_index: int | None
    failure_index: int | None
    second_break_index: int | None
    trigger: float | None
    stop: float | None
    obstacle: float | None
    reasons: list[str]
    failures: list[str]


@dataclass(frozen=True)
class _FBSetup:
    direction: str
    status: str
    score: float
    impulse_start_index: int | None
    impulse_end_index: int | None
    pullback_start_index: int | None
    pullback_end_index: int | None
    trigger_index: int | None
    trigger: float | None
    stop: float | None
    obstacle: float | None
    reasons: list[str]
    failures: list[str]


@dataclass(frozen=True)
class _BBSetup:
    direction: str
    bb_type: str
    status: str
    score: float
    impulse_start_index: int | None
    impulse_end_index: int | None
    pullback_start_index: int | None
    pullback_end_index: int | None
    block_start_index: int | None
    block_end_index: int | None
    block_low: float | None
    block_high: float | None
    trigger: float | None
    stop: float | None
    obstacle: float | None
    reasons: list[str]
    failures: list[str]


@dataclass(frozen=True)
class _RBSetup:
    direction: str
    status: str
    score: float
    breakout_type: str
    range_start_index: int | None
    range_end_index: int | None
    upper_boundary: float | None
    lower_boundary: float | None
    buildup_start_index: int | None
    buildup_end_index: int | None
    buildup_low: float | None
    buildup_high: float | None
    trigger: float | None
    stop: float | None
    reasons: list[str]
    failures: list[str]


@dataclass(frozen=True)
class _IRBSetup:
    direction: str
    irb_type: str
    status: str
    score: float
    range_start_index: int | None
    range_end_index: int | None
    upper_boundary: float | None
    lower_boundary: float | None
    block_start_index: int | None
    block_end_index: int | None
    block_low: float | None
    block_high: float | None
    trigger: float | None
    target: float | None
    stop: float | None
    risk_reward: float | None
    reasons: list[str]
    failures: list[str]


def _detect_sb_setup(candles: list[Candle], config: VCPConfig | None = None) -> VCPEvidence:
    cfg = config or VCPConfig()
    min_needed = max(cfg.min_history_days, cfg.ema_period + 50)
    if len(candles) < min_needed:
        return _not_qualified(f"SB requires at least {min_needed} candles, got {len(candles)}")

    closes = [c.close for c in candles]
    ema_values = _ema(closes, cfg.ema_period)
    candidates = [
        _score_sb_direction(candles, cfg, ema_values, "long"),
        _score_sb_direction(candles, cfg, ema_values, "short"),
    ]
    result = max(candidates, key=lambda item: (_sb_status_rank(item.status), item.score))
    qualified = result.score >= 80 and result.status in {"WAITING", "TRIGGERED"} and not result.failures

    if result.trigger and result.trigger > 0:
        if result.direction == "long":
            distance_to_trigger = ((result.trigger - candles[-1].close) / result.trigger) * 100
        else:
            distance_to_trigger = ((candles[-1].close - result.trigger) / result.trigger) * 100
    else:
        distance_to_trigger = None

    return VCPEvidence(
        qualified=qualified,
        status=result.status if qualified else "rejected",
        score=result.score,
        pivot=result.trigger,
        current_close=candles[-1].close,
        distance_to_pivot_pct=distance_to_trigger,
        contractions=[],
        reasons=_sb_output_lines(result, candles) if qualified else [],
        failures=[] if qualified else _sb_reject_lines(result),
        base_start_index=result.impulse_start_index,
        base_end_index=len(candles) - 1,
        volume_dry_up_ratio=_window_volume_ratio(candles, max(0, len(candles) - cfg.compression_lookback)),
        prior_uptrend_pct=None,
    )


def _detect_fb_setup(candles: list[Candle], config: VCPConfig | None = None) -> VCPEvidence:
    cfg = config or VCPConfig()
    min_needed = max(cfg.min_history_days, cfg.ema_period + 45)
    if len(candles) < min_needed:
        return _not_qualified(f"FB requires at least {min_needed} candles, got {len(candles)}")

    closes = [c.close for c in candles]
    ema_values = _ema(closes, cfg.ema_period)
    candidates = [
        _score_fb_direction(candles, cfg, ema_values, "long"),
        _score_fb_direction(candles, cfg, ema_values, "short"),
    ]
    result = max(candidates, key=lambda item: (_fb_status_rank(item.status), item.score))
    qualified = result.score >= 80 and result.status in {"WAITING", "TRIGGERED"} and not result.failures

    if result.trigger and result.trigger > 0:
        if result.direction == "long":
            distance_to_trigger = ((result.trigger - candles[-1].close) / result.trigger) * 100
        else:
            distance_to_trigger = ((candles[-1].close - result.trigger) / result.trigger) * 100
    else:
        distance_to_trigger = None

    return VCPEvidence(
        qualified=qualified,
        status=result.status if qualified else "rejected",
        score=result.score,
        pivot=result.trigger,
        current_close=candles[-1].close,
        distance_to_pivot_pct=distance_to_trigger,
        contractions=[],
        reasons=_fb_output_lines(result, candles) if qualified else [],
        failures=[] if qualified else _fb_reject_lines(result),
        base_start_index=result.impulse_start_index,
        base_end_index=len(candles) - 1,
        volume_dry_up_ratio=_window_volume_ratio(candles, max(0, len(candles) - cfg.compression_lookback)),
        prior_uptrend_pct=None,
    )


def _score_fb_direction(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
) -> _FBSetup:
    latest = len(candles) - 1
    triggered = _fb_first_break(candles, latest, direction)
    trigger_index = latest if triggered else None
    trigger_ref = latest - 1 if triggered else latest
    if trigger_ref <= 0:
        return _empty_fb(direction, ["Reject reason: not enough candles to form FB trigger"])

    trigger = candles[trigger_ref].high if direction == "long" else candles[trigger_ref].low
    structure_end = latest if triggered else trigger_ref
    pullback_start = _dd_pullback_start(candles, direction, trigger_ref)
    if pullback_start is None:
        return _empty_fb(direction, ["Reject reason: no first clean pullback before the FB trigger"])
    impulse_start = _dd_impulse_start(candles, direction, pullback_start)
    if impulse_start is None:
        return _empty_fb(direction, ["Reject reason: no clear new impulse before the first pullback"])
    impulse_end = pullback_start

    trend_points, trend_reason, trend_failure = _score_fb_trend(
        candles, ema_values, cfg, direction, impulse_start, impulse_end, structure_end
    )
    ema_points, ema_reason, ema_failure = _score_fb_ema(
        candles, ema_values, cfg, direction, pullback_start, structure_end
    )
    pullback_points, pullback_reason, pullback_failure = _score_dd_pullback(
        candles, direction, impulse_start, impulse_end, pullback_start, trigger_ref
    )
    ema_reach_points, ema_reach_reason, ema_reach_failure = _score_dd_pullback_reaches_ema(
        candles, ema_values, cfg, direction, pullback_start, structure_end
    )
    trigger_points, trigger_reason, trigger_failure, status = _score_fb_trigger(
        candles[-1], trigger, triggered, cfg, direction
    )
    stop = min(c.low for c in candles[pullback_start : structure_end + 1]) if direction == "long" else max(
        c.high for c in candles[pullback_start : structure_end + 1]
    )
    stop_points, stop_reason, stop_failure = _score_fb_stop(candles, trigger, stop, cfg, direction, trigger_ref)
    obstacle = _nearest_dd_obstacle(candles, trigger, direction, impulse_start, trigger_ref)
    obstacle_points, obstacle_reason, obstacle_failure = _score_dd_obstacle(
        candles, trigger, obstacle, direction, trigger_ref
    )

    score = (
        trend_points
        + ema_points
        + pullback_points
        + ema_reach_points
        + trigger_points
        + stop_points
        + obstacle_points
    )
    reasons = [
        trend_reason,
        ema_reason,
        pullback_reason,
        ema_reach_reason,
        trigger_reason,
        stop_reason,
        obstacle_reason,
    ]
    failures = [
        *([] if trend_points else [trend_failure]),
        *([] if ema_points else [ema_failure]),
        *([] if pullback_points else [pullback_failure]),
        *([] if ema_reach_points else [ema_reach_failure]),
        *([] if trigger_points else [trigger_failure]),
        *([] if stop_points else [stop_failure]),
        *([] if obstacle_points else [obstacle_failure]),
    ]
    if status in {"LATE", "FAILED", "REJECT"}:
        failures.append(f"Status is {status}, not an active FB entry candidate")
    if score < 80 and status in {"WAITING", "TRIGGERED"}:
        status = "REJECT"
        failures.append(f"Score {score:.0f} is below required FB threshold 80")

    return _FBSetup(
        direction=direction,
        status=status,
        score=max(0.0, score),
        impulse_start_index=impulse_start,
        impulse_end_index=impulse_end,
        pullback_start_index=pullback_start,
        pullback_end_index=trigger_ref - 1,
        trigger_index=trigger_index,
        trigger=trigger,
        stop=stop,
        obstacle=obstacle,
        reasons=[reason for reason in reasons if reason],
        failures=[failure for failure in failures if failure],
    )


def _score_fb_trend(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    impulse_start: int,
    impulse_end: int,
    structure_end: int,
) -> tuple[float, str, str]:
    trend_points, trend_reason, trend_failure = _score_dd_trend(
        candles, ema_values, cfg, direction, impulse_start, impulse_end, structure_end
    )
    if not trend_points:
        return 0, "", trend_failure
    recent_before_impulse = candles[max(0, impulse_start - 18) : impulse_start]
    impulse = candles[impulse_start : impulse_end + 1]
    if len(recent_before_impulse) >= 8 and impulse:
        prior_range = _base_depth_pct(recent_before_impulse)
        impulse_range = _base_depth_pct(impulse)
        # FB should be early in a fresh directional move, not a mature multi-pullback trend.
        if impulse_range < max(2.0, prior_range * 0.45):
            return 0, "", "FB trend is not fresh enough before the first pullback"
    return 20, f"New trend / impulse before first pullback: {trend_reason}", ""


def _score_fb_ema(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    pullback_start: int,
    structure_end: int,
) -> tuple[float, str, str]:
    slope_back = max(0, structure_end - cfg.ema_slope_lookback)
    recent_start = max(0, pullback_start - 12)
    closes = [c.close for c in candles[recent_start : structure_end + 1]]
    emas = ema_values[recent_start : structure_end + 1]
    segment = candles[pullback_start : structure_end + 1]
    segment_emas = ema_values[pullback_start : structure_end + 1]
    if direction == "long":
        slope_ok = ema_values[structure_end] >= ema_values[slope_back]
        side_ratio = sum(1 for close, ema in zip(closes, emas, strict=True) if close >= ema) / len(closes)
        nearest = min(abs(c.low - ema) / ema * 100 for c, ema in zip(segment, segment_emas, strict=True) if ema > 0)
    else:
        slope_ok = ema_values[structure_end] <= ema_values[slope_back]
        side_ratio = sum(1 for close, ema in zip(closes, emas, strict=True) if close <= ema) / len(closes)
        nearest = min(abs(c.high - ema) / ema * 100 for c, ema in zip(segment, segment_emas, strict=True) if ema > 0)
    crossings = _ema_crossings(closes, emas)
    if slope_ok and side_ratio >= 0.55 and crossings <= 4 and nearest <= cfg.max_pullback_ema_distance_pct * 1.2:
        return 15, f"EMA21 condition: first pullback reacts {nearest:.2f}% from EMA with {side_ratio:.0%} closes on correct side", ""
    return 0, "", f"EMA21 failed for FB: side ratio {side_ratio:.0%}, crossings {crossings}, closest {nearest:.2f}%"


def _score_fb_trigger(
    latest: Candle,
    trigger: float,
    triggered: bool,
    cfg: VCPConfig,
    direction: str,
) -> tuple[float, str, str, str]:
    if trigger <= 0:
        return 0, "", "First break trigger level is missing", "REJECT"
    if triggered:
        extension = ((latest.close - trigger) / trigger * 100) if direction == "long" else (
            (trigger - latest.close) / trigger * 100
        )
        status = "TRIGGERED" if extension <= cfg.max_boundary_distance_pct else "LATE"
        if status == "TRIGGERED":
            return 15, f"First break trigger: latest candle closed beyond {_fmt_price(trigger)}", "", status
        return 0, "", "First break already moved too far from trigger", status
    distance = ((trigger - latest.close) / trigger * 100) if direction == "long" else (
        (latest.close - trigger) / trigger * 100
    )
    if 0 <= distance <= cfg.max_boundary_distance_pct:
        return 10, f"First break trigger: waiting {distance:.2f}% from {_fmt_price(trigger)}", "", "WAITING"
    return 0, "", "First break trigger has not happened and price is not close", "REJECT"


def _score_fb_stop(
    candles: list[Candle],
    trigger: float | None,
    stop: float | None,
    cfg: VCPConfig,
    direction: str,
    trigger_ref: int,
) -> tuple[float, str, str]:
    if trigger is None or stop is None or trigger <= 0 or stop <= 0:
        return 0, "", "Stop-loss area is missing"
    atr = _average_range(candles[max(0, trigger_ref - 14) : trigger_ref] or candles[-14:])
    distance = (trigger - stop) if direction == "long" else (stop - trigger)
    if atr > 0 and 0 < distance <= atr * 1.7:
        return 10, f"Stop-loss area: {_fmt_price(stop)} is {distance / atr:.2f} ATR from first break", ""
    return 0, "", f"Stop-loss is too wide: {_fmt_price(distance)} vs 1.7 ATR limit"


def _fb_first_break(candles: list[Candle], index: int, direction: str) -> bool:
    if index <= 0:
        return False
    previous = candles[index - 1]
    candle = candles[index]
    if direction == "long":
        return candle.close > previous.high and candle.close > candle.open
    return candle.close < previous.low and candle.close < candle.open


def _empty_fb(direction: str, failures: list[str]) -> _FBSetup:
    return _FBSetup(
        direction=direction,
        status="REJECT",
        score=0.0,
        impulse_start_index=None,
        impulse_end_index=None,
        pullback_start_index=None,
        pullback_end_index=None,
        trigger_index=None,
        trigger=None,
        stop=None,
        obstacle=None,
        reasons=[],
        failures=failures,
    )


def _fb_output_lines(result: _FBSetup, candles: list[Candle]) -> list[str]:
    direction = "Long" if result.direction == "long" else "Short"
    return [
        "Pattern: FB",
        f"Direction: {direction}",
        f"Status: {result.status}",
        f"Score: {result.score:.0f}",
        f"Trend: new {direction.lower()} trend before first pullback",
        f"EMA21 condition: first pullback reacts near EMA21 in trend direction",
        f"Impulse wave: {_date_range_text(candles, result.impulse_start_index, result.impulse_end_index)}",
        f"First pullback: {_date_range_text(candles, result.pullback_start_index, result.pullback_end_index)}",
        f"First break trigger: {_date_text(candles, result.trigger_index)}; level {_fmt_price(result.trigger)}",
        f"Current price: {_fmt_price(candles[-1].close)}",
        f"Stop-loss area: {_fmt_price(result.stop)}",
        f"Nearest obstacle: {_fmt_price(result.obstacle)}",
        "Reason:",
        *[f"- {reason}" for reason in result.reasons[:8]],
        "Manual review note:",
        "- Confirm this is the first pullback of a fresh trend, EMA21 supports/rejects the pullback, and the first break is fresh before acting.",
    ]


def _fb_reject_lines(result: _FBSetup) -> list[str]:
    failures = result.failures or ["Reject reason: FB story is incomplete or unclear"]
    return [
        "Pattern: FB",
        "Status: REJECT",
        f"Score: {result.score:.0f}",
        "Reject reason:",
        *[f"- {failure}" for failure in failures[:8]],
    ]


def _fb_status_rank(status: str) -> int:
    return {
        "TRIGGERED": 5,
        "WAITING": 4,
        "LATE": 3,
        "FAILED": 2,
        "REJECT": 1,
    }.get(status, 0)


def _score_sb_direction(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
) -> _SBSetup:
    best = _empty_sb(direction, ["Reject reason: no compact first-break failure and second-break structure found"])
    n = len(candles)
    latest = n - 1

    for first_break in range(max(2, n - 12), n - 2):
        if not _sb_first_break(candles, first_break, direction):
            continue
        for failure in range(first_break + 1, min(n - 1, first_break + 6)):
            if not _sb_failure(candles, failure, direction):
                continue
            second_breaks = [
                index
                for index in range(failure + 1, min(n, first_break + 10))
                if _sb_second_break(candles, index, direction)
            ]
            if second_breaks:
                # Use the first second-break after the W/M so later continuation candles do not become fresh SBs.
                trigger_index = second_breaks[0]
                candidate = _build_sb_candidate(
                    candles,
                    cfg,
                    ema_values,
                    direction,
                    first_break,
                    failure,
                    trigger_index,
                )
                if (_sb_status_rank(candidate.status), candidate.score) > (_sb_status_rank(best.status), best.score):
                    best = candidate

            # WAITING: first break failed, the current candle is the trigger reference.
            if not second_breaks and latest > failure and latest - first_break <= 9:
                candidate = _build_sb_candidate(
                    candles,
                    cfg,
                    ema_values,
                    direction,
                    first_break,
                    failure,
                    None,
                )
                if (_sb_status_rank(candidate.status), candidate.score) > (_sb_status_rank(best.status), best.score):
                    best = candidate
    return best


def _build_sb_candidate(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
    first_break: int,
    failure: int,
    second_break: int | None,
) -> _SBSetup:
    trigger_ref = second_break - 1 if second_break is not None else len(candles) - 1
    trigger = candles[trigger_ref].high if direction == "long" else candles[trigger_ref].low
    structure_end = second_break if second_break is not None else len(candles) - 1
    pullback_start = _dd_pullback_start(candles, direction, first_break)
    if pullback_start is None:
        return _empty_sb(direction, ["Reject reason: no one-wave pullback before first break"])
    impulse_start = _dd_impulse_start(candles, direction, pullback_start)
    if impulse_start is None:
        return _empty_sb(direction, ["Reject reason: no clear impulse wave before SB pullback"])
    impulse_end = pullback_start

    trend_points, trend_reason, trend_failure = _score_sb_trend(
        candles, ema_values, cfg, direction, impulse_start, impulse_end, structure_end
    )
    ema_points, ema_reason, ema_failure = _score_sb_ema(
        candles, ema_values, cfg, direction, pullback_start, structure_end
    )
    pullback_points, pullback_reason, pullback_failure = _score_sb_pullback(
        candles, direction, impulse_start, impulse_end, pullback_start, first_break
    )
    ema_reach_points, ema_reach_reason, ema_reach_failure = _score_dd_pullback_reaches_ema(
        candles, ema_values, cfg, direction, pullback_start, structure_end
    )
    first_points, first_reason, first_failure = _score_sb_first_break(candles, first_break, direction)
    failure_points, failure_reason, failure_failure = _score_sb_failure(candles, first_break, failure, direction)
    trigger_points, trigger_reason, trigger_failure, status = _score_sb_trigger(
        candles, cfg, first_break, failure, second_break, trigger, direction
    )
    stop = _sb_stop(candles, first_break, structure_end, direction)
    stop_points, stop_reason, stop_failure = _score_sb_stop(candles, trigger, stop, cfg, direction, first_break)
    obstacle = _nearest_dd_obstacle(candles, trigger, direction, impulse_start, first_break)
    obstacle_failure = _sb_obstacle_failure(candles, trigger, obstacle, direction, first_break)

    score = (
        trend_points
        + ema_points
        + pullback_points
        + ema_reach_points
        + first_points
        + failure_points
        + trigger_points
        + stop_points
    )
    if second_break is not None and second_break - first_break >= 8:
        score -= 10
    reasons = [
        trend_reason,
        ema_reason,
        pullback_reason,
        ema_reach_reason,
        first_reason,
        failure_reason,
        trigger_reason,
        stop_reason,
    ]
    if obstacle_failure:
        reasons.append(f"Nearest obstacle warning: {obstacle_failure}")
    else:
        reasons.append(
            "Nearest obstacle: no immediate blocking swing level"
            if obstacle is None
            else f"Nearest obstacle: {_fmt_price(obstacle)} leaves enough room"
        )

    failures = [
        *([] if trend_points else [trend_failure]),
        *([] if ema_points else [ema_failure]),
        *([] if pullback_points else [pullback_failure]),
        *([] if ema_reach_points else [ema_reach_failure]),
        *([] if first_points else [first_failure]),
        *([] if failure_points else [failure_failure]),
        *([] if trigger_points else [trigger_failure]),
        *([] if stop_points else [stop_failure]),
    ]
    if not _sb_has_wm_shape(candles, pullback_start, first_break, failure, structure_end, direction):
        failures.append("No compact W-shape/M-shape at the end of the pullback")
        status = "REJECT"
    if not _sb_structure_near_ema(candles, ema_values, cfg, first_break, structure_end, direction):
        failures.append("SB W/M structure is not close enough to EMA21")
        status = "REJECT"
    if status in {"LATE", "FAILED", "REJECT"}:
        failures.append(f"Status is {status}, not an active SB entry candidate")
    if score < 80 and status in {"WAITING", "TRIGGERED"}:
        status = "REJECT"
        failures.append(f"Score {score:.0f} is below required SB threshold 80")

    return _SBSetup(
        direction=direction,
        status=status,
        score=max(0.0, score),
        impulse_start_index=impulse_start,
        impulse_end_index=impulse_end,
        pullback_start_index=pullback_start,
        pullback_end_index=first_break - 1,
        first_break_index=first_break,
        failure_index=failure,
        second_break_index=second_break,
        trigger=trigger,
        stop=stop,
        obstacle=obstacle,
        reasons=[reason for reason in reasons if reason],
        failures=[failure for failure in failures if failure],
    )


def _score_sb_ema(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    pullback_start: int,
    structure_end: int,
) -> tuple[float, str, str]:
    slope_back = max(0, structure_end - cfg.ema_slope_lookback)
    segment = candles[pullback_start : structure_end + 1]
    emas = ema_values[pullback_start : structure_end + 1]
    recent_start = max(0, structure_end - 24)
    recent_closes = [c.close for c in candles[recent_start : structure_end + 1]]
    recent_emas = ema_values[recent_start : structure_end + 1]
    if direction == "long":
        slope_ok = ema_values[structure_end] >= ema_values[slope_back]
        side_ratio = sum(1 for close, ema in zip(recent_closes, recent_emas, strict=True) if close >= ema) / len(recent_closes)
        near_ema = min(abs(c.low - ema) / ema * 100 for c, ema in zip(segment, emas, strict=True) if ema > 0)
    else:
        slope_ok = ema_values[structure_end] <= ema_values[slope_back]
        side_ratio = sum(1 for close, ema in zip(recent_closes, recent_emas, strict=True) if close <= ema) / len(recent_closes)
        near_ema = min(abs(c.high - ema) / ema * 100 for c, ema in zip(segment, emas, strict=True) if ema > 0)
    crossings = _ema_crossings(recent_closes, recent_emas)
    if slope_ok and side_ratio >= 0.50 and crossings <= 7 and near_ema <= cfg.max_pullback_ema_distance_pct * 1.5:
        return 15, f"EMA21 condition: supports/rejects SB pullback, closest reaction {near_ema:.2f}% from EMA", ""
    return 0, "", f"EMA21 failed for SB: side ratio {side_ratio:.0%}, crossings {crossings}, closest {near_ema:.2f}%"


def _score_sb_trend(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    impulse_start: int,
    impulse_end: int,
    structure_end: int,
) -> tuple[float, str, str]:
    lookback_start = max(0, impulse_start - 10)
    trend_closes = [c.close for c in candles[lookback_start : structure_end + 1]]
    trend_emas = ema_values[lookback_start : structure_end + 1]
    if len(trend_closes) < 10:
        return 0, "", "Trend is too short to confirm before SB"
    slope_back = max(0, structure_end - cfg.ema_slope_lookback)
    if direction == "long":
        slope_ok = ema_values[structure_end] >= ema_values[slope_back]
        side_ratio = sum(1 for close, ema in zip(trend_closes, trend_emas, strict=True) if close >= ema) / len(trend_closes)
        impulse_pct = (candles[impulse_end].high - candles[impulse_start].low) / candles[impulse_start].low * 100
        impulse_ok = candles[impulse_end].high > candles[impulse_start].high
    else:
        slope_ok = ema_values[structure_end] <= ema_values[slope_back]
        side_ratio = sum(1 for close, ema in zip(trend_closes, trend_emas, strict=True) if close <= ema) / len(trend_closes)
        impulse_pct = (candles[impulse_start].high - candles[impulse_end].low) / candles[impulse_start].high * 100
        impulse_ok = candles[impulse_end].low < candles[impulse_start].low
    crossings = _ema_crossings(trend_closes, trend_emas)
    if slope_ok and side_ratio >= 0.45 and crossings <= 7 and impulse_pct >= 1.5 and impulse_ok:
        return 20, f"Clear enough SB trend: impulse {impulse_pct:.1f}%, EMA side ratio {side_ratio:.0%}, {crossings} crossing(s)", ""
    return 0, "", f"SB trend failed: impulse {impulse_pct:.1f}%, EMA side ratio {side_ratio:.0%}, crossings {crossings}"


def _score_sb_pullback(
    candles: list[Candle],
    direction: str,
    impulse_start: int,
    impulse_end: int,
    pullback_start: int,
    first_break: int,
) -> tuple[float, str, str]:
    pullback = candles[pullback_start:first_break]
    if len(pullback) < 3 or len(pullback) > 12:
        return 0, "", f"Pullback length {len(pullback)} is outside compact SB one-wave range"
    ranges = [c.high - c.low for c in pullback]
    avg_range = mean(ranges)
    if avg_range <= 0:
        return 0, "", "Pullback range cannot be measured"
    if max(ranges) > avg_range * 3.0:
        return 0, "", "Pullback contains a vertical/shock candle"
    if direction == "long":
        impulse_size = candles[impulse_end].high - candles[impulse_start].low
        pullback_size = candles[impulse_end].high - min(c.low for c in pullback)
        direction_steps = sum(1 for previous, current in zip(pullback, pullback[1:], strict=False) if current.close <= previous.close)
        end_near_extreme = pullback[-1].close <= mean(c.close for c in pullback)
    else:
        impulse_size = candles[impulse_start].high - candles[impulse_end].low
        pullback_size = max(c.high for c in pullback) - candles[impulse_end].low
        direction_steps = sum(1 for previous, current in zip(pullback, pullback[1:], strict=False) if current.close >= previous.close)
        end_near_extreme = pullback[-1].close >= mean(c.close for c in pullback)

    retrace = pullback_size / impulse_size if impulse_size > 0 else 9.9
    step_ratio = direction_steps / max(1, len(pullback) - 1)
    net_move = abs(pullback[-1].close - pullback[0].close)
    diagonal = net_move >= avg_range * 0.25
    if 0.15 <= retrace <= 0.85 and step_ratio >= 0.40 and diagonal and end_near_extreme:
        return 20, f"Pullback description: compact one-wave SB pullback, retrace {retrace:.0%}, directional steps {step_ratio:.0%}", ""
    return (
        0,
        "",
        f"Pullback is not a clean SB wave: retrace {retrace:.0%}, directional steps {step_ratio:.0%}, diagonal={diagonal}",
    )


def _score_sb_first_break(candles: list[Candle], first_break: int, direction: str) -> tuple[float, str, str]:
    previous = candles[first_break - 1]
    candle = candles[first_break]
    if direction == "long" and candle.high > previous.high and candle.close > previous.close and candle.close >= candle.open:
        return 10, f"First break: {candle.datetime.date().isoformat()} broke previous candle high {_fmt_price(previous.high)}", ""
    if direction == "short" and candle.low < previous.low and candle.close < previous.close and candle.close <= candle.open:
        return 10, f"First break: {candle.datetime.date().isoformat()} broke previous candle low {_fmt_price(previous.low)}", ""
    return 0, "", "First break is not a directional break of the immediately previous candle"


def _score_sb_failure(
    candles: list[Candle],
    first_break: int,
    failure: int,
    direction: str,
) -> tuple[float, str, str]:
    candle = candles[failure]
    previous = candles[failure - 1]
    if failure - first_break > 5:
        return 0, "", "First break failure happened too late"
    if direction == "long" and candle.low < previous.low:
        return 10, f"First break failure: {candle.datetime.date().isoformat()} broke back below previous low {_fmt_price(previous.low)}", ""
    if direction == "short" and candle.high > previous.high:
        return 10, f"First break failure: {candle.datetime.date().isoformat()} broke back above previous high {_fmt_price(previous.high)}", ""
    return 0, "", "First break did not fail through the opposite previous-candle side"


def _score_sb_trigger(
    candles: list[Candle],
    cfg: VCPConfig,
    first_break: int,
    failure: int,
    second_break: int | None,
    trigger: float,
    direction: str,
) -> tuple[float, str, str, str]:
    latest = candles[-1]
    if second_break is not None:
        if second_break - first_break > 9:
            return 0, "", "Second break happened too late", "REJECT"
        if len(candles) - 1 - second_break > 1:
            return 0, "", "Second break already happened more than one candle ago", "LATE"
        if direction == "long":
            if latest.close <= trigger:
                return 0, "", "Second break did not close above trigger", "REJECT"
            extension = (latest.close - trigger) / trigger * 100
            status = "TRIGGERED" if extension <= cfg.max_boundary_distance_pct else "LATE"
        else:
            if latest.close >= trigger:
                return 0, "", "Second break did not close below trigger", "REJECT"
            extension = (trigger - latest.close) / trigger * 100
            status = "TRIGGERED" if extension <= cfg.max_boundary_distance_pct else "LATE"
        points = 8 if second_break - first_break >= 8 else 10
        return points, f"Second break trigger: latest candle closed beyond {_fmt_price(trigger)} within {second_break - first_break} candle(s)", "", status

    if len(candles) - 1 - first_break > 9:
        return 0, "", "Waiting second break is too late after first break", "REJECT"
    if direction == "long":
        if latest.close < min(c.low for c in candles[first_break:]):
            return 0, "", "SB failed below W-shape low", "FAILED"
        distance = (trigger - latest.close) / trigger * 100
    else:
        if latest.close > max(c.high for c in candles[first_break:]):
            return 0, "", "SB failed above M-shape high", "FAILED"
        distance = (latest.close - trigger) / trigger * 100
    if 0 <= distance <= cfg.max_boundary_distance_pct:
        return 8, f"Second break trigger: waiting {distance:.2f}% from {_fmt_price(trigger)} after first-break failure", "", "WAITING"
    return 0, "", "Second break has not happened and current price is not close to trigger", "REJECT"


def _score_sb_stop(
    candles: list[Candle],
    trigger: float | None,
    stop: float | None,
    cfg: VCPConfig,
    direction: str,
    first_break: int,
) -> tuple[float, str, str]:
    if trigger is None or stop is None or trigger <= 0 or stop <= 0:
        return 0, "", "Stop-loss area is missing"
    atr = _average_range(candles[max(0, first_break - 14) : first_break] or candles[-14:])
    distance = (trigger - stop) if direction == "long" else (stop - trigger)
    if atr > 0 and 0 < distance <= atr * 2.0:
        return 5, f"Stop-loss area: {_fmt_price(stop)} is {distance / atr:.2f} ATR from trigger", ""
    return 0, "", f"Stop-loss is too wide: {_fmt_price(distance)} vs 2.0 ATR limit"


def _sb_obstacle_failure(
    candles: list[Candle],
    trigger: float,
    obstacle: float | None,
    direction: str,
    first_break: int,
) -> str | None:
    if obstacle is None:
        return None
    atr = _average_range(candles[max(0, first_break - 14) : first_break] or candles[-14:])
    distance = (obstacle - trigger) if direction == "long" else (trigger - obstacle)
    if atr > 0 and distance < atr * 0.75:
        return f"Nearest obstacle {_fmt_price(obstacle)} is too close to SB trigger"
    return None


def _sb_stop(candles: list[Candle], first_break: int, structure_end: int, direction: str) -> float:
    structure = candles[first_break : structure_end + 1]
    if direction == "long":
        return min(c.low for c in structure)
    return max(c.high for c in structure)


def _sb_first_break(candles: list[Candle], index: int, direction: str) -> bool:
    if index <= 0:
        return False
    if direction == "long":
        return candles[index].high > candles[index - 1].high
    return candles[index].low < candles[index - 1].low


def _sb_failure(candles: list[Candle], index: int, direction: str) -> bool:
    if index <= 0:
        return False
    if direction == "long":
        return candles[index].low < candles[index - 1].low
    return candles[index].high > candles[index - 1].high


def _sb_second_break(candles: list[Candle], index: int, direction: str) -> bool:
    if index <= 0:
        return False
    if direction == "long":
        return candles[index].close > candles[index - 1].high
    return candles[index].close < candles[index - 1].low


def _sb_has_wm_shape(
    candles: list[Candle],
    pullback_start: int,
    first_break: int,
    failure: int,
    structure_end: int,
    direction: str,
) -> bool:
    if not (first_break < failure <= structure_end):
        return False
    structure = candles[first_break : structure_end + 1]
    if not 3 <= len(structure) <= 6:
        return False
    atr = _average_range(candles[max(0, first_break - 14) : first_break] or candles[-14:])
    if atr <= 0:
        return False
    if max(c.high for c in structure) - min(c.low for c in structure) > atr * 4.0:
        return False

    pullback = candles[pullback_start:first_break]
    if len(pullback) < 3:
        return False
    if direction == "long":
        left_window_start = max(pullback_start, first_break - 3)
        left_window = candles[left_window_start:first_break]
        if not left_window:
            return False
        left_low_index = left_window_start + min(range(len(left_window)), key=lambda index: left_window[index].low)
        pullback_low = min(c.low for c in pullback)
        failure_low = min(c.low for c in candles[first_break : failure + 1])
        failure_near_pullback_low = pullback_low - atr * 0.50 <= failure_low <= pullback_low + atr * 1.60
        first_leg_ok = (
            first_break - left_low_index <= 4
            and candles[first_break].high > candles[first_break - 1].high
        )
        right_side_ok = candles[structure_end].close > candles[failure].close
        failure_not_destructive = candles[failure].close >= pullback_low - atr * 0.35
        return (
            first_leg_ok
            and candles[failure].low < candles[failure - 1].low
            and failure_near_pullback_low
            and failure_not_destructive
            and right_side_ok
        )
    left_window_start = max(pullback_start, first_break - 3)
    left_window = candles[left_window_start:first_break]
    if not left_window:
        return False
    left_high_index = left_window_start + max(range(len(left_window)), key=lambda index: left_window[index].high)
    pullback_high = max(c.high for c in pullback)
    failure_high = max(c.high for c in candles[first_break : failure + 1])
    failure_near_pullback_high = pullback_high - atr * 1.60 <= failure_high <= pullback_high + atr * 0.50
    first_leg_ok = (
        first_break - left_high_index <= 4
        and candles[first_break].low < candles[first_break - 1].low
    )
    right_side_ok = candles[structure_end].close < candles[failure].close
    failure_not_destructive = candles[failure].close <= pullback_high + atr * 0.35
    return (
        first_leg_ok
        and candles[failure].high > candles[failure - 1].high
        and failure_near_pullback_high
        and failure_not_destructive
        and right_side_ok
    )


def _sb_structure_near_ema(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    first_break: int,
    structure_end: int,
    direction: str,
) -> bool:
    start = max(0, first_break - 2)
    segment = candles[start : structure_end + 1]
    emas = ema_values[start : structure_end + 1]
    if not segment or len(segment) != len(emas):
        return False
    if direction == "long":
        nearest = min(abs(c.low - ema) / ema * 100 for c, ema in zip(segment, emas, strict=True) if ema > 0)
        average_close_distance = mean(abs(c.close - ema) / ema * 100 for c, ema in zip(segment, emas, strict=True) if ema > 0)
        return (
            nearest <= cfg.max_pullback_ema_distance_pct * 1.5
            and average_close_distance <= cfg.max_pullback_ema_distance_pct * 3.0
        )
    nearest = min(abs(c.high - ema) / ema * 100 for c, ema in zip(segment, emas, strict=True) if ema > 0)
    average_close_distance = mean(abs(c.close - ema) / ema * 100 for c, ema in zip(segment, emas, strict=True) if ema > 0)
    return (
        nearest <= cfg.max_pullback_ema_distance_pct * 1.5
        and average_close_distance <= cfg.max_pullback_ema_distance_pct * 3.0
    )


def _empty_sb(direction: str, failures: list[str]) -> _SBSetup:
    return _SBSetup(
        direction=direction,
        status="REJECT",
        score=0.0,
        impulse_start_index=None,
        impulse_end_index=None,
        pullback_start_index=None,
        pullback_end_index=None,
        first_break_index=None,
        failure_index=None,
        second_break_index=None,
        trigger=None,
        stop=None,
        obstacle=None,
        reasons=[],
        failures=failures,
    )


def _sb_output_lines(result: _SBSetup, candles: list[Candle]) -> list[str]:
    direction = "Long" if result.direction == "long" else "Short"
    return [
        "Pattern: SB",
        f"Direction: {direction}",
        f"Status: {result.status}",
        f"Score: {result.score:.0f}",
        f"Trend: {direction} trend before pullback",
        f"EMA21 condition: trend EMA supports/rejects the pullback",
        f"Impulse wave: {_date_range_text(candles, result.impulse_start_index, result.impulse_end_index)}",
        f"Pullback description: {_date_range_text(candles, result.pullback_start_index, result.pullback_end_index)}",
        f"First break: {_date_text(candles, result.first_break_index)}",
        f"First break failure: {_date_text(candles, result.failure_index)}",
        f"Second break trigger: {_date_text(candles, result.second_break_index)}; level {_fmt_price(result.trigger)}",
        f"Current price: {_fmt_price(candles[-1].close)}",
        f"Stop-loss area: {_fmt_price(result.stop)}",
        f"Nearest obstacle: {_fmt_price(result.obstacle)}",
        "Reason:",
        *[f"- {reason}" for reason in result.reasons[:8]],
        "Manual review note:",
        "- Confirm clear trend, one clean EMA21 pullback, first break failure, compact W/M shape, second break timing, and stop distance before acting.",
    ]


def _sb_reject_lines(result: _SBSetup) -> list[str]:
    failures = result.failures or ["Reject reason: SB story is incomplete or unclear"]
    return [
        "Pattern: SB",
        "Status: REJECT",
        f"Score: {result.score:.0f}",
        "Reject reason:",
        *[f"- {failure}" for failure in failures[:8]],
    ]


def _sb_status_rank(status: str) -> int:
    return {
        "TRIGGERED": 5,
        "WAITING": 4,
        "LATE": 3,
        "FAILED": 2,
        "REJECT": 1,
    }.get(status, 0)


def _detect_bb_setup(candles: list[Candle], config: VCPConfig | None = None) -> VCPEvidence:
    cfg = config or VCPConfig()
    min_needed = max(cfg.min_history_days, cfg.ema_period + 50)
    if len(candles) < min_needed:
        return _not_qualified(f"BB requires at least {min_needed} candles, got {len(candles)}")

    closes = [c.close for c in candles]
    ema_values = _ema(closes, cfg.ema_period)
    candidates = [
        _score_bb_direction(candles, cfg, ema_values, "long"),
        _score_bb_direction(candles, cfg, ema_values, "short"),
    ]
    result = max(candidates, key=lambda item: (_bb_status_rank(item.status), item.score))
    qualified = result.score >= 80 and result.status in {"WAITING", "TRIGGERED"} and not result.failures

    if result.trigger and result.trigger > 0:
        if result.direction == "long":
            distance_to_trigger = ((result.trigger - candles[-1].close) / result.trigger) * 100
        else:
            distance_to_trigger = ((candles[-1].close - result.trigger) / result.trigger) * 100
    else:
        distance_to_trigger = None

    return VCPEvidence(
        qualified=qualified,
        status=result.status if qualified else "rejected",
        score=result.score,
        pivot=result.trigger,
        current_close=candles[-1].close,
        distance_to_pivot_pct=distance_to_trigger,
        contractions=[],
        reasons=_bb_output_lines(result, candles) if qualified else [],
        failures=[] if qualified else _bb_reject_lines(result),
        base_start_index=result.impulse_start_index,
        base_end_index=len(candles) - 1,
        volume_dry_up_ratio=_window_volume_ratio(candles, max(0, len(candles) - cfg.compression_lookback)),
        prior_uptrend_pct=None,
    )


def _score_bb_direction(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
) -> _BBSetup:
    best = _empty_bb(direction, ["Reject reason: no tight block in a favorable BB context found"])
    n = len(candles)

    for include_latest in (False, True):
        block_end_exclusive = n if include_latest else n - 1
        for block_len in range(4, min(11, block_end_exclusive - 5) + 1):
            block_start = block_end_exclusive - block_len
            block_end = block_end_exclusive - 1
            if block_start < 20:
                continue
            candidate = _build_bb_candidate(
                candles,
                cfg,
                ema_values,
                direction,
                block_start,
                block_end,
                include_latest=include_latest,
            )
            if (_bb_status_rank(candidate.status), candidate.score) > (_bb_status_rank(best.status), best.score):
                best = candidate
    return best


def _build_bb_candidate(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
    block_start: int,
    block_end: int,
    *,
    include_latest: bool,
) -> _BBSetup:
    block = candles[block_start : block_end + 1]
    block_low = min(c.low for c in block)
    block_high = max(c.high for c in block)
    trigger = block_high if direction == "long" else block_low
    stop = _bb_stop(block, direction)
    latest = candles[-1]

    status = _bb_entry_status(latest, trigger, stop, block_low, block_high, cfg, direction, include_latest)
    block_points, block_reason, block_failure = _score_bb_block(block, candles, cfg, block_start)
    boundary_points, boundary_reason, boundary_failure = _score_bb_signal_boundary(block, trigger, cfg, direction)
    context_points, context_reason, context_failure, bb_type, impulse_start, impulse_end, pullback_start, pullback_end = (
        _score_bb_context(candles, ema_values, cfg, direction, block_start, block_end)
    )
    ema_points, ema_reason, ema_failure = _score_bb_ema(candles, ema_values, cfg, direction, block_start, block_end)
    buildup_points, buildup_reason, buildup_failure = _score_bb_buildup(block, direction)
    trigger_points, trigger_reason, trigger_failure = _score_bb_trigger(latest, trigger, status, cfg, direction)
    stop_points, stop_reason, stop_failure = _score_bb_stop(candles, trigger, stop, cfg, direction, block_start)
    obstacle = _nearest_dd_obstacle(candles, trigger, direction, max(0, impulse_start or block_start - 45), block_start)
    obstacle_points, obstacle_reason, obstacle_failure = _score_dd_obstacle(candles, trigger, obstacle, direction, block_start)

    score = (
        context_points
        + block_points
        + boundary_points
        + ema_points
        + buildup_points
        + trigger_points
        + stop_points
        + obstacle_points
    )
    reasons = [
        context_reason,
        block_reason,
        boundary_reason,
        ema_reason,
        buildup_reason,
        trigger_reason,
        stop_reason,
        obstacle_reason,
    ]
    failures = [
        *([] if context_points else [context_failure]),
        *([] if block_points else [block_failure]),
        *([] if boundary_points else [boundary_failure]),
        *([] if ema_points else [ema_failure]),
        *([] if buildup_points else [buildup_failure]),
        *([] if trigger_points else [trigger_failure]),
        *([] if stop_points else [stop_failure]),
        *([] if obstacle_points else [obstacle_failure]),
    ]
    if status in {"LATE", "FAILED", "REJECT"}:
        failures.append(f"Status is {status}, not an active BB entry candidate")
    if score < 80 and status in {"WAITING", "TRIGGERED"}:
        status = "REJECT"
        failures.append(f"Score {score:.0f} is below required BB threshold 80")

    return _BBSetup(
        direction=direction,
        bb_type=bb_type,
        status=status,
        score=max(0.0, score),
        impulse_start_index=impulse_start,
        impulse_end_index=impulse_end,
        pullback_start_index=pullback_start,
        pullback_end_index=pullback_end,
        block_start_index=block_start,
        block_end_index=block_end,
        block_low=block_low,
        block_high=block_high,
        trigger=trigger,
        stop=stop,
        obstacle=obstacle,
        reasons=[reason for reason in reasons if reason],
        failures=[failure for failure in failures if failure],
    )


def _score_bb_context(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    block_start: int,
    block_end: int,
) -> tuple[float, str, str, str, int | None, int | None, int | None, int | None]:
    type1 = _score_bb_type1_context(candles, ema_values, cfg, direction, block_start, block_end)
    type2 = _score_bb_type2_context(candles, ema_values, cfg, direction, block_start, block_end)
    return type1 if type1[0] >= type2[0] else type2


def _score_bb_type1_context(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    block_start: int,
    block_end: int,
) -> tuple[float, str, str, str, int | None, int | None, int | None, int | None]:
    pullback_start = _dd_pullback_start(candles, direction, block_start)
    if pullback_start is None:
        return 0, "", "No diagonal pullback before the BB block", "Type 1 block at end of diagonal pullback", None, None, None, None
    impulse_start = _dd_impulse_start(candles, direction, pullback_start)
    if impulse_start is None:
        return 0, "", "No impulse before the BB Type 1 pullback", "Type 1 block at end of diagonal pullback", None, None, pullback_start, block_start - 1
    impulse_end = pullback_start
    trend_points, trend_reason, trend_failure = _score_sb_trend(
        candles, ema_values, cfg, direction, impulse_start, impulse_end, block_end
    )
    pullback = candles[pullback_start:block_start]
    pullback_ok = _bb_diagonal_pullback_ok(candles, direction, pullback_start, block_start)
    near_ema = _bb_area_near_ema(candles, ema_values, cfg, direction, block_start, block_end)
    if trend_points and pullback_ok and near_ema:
        return (
            20,
            f"Trend/context: Type 1 block at the end of a diagonal pullback; {trend_reason}",
            "",
            "Type 1 block at end of diagonal pullback",
            impulse_start,
            impulse_end,
            pullback_start,
            block_start - 1,
        )
    failures = []
    if not trend_points:
        failures.append(trend_failure)
    if not pullback_ok:
        failures.append(f"Pullback before block is not diagonal/controlled enough ({len(pullback)} candle(s))")
    if not near_ema:
        failures.append("Block is not near EMA21/support-resistance reaction area")
    return 0, "", "; ".join(failures), "Type 1 block at end of diagonal pullback", impulse_start, impulse_end, pullback_start, block_start - 1


def _score_bb_type2_context(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    block_start: int,
    block_end: int,
) -> tuple[float, str, str, str, int | None, int | None, int | None, int | None]:
    impulse_start = _dd_impulse_start(candles, direction, block_start)
    if impulse_start is None:
        return 0, "", "No impulse before the BB Type 2 horizontal block", "Type 2 horizontal pullback block", None, None, None, None
    impulse_end = block_start
    trend_points, trend_reason, trend_failure = _score_sb_trend(
        candles, ema_values, cfg, direction, impulse_start, impulse_end, block_end
    )
    block = candles[block_start : block_end + 1]
    sideways = _bb_sideways_block_ok(block)
    near_ema = _bb_area_near_ema(candles, ema_values, cfg, direction, block_start, block_end)
    if trend_points and sideways and near_ema:
        return (
            20,
            f"Trend/context: Type 2 horizontal pullback block after impulse; {trend_reason}",
            "",
            "Type 2 horizontal pullback block",
            impulse_start,
            impulse_end,
            block_start,
            block_end,
        )
    failures = []
    if not trend_points:
        failures.append(trend_failure)
    if not sideways:
        failures.append("Block does not look like a horizontal pullback")
    if not near_ema:
        failures.append("Horizontal block is disconnected from EMA21")
    return 0, "", "; ".join(failures), "Type 2 horizontal pullback block", impulse_start, impulse_end, block_start, block_end


def _score_bb_block(
    block: list[Candle],
    candles: list[Candle],
    cfg: VCPConfig,
    block_start: int,
) -> tuple[float, str, str]:
    if len(block) < 4:
        return 0, "", "Block needs more than two candles"
    depth = _base_depth_pct(block)
    overlap = _overlap_ratio(block)
    prior = candles[max(0, block_start - 8) : block_start]
    prior_avg_range = _average_range(prior) if prior else _average_range(block)
    avg_range = _average_range(block)
    small = prior_avg_range <= 0 or avg_range <= prior_avg_range * 0.95
    sideways = _bb_sideways_block_ok(block)
    tight_limit = min(cfg.max_block_range_pct, max(cfg.max_compression_range_pct, 6.0))
    if depth <= tight_limit and overlap >= 0.60 and small and sideways:
        return 20, f"Block is tight and clear: {len(block)} candles, depth {depth:.1f}%, overlap {overlap:.0%}", ""
    return 0, "", f"Block is not tight/clear: {len(block)} candles, depth {depth:.1f}%, overlap {overlap:.0%}, sideways={sideways}"


def _score_bb_signal_boundary(
    block: list[Candle],
    trigger: float,
    cfg: VCPConfig,
    direction: str,
) -> tuple[float, str, str]:
    if direction == "long":
        touches = _boundary_touches(block, trigger, cfg.boundary_touch_tolerance_pct)
        label = "upper"
    else:
        touches = _floor_touches(block, trigger, cfg.boundary_touch_tolerance_pct)
        label = "lower"
    if touches >= 2:
        return 15, f"Signal boundary is clear: {label} block boundary has {touches} touch(es)", ""
    return 0, "", f"Signal boundary is unclear: only {touches} touch(es) on the {label} boundary"


def _score_bb_ema(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    block_start: int,
    block_end: int,
) -> tuple[float, str, str]:
    slope_back = max(0, block_end - cfg.ema_slope_lookback)
    recent_start = max(0, block_end - 24)
    recent_closes = [c.close for c in candles[recent_start : block_end + 1]]
    recent_emas = ema_values[recent_start : block_end + 1]
    block = candles[block_start : block_end + 1]
    block_emas = ema_values[block_start : block_end + 1]
    if direction == "long":
        slope_ok = ema_values[block_end] >= ema_values[slope_back]
        side_ratio = sum(1 for close, ema in zip(recent_closes, recent_emas, strict=True) if close >= ema) / len(recent_closes)
        nearest = min(abs(c.low - ema) / ema * 100 for c, ema in zip(block, block_emas, strict=True) if ema > 0)
    else:
        slope_ok = ema_values[block_end] <= ema_values[slope_back]
        side_ratio = sum(1 for close, ema in zip(recent_closes, recent_emas, strict=True) if close <= ema) / len(recent_closes)
        nearest = min(abs(c.high - ema) / ema * 100 for c, ema in zip(block, block_emas, strict=True) if ema > 0)
    crossings = _ema_crossings(recent_closes, recent_emas)
    if slope_ok and side_ratio >= 0.50 and crossings <= 7 and nearest <= cfg.max_pullback_ema_distance_pct * 1.8:
        return 10, f"EMA21 condition: supports/rejects the block, closest block reaction {nearest:.2f}% from EMA", ""
    return 0, "", f"EMA21 does not support BB: side ratio {side_ratio:.0%}, crossings {crossings}, closest {nearest:.2f}%"


def _score_bb_buildup(block: list[Candle], direction: str) -> tuple[float, str, str]:
    if len(block) < 4:
        return 0, "", "Build-up cannot be confirmed without a real block"
    midpoint = len(block) // 2
    early = block[:midpoint]
    late = block[midpoint:]
    early_range = _average_range(early)
    late_range = _average_range(late)
    if direction == "long":
        signal = max(c.high for c in block)
        late_pressure = mean(c.close for c in late) >= mean(c.close for c in early) * 0.995
        near_signal = mean(signal - c.close for c in late) <= max(early_range, late_range) * 1.5
    else:
        signal = min(c.low for c in block)
        late_pressure = mean(c.close for c in late) <= mean(c.close for c in early) * 1.005
        near_signal = mean(c.close - signal for c in late) <= max(early_range, late_range) * 1.5
    compressing = late_range <= early_range * 1.10 if early_range > 0 else True
    if compressing and late_pressure and near_signal:
        return 10, "Build-up/compression forms near the signal boundary", ""
    return 0, "", "Build-up near the signal boundary is weak"


def _score_bb_trigger(
    latest: Candle,
    trigger: float | None,
    status: str,
    cfg: VCPConfig,
    direction: str,
) -> tuple[float, str, str]:
    if trigger is None or trigger <= 0:
        return 0, "", "Trigger level is missing"
    if status == "TRIGGERED":
        return 10, f"Breakout trigger is clear: latest candle closed beyond {_fmt_price(trigger)}", ""
    if status == "WAITING":
        distance = ((trigger - latest.close) / trigger * 100) if direction == "long" else ((latest.close - trigger) / trigger * 100)
        if 0 <= distance <= cfg.max_boundary_distance_pct:
            return 8, f"Breakout trigger is close: current price is {distance:.2f}% from {_fmt_price(trigger)}", ""
    return 0, "", "Price is not triggering or waiting near the BB boundary"


def _score_bb_stop(
    candles: list[Candle],
    trigger: float | None,
    stop: float | None,
    cfg: VCPConfig,
    direction: str,
    block_start: int,
) -> tuple[float, str, str]:
    if trigger is None or stop is None or trigger <= 0 or stop <= 0:
        return 0, "", "Stop-loss area is missing"
    distance = (trigger - stop) if direction == "long" else (stop - trigger)
    atr = _average_range(candles[max(0, block_start - 14) : block_start] or candles[-14:])
    distance_pct = distance / trigger * 100
    if distance > 0 and (distance_pct <= cfg.max_signal_range_pct or (atr > 0 and distance <= atr * 1.5)):
        atr_text = f", {distance / atr:.2f} ATR" if atr > 0 else ""
        return 10, f"Stop-loss area is logical: {_fmt_price(stop)} is {distance_pct:.2f}% from trigger{atr_text}", ""
    return 0, "", f"Stop-loss is too wide or unclear: {distance_pct:.2f}% from trigger"


def _bb_entry_status(
    latest: Candle,
    trigger: float,
    stop: float,
    block_low: float,
    block_high: float,
    cfg: VCPConfig,
    direction: str,
    include_latest: bool,
) -> str:
    if trigger <= 0 or stop <= 0 or block_high <= block_low:
        return "REJECT"
    if direction == "long":
        if latest.close < block_low:
            return "FAILED"
        if not include_latest and latest.close > trigger and latest.close > latest.open:
            extension = (latest.close - trigger) / trigger * 100
            return "TRIGGERED" if extension <= cfg.max_boundary_distance_pct else "LATE"
        if include_latest:
            distance = (trigger - latest.close) / trigger * 100
            return "WAITING" if 0 <= distance <= cfg.max_boundary_distance_pct else "REJECT"
        return "REJECT"
    if latest.close > block_high:
        return "FAILED"
    if not include_latest and latest.close < trigger and latest.close < latest.open:
        extension = (trigger - latest.close) / trigger * 100
        return "TRIGGERED" if extension <= cfg.max_boundary_distance_pct else "LATE"
    if include_latest:
        distance = (latest.close - trigger) / trigger * 100
        return "WAITING" if 0 <= distance <= cfg.max_boundary_distance_pct else "REJECT"
    return "REJECT"


def _bb_stop(block: list[Candle], direction: str) -> float:
    if direction == "long":
        return min(c.low for c in block)
    return max(c.high for c in block)


def _bb_diagonal_pullback_ok(candles: list[Candle], direction: str, pullback_start: int, block_start: int) -> bool:
    pullback = candles[pullback_start:block_start]
    if len(pullback) < 3 or len(pullback) > 12:
        return False
    ranges = [c.high - c.low for c in pullback]
    if max(ranges) > mean(ranges) * 3.0:
        return False
    net_move = abs(pullback[-1].close - pullback[0].close)
    diagonal = net_move >= mean(ranges) * 0.25
    if direction == "long":
        steps = sum(1 for previous, current in zip(pullback, pullback[1:], strict=False) if current.close <= previous.close)
    else:
        steps = sum(1 for previous, current in zip(pullback, pullback[1:], strict=False) if current.close >= previous.close)
    return diagonal and steps / max(1, len(pullback) - 1) >= 0.40


def _bb_sideways_block_ok(block: list[Candle]) -> bool:
    if len(block) < 4:
        return False
    close_drift = abs(block[-1].close - block[0].close)
    height = max(c.high for c in block) - min(c.low for c in block)
    if height <= 0:
        return False
    return close_drift <= height * 0.55 and _overlap_ratio(block) >= 0.60


def _bb_area_near_ema(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    start: int,
    end: int,
) -> bool:
    segment = candles[start : end + 1]
    emas = ema_values[start : end + 1]
    if not segment or len(segment) != len(emas):
        return False
    if direction == "long":
        nearest = min(abs(c.low - ema) / ema * 100 for c, ema in zip(segment, emas, strict=True) if ema > 0)
    else:
        nearest = min(abs(c.high - ema) / ema * 100 for c, ema in zip(segment, emas, strict=True) if ema > 0)
    return nearest <= cfg.max_pullback_ema_distance_pct * 1.8


def _empty_bb(direction: str, failures: list[str]) -> _BBSetup:
    return _BBSetup(
        direction=direction,
        bb_type="",
        status="REJECT",
        score=0.0,
        impulse_start_index=None,
        impulse_end_index=None,
        pullback_start_index=None,
        pullback_end_index=None,
        block_start_index=None,
        block_end_index=None,
        block_low=None,
        block_high=None,
        trigger=None,
        stop=None,
        obstacle=None,
        reasons=[],
        failures=failures,
    )


def _bb_output_lines(result: _BBSetup, candles: list[Candle]) -> list[str]:
    direction = "Long" if result.direction == "long" else "Short"
    return [
        "Pattern: BB",
        f"Direction: {direction}",
        f"BB Type: {result.bb_type or 'n/a'}",
        f"Status: {result.status}",
        f"Score: {result.score:.0f}",
        f"Trend/context: {_date_range_text(candles, result.impulse_start_index, result.impulse_end_index)}",
        f"EMA21 condition: block is near EMA21 in the expected direction",
        f"Pullback description: {_date_range_text(candles, result.pullback_start_index, result.pullback_end_index)}",
        f"Block description: {_date_range_text(candles, result.block_start_index, result.block_end_index)}; area {_fmt_price(result.block_low)} - {_fmt_price(result.block_high)}",
        f"Signal boundary: {_fmt_price(result.trigger)}",
        f"Current price: {_fmt_price(candles[-1].close)}",
        f"Trigger level: {_fmt_price(result.trigger)}",
        f"Stop-loss area: {_fmt_price(result.stop)}",
        f"Nearest obstacle: {_fmt_price(result.obstacle)}",
        "Reason:",
        *[f"- {reason}" for reason in result.reasons[:8]],
        "Manual review note:",
        "- Confirm trend context, tight block quality, EMA21 support/rejection, signal-boundary break, and stop distance before acting.",
    ]


def _bb_reject_lines(result: _BBSetup) -> list[str]:
    failures = result.failures or ["Reject reason: BB story is incomplete or unclear"]
    return [
        "Pattern: BB",
        "Status: REJECT",
        f"Score: {result.score:.0f}",
        "Reject reason:",
        *[f"- {failure}" for failure in failures[:8]],
    ]


def _bb_status_rank(status: str) -> int:
    return {
        "TRIGGERED": 5,
        "WAITING": 4,
        "LATE": 3,
        "FAILED": 2,
        "REJECT": 1,
    }.get(status, 0)


def _detect_rb_setup(candles: list[Candle], config: VCPConfig | None = None) -> VCPEvidence:
    cfg = config or VCPConfig()
    min_needed = max(cfg.min_history_days, cfg.ema_period + 80)
    if len(candles) < min_needed:
        return _not_qualified(f"RB requires at least {min_needed} candles, got {len(candles)}")

    closes = [c.close for c in candles]
    ema_values = _ema(closes, cfg.ema_period)
    candidates = [
        _score_rb_direction(candles, cfg, ema_values, "long"),
        _score_rb_direction(candles, cfg, ema_values, "short"),
    ]
    result = max(candidates, key=lambda item: (_rb_status_rank(item.status), item.score))
    qualified = (
        result.breakout_type == "TRUE_RB"
        and result.score >= 80
        and result.status in {"WAITING", "TRIGGERED"}
        and not result.failures
    )

    if result.trigger and result.trigger > 0:
        if result.direction == "long":
            distance_to_trigger = ((result.trigger - candles[-1].close) / result.trigger) * 100
        else:
            distance_to_trigger = ((candles[-1].close - result.trigger) / result.trigger) * 100
    else:
        distance_to_trigger = None

    near_reject_reasons = _rb_output_lines(result, candles) if not qualified and result.score >= 60 else []
    return VCPEvidence(
        qualified=qualified,
        status=result.status if qualified else "rejected",
        score=result.score,
        pivot=result.trigger,
        current_close=candles[-1].close,
        distance_to_pivot_pct=distance_to_trigger,
        contractions=[],
        reasons=_rb_output_lines(result, candles) if qualified else near_reject_reasons,
        failures=[] if qualified else _rb_reject_lines(result),
        base_start_index=result.range_start_index,
        base_end_index=len(candles) - 1,
        volume_dry_up_ratio=_window_volume_ratio(candles, max(0, len(candles) - cfg.compression_lookback)),
        prior_uptrend_pct=None,
    )


def _score_rb_direction(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
) -> _RBSetup:
    best = _empty_rb(direction, ["Reject reason: no long range with near-boundary build-up found"])
    n = len(candles)
    max_range_len = min(cfg.max_base_days, 80)
    min_range_len = max(24, cfg.compression_lookback * 2)

    for include_latest in (False, True):
        buildup_end_exclusive = n if include_latest else n - 1
        for buildup_len in range(4, min(11, buildup_end_exclusive - min_range_len) + 1):
            buildup_start = buildup_end_exclusive - buildup_len
            buildup_end = buildup_end_exclusive - 1
            range_end = buildup_start
            for range_len in range(min_range_len, max_range_len + 1):
                range_start = range_end - range_len
                if range_start < 0:
                    continue
                candidate = _build_rb_candidate(
                    candles,
                    cfg,
                    ema_values,
                    direction,
                    range_start,
                    range_end - 1,
                    buildup_start,
                    buildup_end,
                    include_latest=include_latest,
                )
                if (_rb_status_rank(candidate.status), candidate.score) > (_rb_status_rank(best.status), best.score):
                    best = candidate
    return best


def _build_rb_candidate(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
    range_start: int,
    range_end: int,
    buildup_start: int,
    buildup_end: int,
    *,
    include_latest: bool,
) -> _RBSetup:
    range_candles = candles[range_start : range_end + 1]
    buildup = candles[buildup_start : buildup_end + 1]
    upper = max(c.high for c in range_candles)
    lower = min(c.low for c in range_candles)
    boundary = upper if direction == "long" else lower
    buildup_low = min(c.low for c in buildup)
    buildup_high = max(c.high for c in buildup)
    stop = buildup_low if direction == "long" else buildup_high

    range_points, range_reason, range_failure = _score_rb_range(range_candles, cfg)
    boundary_points, boundary_reason, boundary_failure = _score_rb_boundaries(range_candles, upper, lower, cfg)
    ema_points, ema_reason, ema_failure = _score_rb_ema_context(candles, ema_values, cfg, range_start, range_end)
    buildup_points, buildup_reason, buildup_failure = _score_rb_buildup(buildup, cfg)
    near_points, near_reason, near_failure, breakout_type = _score_rb_buildup_near_boundary(
        buildup, upper, lower, cfg, direction
    )
    status = _rb_entry_status(candles[-1], boundary, stop, upper, lower, cfg, direction, include_latest)
    trigger_points, trigger_reason, trigger_failure = _score_rb_trigger(candles[-1], boundary, status, cfg, direction)
    stop_points, stop_reason, stop_failure = _score_rb_stop(candles, boundary, stop, cfg, direction, buildup_start)

    if not buildup_points:
        breakout_type = "NO_BUILDUP"
    if range_points == 0:
        breakout_type = "NOT_RANGE"
    if status == "LATE":
        breakout_type = "LATE"

    score = range_points + boundary_points + ema_points + buildup_points + near_points + trigger_points + stop_points
    if breakout_type == "BAIT_TEASE_BREAK":
        score = min(score, 70)
        status = "WATCH_BAIT_BREAK"
    if breakout_type in {"NO_BUILDUP", "FALSE_BREAK"}:
        score = min(score, 50)
        status = "REJECT"
    if breakout_type == "NOT_RANGE":
        score = min(score, 45)
        status = "REJECT"

    reasons = [
        range_reason,
        boundary_reason,
        ema_reason,
        buildup_reason,
        near_reason,
        trigger_reason,
        stop_reason,
    ]
    failures = [
        *([] if range_points else [range_failure]),
        *([] if boundary_points else [boundary_failure]),
        *([] if ema_points else [ema_failure]),
        *([] if buildup_points else [buildup_failure]),
        *([] if near_points else [near_failure]),
        *([] if trigger_points else [trigger_failure]),
        *([] if stop_points else [stop_failure]),
    ]
    if status in {"LATE", "FAILED", "REJECT"}:
        failures.append(f"Status is {status}, not an active RB entry candidate")
    if status == "WATCH_BAIT_BREAK":
        failures.append("Build-up exists but is too far from the range boundary")
    if score < 80 and status in {"WAITING", "TRIGGERED"}:
        status = "REJECT"
        failures.append(f"Score {score:.0f} is below required RB threshold 80")

    return _RBSetup(
        direction=direction,
        status=status,
        score=max(0.0, score),
        breakout_type=breakout_type,
        range_start_index=range_start,
        range_end_index=range_end,
        upper_boundary=upper,
        lower_boundary=lower,
        buildup_start_index=buildup_start,
        buildup_end_index=buildup_end,
        buildup_low=buildup_low,
        buildup_high=buildup_high,
        trigger=boundary,
        stop=stop,
        reasons=[reason for reason in reasons if reason],
        failures=[failure for failure in failures if failure],
    )


def _score_rb_range(range_candles: list[Candle], cfg: VCPConfig) -> tuple[float, str, str]:
    if len(range_candles) < 24:
        return 0, "", f"Range is too short: {len(range_candles)} candles"
    upper = max(c.high for c in range_candles)
    lower = min(c.low for c in range_candles)
    height = upper - lower
    depth = _base_depth_pct(range_candles)
    close_drift = abs(range_candles[-1].close - range_candles[0].close)
    sideways = height > 0 and close_drift <= height * 0.65
    if cfg.min_range_depth_pct <= depth <= min(cfg.max_base_depth_pct, 35.0) and sideways:
        return 20, f"Long range is clear: {len(range_candles)} candles, depth {depth:.1f}%, close drift {_fmt_price(close_drift)}", ""
    return 0, "", f"Range is unclear: {len(range_candles)} candles, depth {depth:.1f}%, sideways={sideways}"


def _score_rb_boundaries(
    range_candles: list[Candle],
    upper: float,
    lower: float,
    cfg: VCPConfig,
) -> tuple[float, str, str]:
    upper_touches = _boundary_touches(range_candles, upper, cfg.boundary_touch_tolerance_pct)
    lower_touches = _floor_touches(range_candles, lower, cfg.boundary_touch_tolerance_pct)
    min_touches = max(3, cfg.min_boundary_touches)
    if upper_touches >= min_touches and lower_touches >= min_touches:
        return 15, f"Boundaries are clear: upper {_fmt_price(upper)} ({upper_touches} touches), lower {_fmt_price(lower)} ({lower_touches} touches)", ""
    return 0, "", f"Range boundaries are unclear: upper touches {upper_touches}, lower touches {lower_touches}"


def _score_rb_ema_context(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    range_start: int,
    range_end: int,
) -> tuple[float, str, str]:
    closes = [c.close for c in candles[range_start : range_end + 1]]
    emas = ema_values[range_start : range_end + 1]
    if len(closes) < 10 or len(closes) != len(emas):
        return 0, "", "EMA21 range context cannot be measured"
    crossings = _ema_crossings(closes, emas)
    avg_close = mean(closes)
    ema_slope_pct = abs(emas[-1] - emas[0]) / avg_close * 100 if avg_close > 0 else 100
    if crossings >= 4 or ema_slope_pct <= min(cfg.max_retest_distance_pct, 1.0):
        return 10, f"EMA21 confirms sideways context: {crossings} crossing(s), EMA drift {ema_slope_pct:.2f}%", ""
    return 0, "", f"EMA21 does not look sideways enough: {crossings} crossing(s), EMA drift {ema_slope_pct:.2f}%"


def _score_rb_buildup(buildup: list[Candle], cfg: VCPConfig) -> tuple[float, str, str]:
    if len(buildup) < 4:
        return 0, "", f"Build-up needs several candles, got {len(buildup)}"
    depth = _base_depth_pct(buildup)
    overlap = _overlap_ratio(buildup)
    if depth <= cfg.max_block_range_pct and overlap >= 0.60 and _bb_sideways_block_ok(buildup):
        return 15, f"Build-up exists: {len(buildup)} tight overlapping candles, depth {depth:.1f}%, overlap {overlap:.0%}", ""
    return 0, "", f"Build-up is not tight enough: depth {depth:.1f}%, overlap {overlap:.0%}"


def _score_rb_buildup_near_boundary(
    buildup: list[Candle],
    upper: float,
    lower: float,
    cfg: VCPConfig,
    direction: str,
) -> tuple[float, str, str, str]:
    range_height = upper - lower
    boundary = upper if direction == "long" else lower
    if range_height <= 0 or boundary <= 0:
        return 0, "", "Boundary distance cannot be measured", "UNCLEAR"
    tolerance = max(boundary * cfg.max_retest_distance_pct / 100, range_height * 0.18)
    if direction == "long":
        empty_space = upper - max(c.high for c in buildup)
        in_zone = min(c.low for c in buildup) >= lower + range_height * 0.50
    else:
        empty_space = min(c.low for c in buildup) - lower
        in_zone = max(c.high for c in buildup) <= upper - range_height * 0.50
    if empty_space < 0:
        empty_space = 0
    distance_pct = empty_space / boundary * 100
    if empty_space <= tolerance and in_zone:
        return 20, f"Build-up is tight against boundary: empty space {distance_pct:.2f}%", "", "TRUE_RB"
    if empty_space <= range_height * 0.60:
        return 0, "", f"Build-up exists but is too far from boundary: empty space {distance_pct:.2f}%", "BAIT_TEASE_BREAK"
    return 0, "", f"No useful near-boundary build-up; empty space {distance_pct:.2f}%", "FALSE_BREAK"


def _rb_entry_status(
    latest: Candle,
    boundary: float,
    stop: float,
    upper: float,
    lower: float,
    cfg: VCPConfig,
    direction: str,
    include_latest: bool,
) -> str:
    if boundary <= 0 or stop <= 0:
        return "REJECT"
    range_height = upper - lower
    if range_height <= 0:
        return "REJECT"
    if direction == "long":
        if latest.close <= lower + range_height * 0.35:
            return "FAILED"
        if not include_latest and latest.close > boundary and latest.close > latest.open:
            extension = (latest.close - boundary) / boundary * 100
            return "TRIGGERED" if extension <= cfg.max_boundary_distance_pct else "LATE"
        if include_latest:
            distance = (boundary - latest.close) / boundary * 100
            return "WAITING" if 0 <= distance <= cfg.max_boundary_distance_pct else "REJECT"
        return "REJECT"
    if latest.close >= upper - range_height * 0.35:
        return "FAILED"
    if not include_latest and latest.close < boundary and latest.close < latest.open:
        extension = (boundary - latest.close) / boundary * 100
        return "TRIGGERED" if extension <= cfg.max_boundary_distance_pct else "LATE"
    if include_latest:
        distance = (latest.close - boundary) / boundary * 100
        return "WAITING" if 0 <= distance <= cfg.max_boundary_distance_pct else "REJECT"
    return "REJECT"


def _score_rb_trigger(
    latest: Candle,
    boundary: float | None,
    status: str,
    cfg: VCPConfig,
    direction: str,
) -> tuple[float, str, str]:
    if boundary is None or boundary <= 0:
        return 0, "", "Breakout boundary is missing"
    if status == "TRIGGERED":
        return 10, f"Breakout trigger is clear: latest candle closed beyond {_fmt_price(boundary)}", ""
    if status == "WAITING":
        distance = ((boundary - latest.close) / boundary * 100) if direction == "long" else ((latest.close - boundary) / boundary * 100)
        if 0 <= distance <= cfg.max_boundary_distance_pct:
            return 8, f"Breakout trigger is close: current price is {distance:.2f}% from {_fmt_price(boundary)}", ""
    return 0, "", "Breakout is not triggered or close enough"


def _score_rb_stop(
    candles: list[Candle],
    boundary: float | None,
    stop: float | None,
    cfg: VCPConfig,
    direction: str,
    buildup_start: int,
) -> tuple[float, str, str]:
    if boundary is None or stop is None or boundary <= 0 or stop <= 0:
        return 0, "", "Stop-loss area is missing"
    distance = (boundary - stop) if direction == "long" else (stop - boundary)
    atr = _average_range(candles[max(0, buildup_start - 14) : buildup_start] or candles[-14:])
    distance_pct = distance / boundary * 100
    if distance > 0 and distance_pct <= cfg.max_signal_range_pct and (atr <= 0 or distance <= atr * 2.0):
        atr_text = f", {distance / atr:.2f} ATR" if atr > 0 else ""
        return 10, f"Stop-loss area is logical: {_fmt_price(stop)} is {distance_pct:.2f}% from boundary{atr_text}", ""
    return 0, "", f"Stop-loss is too wide: {distance_pct:.2f}% from boundary"


def _empty_rb(direction: str, failures: list[str]) -> _RBSetup:
    return _RBSetup(
        direction=direction,
        status="REJECT",
        score=0.0,
        breakout_type="UNCLEAR",
        range_start_index=None,
        range_end_index=None,
        upper_boundary=None,
        lower_boundary=None,
        buildup_start_index=None,
        buildup_end_index=None,
        buildup_low=None,
        buildup_high=None,
        trigger=None,
        stop=None,
        reasons=[],
        failures=failures,
    )


def _rb_output_lines(result: _RBSetup, candles: list[Candle]) -> list[str]:
    direction = "Long" if result.direction == "long" else "Short"
    boundary = result.upper_boundary if result.direction == "long" else result.lower_boundary
    empty_space = _rb_empty_space_text(result)
    return [
        "Pattern: RB",
        f"Direction: {direction}",
        f"Status: {result.status}",
        f"Score: {result.score:.0f}",
        f"Range description: {_date_range_text(candles, result.range_start_index, result.range_end_index)}",
        f"Upper range boundary: {_fmt_price(result.upper_boundary)}",
        f"Lower range boundary: {_fmt_price(result.lower_boundary)}",
        "EMA21 condition: flat/crossed EMA21 range context",
        f"Build-up description: {_date_range_text(candles, result.buildup_start_index, result.buildup_end_index)}; area {_fmt_price(result.buildup_low)} - {_fmt_price(result.buildup_high)}",
        f"Distance from build-up to boundary: {empty_space}",
        f"Breakout boundary: {_fmt_price(boundary)}",
        f"Trigger level: {_fmt_price(result.trigger)}",
        f"Current price: {_fmt_price(candles[-1].close)}",
        f"Stop-loss area: {_fmt_price(result.stop)}",
        "Breakout type:",
        f"- {result.breakout_type}",
        "Reason:",
        *[f"- {reason}" for reason in result.reasons[:8]],
        "Manual review note:",
        "- Confirm the long range boundaries, flat/crossed EMA21, near-boundary build-up, breakout close, and stop distance before acting.",
    ]


def _rb_reject_lines(result: _RBSetup) -> list[str]:
    failures = result.failures or ["Reject reason: RB story is incomplete or unclear"]
    if result.status == "WATCH_BAIT_BREAK":
        return [
            "Pattern: RB",
            "Status: WATCH_BAIT_BREAK",
            f"Score: {result.score:.0f}",
            "Breakout type:",
            "BAIT_TEASE_BREAK",
            "Reason:",
            "- Build-up exists but is too far from the boundary.",
            "- Empty space remains between build-up and range boundary.",
            "- First breakout is unsafe.",
            "- Wait for retest, tighter build-up near boundary, or later continuation.",
            "Manual review note:",
            "- Do not enter now. Keep watching for a better RB or ARB.",
        ]
    return [
        "Pattern: RB",
        "Status: REJECT",
        f"Score: {result.score:.0f}",
        "Breakout type:",
        f"- {result.breakout_type}",
        "Reject reason:",
        *[f"- {failure}" for failure in failures[:8]],
    ]


def _rb_empty_space_text(result: _RBSetup) -> str:
    if result.trigger is None or result.upper_boundary is None or result.lower_boundary is None:
        return "n/a"
    if result.direction == "long" and result.buildup_high is not None:
        empty = max(0.0, result.upper_boundary - result.buildup_high)
        return f"{_fmt_price(empty)}"
    if result.direction == "short" and result.buildup_low is not None:
        empty = max(0.0, result.buildup_low - result.lower_boundary)
        return f"{_fmt_price(empty)}"
    return "n/a"


def _rb_status_rank(status: str) -> int:
    return {
        "TRIGGERED": 6,
        "WAITING": 5,
        "WATCH_BAIT_BREAK": 4,
        "LATE": 3,
        "FAILED": 2,
        "REJECT": 1,
    }.get(status, 0)


def _detect_irb_setup(candles: list[Candle], config: VCPConfig | None = None) -> VCPEvidence:
    cfg = config or VCPConfig()
    min_needed = max(cfg.min_history_days, cfg.ema_period + 80)
    if len(candles) < min_needed:
        return _not_qualified(f"IRB requires at least {min_needed} candles, got {len(candles)}")

    closes = [c.close for c in candles]
    ema_values = _ema(closes, cfg.ema_period)
    candidates = [
        _score_irb_direction(candles, cfg, ema_values, "long"),
        _score_irb_direction(candles, cfg, ema_values, "short"),
    ]
    result = max(candidates, key=lambda item: (_irb_status_rank(item.status), item.score))
    qualified = result.score >= 80 and result.status in {"WAITING", "TRIGGERED"} and not result.failures

    if result.trigger and result.trigger > 0:
        if result.direction == "long":
            distance_to_trigger = ((result.trigger - candles[-1].close) / result.trigger) * 100
        else:
            distance_to_trigger = ((candles[-1].close - result.trigger) / result.trigger) * 100
    else:
        distance_to_trigger = None

    near_reject_reasons = _irb_output_lines(result, candles) if not qualified and result.score >= 60 else []
    return VCPEvidence(
        qualified=qualified,
        status=result.status if qualified else "rejected",
        score=result.score,
        pivot=result.trigger,
        current_close=candles[-1].close,
        distance_to_pivot_pct=distance_to_trigger,
        contractions=[],
        reasons=_irb_output_lines(result, candles) if qualified else near_reject_reasons,
        failures=[] if qualified else _irb_reject_lines(result),
        base_start_index=result.range_start_index,
        base_end_index=len(candles) - 1,
        volume_dry_up_ratio=_window_volume_ratio(candles, max(0, len(candles) - cfg.compression_lookback)),
        prior_uptrend_pct=None,
    )


def _score_irb_direction(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
) -> _IRBSetup:
    best = _empty_irb(direction, ["Reject reason: no long range with a tradable inner block found"])
    n = len(candles)
    max_range_len = min(cfg.max_base_days, 90)
    min_range_len = max(24, cfg.compression_lookback * 2)

    for include_latest in (False, True):
        block_end_exclusive = n if include_latest else n - 1
        for block_len in range(4, min(11, block_end_exclusive - min_range_len) + 1):
            block_start = block_end_exclusive - block_len
            block_end = block_end_exclusive - 1
            range_end = block_start - 1
            for range_len in range(min_range_len, max_range_len + 1):
                range_start = range_end - range_len + 1
                if range_start < 0:
                    continue
                candidate = _build_irb_candidate(
                    candles,
                    cfg,
                    ema_values,
                    direction,
                    range_start,
                    range_end,
                    block_start,
                    block_end,
                    include_latest=include_latest,
                )
                if (_irb_status_rank(candidate.status), candidate.score) > (
                    _irb_status_rank(best.status),
                    best.score,
                ):
                    best = candidate
    return best


def _build_irb_candidate(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
    range_start: int,
    range_end: int,
    block_start: int,
    block_end: int,
    *,
    include_latest: bool,
) -> _IRBSetup:
    range_candles = candles[range_start : range_end + 1]
    block = candles[block_start : block_end + 1]
    upper = max(c.high for c in range_candles)
    lower = min(c.low for c in range_candles)
    height = upper - lower
    block_low = min(c.low for c in block)
    block_high = max(c.high for c in block)
    trigger = block_high if direction == "long" else block_low
    target = upper if direction == "long" else lower
    stop = block_low if direction == "long" else block_high

    range_points, range_reason, range_failure = _score_rb_range(range_candles, cfg)
    boundary_points, boundary_reason, boundary_failure = _score_rb_boundaries(range_candles, upper, lower, cfg)
    ema_points, ema_reason, ema_failure = _score_rb_ema_context(candles, ema_values, cfg, range_start, range_end)
    block_points, block_reason, block_failure = _score_irb_inner_block(block, upper, lower, cfg)
    direction_points, direction_reason, direction_failure = _score_irb_directional_clue(
        candles, ema_values, direction, block_start, block_end, upper, lower
    )
    status = _irb_entry_status(candles[-1], trigger, target, stop, upper, lower, cfg, direction, include_latest)
    trigger_points, trigger_reason, trigger_failure = _score_irb_trigger(
        candles[-1], trigger, status, cfg, direction
    )
    rr_points, rr_reason, rr_failure, risk_reward = _score_irb_rr(trigger, target, stop, cfg, direction)
    stop_points, stop_reason, stop_failure = _score_irb_stop(candles, trigger, stop, cfg, direction, block_start)
    irb_type = _irb_type(direction, block_low, block_high, upper, lower)

    score = (
        range_points
        + boundary_points
        + ema_points
        + block_points
        + direction_points
        + trigger_points
        + rr_points
        + stop_points
    )
    failures = [
        *([] if range_points else [range_failure]),
        *([] if boundary_points else [boundary_failure]),
        *([] if ema_points else [ema_failure]),
        *([] if block_points else [block_failure]),
        *([] if direction_points else [direction_failure]),
        *([] if trigger_points else [trigger_failure]),
        *([] if rr_points else [rr_failure]),
        *([] if stop_points else [stop_failure]),
    ]

    if range_points == 0:
        score = min(score, 45)
    if block_points == 0:
        score = min(score, 55)
    if rr_points == 0:
        score = min(score, 74)
    if status in {"LATE", "FAILED", "REJECT"}:
        failures.append(f"Status is {status}, not an active IRB entry candidate")
    if score < 80 and status in {"WAITING", "TRIGGERED"}:
        status = "REJECT"
        failures.append(f"Score {score:.0f} is below required IRB threshold 80")

    reasons = [
        range_reason,
        boundary_reason,
        ema_reason,
        block_reason,
        direction_reason,
        trigger_reason,
        rr_reason,
        stop_reason,
    ]
    return _IRBSetup(
        direction=direction,
        irb_type=irb_type,
        status=status,
        score=max(0.0, score),
        range_start_index=range_start,
        range_end_index=range_end,
        upper_boundary=upper,
        lower_boundary=lower,
        block_start_index=block_start,
        block_end_index=block_end,
        block_low=block_low,
        block_high=block_high,
        trigger=trigger,
        target=target,
        stop=stop,
        risk_reward=risk_reward,
        reasons=[reason for reason in reasons if reason],
        failures=[failure for failure in failures if failure],
    )


def _score_irb_inner_block(
    block: list[Candle],
    upper: float,
    lower: float,
    cfg: VCPConfig,
) -> tuple[float, str, str]:
    if len(block) < 4:
        return 0, "", f"Inner block needs several candles, got {len(block)}"
    height = upper - lower
    if height <= 0:
        return 0, "", "Range height cannot be measured"
    block_low = min(c.low for c in block)
    block_high = max(c.high for c in block)
    block_height = block_high - block_low
    inside = block_low > lower + height * 0.08 and block_high < upper - height * 0.08
    depth = _base_depth_pct(block)
    overlap = _overlap_ratio(block)
    if inside and block_height <= height * 0.45 and depth <= cfg.max_block_range_pct and overlap >= 0.55:
        return 20, f"Inner buildup/block is clear: {len(block)} candles, depth {depth:.1f}%, overlap {overlap:.0%}", ""
    return 0, "", f"Inner block is not clean/inside enough: depth {depth:.1f}%, overlap {overlap:.0%}"


def _score_irb_directional_clue(
    candles: list[Candle],
    ema_values: list[float],
    direction: str,
    block_start: int,
    block_end: int,
    upper: float,
    lower: float,
) -> tuple[float, str, str]:
    block = candles[block_start : block_end + 1]
    block_mid = (max(c.high for c in block) + min(c.low for c in block)) / 2
    ema_mid = mean(ema_values[block_start : block_end + 1])
    height = upper - lower
    position = (block_mid - lower) / height if height > 0 else 0.5
    closes = [c.close for c in block]
    pressing_up = closes[-1] >= max(closes[: max(1, len(closes) - 1)])
    pressing_down = closes[-1] <= min(closes[: max(1, len(closes) - 1)])
    if direction == "long" and (block_mid >= ema_mid or pressing_up or position <= 0.35):
        return 10, "Direction is logical: inner block favors a move toward the upper range boundary", ""
    if direction == "short" and (block_mid <= ema_mid or pressing_down or position >= 0.65):
        return 10, "Direction is logical: inner block favors a move toward the lower range boundary", ""
    return 0, "", "Inner block direction is unclear versus EMA21 and range position"


def _irb_entry_status(
    latest: Candle,
    trigger: float,
    target: float,
    stop: float,
    upper: float,
    lower: float,
    cfg: VCPConfig,
    direction: str,
    include_latest: bool,
) -> str:
    if min(trigger, target, stop, upper, lower) <= 0:
        return "REJECT"
    height = upper - lower
    if height <= 0:
        return "REJECT"
    if direction == "long":
        if latest.close <= stop:
            return "FAILED"
        if latest.close >= target - height * 0.10:
            return "LATE"
        if not include_latest and latest.close > trigger and latest.close > latest.open:
            extension = (latest.close - trigger) / trigger * 100
            return "TRIGGERED" if extension <= cfg.max_boundary_distance_pct else "LATE"
        if include_latest:
            distance = (trigger - latest.close) / trigger * 100
            return "WAITING" if 0 <= distance <= cfg.max_boundary_distance_pct else "REJECT"
        return "REJECT"
    if latest.close >= stop:
        return "FAILED"
    if latest.close <= target + height * 0.10:
        return "LATE"
    if not include_latest and latest.close < trigger and latest.close < latest.open:
        extension = (trigger - latest.close) / trigger * 100
        return "TRIGGERED" if extension <= cfg.max_boundary_distance_pct else "LATE"
    if include_latest:
        distance = (latest.close - trigger) / trigger * 100
        return "WAITING" if 0 <= distance <= cfg.max_boundary_distance_pct else "REJECT"
    return "REJECT"


def _score_irb_trigger(
    latest: Candle,
    trigger: float | None,
    status: str,
    cfg: VCPConfig,
    direction: str,
) -> tuple[float, str, str]:
    if trigger is None or trigger <= 0:
        return 0, "", "Inner block trigger level is missing"
    if status == "TRIGGERED":
        return 10, f"Break trigger is clear: latest candle closed beyond inner block {_fmt_price(trigger)}", ""
    if status == "WAITING":
        distance = ((trigger - latest.close) / trigger * 100) if direction == "long" else ((latest.close - trigger) / trigger * 100)
        if 0 <= distance <= cfg.max_boundary_distance_pct:
            return 8, f"Break trigger is close: current price is {distance:.2f}% from {_fmt_price(trigger)}", ""
    return 0, "", "Inner block break is not triggered or close enough"


def _score_irb_rr(
    trigger: float,
    target: float,
    stop: float,
    cfg: VCPConfig,
    direction: str,
) -> tuple[float, str, str, float | None]:
    risk = (trigger - stop) if direction == "long" else (stop - trigger)
    reward = (target - trigger) if direction == "long" else (trigger - target)
    if risk <= 0 or reward <= 0 or trigger <= 0:
        return 0, "", "Risk/reward to target boundary cannot be measured", None
    risk_reward = reward / risk
    risk_pct = risk / trigger * 100
    if risk_reward >= 1.2 and risk_pct <= cfg.max_signal_range_pct:
        return 10, f"Risk/reward to boundary is reasonable: {risk_reward:.2f}R with {risk_pct:.2f}% risk", "", risk_reward
    return 0, "", f"Risk/reward to boundary is poor: {risk_reward:.2f}R with {risk_pct:.2f}% risk", risk_reward


def _score_irb_stop(
    candles: list[Candle],
    trigger: float | None,
    stop: float | None,
    cfg: VCPConfig,
    direction: str,
    block_start: int,
) -> tuple[float, str, str]:
    if trigger is None or stop is None or trigger <= 0 or stop <= 0:
        return 0, "", "Stop-loss area is missing"
    risk = (trigger - stop) if direction == "long" else (stop - trigger)
    atr = _average_range(candles[max(0, block_start - 14) : block_start] or candles[-14:])
    risk_pct = risk / trigger * 100
    if risk > 0 and risk_pct <= cfg.max_signal_range_pct and (atr <= 0 or risk <= atr * 2.0):
        atr_text = f", {risk / atr:.2f} ATR" if atr > 0 else ""
        return 5, f"Stop-loss is logical behind the inner block: {_fmt_price(stop)} ({risk_pct:.2f}% risk{atr_text})", ""
    return 0, "", f"Stop-loss is too wide for the inner block: {risk_pct:.2f}% risk"


def _irb_type(direction: str, block_low: float, block_high: float, upper: float, lower: float) -> str:
    height = upper - lower
    if height <= 0:
        return "Type 2 middle block to boundary"
    block_mid = (block_low + block_high) / 2
    position = (block_mid - lower) / height
    if direction == "long" and position <= 0.35:
        return "Type 1 failed boundary pressure"
    if direction == "short" and position >= 0.65:
        return "Type 1 failed boundary pressure"
    if (direction == "long" and position >= 0.55) or (direction == "short" and position <= 0.45):
        return "Type 3 inner break with possible full range breakout"
    return "Type 2 middle block to boundary"


def _empty_irb(direction: str, failures: list[str]) -> _IRBSetup:
    return _IRBSetup(
        direction=direction,
        irb_type="",
        status="REJECT",
        score=0.0,
        range_start_index=None,
        range_end_index=None,
        upper_boundary=None,
        lower_boundary=None,
        block_start_index=None,
        block_end_index=None,
        block_low=None,
        block_high=None,
        trigger=None,
        target=None,
        stop=None,
        risk_reward=None,
        reasons=[],
        failures=failures,
    )


def _irb_output_lines(result: _IRBSetup, candles: list[Candle]) -> list[str]:
    direction = "Long" if result.direction == "long" else "Short"
    rr_text = f"{result.risk_reward:.2f}R to target boundary" if result.risk_reward is not None else "n/a"
    return [
        "Pattern: IRB",
        f"Direction: {direction}",
        f"IRB Type: {result.irb_type or 'n/a'}",
        f"Status: {result.status}",
        f"Score: {result.score:.0f}",
        f"Range description: {_date_range_text(candles, result.range_start_index, result.range_end_index)}",
        f"Upper range boundary: {_fmt_price(result.upper_boundary)}",
        f"Lower range boundary: {_fmt_price(result.lower_boundary)}",
        "EMA21 condition: flat/crossed EMA21 confirms range context",
        f"Inner buildup/block description: {_date_range_text(candles, result.block_start_index, result.block_end_index)}; area {_fmt_price(result.block_low)} - {_fmt_price(result.block_high)}",
        f"Block position relative to EMA21: direction judged from block/EMA/range position",
        f"Trigger level: {_fmt_price(result.trigger)}",
        f"Current price: {_fmt_price(candles[-1].close)}",
        f"Target boundary: {_fmt_price(result.target)}",
        f"Stop-loss area: {_fmt_price(result.stop)}",
        f"Risk/reward comment: {rr_text}",
        "Reason:",
        *[f"- {reason}" for reason in result.reasons[:8]],
        "Manual review note:",
        "- Confirm this is a long sideways range, entry comes from an inner block, target is the range boundary, and risk/reward remains acceptable.",
    ]


def _irb_reject_lines(result: _IRBSetup) -> list[str]:
    failures = result.failures or ["Reject reason: IRB story is incomplete or unclear"]
    return [
        "Pattern: IRB",
        "Status: REJECT",
        f"Score: {result.score:.0f}",
        "Reject reason:",
        *[f"- {failure}" for failure in failures[:8]],
    ]


def _irb_status_rank(status: str) -> int:
    return {
        "TRIGGERED": 5,
        "WAITING": 4,
        "LATE": 3,
        "FAILED": 2,
        "REJECT": 1,
    }.get(status, 0)


def _date_text(candles: list[Candle], index: int | None) -> str:
    if index is None:
        return "waiting"
    return candles[index].datetime.date().isoformat()


def _detect_dd_setup(candles: list[Candle], config: VCPConfig | None = None) -> VCPEvidence:
    cfg = config or VCPConfig()
    min_needed = max(cfg.min_history_days, cfg.ema_period + 50)
    if len(candles) < min_needed:
        return _not_qualified(f"DD requires at least {min_needed} candles, got {len(candles)}")

    closes = [c.close for c in candles]
    ema_values = _ema(closes, cfg.ema_period)
    candidates = [
        _score_dd_direction(candles, cfg, ema_values, "long"),
        _score_dd_direction(candles, cfg, ema_values, "short"),
    ]
    result = max(candidates, key=lambda item: (_dd_status_rank(item.status), item.score))
    qualified = result.score >= 80 and result.status in {"WAITING", "TRIGGERED"} and not result.failures

    if result.signal and result.signal > 0:
        if result.direction == "long":
            distance_to_signal = ((result.signal - candles[-1].close) / result.signal) * 100
        else:
            distance_to_signal = ((candles[-1].close - result.signal) / result.signal) * 100
    else:
        distance_to_signal = None

    return VCPEvidence(
        qualified=qualified,
        status=result.status if qualified else "rejected",
        score=result.score,
        pivot=result.signal,
        current_close=candles[-1].close,
        distance_to_pivot_pct=distance_to_signal,
        contractions=[],
        reasons=_dd_output_lines(result, candles) if qualified else [],
        failures=[] if qualified else _dd_reject_lines(result),
        base_start_index=result.impulse_start_index,
        base_end_index=len(candles) - 1,
        volume_dry_up_ratio=_window_volume_ratio(candles, max(0, len(candles) - cfg.compression_lookback)),
        prior_uptrend_pct=None,
    )


def _score_dd_direction(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
) -> _DDSetup:
    best = _empty_dd(direction, ["Reject reason: no active 2+ doji cluster near EMA21 found"])
    n = len(candles)
    for cluster_end in (n - 2, n - 1):
        if cluster_end < 5:
            continue
        for cluster_len in range(2, 5):
            cluster_start = cluster_end - cluster_len + 1
            if cluster_start < 10:
                continue
            cluster = candles[cluster_start : cluster_end + 1]
            cluster_score, cluster_reasons, cluster_failures = _score_dd_cluster(
                cluster, candles, ema_values, cfg, direction, cluster_start
            )
            if cluster_score <= 0:
                candidate = _empty_dd(direction, cluster_failures)
                if candidate.score > best.score:
                    best = candidate
                continue

            pullback_start = _dd_pullback_start(candles, direction, cluster_start)
            if pullback_start is None:
                candidate = _empty_dd(direction, ["Reject reason: no single clean pullback wave before the doji cluster"])
                if candidate.score > best.score:
                    best = candidate
                continue
            pullback = candles[pullback_start:cluster_start]
            impulse_start = _dd_impulse_start(candles, direction, pullback_start)
            if impulse_start is None:
                candidate = _empty_dd(direction, ["Reject reason: no clear impulse wave before the pullback"])
                if candidate.score > best.score:
                    best = candidate
                continue

            impulse_end = pullback_start
            trend_points, trend_reason, trend_failure = _score_dd_trend(
                candles, ema_values, cfg, direction, impulse_start, impulse_end, cluster_end
            )
            ema_points, ema_reason, ema_failure = _score_dd_ema(
                candles, ema_values, cfg, direction, cluster_start, cluster_end
            )
            pullback_points, pullback_reason, pullback_failure = _score_dd_pullback(
                candles, direction, impulse_start, impulse_end, pullback_start, cluster_start
            )
            ema_reach_points, ema_reach_reason, ema_reach_failure = _score_dd_pullback_reaches_ema(
                candles, ema_values, cfg, direction, pullback_start, cluster_end
            )

            signal = max(c.high for c in cluster) if direction == "long" else min(c.low for c in cluster)
            stop = min(c.low for c in cluster) if direction == "long" else max(c.high for c in cluster)
            status = _dd_entry_status(candles[-1], signal, stop, cfg, direction, cluster_end)
            trigger_points, trigger_reason, trigger_failure = _score_dd_signal(
                candles[-1], signal, status, cfg, direction
            )
            stop_points, stop_reason, stop_failure = _score_dd_stop(
                candles, signal, stop, cfg, direction, cluster_start
            )
            obstacle = _nearest_dd_obstacle(candles, signal, direction, impulse_start, cluster_start)
            obstacle_points, obstacle_reason, obstacle_failure = _score_dd_obstacle(
                candles, signal, obstacle, direction, cluster_start
            )

            score = (
                trend_points
                + ema_points
                + pullback_points
                + ema_reach_points
                + cluster_score
                + trigger_points
                + stop_points
                + obstacle_points
            )
            reasons = [
                trend_reason,
                ema_reason,
                pullback_reason,
                ema_reach_reason,
                *cluster_reasons,
                trigger_reason,
                stop_reason,
                obstacle_reason,
            ]
            failures = [
                *([] if trend_points else [trend_failure]),
                *([] if ema_points else [ema_failure]),
                *([] if pullback_points else [pullback_failure]),
                *([] if ema_reach_points else [ema_reach_failure]),
                *cluster_failures,
                *([] if trigger_points else [trigger_failure]),
                *([] if stop_points else [stop_failure]),
                *([] if obstacle_points else [obstacle_failure]),
            ]
            if status in {"LATE", "FAILED", "REJECT"}:
                failures.append(f"Status is {status}, not an active DD entry candidate")
            if score < 80 and status in {"WAITING", "TRIGGERED"}:
                status = "REJECT"
                failures.append(f"Score {score:.0f} is below required DD threshold 80")

            candidate = _DDSetup(
                direction=direction,
                status=status,
                score=score,
                impulse_start_index=impulse_start,
                impulse_end_index=impulse_end,
                pullback_start_index=pullback_start,
                pullback_end_index=cluster_start - 1,
                cluster_start_index=cluster_start,
                cluster_end_index=cluster_end,
                cluster_low=min(c.low for c in cluster),
                cluster_high=max(c.high for c in cluster),
                signal=signal,
                stop=stop,
                obstacle=obstacle,
                reasons=[reason for reason in reasons if reason],
                failures=[failure for failure in failures if failure],
            )
            if (_dd_status_rank(candidate.status), candidate.score) > (_dd_status_rank(best.status), best.score):
                best = candidate
    return best


def _score_dd_trend(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    impulse_start: int,
    impulse_end: int,
    cluster_end: int,
) -> tuple[float, str, str]:
    lookback_start = max(0, impulse_start - 12)
    trend_closes = [c.close for c in candles[lookback_start : cluster_end + 1]]
    trend_emas = ema_values[lookback_start : cluster_end + 1]
    if len(trend_closes) < 15:
        return 0, "", "Trend is too short to confirm"
    slope_back = max(0, cluster_end - cfg.ema_slope_lookback)
    if direction == "long":
        slope_ok = ema_values[cluster_end] > ema_values[slope_back]
        side_ratio = sum(1 for close, ema in zip(trend_closes, trend_emas, strict=True) if close >= ema) / len(trend_closes)
        impulse_pct = (candles[impulse_end].high - candles[impulse_start].low) / candles[impulse_start].low * 100
        structure_ok = candles[impulse_end].high > max(c.high for c in candles[lookback_start:impulse_end] or [candles[impulse_end]])
    else:
        slope_ok = ema_values[cluster_end] < ema_values[slope_back]
        side_ratio = sum(1 for close, ema in zip(trend_closes, trend_emas, strict=True) if close <= ema) / len(trend_closes)
        impulse_pct = (candles[impulse_start].high - candles[impulse_end].low) / candles[impulse_start].high * 100
        structure_ok = candles[impulse_end].low < min(c.low for c in candles[lookback_start:impulse_end] or [candles[impulse_end]])
    crossings = _ema_crossings(trend_closes, trend_emas)
    if slope_ok and side_ratio >= 0.62 and crossings <= 4 and impulse_pct >= 2.5 and structure_ok:
        return 20, f"Clear existing trend: impulse {impulse_pct:.1f}%, EMA side ratio {side_ratio:.0%}, {crossings} crossing(s)", ""
    return 0, "", f"Trend failed: impulse {impulse_pct:.1f}%, EMA side ratio {side_ratio:.0%}, crossings {crossings}"


def _score_dd_ema(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    cluster_start: int,
    cluster_end: int,
) -> tuple[float, str, str]:
    slope_back = max(0, cluster_end - cfg.ema_slope_lookback)
    cluster = candles[cluster_start : cluster_end + 1]
    emas = ema_values[cluster_start : cluster_end + 1]
    if direction == "long":
        slope_ok = ema_values[cluster_end] >= ema_values[slope_back]
        support_ok = min(c.low for c in cluster) >= min(emas) * (1 - cfg.max_pullback_ema_distance_pct / 100)
        final_side_ok = candles[-1].close >= ema_values[-1] * (1 - cfg.max_pullback_ema_distance_pct / 100)
    else:
        slope_ok = ema_values[cluster_end] <= ema_values[slope_back]
        support_ok = max(c.high for c in cluster) <= max(emas) * (1 + cfg.max_pullback_ema_distance_pct / 100)
        final_side_ok = candles[-1].close <= ema_values[-1] * (1 + cfg.max_pullback_ema_distance_pct / 100)
    if slope_ok and support_ok and final_side_ok:
        return 15, f"EMA21 condition: cluster forms near EMA{cfg.ema_period} with correct trend slope", ""
    return 0, "", f"EMA21 does not support/reject correctly around the doji cluster"


def _score_dd_pullback(
    candles: list[Candle],
    direction: str,
    impulse_start: int,
    impulse_end: int,
    pullback_start: int,
    cluster_start: int,
) -> tuple[float, str, str]:
    pullback = candles[pullback_start:cluster_start]
    if len(pullback) < 3 or len(pullback) > 12:
        return 0, "", f"Pullback length {len(pullback)} is outside clean one-wave range"
    ranges = [c.high - c.low for c in pullback]
    if max(ranges) > mean(ranges) * 2.4:
        return 0, "", "Pullback contains a vertical/shock candle"
    if direction == "long":
        impulse_size = candles[impulse_end].high - candles[impulse_start].low
        pullback_size = candles[impulse_end].high - min(c.low for c in pullback)
        direction_steps = sum(1 for previous, current in zip(pullback, pullback[1:], strict=False) if current.close <= previous.close)
    else:
        impulse_size = candles[impulse_start].high - candles[impulse_end].low
        pullback_size = max(c.high for c in pullback) - candles[impulse_end].low
        direction_steps = sum(1 for previous, current in zip(pullback, pullback[1:], strict=False) if current.close >= previous.close)
    retrace = pullback_size / impulse_size if impulse_size > 0 else 9.9
    step_ratio = direction_steps / max(1, len(pullback) - 1)
    net_move = abs(pullback[-1].close - pullback[0].close)
    avg_range = mean(ranges)
    diagonal = net_move >= avg_range * 0.45
    if 0.25 <= retrace <= 0.70 and step_ratio >= 0.55 and diagonal:
        return 20, f"Pullback description: one clean wave, retrace {retrace:.0%}, directional steps {step_ratio:.0%}", ""
    return 0, "", f"Pullback is not one clean wave: retrace {retrace:.0%}, directional steps {step_ratio:.0%}"


def _score_dd_pullback_reaches_ema(
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    pullback_start: int,
    cluster_end: int,
) -> tuple[float, str, str]:
    segment = candles[pullback_start : cluster_end + 1]
    emas = ema_values[pullback_start : cluster_end + 1]
    if direction == "long":
        closest = min(abs(c.low - ema) / ema * 100 for c, ema in zip(segment, emas, strict=True) if ema > 0)
    else:
        closest = min(abs(c.high - ema) / ema * 100 for c, ema in zip(segment, emas, strict=True) if ema > 0)
    if closest <= cfg.max_pullback_ema_distance_pct:
        return 10, f"Pullback reaches EMA21 area: closest reaction {closest:.2f}% from EMA", ""
    return 0, "", f"Pullback does not reach EMA21 area: closest reaction {closest:.2f}% away"


def _score_dd_cluster(
    cluster: list[Candle],
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    cluster_start: int,
) -> tuple[float, list[str], list[str]]:
    prior = candles[max(0, cluster_start - 8) : cluster_start]
    prior_avg_range = mean(c.high - c.low for c in prior) if prior else mean(c.high - c.low for c in cluster)
    small_count = 0
    near_count = 0
    wick_warning = False
    for offset, candle in enumerate(cluster):
        candle_range = candle.high - candle.low
        if candle_range <= 0:
            continue
        body_ratio = abs(candle.close - candle.open) / candle_range
        range_pct = _candle_range_pct(candle)
        small_body = body_ratio <= max(cfg.doji_body_ratio, 0.35)
        small_range = candle_range <= prior_avg_range * 0.90 and range_pct <= cfg.max_signal_range_pct
        if small_body and small_range:
            small_count += 1
        ema = ema_values[cluster_start + offset]
        distance = min(abs(candle.close - ema), abs(candle.high - ema), abs(candle.low - ema)) / ema * 100 if ema > 0 else 100
        if distance <= cfg.max_pullback_ema_distance_pct:
            near_count += 1
        upper_wick = candle.high - max(candle.open, candle.close)
        lower_wick = min(candle.open, candle.close) - candle.low
        if direction == "long" and upper_wick > candle_range * 0.60:
            wick_warning = True
        if direction == "short" and lower_wick > candle_range * 0.60:
            wick_warning = True
    if small_count >= 2 and near_count == len(cluster) and not wick_warning:
        return (
            15,
            [f"Doji cluster: {len(cluster)} small hesitation candle(s) near EMA21"],
            [],
        )
    failures = []
    if small_count < 2:
        failures.append(f"Doji cluster needs at least 2 valid small/doji candles, found {small_count}")
    if near_count != len(cluster):
        failures.append("Doji cluster is not fully near EMA21")
    if wick_warning:
        failures.append("Signal doji wick strongly rejects the trade direction")
    return 0, [], failures


def _dd_entry_status(
    latest: Candle,
    signal: float,
    stop: float,
    cfg: VCPConfig,
    direction: str,
    cluster_end: int,
) -> str:
    if direction == "long":
        if latest.close < stop:
            return "FAILED"
        if latest.close > signal:
            extension = (latest.close - signal) / signal * 100
            return "TRIGGERED" if extension <= cfg.max_boundary_distance_pct else "LATE"
        distance = (signal - latest.close) / signal * 100
        return "WAITING" if distance <= cfg.max_boundary_distance_pct else "REJECT"
    if latest.close > stop:
        return "FAILED"
    if latest.close < signal:
        extension = (signal - latest.close) / signal * 100
        return "TRIGGERED" if extension <= cfg.max_boundary_distance_pct else "LATE"
    distance = (latest.close - signal) / signal * 100
    return "WAITING" if distance <= cfg.max_boundary_distance_pct else "REJECT"


def _score_dd_signal(
    latest: Candle,
    signal: float | None,
    status: str,
    cfg: VCPConfig,
    direction: str,
) -> tuple[float, str, str]:
    if signal is None or signal <= 0:
        return 0, "", "Signal level is missing"
    if status == "TRIGGERED":
        return 10, f"Signal level: latest candle closed beyond doji cluster at {_fmt_price(signal)}", ""
    if status == "WAITING":
        distance = ((signal - latest.close) / signal * 100) if direction == "long" else ((latest.close - signal) / signal * 100)
        if 0 <= distance <= cfg.max_boundary_distance_pct:
            return 8, f"Signal level: price is waiting {distance:.2f}% from doji cluster trigger {_fmt_price(signal)}", ""
    return 0, "", "Price has not produced a valid DD signal break or near-signal waiting state"


def _score_dd_stop(
    candles: list[Candle],
    signal: float | None,
    stop: float | None,
    cfg: VCPConfig,
    direction: str,
    cluster_start: int,
) -> tuple[float, str, str]:
    if signal is None or stop is None or signal <= 0 or stop <= 0:
        return 0, "", "Stop-loss area is missing"
    atr = _average_range(candles[max(0, cluster_start - 14) : cluster_start] or candles[-14:])
    distance = (signal - stop) if direction == "long" else (stop - signal)
    if atr > 0 and 0 < distance <= atr * 1.5:
        return 5, f"Stop-loss area: {_fmt_price(stop)} is {distance / atr:.2f} ATR from signal", ""
    return 0, "", f"Stop-loss is too wide: {_fmt_price(distance)} vs 1.5 ATR limit"


def _nearest_dd_obstacle(
    candles: list[Candle],
    signal: float,
    direction: str,
    impulse_start: int,
    cluster_start: int,
) -> float | None:
    left = candles[max(0, impulse_start - 45) : cluster_start]
    swings = _swing_points(left, 0, len(left) - 1, 2) if len(left) >= 7 else []
    if direction == "long":
        obstacles = [price for _, kind, price in swings if kind == "high" and price > signal]
        return min(obstacles, default=None)
    obstacles = [price for _, kind, price in swings if kind == "low" and price < signal]
    return max(obstacles, default=None)


def _score_dd_obstacle(
    candles: list[Candle],
    signal: float | None,
    obstacle: float | None,
    direction: str,
    cluster_start: int,
) -> tuple[float, str, str]:
    if signal is None or signal <= 0:
        return 0, "", "Obstacle cannot be checked without signal"
    atr = _average_range(candles[max(0, cluster_start - 14) : cluster_start] or candles[-14:])
    if obstacle is None:
        return 5, "Nearest obstacle: no immediate left-side obstacle in trade direction", ""
    distance = (obstacle - signal) if direction == "long" else (signal - obstacle)
    if atr > 0 and distance >= atr:
        return 5, f"Nearest obstacle: {_fmt_price(obstacle)} leaves {distance / atr:.2f} ATR of room", ""
    return 0, "", f"Nearest obstacle {_fmt_price(obstacle)} is too close to signal"


def _dd_pullback_start(candles: list[Candle], direction: str, cluster_start: int) -> int | None:
    lookback_start = max(0, cluster_start - 14)
    segment = candles[lookback_start:cluster_start]
    if len(segment) < 3:
        return None
    if direction == "long":
        local = max(range(len(segment)), key=lambda index: segment[index].high)
    else:
        local = min(range(len(segment)), key=lambda index: segment[index].low)
    start = lookback_start + local
    length = cluster_start - start
    if 3 <= length <= 12:
        return start
    return None


def _dd_impulse_start(candles: list[Candle], direction: str, pullback_start: int) -> int | None:
    lookback_start = max(0, pullback_start - 35)
    segment = candles[lookback_start : pullback_start + 1]
    if len(segment) < 6:
        return None
    if direction == "long":
        local = min(range(max(1, len(segment) - 3)), key=lambda index: segment[index].low)
        if local >= len(segment) - 4:
            return None
    else:
        local = max(range(max(1, len(segment) - 3)), key=lambda index: segment[index].high)
        if local >= len(segment) - 4:
            return None
    return lookback_start + local


def _empty_dd(direction: str, failures: list[str]) -> _DDSetup:
    return _DDSetup(
        direction=direction,
        status="REJECT",
        score=0.0,
        impulse_start_index=None,
        impulse_end_index=None,
        pullback_start_index=None,
        pullback_end_index=None,
        cluster_start_index=None,
        cluster_end_index=None,
        cluster_low=None,
        cluster_high=None,
        signal=None,
        stop=None,
        obstacle=None,
        reasons=[],
        failures=failures,
    )


def _dd_output_lines(result: _DDSetup, candles: list[Candle]) -> list[str]:
    direction = "Long" if result.direction == "long" else "Short"
    impulse = _date_range_text(candles, result.impulse_start_index, result.impulse_end_index)
    pullback = _date_range_text(candles, result.pullback_start_index, result.pullback_end_index)
    cluster = _date_range_text(candles, result.cluster_start_index, result.cluster_end_index)
    return [
        "Pattern: DD",
        f"Direction: {direction}",
        f"Status: {result.status}",
        f"Score: {result.score:.0f}",
        f"Trend: {direction} trend before pullback",
        f"EMA21 condition: cluster is near EMA21 in trend direction",
        f"Impulse wave: {impulse}",
        f"Pullback description: {pullback}",
        f"Doji cluster: {cluster}; area {_fmt_price(result.cluster_low)} - {_fmt_price(result.cluster_high)}",
        f"Signal level: {_fmt_price(result.signal)}",
        f"Current price: {_fmt_price(candles[-1].close)}",
        f"Stop-loss area: {_fmt_price(result.stop)}",
        f"Nearest obstacle: {_fmt_price(result.obstacle)}",
        "Reason:",
        *[f"- {reason}" for reason in result.reasons[:8]],
        "Manual review note:",
        "- Confirm trend strength, one clean pullback to EMA21, the 2+ doji cluster, signal break, stop distance, and nearby obstacle before acting.",
    ]


def _dd_reject_lines(result: _DDSetup) -> list[str]:
    failures = result.failures or ["Reject reason: DD story is incomplete or unclear"]
    return [
        "Pattern: DD",
        "Status: REJECT",
        f"Score: {result.score:.0f}",
        "Reject reason:",
        *[f"- {failure}" for failure in failures[:8]],
    ]


def _dd_status_rank(status: str) -> int:
    return {
        "TRIGGERED": 5,
        "WAITING": 4,
        "LATE": 3,
        "FAILED": 2,
        "REJECT": 1,
    }.get(status, 0)


def _date_range_text(candles: list[Candle], start: int | None, end: int | None) -> str:
    if start is None or end is None:
        return "n/a"
    return f"{candles[start].datetime.date().isoformat()} -> {candles[end].datetime.date().isoformat()}"


def _detect_arb_setup(candles: list[Candle], config: VCPConfig | None = None) -> VCPEvidence:
    cfg = config or VCPConfig()
    min_needed = max(cfg.min_history_days, cfg.ema_period + 60)
    if len(candles) < min_needed:
        return _not_qualified(f"ARB requires at least {min_needed} candles, got {len(candles)}")

    closes = [c.close for c in candles]
    ema_values = _ema(closes, cfg.ema_period)
    candidates = [
        _score_arb_direction(candles, cfg, ema_values, "long"),
        _score_arb_direction(candles, cfg, ema_values, "short"),
    ]
    result = max(candidates, key=lambda item: (_arb_status_rank(item.status), item.score))
    qualified = result.score >= 80 and result.status in {"WAITING", "TRIGGERED"} and not result.failures

    if result.trigger and result.trigger > 0:
        if result.direction == "long":
            distance_to_trigger = ((result.trigger - candles[-1].close) / result.trigger) * 100
        else:
            distance_to_trigger = ((candles[-1].close - result.trigger) / result.trigger) * 100
    else:
        distance_to_trigger = None

    reasons = _arb_output_lines(result, candles)
    failures = [] if qualified else _arb_reject_lines(result)
    return VCPEvidence(
        qualified=qualified,
        status=result.status if qualified else "rejected",
        score=result.score,
        pivot=result.trigger,
        current_close=candles[-1].close,
        distance_to_pivot_pct=distance_to_trigger,
        contractions=[],
        reasons=reasons if qualified else [],
        failures=failures,
        base_start_index=result.base_start,
        base_end_index=len(candles) - 1,
        volume_dry_up_ratio=_window_volume_ratio(candles, max(0, len(candles) - cfg.compression_lookback)),
        prior_uptrend_pct=None,
    )


def _score_arb_direction(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
) -> _ARBSetup:
    best = _empty_arb(direction, ["Reject reason: no old range and first breakout sequence found"])
    n = len(candles)
    min_range_len = 12
    max_range_len = min(36, cfg.max_base_days)
    search_start = max(0, n - cfg.max_base_days - 55)

    for start in range(search_start, n - min_range_len - 5):
        for length in range(min_range_len, max_range_len + 1):
            end = start + length
            if end > n - 5:
                continue
            old_range = candles[start:end]
            range_score, range_reasons, range_failures = _score_arb_old_range(old_range, cfg)
            if range_score <= 0:
                continue

            old_high = max(c.high for c in old_range)
            old_low = min(c.low for c in old_range)
            first_break = _find_arb_first_break(candles, end, n - 3, old_high, old_low, direction)
            if first_break is None:
                candidate = _empty_arb(
                    direction,
                    range_failures + ["Reject reason: old range exists but no first breakout before the latest setup"],
                )
                if candidate.score > best.score:
                    best = candidate
                continue
            if first_break - end > 3:
                continue

            type_candidates = [
                _score_arb_type1(candles, cfg, ema_values, direction, start, end, first_break, range_score, range_reasons),
                _score_arb_type2(candles, cfg, ema_values, direction, start, end, first_break, range_score, range_reasons),
            ]
            local_best = max(type_candidates, key=lambda item: (_arb_status_rank(item.status), item.score))
            if (_arb_status_rank(local_best.status), local_best.score) > (_arb_status_rank(best.status), best.score):
                best = local_best

    if best.score < 80 and best.status in {"WAITING", "TRIGGERED"}:
        return _replace_arb(
            best,
            status="REJECT",
            failures=best.failures + [f"Score {best.score:.0f} is below required ARB threshold 80"],
        )
    return best


def _score_arb_old_range(old_range: list[Candle], cfg: VCPConfig) -> tuple[float, list[str], list[str]]:
    old_high = max(c.high for c in old_range)
    old_low = min(c.low for c in old_range)
    depth = _base_depth_pct(old_range)
    high_touches = _boundary_touches(old_range, old_high, cfg.boundary_touch_tolerance_pct)
    low_touches = _floor_touches(old_range, old_low, cfg.boundary_touch_tolerance_pct)
    range_height = old_high - old_low
    close_drift = abs(old_range[-1].close - old_range[0].close)
    sideways = _arb_range_is_sideways(old_range, old_high, old_low, cfg.boundary_touch_tolerance_pct)
    if (
        cfg.min_range_depth_pct <= depth <= cfg.max_base_depth_pct
        and high_touches >= cfg.min_boundary_touches
        and low_touches >= cfg.min_boundary_touches
        and range_height > 0
        and close_drift <= range_height * 0.45
        and sideways
    ):
        return (
            20,
            [
                f"Old range is clear: high {_fmt_price(old_high)}, low {_fmt_price(old_low)}, "
                f"depth {depth:.1f}%, upper touches {high_touches}, lower touches {low_touches}"
            ],
            [],
        )
    return (
        0,
        [],
        [
            f"Old range is unclear: depth {depth:.1f}%, upper touches {high_touches}, "
            f"lower touches {low_touches}, close drift {_fmt_price(close_drift)}, sideways={sideways}"
        ],
    )


def _find_arb_first_break(
    candles: list[Candle],
    start: int,
    end: int,
    old_high: float,
    old_low: float,
    direction: str,
) -> int | None:
    boundary = old_high if direction == "long" else old_low
    for index in range(start, max(start, end)):
        candle = candles[index]
        if _trigger_close(candle, boundary, direction):
            return index
    return None


def _score_arb_type1(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
    range_start: int,
    range_end: int,
    first_break: int,
    range_score: float,
    range_reasons: list[str],
) -> _ARBSetup:
    n = len(candles)
    old_range = candles[range_start:range_end]
    old_high = max(c.high for c in old_range)
    old_low = min(c.low for c in old_range)
    boundary = old_high if direction == "long" else old_low
    best = _empty_arb(direction, ["Reject reason: no tight build-up after the first breakout"])

    for include_latest in (False, True):
        area_end = n if include_latest else n - 1
        for length in range(3, min(9, area_end - first_break - 1) + 1):
            area_start = first_break + 1
            if area_start + length != area_end:
                continue
            if area_start <= first_break:
                continue
            area = candles[area_start:area_end]
            score, reasons, failures = _score_arb_buildup(
                area, candles, cfg, ema_values, direction, boundary, old_high, old_low, area_start
            )
            trigger = max(c.high for c in area) if direction == "long" else min(c.low for c in area)
            stop = _arb_stop(area, boundary, direction)
            status = _arb_entry_status(candles[-1], trigger, stop, boundary, old_high, old_low, cfg, direction)
            if include_latest and status == "TRIGGERED":
                continue
            if not include_latest and status == "WAITING":
                continue
            outside = _arb_buildup_outside_old_range(area, boundary, direction)
            trigger_points, trigger_reason, trigger_failure = _score_arb_second_trigger(
                candles[-1], trigger, status, cfg, direction
            )
            stop_points, stop_reason, stop_failure = _score_arb_stop(candles[-1], trigger, stop, cfg, direction)
            first_points, first_reason = _score_arb_first_break(candles[first_break], boundary, direction)
            total = range_score + first_points + score + trigger_points + stop_points
            all_reasons = [
                *range_reasons,
                first_reason,
                *reasons,
                trigger_reason,
                stop_reason,
            ]
            all_failures = [
                *failures,
                *(["Build-up must form immediately outside the old range after the first breakout"] if not outside else []),
                *([] if trigger_points else [trigger_failure]),
                *([] if stop_points else [stop_failure]),
            ]
            if status in {"LATE", "FAILED", "REJECT"}:
                all_failures.append(f"Status is {status}, not an entry candidate")
            candidate = _ARBSetup(
                direction=direction,
                arb_type="Outside Build-up",
                status=status,
                score=total,
                old_high=old_high,
                old_low=old_low,
                boundary=boundary,
                first_break_index=first_break,
                area_start_index=area_start,
                area_end_index=area_end - 1,
                area_low=min(c.low for c in area),
                area_high=max(c.high for c in area),
                trigger=trigger,
                stop=stop,
                base_start=range_start,
                reasons=[reason for reason in all_reasons if reason],
                failures=[failure for failure in all_failures if failure],
            )
            if not outside:
                candidate = _replace_arb(
                    candidate,
                    status="REJECT",
                    failures=candidate.failures,
                )
            if (_arb_status_rank(candidate.status), candidate.score) > (_arb_status_rank(best.status), best.score):
                best = candidate
    return best


def _score_arb_type2(
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
    range_start: int,
    range_end: int,
    first_break: int,
    range_score: float,
    range_reasons: list[str],
) -> _ARBSetup:
    n = len(candles)
    old_range = candles[range_start:range_end]
    old_high = max(c.high for c in old_range)
    old_low = min(c.low for c in old_range)
    boundary = old_high if direction == "long" else old_low
    best = _empty_arb(direction, ["Reject reason: no controlled pullback/retest after the first breakout"])

    for include_latest in (False, True):
        area_end = n if include_latest else n - 1
        for length in range(3, min(8, area_end - first_break - 1) + 1):
            area_start = area_end - length
            if area_start <= first_break:
                continue
            area = candles[area_start:area_end]
            far = _arb_moved_far(candles[first_break + 1 : area_start] or [candles[first_break]], boundary, cfg, direction)
            arb_type = "Type 2A Pullback from far" if far else "Type 2B Pullback from near"
            score, reasons, failures = _score_arb_pullback(
                area, candles, cfg, ema_values, direction, boundary, old_high, old_low, area_start, far
            )
            trigger = max(c.high for c in area) if direction == "long" else min(c.low for c in area)
            stop = _arb_stop(area, boundary, direction)
            status = _arb_entry_status(candles[-1], trigger, stop, boundary, old_high, old_low, cfg, direction)
            if include_latest and status == "TRIGGERED":
                continue
            if not include_latest and status == "WAITING":
                continue
            trigger_points, trigger_reason, trigger_failure = _score_arb_second_trigger(
                candles[-1], trigger, status, cfg, direction
            )
            stop_points, stop_reason, stop_failure = _score_arb_stop(candles[-1], trigger, stop, cfg, direction)
            first_points, first_reason = _score_arb_first_break(candles[first_break], boundary, direction)
            total = range_score + first_points + score + trigger_points + stop_points
            all_reasons = [
                *range_reasons,
                first_reason,
                *reasons,
                trigger_reason,
                stop_reason,
            ]
            all_failures = [
                *failures,
                *([] if trigger_points else [trigger_failure]),
                *([] if stop_points else [stop_failure]),
            ]
            if status in {"LATE", "FAILED", "REJECT"}:
                all_failures.append(f"Status is {status}, not an entry candidate")
            candidate = _ARBSetup(
                direction=direction,
                arb_type=arb_type,
                status=status,
                score=total,
                old_high=old_high,
                old_low=old_low,
                boundary=boundary,
                first_break_index=first_break,
                area_start_index=area_start,
                area_end_index=area_end - 1,
                area_low=min(c.low for c in area),
                area_high=max(c.high for c in area),
                trigger=trigger,
                stop=stop,
                base_start=range_start,
                reasons=[reason for reason in all_reasons if reason],
                failures=[failure for failure in all_failures if failure],
            )
            if (_arb_status_rank(candidate.status), candidate.score) > (_arb_status_rank(best.status), best.score):
                best = candidate
    return best


def _score_arb_first_break(candle: Candle, boundary: float, direction: str) -> tuple[float, str]:
    if not _trigger_close(candle, boundary, direction):
        return 0, "First breakout is missing"
    extension = (
        ((candle.close - boundary) / boundary) * 100
        if direction == "long"
        else ((boundary - candle.close) / boundary) * 100
    )
    return 15, f"First breakout is clear: closed {extension:.2f}% beyond the old boundary"


def _score_arb_buildup(
    area: list[Candle],
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
    boundary: float,
    old_high: float,
    old_low: float,
    area_start: int,
) -> tuple[float, list[str], list[str]]:
    score = 0.0
    reasons: list[str] = []
    failures: list[str] = []
    depth = _base_depth_pct(area)
    overlap_ratio = _overlap_ratio(area)
    stable = _rising_lows(area) if direction == "long" else _falling_highs(area)
    tight = depth <= cfg.max_block_range_pct and overlap_ratio >= 0.60 and stable
    if tight:
        score += 20
        reasons.append(f"Build-up is clear: tight overlapping box, depth {depth:.1f}%, overlap {overlap_ratio:.0%}")
    else:
        failures.append(f"Build-up is not tight/clean enough: depth {depth:.1f}%, overlap {overlap_ratio:.0%}")

    near = _arb_area_near_boundary(area, boundary, old_high, old_low, cfg, direction, allow_deep_inside=False)
    if near:
        score += 15
        reasons.append("Build-up stays near the old boundary and does not fall/rise deeply back into the range")
    else:
        failures.append("Build-up is too far from the old boundary or returns deeply into the old range")

    ema_points, ema_reason, ema_failure = _score_arb_ema(area, candles, ema_values, cfg, direction, area_start)
    score += ema_points
    if ema_points:
        reasons.append(ema_reason)
    else:
        failures.append(ema_failure)
    return score, reasons, failures


def _score_arb_pullback(
    area: list[Candle],
    candles: list[Candle],
    cfg: VCPConfig,
    ema_values: list[float],
    direction: str,
    boundary: float,
    old_high: float,
    old_low: float,
    area_start: int,
    far: bool,
) -> tuple[float, list[str], list[str]]:
    score = 0.0
    reasons: list[str] = []
    failures: list[str] = []
    depth = _base_depth_pct(area)
    controlled = _arb_pullback_controlled(area, direction) and depth <= cfg.max_later_contraction_depth_pct
    if controlled:
        score += 20
        reasons.append(f"Pullback/retest is controlled: pullback area depth {depth:.1f}%")
    else:
        failures.append(f"Pullback/retest is not controlled enough: pullback area depth {depth:.1f}%")

    near = _arb_area_near_boundary(area, boundary, old_high, old_low, cfg, direction, allow_deep_inside=not far)
    if near:
        score += 15
        if far:
            reasons.append("Pullback retests near the broken boundary after price first moved clearly away")
        else:
            reasons.append("Near pullback holds in the upper/lower part of the old range before turning again")
    else:
        failures.append("Pullback is too deep or does not react near the old boundary/internal reaction area")

    ema_points, ema_reason, ema_failure = _score_arb_ema(area, candles, ema_values, cfg, direction, area_start)
    score += ema_points
    if ema_points:
        reasons.append(ema_reason)
    else:
        failures.append(ema_failure)
    return score, reasons, failures


def _score_arb_ema(
    area: list[Candle],
    candles: list[Candle],
    ema_values: list[float],
    cfg: VCPConfig,
    direction: str,
    area_start: int,
) -> tuple[float, str, str]:
    lookback = min(25, len(candles))
    closes = [c.close for c in candles[-lookback:]]
    emas = ema_values[-lookback:]
    area_emas = ema_values[area_start : area_start + len(area)]
    if direction == "long":
        slope_ok = ema_values[-1] >= ema_values[-1 - min(cfg.ema_slope_lookback, len(ema_values) - 1)]
        side_ratio = sum(1 for close, ema in zip(closes, emas, strict=True) if close >= ema) / len(closes)
        area_ok = min(c.low for c in area) >= min(area_emas) * (1 - cfg.max_pullback_ema_distance_pct / 100)
    else:
        slope_ok = ema_values[-1] <= ema_values[-1 - min(cfg.ema_slope_lookback, len(ema_values) - 1)]
        side_ratio = sum(1 for close, ema in zip(closes, emas, strict=True) if close <= ema) / len(closes)
        area_ok = max(c.high for c in area) <= max(area_emas) * (1 + cfg.max_pullback_ema_distance_pct / 100)
    crossings = _ema_crossings(closes, emas)
    if slope_ok and side_ratio >= cfg.trend_above_ema_ratio and crossings <= 6 and area_ok:
        return 10, f"EMA21 supports/rejects correctly: {side_ratio:.0%} recent closes on the right side, {crossings} crossing(s)", ""
    return 0, "", f"EMA21 is not helpful enough: side ratio {side_ratio:.0%}, crossings {crossings}"


def _score_arb_second_trigger(
    latest: Candle,
    trigger: float | None,
    status: str,
    cfg: VCPConfig,
    direction: str,
) -> tuple[float, str, str]:
    if trigger is None or trigger <= 0:
        return 0, "", "Second trigger level is missing"
    if status == "TRIGGERED":
        return 10, f"Second trigger is clear: latest candle closed beyond {_fmt_price(trigger)}", ""
    if status == "WAITING":
        distance = (
            ((trigger - latest.close) / trigger) * 100
            if direction == "long"
            else ((latest.close - trigger) / trigger) * 100
        )
        if 0 <= distance <= cfg.max_boundary_distance_pct:
            return 8, f"Second trigger is close: current price is {distance:.2f}% from {_fmt_price(trigger)}", ""
    return 0, "", "Second trigger is not clear or price is not close to it"


def _score_arb_stop(
    latest: Candle,
    trigger: float | None,
    stop: float | None,
    cfg: VCPConfig,
    direction: str,
) -> tuple[float, str, str]:
    if trigger is None or stop is None or trigger <= 0 or stop <= 0:
        return 0, "", "Stop-loss area is missing"
    reference = trigger if direction == "long" else trigger
    distance = ((reference - stop) / reference) * 100 if direction == "long" else ((stop - reference) / reference) * 100
    limit = max(cfg.max_signal_range_pct, cfg.max_retest_distance_pct * 2.5)
    if 0 < distance <= limit:
        return 10, f"Stop-loss area is logical: {_fmt_price(stop)} is {distance:.2f}% from trigger", ""
    return 0, "", f"Stop-loss is too wide or illogical: distance {distance:.2f}% from trigger"


def _arb_entry_status(
    latest: Candle,
    trigger: float,
    stop: float,
    boundary: float,
    old_high: float,
    old_low: float,
    cfg: VCPConfig,
    direction: str,
) -> str:
    range_height = old_high - old_low
    if range_height <= 0:
        return "REJECT"
    if direction == "long":
        if latest.close <= stop or latest.close < old_high - range_height * 0.45:
            return "FAILED"
        if latest.close > trigger and latest.close > latest.open:
            extension = (latest.close - trigger) / trigger * 100
            return "TRIGGERED" if extension <= cfg.max_boundary_distance_pct else "LATE"
        distance = (trigger - latest.close) / trigger * 100
        return "WAITING" if 0 <= distance <= cfg.max_boundary_distance_pct else "REJECT"
    if latest.close >= stop or latest.close > old_low + range_height * 0.45:
        return "FAILED"
    if latest.close < trigger and latest.close < latest.open:
        extension = (trigger - latest.close) / trigger * 100
        return "TRIGGERED" if extension <= cfg.max_boundary_distance_pct else "LATE"
    distance = (latest.close - trigger) / trigger * 100
    return "WAITING" if 0 <= distance <= cfg.max_boundary_distance_pct else "REJECT"


def _arb_area_near_boundary(
    area: list[Candle],
    boundary: float,
    old_high: float,
    old_low: float,
    cfg: VCPConfig,
    direction: str,
    allow_deep_inside: bool,
) -> bool:
    range_height = old_high - old_low
    if boundary <= 0 or range_height <= 0:
        return False
    tolerance = max(cfg.max_retest_distance_pct / 100 * boundary, range_height * 0.25)
    if direction == "long":
        area_low = min(c.low for c in area)
        avg_close = mean(c.close for c in area)
        deepest_allowed = old_low + range_height * (0.52 if allow_deep_inside else 0.65)
        near_boundary = abs(area_low - boundary) <= tolerance or abs(avg_close - boundary) <= tolerance
        return near_boundary and area_low >= deepest_allowed
    area_high = max(c.high for c in area)
    avg_close = mean(c.close for c in area)
    deepest_allowed = old_high - range_height * (0.52 if allow_deep_inside else 0.65)
    near_boundary = abs(area_high - boundary) <= tolerance or abs(avg_close - boundary) <= tolerance
    return near_boundary and area_high <= deepest_allowed


def _arb_buildup_outside_old_range(area: list[Candle], boundary: float, direction: str) -> bool:
    if not area or boundary <= 0:
        return False
    if direction == "long":
        closes_outside = sum(1 for candle in area if candle.close >= boundary) / len(area)
        shallow_wicks = min(candle.low for candle in area) >= boundary * 0.995
        return closes_outside >= 0.80 and shallow_wicks
    closes_outside = sum(1 for candle in area if candle.close <= boundary) / len(area)
    shallow_wicks = max(candle.high for candle in area) <= boundary * 1.005
    return closes_outside >= 0.80 and shallow_wicks


def _arb_range_is_sideways(
    candles: list[Candle],
    high: float,
    low: float,
    tolerance_pct: float,
) -> bool:
    if len(candles) < 8 or high <= low:
        return False
    high_touch_indexes = [
        index for index, candle in enumerate(candles)
        if high * (1 - tolerance_pct / 100) <= candle.high <= high * 1.002
    ]
    low_touch_indexes = [
        index for index, candle in enumerate(candles)
        if low * 0.998 <= candle.low <= low * (1 + tolerance_pct / 100)
    ]
    if len(high_touch_indexes) < 2 or len(low_touch_indexes) < 2:
        return False

    midpoint = len(candles) // 2
    distributed_highs = any(index < midpoint for index in high_touch_indexes) and any(index >= midpoint for index in high_touch_indexes)
    distributed_lows = any(index < midpoint for index in low_touch_indexes) and any(index >= midpoint for index in low_touch_indexes)
    has_alternation = (
        min(high_touch_indexes) < max(low_touch_indexes)
        and min(low_touch_indexes) < max(high_touch_indexes)
    )
    return distributed_highs and distributed_lows and has_alternation


def _arb_moved_far(area: list[Candle], boundary: float, cfg: VCPConfig, direction: str) -> bool:
    if not area or boundary <= 0:
        return False
    atr = _average_range(area)
    if direction == "long":
        excursion = max(c.high for c in area) - boundary
        away_candles = sum(1 for c in area if c.close >= boundary + atr * 0.5)
    else:
        excursion = boundary - min(c.low for c in area)
        away_candles = sum(1 for c in area if c.close <= boundary - atr * 0.5)
    return excursion >= atr or away_candles >= 3


def _arb_pullback_controlled(area: list[Candle], direction: str) -> bool:
    if len(area) < 3:
        return False
    ranges = [c.high - c.low for c in area]
    if max(ranges) > mean(ranges) * 2.2:
        return False
    first_close = area[0].close
    last_close = area[-1].close
    if direction == "long":
        return min(c.close for c in area) >= min(c.low for c in area) and last_close >= min(c.close for c in area)
    return max(c.close for c in area) <= max(c.high for c in area) and last_close <= max(c.close for c in area)


def _arb_stop(area: list[Candle], boundary: float, direction: str) -> float:
    if direction == "long":
        return min(min(c.low for c in area), boundary * 0.998)
    return max(max(c.high for c in area), boundary * 1.002)


def _empty_arb(direction: str, failures: list[str]) -> _ARBSetup:
    return _ARBSetup(
        direction=direction,
        arb_type="",
        status="REJECT",
        score=0.0,
        old_high=None,
        old_low=None,
        boundary=None,
        first_break_index=None,
        area_start_index=None,
        area_end_index=None,
        area_low=None,
        area_high=None,
        trigger=None,
        stop=None,
        base_start=None,
        reasons=[],
        failures=failures,
    )


def _replace_arb(
    setup: _ARBSetup,
    *,
    status: str | None = None,
    failures: list[str] | None = None,
) -> _ARBSetup:
    return _ARBSetup(
        direction=setup.direction,
        arb_type=setup.arb_type,
        status=status or setup.status,
        score=setup.score,
        old_high=setup.old_high,
        old_low=setup.old_low,
        boundary=setup.boundary,
        first_break_index=setup.first_break_index,
        area_start_index=setup.area_start_index,
        area_end_index=setup.area_end_index,
        area_low=setup.area_low,
        area_high=setup.area_high,
        trigger=setup.trigger,
        stop=setup.stop,
        base_start=setup.base_start,
        reasons=setup.reasons,
        failures=failures if failures is not None else setup.failures,
    )


def _arb_output_lines(result: _ARBSetup, candles: list[Candle]) -> list[str]:
    direction = "Long" if result.direction == "long" else "Short"
    first_break = (
        candles[result.first_break_index].datetime.date().isoformat()
        if result.first_break_index is not None
        else "n/a"
    )
    area_start = (
        candles[result.area_start_index].datetime.date().isoformat()
        if result.area_start_index is not None
        else "n/a"
    )
    area_end = (
        candles[result.area_end_index].datetime.date().isoformat()
        if result.area_end_index is not None
        else "n/a"
    )
    lines = [
        "Pattern: ARB",
        f"Direction: {direction}",
        f"ARB Type: {result.arb_type or 'n/a'}",
        f"Status: {result.status}",
        f"Score: {result.score:.0f}",
        f"Old range high: {_fmt_price(result.old_high)}",
        f"Old range low: {_fmt_price(result.old_low)}",
        f"Breakout boundary: {_fmt_price(result.boundary)}",
        f"First breakout candle: {first_break}",
        f"Build-up or pullback candles: {area_start} -> {area_end}",
        f"Build-up or pullback area: {_fmt_price(result.area_low)} - {_fmt_price(result.area_high)}",
        f"Second trigger level: {_fmt_price(result.trigger)}",
        f"Current price: {_fmt_price(candles[-1].close)}",
        f"Stop-loss area: {_fmt_price(result.stop)}",
        "Reason:",
        *[f"- {reason}" for reason in result.reasons[:8]],
        "Manual review note:",
        "- Confirm the old range boundary, the post-break build-up/retest, the second trigger close, and the stop area on TradingView before acting.",
    ]
    return lines


def _arb_reject_lines(result: _ARBSetup) -> list[str]:
    failures = result.failures or ["Reject reason: ARB story is incomplete or unclear"]
    return [
        "Pattern: ARB",
        f"Status: {result.status}",
        f"Score: {result.score:.0f}",
        "Reject reason:",
        *[f"- {failure}" for failure in failures[:8]],
    ]


def _arb_status_rank(status: str) -> int:
    return {
        "TRIGGERED": 5,
        "WAITING": 4,
        "LATE": 3,
        "FAILED": 2,
        "REJECT": 1,
    }.get(status, 0)


def _overlap_ratio(candles: list[Candle]) -> float:
    if len(candles) < 2:
        return 0.0
    overlaps = 0
    for previous, current in zip(candles, candles[1:], strict=False):
        if current.low <= previous.high and current.high >= previous.low:
            overlaps += 1
    return overlaps / (len(candles) - 1)


def _average_range(candles: list[Candle]) -> float:
    if not candles:
        return 0.0
    return mean(max(0.0, c.high - c.low) for c in candles)


def _average_range_pct(candles: list[Candle]) -> float:
    if not candles:
        return 100.0
    avg_close = mean(c.close for c in candles)
    if avg_close <= 0:
        return 100.0
    return _average_range(candles) / avg_close * 100


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.5f}".rstrip("0").rstrip(".")


def _detect_nhathoai_vcp_setup(candles: list[Candle], config: VCPConfig | None = None) -> VCPEvidence:
    cfg = config or VCPConfig()
    min_needed = max(cfg.min_history_days, cfg.ema_period + cfg.pre_base_days + 35)
    if len(candles) < min_needed:
        return _not_qualified(f"Nhật Hoài VCP requires at least {min_needed} candles, got {len(candles)}")

    result = _score_nhathoai_vcp(candles, cfg)
    qualified = result.score >= 80 and result.status in {"NEAR_PIVOT", "WAITING", "TRIGGERED"} and not result.failures

    return VCPEvidence(
        qualified=qualified,
        status=result.status if result.status != "REJECT" else "rejected",
        score=result.score,
        pivot=result.pivot,
        current_close=result.current_close,
        distance_to_pivot_pct=result.distance_to_pivot_pct,
        contractions=result.contractions,
        reasons=_nhathoai_vcp_output_lines(result, candles) if qualified else [],
        failures=[] if qualified else _nhathoai_vcp_reject_lines(result),
        base_start_index=result.base_start_index,
        base_end_index=result.base_end_index,
        volume_dry_up_ratio=result.volume_ratio,
        prior_uptrend_pct=result.prior_uptrend_pct,
    )


def _score_nhathoai_vcp(candles: list[Candle], cfg: VCPConfig) -> _NhathoaiVCPSetup:
    min_base_len = max(30, cfg.compression_lookback * 2)
    max_base_len = min(cfg.max_base_days, len(candles) - cfg.pre_base_days)
    best: _NhathoaiVCPSetup | None = None
    for base_len in range(min_base_len, max_base_len + 1):
        candidate = _score_nhathoai_vcp_candidate(candles, cfg, len(candles) - base_len)
        if best is None or (_nhathoai_vcp_status_rank(candidate.status), candidate.score) > (
            _nhathoai_vcp_status_rank(best.status),
            best.score,
        ):
            best = candidate
    if best is None:
        return _empty_nhathoai_vcp(["Reject reason: not enough history to form a VCP base"])
    return best


def _score_nhathoai_vcp_candidate(
    candles: list[Candle],
    cfg: VCPConfig,
    base_start: int,
) -> _NhathoaiVCPSetup:
    base_end = len(candles) - 1
    pre_start = max(0, base_start - cfg.pre_base_days)
    base = candles[base_start:]
    pre_base = candles[pre_start:base_start]
    current = candles[-1]
    prior_uptrend_pct = _prior_uptrend_pct(pre_base, base)
    contractions = _detect_contractions(candles, base_start, cfg)

    pivot_source = base[:-1] if len(base) > 1 else base
    pivot = max(c.high for c in pivot_source)
    current_close = current.close
    stop = _nhathoai_vcp_stop(candles, contractions, base_start)
    distance_to_pivot_pct = ((pivot - current_close) / pivot) * 100 if pivot > 0 else None
    volume_ratio = _volume_dry_up_ratio(candles, base_start, contractions)
    status = _nhathoai_vcp_status(candles, pivot, stop, cfg)

    prior_points, prior_reason, prior_failure = _score_nhathoai_vcp_prior_trend(
        candles, cfg, pre_base, base, prior_uptrend_pct
    )
    base_points, base_reason, base_failure = _score_nhathoai_vcp_base(base, cfg)
    count_points, count_reason, count_failure = _score_nhathoai_vcp_contraction_count(contractions)
    shrink_points, shrink_reason, shrink_failure = _score_nhathoai_vcp_shrinking(contractions, cfg)
    tight_points, tight_reason, tight_failure = _score_nhathoai_vcp_right_side(candles, base_start, pivot, cfg)
    volume_points, volume_reason, volume_failure = _score_nhathoai_vcp_volume(candles, volume_ratio, status, cfg)
    pivot_points, pivot_reason, pivot_failure = _score_nhathoai_vcp_pivot(candles, base_start, pivot, cfg)
    stop_points, stop_reason, stop_failure = _score_nhathoai_vcp_stop_score(pivot, stop, cfg)

    score = (
        prior_points
        + base_points
        + count_points
        + shrink_points
        + tight_points
        + volume_points
        + pivot_points
        + stop_points
    )
    failures = [
        *([] if prior_points else [prior_failure]),
        *([] if base_points else [base_failure]),
        *([] if count_points else [count_failure]),
        *([] if shrink_points else [shrink_failure]),
        *([] if tight_points else [tight_failure]),
        *([] if volume_points else [volume_failure]),
        *([] if pivot_points else [pivot_failure]),
        *([] if stop_points else [stop_failure]),
    ]

    if prior_points == 0:
        score = min(score, 50)
    if shrink_points == 0:
        score = min(score, 60)
    if tight_points == 0:
        score = min(score, 70)
    if distance_to_pivot_pct is None or distance_to_pivot_pct > cfg.near_pivot_pct:
        score = min(score, 75)
    if volume_ratio is None:
        score = min(score, 85)
    if status in {"DEVELOPING", "LATE", "FAILED", "REJECT"}:
        failures.append(f"Status is {status}, not an active VCP entry candidate")
    if status == "TRIGGERED" and not _nhathoai_vcp_breakout_volume_ok(candles):
        score = min(score, 79)
        failures.append("Breakout volume does not confirm the pivot break")
    if score < 80 and status in {"NEAR_PIVOT", "WAITING", "TRIGGERED"}:
        status = "REJECT"
        failures.append(f"Score {score:.0f} is below required VCP threshold 80")

    reasons = [
        prior_reason,
        base_reason,
        count_reason,
        shrink_reason,
        tight_reason,
        volume_reason,
        pivot_reason,
        stop_reason,
    ]
    return _NhathoaiVCPSetup(
        status=status,
        score=max(0.0, score),
        pivot=pivot,
        current_close=current_close,
        distance_to_pivot_pct=distance_to_pivot_pct,
        stop=stop,
        base_start_index=base_start,
        base_end_index=base_end,
        contractions=contractions,
        volume_ratio=volume_ratio,
        prior_uptrend_pct=prior_uptrend_pct,
        reasons=[reason for reason in reasons if reason],
        failures=[failure for failure in failures if failure],
    )


def _score_nhathoai_vcp_prior_trend(
    candles: list[Candle],
    cfg: VCPConfig,
    pre_base: list[Candle],
    base: list[Candle],
    prior_uptrend_pct: float | None,
) -> tuple[float, str, str]:
    if not pre_base or not base or prior_uptrend_pct is None:
        return 0, "", "No measurable prior uptrend before the base"
    closes = [c.close for c in candles]
    ema_values = _ema(closes, cfg.ema_period)
    base_start = len(candles) - len(base)
    lookback_start = max(0, base_start - cfg.pre_base_days)
    trend_closes = closes[lookback_start:base_start]
    trend_emas = ema_values[lookback_start:base_start]
    side_ratio = (
        sum(1 for close, ema in zip(trend_closes, trend_emas, strict=True) if close >= ema) / len(trend_closes)
        if trend_closes
        else 0.0
    )
    if prior_uptrend_pct >= cfg.min_prior_uptrend_pct and side_ratio >= cfg.trend_above_ema_ratio:
        return 15, f"Prior trend: prior advance {prior_uptrend_pct:.1f}% with price above EMA21 {side_ratio:.0%} of the time", ""
    return 0, "", f"Prior trend is not strong enough: advance {prior_uptrend_pct:.1f}%, EMA side ratio {side_ratio:.0%}"


def _score_nhathoai_vcp_base(base: list[Candle], cfg: VCPConfig) -> tuple[float, str, str]:
    duration = len(base)
    depth = _base_depth_pct(base)
    if duration >= max(25, cfg.compression_lookback * 2) and cfg.min_range_depth_pct <= depth <= cfg.max_base_depth_pct:
        return 10, f"Base duration: {duration} candles with controlled depth {depth:.1f}%", ""
    return 0, "", f"Base is not a clear VCP digestion area: {duration} candles, depth {depth:.1f}%"


def _score_nhathoai_vcp_contraction_count(contractions: list[Contraction]) -> tuple[float, str, str]:
    if len(contractions) >= 4:
        return 15, f"Flexible contraction count: {len(contractions)} contraction(s) found", ""
    if len(contractions) == 3:
        return 15, "Flexible contraction count: 3 contraction(s) found", ""
    if len(contractions) == 2:
        return 13, "Flexible contraction count: 2 clear contractions found", ""
    if len(contractions) == 1:
        return 0, "", "Need at least 2 contractions; single contraction is a developing watch only, not actionable VCP"
    return 0, "", "No measurable contraction found"


def _score_nhathoai_vcp_shrinking(
    contractions: list[Contraction],
    cfg: VCPConfig,
) -> tuple[float, str, str]:
    if len(contractions) < 2:
        if contractions:
            return 10, "Contraction structure: single contraction, so shrinking cannot be compared yet", ""
        return 0, "", "Contractions are not enough to prove shrinking volatility"
    depths = " -> ".join(f"{item.depth_pct:.1f}%" for item in contractions)
    lows_ok = _has_rising_lows(contractions, cfg.low_tolerance_pct)
    if _is_tightening(contractions, cfg.depth_tolerance_pct) and lows_ok:
        return 20, f"Contractions shrink clearly: {depths}, with lows holding higher/tighter", ""
    if _is_tightening(contractions, cfg.depth_tolerance_pct):
        return 14, f"Contractions shrink clearly: {depths}, but lows are not perfectly higher", ""
    return 0, "", f"Contractions do not shrink cleanly: {depths}"


def _score_nhathoai_vcp_right_side(
    candles: list[Candle],
    base_start: int,
    pivot: float,
    cfg: VCPConfig,
) -> tuple[float, str, str]:
    final = candles[max(base_start, len(candles) - cfg.compression_lookback) :]
    if len(final) < 5 or pivot <= 0:
        return 0, "", "Right-side tightness cannot be measured"
    tightness = _base_depth_pct(final)
    current = candles[-1].close
    distance = ((pivot - current) / pivot) * 100
    base = candles[base_start:]
    base_low = min(c.low for c in base)
    upper_half = min(c.low for c in final) >= base_low + (pivot - base_low) * 0.45
    close_to_pivot = -cfg.max_boundary_distance_pct <= distance <= cfg.near_pivot_pct
    if tightness <= cfg.max_final_contraction_depth_pct and close_to_pivot and upper_half:
        return 15, f"Right-side tightness: final area depth {tightness:.1f}% and price is {distance:.2f}% from pivot", ""
    return 0, "", f"Right side is not tight/actionable: final depth {tightness:.1f}%, distance {distance:.2f}%"


def _score_nhathoai_vcp_volume(
    candles: list[Candle],
    volume_ratio: float | None,
    status: str,
    cfg: VCPConfig,
) -> tuple[float, str, str]:
    if volume_ratio is None:
        return 0, "Volume behavior: volume unavailable; price-only VCP evidence has lower confidence", "Volume dry-up cannot be confirmed"
    if status == "TRIGGERED":
        if volume_ratio <= 0.90 and _nhathoai_vcp_breakout_volume_ok(candles):
            return 10, f"Volume behavior: dry-up ratio {volume_ratio:.2f} and breakout volume expands", ""
        return 0, "", f"Triggered VCP lacks volume confirmation: dry-up ratio {volume_ratio:.2f}"
    if volume_ratio <= cfg.volume_dry_up_ratio:
        return 10, f"Volume behavior: dry-up confirmed with late/base ratio {volume_ratio:.2f}", ""
    return 0, "", f"Volume does not dry up enough: late/base ratio {volume_ratio:.2f}"


def _score_nhathoai_vcp_pivot(
    candles: list[Candle],
    base_start: int,
    pivot: float,
    cfg: VCPConfig,
) -> tuple[float, str, str]:
    base = candles[base_start:-1] or candles[base_start:]
    touches = _boundary_touches(base, pivot, cfg.boundary_touch_tolerance_pct)
    if touches >= cfg.min_boundary_touches:
        return 10, f"Pivot / trigger level: {_fmt_price(pivot)} with {touches} resistance touch(es)", ""
    return 0, "", f"Pivot is not clear enough: {_fmt_price(pivot)} has only {touches} touch(es)"


def _score_nhathoai_vcp_stop_score(
    pivot: float | None,
    stop: float | None,
    cfg: VCPConfig,
) -> tuple[float, str, str]:
    if pivot is None or stop is None or pivot <= 0 or stop <= 0:
        return 0, "", "Stop-loss area is missing"
    risk_pct = (pivot - stop) / pivot * 100
    if 0 < risk_pct <= max(8.0, cfg.max_signal_range_pct):
        return 5, f"Stop-loss area: {_fmt_price(stop)} below final contraction, risk {risk_pct:.1f}% from pivot", ""
    return 0, "", f"Stop-loss is too wide from pivot: {risk_pct:.1f}%"


def _nhathoai_vcp_status(
    candles: list[Candle],
    pivot: float,
    stop: float | None,
    cfg: VCPConfig,
) -> str:
    latest = candles[-1]
    previous = candles[-2] if len(candles) >= 2 else latest
    if pivot <= 0:
        return "REJECT"
    if stop is not None and latest.close < stop:
        return "FAILED"
    if previous.close > pivot and latest.close < pivot:
        return "FAILED"
    if latest.close > pivot:
        extension = (latest.close - pivot) / pivot * 100
        if previous.close <= pivot and extension <= cfg.max_boundary_distance_pct:
            return "TRIGGERED"
        return "LATE"
    distance = (pivot - latest.close) / pivot * 100
    if 0 <= distance <= min(3.0, cfg.near_pivot_pct):
        return "WAITING"
    if 0 <= distance <= cfg.near_pivot_pct:
        return "NEAR_PIVOT"
    return "DEVELOPING"


def _nhathoai_vcp_status_rank(status: str) -> int:
    return {
        "TRIGGERED": 7,
        "WAITING": 6,
        "NEAR_PIVOT": 5,
        "DEVELOPING": 4,
        "LATE": 3,
        "FAILED": 2,
        "REJECT": 1,
    }.get(status, 0)


def _nhathoai_vcp_breakout_volume_ok(candles: list[Candle]) -> bool:
    if len(candles) < 22 or candles[-1].volume <= 0:
        return False
    prior = [c.volume for c in candles[-21:-1] if c.volume > 0]
    if len(prior) < 10:
        return False
    return candles[-1].volume >= mean(prior) * 1.20


def _nhathoai_vcp_stop(
    candles: list[Candle],
    contractions: list[Contraction],
    base_start: int,
) -> float | None:
    if contractions:
        return contractions[-1].low
    final = candles[max(base_start, len(candles) - 12) :]
    if not final:
        return None
    return min(c.low for c in final)


def _empty_nhathoai_vcp(failures: list[str]) -> _NhathoaiVCPSetup:
    return _NhathoaiVCPSetup(
        status="REJECT",
        score=0.0,
        pivot=None,
        current_close=None,
        distance_to_pivot_pct=None,
        stop=None,
        base_start_index=None,
        base_end_index=None,
        contractions=[],
        volume_ratio=None,
        prior_uptrend_pct=None,
        reasons=[],
        failures=failures,
    )


def _nhathoai_vcp_output_lines(result: _NhathoaiVCPSetup, candles: list[Candle]) -> list[str]:
    return [
        "Pattern: VCP",
        f"Status: {result.status}",
        f"Score: {result.score:.0f}",
        f"Prior trend: {result.prior_uptrend_pct:.1f}% prior advance" if result.prior_uptrend_pct is not None else "Prior trend: n/a",
        f"Base duration: {_date_range_text(candles, result.base_start_index, result.base_end_index)}",
        *_nhathoai_vcp_contraction_lines(result.contractions),
        f"Right-side tightness: final contraction area is near pivot {_fmt_price(result.pivot)}",
        f"Volume behavior: dry-up ratio {_fmt_price(result.volume_ratio)}" if result.volume_ratio is not None else "Volume behavior: n/a",
        f"Pivot / trigger level: {_fmt_price(result.pivot)}",
        f"Current price: {_fmt_price(result.current_close)}",
        f"Distance to pivot: {result.distance_to_pivot_pct:.2f}%" if result.distance_to_pivot_pct is not None else "Distance to pivot: n/a",
        f"Stop-loss area: {_fmt_price(result.stop)}",
        f"Risk comment: stop should stay close under final contraction; do not chase if price extends away from {_fmt_price(result.pivot)}",
        "Market context: not measured by this OHLCV-only scanner",
        "Reason:",
        *[f"- {reason}" for reason in result.reasons[:8]],
        "Manual review note:",
        "- Confirm prior leadership, shrinking contractions, volume dry-up, pivot quality, breakout volume if triggered, and market context before acting.",
    ]


def _nhathoai_vcp_reject_lines(result: _NhathoaiVCPSetup) -> list[str]:
    if result.status in {"DEVELOPING", "NEAR_PIVOT"} and result.score >= 60:
        return [
            "Pattern: VCP",
            f"Status: {result.status}",
            f"Score: {result.score:.0f}",
            "Reason:",
            *[f"- {reason}" for reason in result.reasons[:6]],
            *[f"- {failure}" for failure in result.failures[:4]],
            "Manual review note:",
            "- Watch only if this is not qualified. Do not enter until the right side tightens, price approaches pivot, and volume dries up.",
        ]
    failures = result.failures or ["Reject reason: VCP story is incomplete or unclear"]
    return [
        "Pattern: VCP",
        "Status: REJECT",
        f"Score: {result.score:.0f}",
        "Reject reason:",
        *[f"- {failure}" for failure in failures[:8]],
    ]


def _nhathoai_vcp_contraction_lines(contractions: list[Contraction]) -> list[str]:
    lines = []
    for index, item in enumerate(contractions, start=1):
        lines.append(
            f"Contraction {index}: {_fmt_price(item.high)} -> {_fmt_price(item.low)} ({item.depth_pct:.1f}%)"
        )
    if not lines:
        lines.append("Contraction 1: n/a")
    return lines


def _detect_bob_volman_setup(context: _NhathoaiContext, setup_name: str) -> VCPEvidence:
    long_setup = _score_bob_volman_direction(context, setup_name, "long")
    short_setup = _score_bob_volman_direction(context, setup_name, "short")
    result = max([long_setup, short_setup], key=lambda item: item.score)
    threshold = 85 if setup_name == "irb" else 75
    qualified = result.score >= threshold and not result.failures
    distance_to_trigger = None
    if result.trigger:
        if result.direction == "long":
            distance_to_trigger = ((result.trigger - context.current_close) / result.trigger) * 100
        else:
            distance_to_trigger = ((context.current_close - result.trigger) / result.trigger) * 100

    reasons = [
        f"Pattern name: {result.name.upper()}",
        f"Direction: {result.direction}",
        f"Entry trigger level: {result.trigger:.5f}" if result.trigger is not None else "Entry trigger level: n/a",
        f"Invalidation level: {result.stop:.5f}" if result.stop is not None else "Invalidation level: n/a",
        "Status: Candidate for manual review" if qualified else "Status: Reject",
    ] + result.reasons
    failures = result.failures
    if result.score < threshold:
        failures = failures + [f"Score {result.score:.1f} is below required threshold {threshold}"]

    return VCPEvidence(
        qualified=qualified,
        status=f"candidate_nhathoai_{setup_name}_{result.direction}" if qualified else "rejected",
        score=result.score if qualified else 0.0,
        pivot=result.trigger,
        current_close=context.current_close,
        distance_to_pivot_pct=distance_to_trigger,
        contractions=[],
        reasons=reasons,
        failures=failures,
        base_start_index=result.base_start,
        base_end_index=len(context.closes) - 1,
        volume_dry_up_ratio=_window_volume_ratio_from_context(context),
        prior_uptrend_pct=None,
    )


def _score_bob_volman_direction(context: _NhathoaiContext, setup_name: str, direction: str) -> _BVSetup:
    score = 0.0
    reasons: list[str] = []
    failures: list[str] = []

    context_points, context_reason, context_failure = _score_context(context, setup_name, direction)
    score += context_points
    _append_score("Context/range", context_points, context_reason, context_failure, reasons, failures)

    ema_points, ema_reason, ema_failure = _score_ema_respect(context, direction)
    score += ema_points
    _append_score("EMA21 respect", ema_points, ema_reason, ema_failure, reasons, failures)

    structure = _setup_structure(context, setup_name, direction)
    score += structure["compression_points"]
    _append_score(
        "Compression/pullback",
        structure["compression_points"],
        structure["compression_reason"],
        structure["compression_failure"],
        reasons,
        failures,
    )

    score += structure["trigger_points"]
    _append_score(
        "Trigger level",
        structure["trigger_points"],
        structure["trigger_reason"],
        structure["trigger_failure"],
        reasons,
        failures,
    )

    candle_points, candle_reason, candle_failure = _score_breakout_candle(context, direction, structure["trigger"])
    score += candle_points
    _append_score("Breakout candle", candle_points, candle_reason, candle_failure, reasons, failures)

    stop = _stop_level(context, direction, structure["stop"])
    stop_points, stop_reason, stop_failure = _score_stop(context, direction, stop)
    score += stop_points
    _append_score("Stop-loss area", stop_points, stop_reason, stop_failure, reasons, failures)

    return _BVSetup(
        name=setup_name,
        direction=direction,
        score=score,
        trigger=structure["trigger"],
        stop=stop,
        base_start=structure["base_start"],
        reasons=reasons,
        failures=failures,
    )


def _append_score(
    label: str,
    points: float,
    reason: str,
    failure: str,
    reasons: list[str],
    failures: list[str],
) -> None:
    if points > 0:
        reasons.append(f"{label}: {reason} ({points:.0f} pts)")
    else:
        failures.append(f"{label}: {failure}")


def _score_context(context: _NhathoaiContext, setup_name: str, direction: str) -> tuple[float, str, str]:
    if setup_name in {"rb", "irb", "arb", "fb"}:
        window = context.setup[:-1]
        depth = _base_depth_pct(window)
        touches_high = _boundary_touches(window, max(c.high for c in window), context.cfg.boundary_touch_tolerance_pct)
        touches_low = _floor_touches(window, min(c.low for c in window), context.cfg.boundary_touch_tolerance_pct)
        if depth >= context.cfg.min_range_depth_pct and touches_high >= 2 and touches_low >= 2:
            return 20, f"clean range depth {depth:.1f}% with ceiling/floor touches", ""
        return 0, "", f"range is not clean enough (depth {depth:.1f}%, high touches {touches_high}, low touches {touches_low})"

    if setup_name in {"dd", "sb"}:
        impulse = _trend_impulse_pct(context, direction)
        if impulse >= 3:
            return 20, f"clear {direction} trend impulse of {impulse:.1f}%", ""
        return 0, "", f"trend impulse is only {impulse:.1f}%"

    if setup_name == "bb":
        if _clean_ema_behavior(context, direction):
            return 20, "clean directional pressure around EMA21", ""
        return 0, "", "price action is too messy around EMA21"

    return 0, "", "unknown setup context"


def _score_ema_respect(context: _NhathoaiContext, direction: str) -> tuple[float, str, str]:
    recent_count = min(25, len(context.setup))
    closes = context.closes[-recent_count:]
    emas = context.ema_values[-recent_count:]
    if direction == "long":
        direction_ok = context.current_ema >= context.previous_ema
        respect_ratio = sum(1 for close, ema in zip(closes, emas, strict=True) if close >= ema) / recent_count
    else:
        direction_ok = context.current_ema <= context.previous_ema
        respect_ratio = sum(1 for close, ema in zip(closes, emas, strict=True) if close <= ema) / recent_count
    crossings = _ema_crossings(closes, emas)
    if direction_ok and respect_ratio >= 0.65 and crossings <= 4:
        return 20, f"EMA21 respected with {respect_ratio:.0%} closes on the correct side and {crossings} crossing(s)", ""
    if direction_ok and respect_ratio >= 0.55 and crossings <= 6:
        return 12, f"EMA21 mostly respected with {respect_ratio:.0%} closes on the correct side", ""
    return 0, "", f"EMA21 respect failed: ratio {respect_ratio:.0%}, crossings {crossings}"


def _clean_ema_behavior(context: _NhathoaiContext, direction: str) -> bool:
    points, _, _ = _score_ema_respect(context, direction)
    return points >= 12


def _setup_structure(context: _NhathoaiContext, setup_name: str, direction: str) -> dict[str, object]:
    if setup_name == "rb":
        return _structure_range_break(context, direction)
    if setup_name == "bb":
        return _structure_block_break(context, direction)
    if setup_name == "irb":
        return _structure_inside_range_break(context, direction)
    if setup_name == "arb":
        return _structure_advance_range_break(context, direction)
    if setup_name == "dd":
        return _structure_double_doji(context, direction)
    if setup_name == "fb":
        return _structure_first_break(context, direction)
    if setup_name == "sb":
        return _structure_second_break(context, direction)
    raise ValueError(f"unknown nhathoai setup: {setup_name}")


def _structure_range_break(context: _NhathoaiContext, direction: str) -> dict[str, object]:
    box = context.setup[:-1]
    trigger = max(c.high for c in box) if direction == "long" else min(c.low for c in box)
    stop = min(c.low for c in context.compression) if direction == "long" else max(c.high for c in context.compression)
    compressed = _compression_is_tightening(context)
    near_side = _near_range_side(context.compression, trigger, direction, context.cfg.boundary_touch_tolerance_pct)
    return {
        "trigger": trigger,
        "stop": stop,
        "base_start": context.setup_start,
        "compression_points": 20 if compressed and near_side else 0,
        "compression_reason": "candles tighten near the range breakout side",
        "compression_failure": "price is not compressed near the range breakout side",
        "trigger_points": 15 if _trigger_close(context.setup[-1], trigger, direction) else 0,
        "trigger_reason": "latest candle closed beyond the range boundary",
        "trigger_failure": "latest candle did not close beyond the range boundary",
    }


def _structure_block_break(context: _NhathoaiContext, direction: str) -> dict[str, object]:
    block = context.setup[-13:-1]
    trigger = max(c.high for c in block) if direction == "long" else min(c.low for c in block)
    stop = min(c.low for c in block) if direction == "long" else max(c.high for c in block)
    block_range = _base_depth_pct(block)
    prior = context.setup[-25:-13]
    prior_range = _base_depth_pct(prior) if len(prior) >= 5 else block_range
    shape_ok = _rising_lows(block) if direction == "long" else _falling_highs(block)
    tight = block_range <= context.cfg.max_block_range_pct and block_range <= prior_range * 0.8 and shape_ok
    return {
        "trigger": trigger,
        "stop": stop,
        "base_start": len(context.closes) - len(block) - 1,
        "compression_points": 20 if tight else 0,
        "compression_reason": f"tight 5-12 candle block ({block_range:.1f}%) with directional pressure",
        "compression_failure": f"block is not tight or directional enough ({block_range:.1f}%)",
        "trigger_points": 15 if _trigger_close(context.setup[-1], trigger, direction) else 0,
        "trigger_reason": "latest candle closed beyond the block",
        "trigger_failure": "latest candle did not close beyond the block",
    }


def _structure_inside_range_break(context: _NhathoaiContext, direction: str) -> dict[str, object]:
    outer = context.setup[:-1]
    inner = context.compression[:-1] if len(context.compression) > 1 else context.compression
    trigger = max(c.high for c in outer) if direction == "long" else min(c.low for c in outer)
    stop = min(c.low for c in inner) if direction == "long" else max(c.high for c in inner)
    inner_range = _base_depth_pct(inner)
    outer_range = _base_depth_pct(outer)
    squeezed = inner_range <= outer_range * 0.55 and inner_range <= context.cfg.max_inside_range_pct
    near_side = _near_range_side(inner, trigger, direction, context.cfg.boundary_touch_tolerance_pct)
    return {
        "trigger": trigger,
        "stop": stop,
        "base_start": context.setup_start,
        "compression_points": 20 if squeezed and near_side else 0,
        "compression_reason": f"inner range is squeezed near one side ({inner_range:.1f}% vs outer {outer_range:.1f}%)",
        "compression_failure": "inside range is not tightly squeezed near the breakout side",
        "trigger_points": 15 if _trigger_close(context.setup[-1], trigger, direction) else 0,
        "trigger_reason": "latest candle closed outside the large range",
        "trigger_failure": "latest candle did not close outside the large range",
    }


def _structure_advance_range_break(context: _NhathoaiContext, direction: str) -> dict[str, object]:
    previous = context.setup[:-1]
    swings = _swing_points(previous, 0, len(previous) - 1, context.cfg.swing_window)
    points = [(idx, price) for idx, kind, price in swings if kind == ("high" if direction == "long" else "low")]
    trigger = None
    stop = None
    compression_points = 0
    compression_reason = ""
    compression_failure = "advance break needs two nearby highs/lows and a controlled pullback"
    base_start = context.setup_start
    if len(points) >= 2:
        first, second = points[-2], points[-1]
        spread = abs(second[1] - first[1]) / max(abs(second[1]), abs(first[1])) * 100
        between = previous[first[0] : second[0] + 1]
        pullback_controlled = _pullback_controlled(context, between, direction)
        trigger = max(first[1], second[1]) if direction == "long" else min(first[1], second[1])
        stop = min(c.low for c in between) if direction == "long" else max(c.high for c in between)
        base_start = context.setup_start + first[0]
        if spread <= context.cfg.max_double_level_spread_pct and pullback_controlled:
            compression_points = 20
            compression_reason = f"two similar {'highs' if direction == 'long' else 'lows'} with controlled pullback, spread {spread:.2f}%"
        else:
            compression_failure = f"advance levels spread {spread:.2f}% or pullback not controlled"
    return {
        "trigger": trigger,
        "stop": stop,
        "base_start": base_start,
        "compression_points": compression_points,
        "compression_reason": compression_reason,
        "compression_failure": compression_failure,
        "trigger_points": 15 if trigger is not None and _trigger_close(context.setup[-1], trigger, direction) else 0,
        "trigger_reason": "latest candle closed beyond both advance levels",
        "trigger_failure": "latest candle did not close beyond both advance levels",
    }


def _structure_double_doji(context: _NhathoaiContext, direction: str) -> dict[str, object]:
    dojis = context.setup[-3:-1]
    trigger = max(c.high for c in dojis) if direction == "long" else min(c.low for c in dojis)
    stop = min(c.low for c in dojis) if direction == "long" else max(c.high for c in dojis)
    doji_ok = (
        len(dojis) == 2
        and all(_is_doji(candle, context.cfg.doji_body_ratio) for candle in dojis)
        and all(_candle_near_ema(context, len(context.setup) - 3 + index, candle) for index, candle in enumerate(dojis))
        and all(_candle_range_pct(candle) <= context.cfg.max_signal_range_pct for candle in dojis)
    )
    return {
        "trigger": trigger,
        "stop": stop,
        "base_start": len(context.closes) - 3,
        "compression_points": 20 if doji_ok else 0,
        "compression_reason": "two small doji candles formed beside each other near EMA21",
        "compression_failure": "two latest setup candles are not small dojis near EMA21",
        "trigger_points": 15 if _trigger_close(context.setup[-1], trigger, direction) else 0,
        "trigger_reason": "next candle closed beyond both dojis",
        "trigger_failure": "next candle did not close beyond both dojis",
    }


def _structure_first_break(context: _NhathoaiContext, direction: str) -> dict[str, object]:
    box = context.setup[:18]
    after_break = context.setup[18:-1]
    box_high = max(c.high for c in box)
    box_low = min(c.low for c in box)
    box_trigger = box_high if direction == "long" else box_low
    breakout_seen = any(_trigger_close(candle, box_trigger, direction) and _strong_candle(candle, direction) for candle in after_break)
    pullback_ok = _pullback_to_level_or_ema(context, after_break, box_trigger, direction)
    trigger = max(c.high for c in after_break[-6:] or after_break) if direction == "long" else min(c.low for c in after_break[-6:] or after_break)
    stop = min(c.low for c in after_break[-6:] or after_break) if direction == "long" else max(c.high for c in after_break[-6:] or after_break)
    return {
        "trigger": trigger,
        "stop": stop,
        "base_start": context.setup_start,
        "compression_points": 20 if breakout_seen and pullback_ok else 0,
        "compression_reason": "strong first breakout followed by controlled pullback to old level/EMA21",
        "compression_failure": "first breakout or controlled pullback is missing",
        "trigger_points": 15 if _trigger_close(context.setup[-1], trigger, direction) else 0,
        "trigger_reason": "continuation candle closed beyond pullback resistance/support",
        "trigger_failure": "continuation trigger has not closed beyond the pullback level",
    }


def _structure_second_break(context: _NhathoaiContext, direction: str) -> dict[str, object]:
    earlier = context.setup[:20]
    pullback = context.setup[-8:-1]
    prior_move = _trend_impulse_pct_for_candles(earlier, direction)
    pullback_ok = _pullback_controlled(context, pullback, direction)
    trigger = max(c.high for c in pullback) if direction == "long" else min(c.low for c in pullback)
    stop = min(c.low for c in pullback) if direction == "long" else max(c.high for c in pullback)
    return {
        "trigger": trigger,
        "stop": stop,
        "base_start": len(context.closes) - len(pullback) - 1,
        "compression_points": 20 if prior_move >= 3 and pullback_ok else 0,
        "compression_reason": f"existing trend move ({prior_move:.1f}%) followed by controlled EMA21 pullback",
        "compression_failure": f"prior move ({prior_move:.1f}%) or controlled EMA21 pullback is missing",
        "trigger_points": 15 if _trigger_close(context.setup[-1], trigger, direction) else 0,
        "trigger_reason": "second continuation candle closed beyond small pullback level",
        "trigger_failure": "second continuation trigger has not closed beyond the pullback level",
    }


def _score_breakout_candle(context: _NhathoaiContext, direction: str, trigger: object) -> tuple[float, str, str]:
    candle = context.setup[-1]
    if trigger is None:
        return 0, "", "no trigger level exists"
    if not _trigger_close(candle, float(trigger), direction):
        return 0, "", "breakout candle did not close beyond trigger"
    if _strong_candle(candle, direction):
        return 15, "breakout candle is directional and closes strongly", ""
    return 0, "", "breakout candle is weak or mostly wick"


def _score_stop(context: _NhathoaiContext, direction: str, stop: float | None) -> tuple[float, str, str]:
    if stop is None or stop <= 0:
        return 0, "", "no logical invalidation level"
    close = context.current_close
    distance = ((close - stop) / close * 100) if direction == "long" else ((stop - close) / close * 100)
    if 0 < distance <= context.cfg.max_signal_range_pct:
        return 10, f"stop is close and logical at {distance:.2f}% from close", ""
    return 0, "", f"stop distance {distance:.2f}% is not close/logical"


def _stop_level(context: _NhathoaiContext, direction: str, proposed: object) -> float | None:
    if proposed is None:
        return None
    proposed_float = float(proposed)
    candle = context.setup[-1]
    if direction == "long":
        return max(proposed_float, candle.low)
    return min(proposed_float, candle.high)


def _window_volume_ratio_from_context(context: _NhathoaiContext) -> float | None:
    synthetic = [
        Candle(c.datetime, c.open, c.high, c.low, c.close, c.volume)
        for c in context.setup
    ]
    return _window_volume_ratio(synthetic, max(0, len(synthetic) - context.cfg.compression_lookback))


def _ema_crossings(closes: list[float], emas: list[float]) -> int:
    if len(closes) < 2:
        return 0
    signs = [1 if close >= ema else -1 for close, ema in zip(closes, emas, strict=True)]
    return sum(1 for index in range(1, len(signs)) if signs[index] != signs[index - 1])


def _trigger_close(candle: Candle, trigger: float, direction: str) -> bool:
    if direction == "long":
        return candle.close > trigger and candle.close > candle.open
    return candle.close < trigger and candle.close < candle.open


def _strong_candle(candle: Candle, direction: str) -> bool:
    candle_range = candle.high - candle.low
    if candle_range <= 0:
        return False
    body_ratio = abs(candle.close - candle.open) / candle_range
    if body_ratio < 0.45:
        return False
    close_position = (candle.close - candle.low) / candle_range
    if direction == "long":
        return candle.close > candle.open and close_position >= 0.65
    return candle.close < candle.open and close_position <= 0.35


def _near_range_side(candles: list[Candle], trigger: float, direction: str, tolerance_pct: float) -> bool:
    if trigger <= 0 or not candles:
        return False
    if direction == "long":
        average_high = mean(c.high for c in candles)
        return abs(trigger - average_high) / trigger * 100 <= tolerance_pct * 2.0
    average_low = mean(c.low for c in candles)
    return abs(average_low - trigger) / trigger * 100 <= tolerance_pct * 2.0


def _rising_lows(candles: list[Candle]) -> bool:
    if len(candles) < 4:
        return False
    midpoint = len(candles) // 2
    return mean(c.low for c in candles[midpoint:]) >= mean(c.low for c in candles[:midpoint]) * 0.995


def _falling_highs(candles: list[Candle]) -> bool:
    if len(candles) < 4:
        return False
    midpoint = len(candles) // 2
    return mean(c.high for c in candles[midpoint:]) <= mean(c.high for c in candles[:midpoint]) * 1.005


def _pullback_controlled(context: _NhathoaiContext, candles: list[Candle], direction: str) -> bool:
    if not candles:
        return False
    setup_offset = max(0, len(context.setup) - len(candles) - 1)
    ema_segment = context.ema_values[context.setup_start + setup_offset : context.setup_start + setup_offset + len(candles)]
    if direction == "long":
        deepest = min(c.low for c in candles)
        recent_high = max(c.high for c in context.setup)
        if recent_high <= 0 or not ema_segment:
            return False
        pullback_depth = (recent_high - deepest) / recent_high * 100
        return deepest >= min(ema_segment) * (1 - context.cfg.max_pullback_ema_distance_pct / 100) and pullback_depth <= context.cfg.max_later_contraction_depth_pct
    highest = max(c.high for c in candles)
    recent_low = min(c.low for c in context.setup)
    if recent_low <= 0 or not ema_segment:
        return False
    pullback_depth = (highest - recent_low) / recent_low * 100
    return highest <= max(ema_segment) * (1 + context.cfg.max_pullback_ema_distance_pct / 100) and pullback_depth <= context.cfg.max_later_contraction_depth_pct


def _pullback_to_level_or_ema(
    context: _NhathoaiContext,
    candles: list[Candle],
    level: float,
    direction: str,
) -> bool:
    if not candles or level <= 0:
        return False
    start = max(0, len(context.setup) - len(candles) - 1)
    for offset, candle in enumerate(candles):
        ema = context.ema_values[context.setup_start + min(start + offset, len(context.setup) - 1)]
        if direction == "long":
            near_level = abs(candle.low - level) / level * 100 <= context.cfg.max_retest_distance_pct
            near_ema = candle.low <= ema * (1 + context.cfg.max_pullback_ema_distance_pct / 100)
            not_deep = candle.close >= level * (1 - context.cfg.max_retest_distance_pct / 100)
            if (near_level or near_ema) and not_deep:
                return True
        else:
            near_level = abs(candle.high - level) / level * 100 <= context.cfg.max_retest_distance_pct
            near_ema = candle.high >= ema * (1 - context.cfg.max_pullback_ema_distance_pct / 100)
            not_deep = candle.close <= level * (1 + context.cfg.max_retest_distance_pct / 100)
            if (near_level or near_ema) and not_deep:
                return True
    return False


def _trend_impulse_pct(context: _NhathoaiContext, direction: str) -> float:
    return _trend_impulse_pct_for_candles(context.setup[-25:], direction)


def _trend_impulse_pct_for_candles(candles: list[Candle], direction: str) -> float:
    if len(candles) < 3:
        return 0.0
    start = candles[0].close
    if start <= 0:
        return 0.0
    if direction == "long":
        return (max(c.high for c in candles) - start) / start * 100
    return (start - min(c.low for c in candles)) / start * 100


def _nhathoai_context(candles: list[Candle], cfg: VCPConfig) -> _NhathoaiContext | VCPEvidence:
    min_needed = max(cfg.min_history_days, cfg.ema_period + cfg.setup_lookback + cfg.ema_slope_lookback)
    if len(candles) < min_needed:
        return _not_qualified(f"Need at least {min_needed} candles, got {len(candles)}")
    closes = [c.close for c in candles]
    ema_values = _ema(closes, cfg.ema_period)
    setup_start = max(0, len(candles) - cfg.setup_lookback)
    compression_start = max(0, len(candles) - cfg.compression_lookback)
    return _NhathoaiContext(
        cfg=cfg,
        closes=closes,
        ema_values=ema_values,
        setup_start=setup_start,
        setup=candles[setup_start:],
        compression_start=compression_start,
        compression=candles[compression_start:],
        current_close=candles[-1].close,
        current_ema=ema_values[-1],
        previous_ema=ema_values[-1 - cfg.ema_slope_lookback],
    )


def _require_trend_pullback_context(context: _NhathoaiContext, reasons: list[str], failures: list[str]) -> None:
    _require_ema_support(context, reasons, failures)
    if _has_recent_impulse(context):
        reasons.append("Recent impulse is present before the pullback")
    else:
        failures.append("No clear recent impulse before the pullback")
    if _has_ema_pullback(context):
        reasons.append(f"Pullback returned to EMA{context.cfg.ema_period} support area")
    else:
        failures.append(f"No clean pullback to EMA{context.cfg.ema_period} support area")


def _require_ema_support(context: _NhathoaiContext, reasons: list[str], failures: list[str]) -> None:
    if context.current_ema > context.previous_ema:
        reasons.append(f"EMA{context.cfg.ema_period} is rising")
    else:
        failures.append(f"EMA{context.cfg.ema_period} is not rising")

    recent_count = min(20, len(context.setup))
    recent_closes = context.closes[-recent_count:]
    recent_ema = context.ema_values[-recent_count:]
    above_ratio = sum(1 for close, ema in zip(recent_closes, recent_ema, strict=True) if close >= ema) / recent_count
    if above_ratio >= context.cfg.trend_above_ema_ratio:
        reasons.append(f"Trend pressure confirmed: {above_ratio:.0%} of recent closes above EMA")
    else:
        failures.append(
            f"Trend pressure is weak: {above_ratio:.0%} of recent closes above EMA, "
            f"need {context.cfg.trend_above_ema_ratio:.0%}"
        )

    ema_distance_pct = abs((context.current_close - context.current_ema) / context.current_ema) * 100
    if context.current_close >= context.current_ema * (1 - context.cfg.max_pullback_ema_distance_pct / 100):
        reasons.append(f"Price is supported by EMA area: {ema_distance_pct:.2f}% from EMA")
    else:
        failures.append(
            f"Price is {ema_distance_pct:.2f}% from EMA support, above "
            f"{context.cfg.max_pullback_ema_distance_pct:.2f}%"
        )


def _require_range_context(context: _NhathoaiContext, reasons: list[str], failures: list[str]) -> None:
    range_depth = _base_depth_pct(context.setup)
    if range_depth >= context.cfg.min_range_depth_pct:
        reasons.append(f"Range is visible at {range_depth:.1f}% depth")
    else:
        failures.append(f"Range depth is {range_depth:.1f}%, below {context.cfg.min_range_depth_pct:.1f}%")
    _require_ema_support(context, reasons, failures)
    if _compression_is_tightening(context):
        reasons.append("Current action is compressed versus the prior range")
    else:
        failures.append("Current action is not compressed versus the prior range")


def _nh_dd(context: _NhathoaiContext) -> tuple[float | None, list[str], list[str], int]:
    reasons: list[str] = []
    failures: list[str] = []
    recent = context.setup[-3:]
    dojis = recent[-2:]
    if len(dojis) == 2 and all(_is_doji(candle, context.cfg.doji_body_ratio) for candle in dojis):
        reasons.append("DD structure: two consecutive doji candles at the pullback")
    else:
        failures.append("DD requires two consecutive doji candles")
    if len(dojis) == 2 and all(_candle_near_ema(context, len(context.setup) - 2 + index, candle) for index, candle in enumerate(dojis)):
        reasons.append(f"Both doji candles sit near EMA{context.cfg.ema_period}")
    else:
        failures.append(f"DD doji candles are not both near EMA{context.cfg.ema_period}")
    signal_range_pct = _candle_range_pct(dojis[-1]) if dojis else 100.0
    if signal_range_pct <= context.cfg.max_signal_range_pct:
        reasons.append(f"Signal doji range is controlled at {signal_range_pct:.1f}%")
    else:
        failures.append(f"Signal doji range is {signal_range_pct:.1f}%, above {context.cfg.max_signal_range_pct:.1f}%")
    pivot = max((c.high for c in dojis), default=None)
    return pivot, reasons, failures, len(context.closes) - len(dojis)


def _nh_fb(context: _NhathoaiContext) -> tuple[float | None, list[str], list[str], int]:
    reasons: list[str] = []
    failures: list[str] = []
    pullback_start = _last_ema_pullback_start(context)
    if pullback_start is None:
        failures.append("FB requires a first pullback to EMA before the break")
        pullback_start = max(0, len(context.setup) - context.cfg.compression_lookback)
    else:
        reasons.append("FB structure: first pullback to EMA is in place")
    pullback = context.setup[pullback_start:]
    if len(pullback) > 12:
        failures.append(f"FB pullback has {len(pullback)} candles, too mature for a first break")
    else:
        reasons.append(f"FB pullback is fresh with {len(pullback)} candles")
    pivot = max((c.high for c in pullback[:-1] or pullback), default=None)
    touches = _boundary_touches(pullback, pivot or 0, context.cfg.boundary_touch_tolerance_pct)
    if 1 <= touches <= 2:
        reasons.append(f"FB remains an early break attempt with {touches} boundary touch(es)")
    else:
        failures.append(f"FB has {touches} boundary touches, not a clean first break")
    return pivot, reasons, failures, context.setup_start + pullback_start


def _nh_sb(context: _NhathoaiContext) -> tuple[float | None, list[str], list[str], int]:
    reasons: list[str] = []
    failures: list[str] = []
    swings = _swing_points(context.setup, 0, len(context.setup) - 1, context.cfg.swing_window)
    highs = [(index, price) for index, swing_type, price in swings if swing_type == "high"]
    if len(highs) >= 2:
        first, second = highs[-2], highs[-1]
        spread = abs(second[1] - first[1]) / max(second[1], first[1]) * 100
        separation = second[0] - first[0]
        if spread <= context.cfg.max_double_level_spread_pct:
            reasons.append(f"SB structure: second break forming near prior high, spread {spread:.2f}%")
        else:
            failures.append(
                f"SB double-level spread is {spread:.2f}%, above {context.cfg.max_double_level_spread_pct:.2f}%"
            )
        if 4 <= separation <= 20:
            reasons.append(f"SB attempts are separated by {separation} candles")
        else:
            failures.append(f"SB attempts are separated by {separation} candles, outside 4-20 candle range")
        pullback_between = context.setup[first[0] : second[0] + 1]
        if min(c.low for c in pullback_between) <= context.ema_values[context.setup_start + second[0]] * (
            1 + context.cfg.max_pullback_ema_distance_pct / 100
        ):
            reasons.append("SB second attempt follows a pullback toward EMA support")
        else:
            failures.append("SB second attempt did not follow an EMA pullback")
        pivot = max(first[1], second[1])
        base_start = context.setup_start + first[0]
    else:
        failures.append("SB requires two nearby break attempts")
        pivot = max((c.high for c in context.setup[:-1] or context.setup), default=None)
        base_start = context.setup_start
    return pivot, reasons, failures, base_start


def _nh_bb(context: _NhathoaiContext) -> tuple[float | None, list[str], list[str], int]:
    reasons: list[str] = []
    failures: list[str] = []
    block = context.compression
    pivot = max((c.high for c in block[:-1] or block), default=None)
    block_range = _base_depth_pct(block)
    if block_range <= context.cfg.max_block_range_pct:
        reasons.append(f"BB structure: compact block range at {block_range:.1f}%")
    else:
        failures.append(f"BB block range is {block_range:.1f}%, above {context.cfg.max_block_range_pct:.1f}%")
    if _compression_is_tightening(context):
        reasons.append("BB block is tighter than the previous price action")
    else:
        failures.append("BB block is not tighter than the previous price action")
    touches = _boundary_touches(block, pivot or 0, context.cfg.boundary_touch_tolerance_pct)
    if touches >= context.cfg.min_boundary_touches:
        reasons.append(f"Block boundary has {touches} pressure touch(es)")
    else:
        failures.append(f"Block boundary has {touches} pressure touch(es), need {context.cfg.min_boundary_touches}")
    return pivot, reasons, failures, context.compression_start


def _nh_rb(context: _NhathoaiContext) -> tuple[float | None, list[str], list[str], int]:
    reasons: list[str] = []
    failures: list[str] = []
    range_window = context.setup
    pivot = max((c.high for c in range_window[:-1] or range_window), default=None)
    touches = _boundary_touches(range_window, pivot or 0, context.cfg.boundary_touch_tolerance_pct)
    floor_touches = _floor_touches(range_window, min(c.low for c in range_window), context.cfg.boundary_touch_tolerance_pct)
    if touches >= context.cfg.min_boundary_touches:
        reasons.append(f"RB structure: range ceiling has {touches} pressure touch(es)")
    else:
        failures.append(f"RB range ceiling has {touches} pressure touch(es), need {context.cfg.min_boundary_touches}")
    if floor_touches >= context.cfg.min_boundary_touches:
        reasons.append(f"RB structure: range floor has {floor_touches} touch(es)")
    else:
        failures.append(f"RB range floor has {floor_touches} touch(es), need {context.cfg.min_boundary_touches}")
    if _base_depth_pct(context.compression) <= _base_depth_pct(range_window):
        reasons.append("Current action is pressing inside a broader range")
    else:
        failures.append("Current action is wider than the broader range structure")
    return pivot, reasons, failures, context.setup_start


def _nh_irb(context: _NhathoaiContext) -> tuple[float | None, list[str], list[str], int]:
    reasons: list[str] = []
    failures: list[str] = []
    outer_high = max(c.high for c in context.setup)
    outer_low = min(c.low for c in context.setup)
    inner = context.compression
    pivot = max((c.high for c in inner[:-1] or inner), default=None)
    inner_range = _base_depth_pct(inner)
    if pivot is not None and pivot < outer_high * (1 - context.cfg.boundary_touch_tolerance_pct / 100):
        reasons.append("IRB structure: trigger sits inside the broader range, not at the outer high")
    else:
        failures.append("IRB trigger is not clearly inside the broader range")
    if min(c.low for c in inner) > outer_low:
        reasons.append("IRB structure: recent lows stay inside the outer range")
    else:
        failures.append("IRB recent lows broke the outer range low")
    if inner_range <= context.cfg.max_inside_range_pct:
        reasons.append(f"Inside range is compact at {inner_range:.1f}%")
    else:
        failures.append(f"Inside range is {inner_range:.1f}%, above {context.cfg.max_inside_range_pct:.1f}%")
    if inner_range <= _base_depth_pct(context.setup) * 0.65:
        reasons.append("Inside range is meaningfully smaller than the outer range")
    else:
        failures.append("Inside range is not meaningfully smaller than the outer range")
    return pivot, reasons, failures, context.compression_start


def _nh_arb(context: _NhathoaiContext) -> tuple[float | None, list[str], list[str], int]:
    reasons: list[str] = []
    failures: list[str] = []
    early = context.setup[: max(5, len(context.setup) - context.cfg.compression_lookback)]
    retest = context.compression
    early_high = max(c.high for c in early)
    early_low = min(c.low for c in early)
    early_range = early_high - early_low
    break_level = early_high
    broke_early = any(c.high > early_high for c in context.setup[len(early) : -1])
    if broke_early:
        reasons.append("ARB structure: prior bait break above the range is visible")
    else:
        failures.append("ARB requires a prior bait break before the retest")
    retest_distance = min(abs(c.low - break_level) for c in retest) / break_level * 100
    if retest_distance <= context.cfg.max_retest_distance_pct:
        reasons.append(f"Retest returned to the broken range within {retest_distance:.2f}%")
    else:
        failures.append(
            f"Retest is {retest_distance:.2f}% from broken range, above {context.cfg.max_retest_distance_pct:.2f}%"
        )
    if early_range > 0 and min(c.low for c in retest) >= early_low:
        reasons.append("Retest held above the original range low")
    else:
        failures.append("Retest did not hold the original range")
    pivot = max((c.high for c in retest[:-1] or retest), default=None)
    return pivot, reasons, failures, context.setup_start


def _has_ema_pullback(context: _NhathoaiContext) -> bool:
    threshold = 1 + context.cfg.max_pullback_ema_distance_pct / 100
    start = len(context.closes) - len(context.setup)
    for offset, candle in enumerate(context.setup):
        ema = context.ema_values[start + offset]
        if candle.low <= ema * threshold:
            return True
    return False


def _has_recent_impulse(context: _NhathoaiContext) -> bool:
    lookback = min(25, len(context.setup))
    start_close = context.setup[-lookback].close
    recent_high = max(c.high for c in context.setup[-lookback:])
    if start_close <= 0:
        return False
    impulse_pct = (recent_high - start_close) / start_close * 100
    return impulse_pct >= 2.0 and context.current_ema > context.previous_ema


def _compression_is_tightening(context: _NhathoaiContext) -> bool:
    prior = context.setup[
        max(0, len(context.setup) - context.cfg.compression_lookback * 2) : len(context.setup) - context.cfg.compression_lookback
    ]
    if len(prior) < 4:
        return False
    compression_range = _base_depth_pct(context.compression)
    prior_range = _base_depth_pct(prior)
    return compression_range <= context.cfg.max_compression_range_pct and compression_range <= prior_range * 0.85


def _candle_near_ema(context: _NhathoaiContext, setup_offset: int, candle: Candle) -> bool:
    ema = context.ema_values[context.setup_start + setup_offset]
    if ema <= 0:
        return False
    return candle.low <= ema * (1 + context.cfg.max_pullback_ema_distance_pct / 100)


def _last_ema_pullback_start(context: _NhathoaiContext) -> int | None:
    threshold = 1 + context.cfg.max_pullback_ema_distance_pct / 100
    start = len(context.closes) - len(context.setup)
    for offset in range(len(context.setup) - 1, -1, -1):
        candle = context.setup[offset]
        ema = context.ema_values[start + offset]
        if candle.low <= ema * threshold:
            return max(0, offset - 2)
    return None


def _is_doji(candle: Candle, max_body_ratio: float) -> bool:
    candle_range = candle.high - candle.low
    if candle_range <= 0:
        return False
    return abs(candle.close - candle.open) / candle_range <= max_body_ratio


def _candle_range_pct(candle: Candle) -> float:
    if candle.high <= 0:
        return 100.0
    return (candle.high - candle.low) / candle.high * 100


def _floor_touches(candles: list[Candle], floor: float, tolerance_pct: float) -> int:
    if floor <= 0:
        return 0
    upper = floor * (1 + tolerance_pct / 100)
    return sum(1 for candle in candles if floor * 0.998 <= candle.low <= upper)


def _detect_contractions(candles: list[Candle], base_start: int, cfg: VCPConfig) -> list[Contraction]:
    swings = _swing_points(candles, base_start, len(candles) - 1, cfg.swing_window)
    pairs: list[Contraction] = []

    for position, swing in enumerate(swings):
        swing_index, swing_type, swing_price = swing
        if swing_type != "high":
            continue
        following_lows = [item for item in swings[position + 1 :] if item[1] == "low"]
        if not following_lows:
            continue
        low_index, _, low_price = following_lows[0]
        depth_pct = ((swing_price - low_price) / swing_price) * 100
        if depth_pct < cfg.min_contraction_depth_pct:
            continue
        if not pairs and depth_pct > cfg.max_first_contraction_depth_pct:
            continue
        if pairs and depth_pct > cfg.max_later_contraction_depth_pct:
            continue
        pairs.append(
            Contraction(
                start_index=swing_index,
                end_index=low_index,
                start_date=candles[swing_index].datetime,
                end_date=candles[low_index].datetime,
                high=swing_price,
                low=low_price,
                depth_pct=depth_pct,
            )
        )

    # Keep the most recent non-overlapping contraction sequence.
    non_overlapping: list[Contraction] = []
    for item in pairs:
        if non_overlapping and item.start_index <= non_overlapping[-1].end_index:
            continue
        non_overlapping.append(item)
    return non_overlapping[-cfg.max_contractions :]


def _swing_points(
    candles: list[Candle],
    start: int,
    end: int,
    window: int,
) -> list[tuple[int, str, float]]:
    swings: list[tuple[int, str, float]] = []
    left = max(start + window, window)
    right = min(end - window, len(candles) - window - 1)

    for index in range(left, right + 1):
        segment = candles[index - window : index + window + 1]
        high = candles[index].high
        low = candles[index].low
        if high == max(c.high for c in segment) and high > candles[index - 1].high and high >= candles[index + 1].high:
            swings.append((index, "high", high))
        if low == min(c.low for c in segment) and low < candles[index - 1].low and low <= candles[index + 1].low:
            swings.append((index, "low", low))

    return _dedupe_adjacent_swings(swings)


def _dedupe_adjacent_swings(swings: list[tuple[int, str, float]]) -> list[tuple[int, str, float]]:
    if not swings:
        return swings

    deduped = [swings[0]]
    for index, swing_type, price in swings[1:]:
        last_index, last_type, last_price = deduped[-1]
        if swing_type != last_type:
            deduped.append((index, swing_type, price))
            continue
        if (swing_type == "high" and price > last_price) or (swing_type == "low" and price < last_price):
            deduped[-1] = (index, swing_type, price)
        elif index - last_index > 3:
            deduped.append((index, swing_type, price))
    return deduped


def _is_tightening(contractions: list[Contraction], tolerance_pct: float) -> bool:
    return all(
        contractions[index].depth_pct <= contractions[index - 1].depth_pct + tolerance_pct
        for index in range(1, len(contractions))
    )


def _has_rising_lows(contractions: list[Contraction], tolerance_pct: float) -> bool:
    return all(
        contractions[index].low >= contractions[index - 1].low * (1 - tolerance_pct / 100)
        for index in range(1, len(contractions))
    )


def _pivot_spread_pct(contractions: list[Contraction]) -> float:
    highs = [item.high for item in contractions]
    if not highs:
        return 0.0
    highest = max(highs)
    if highest <= 0:
        return 100.0
    return ((highest - min(highs)) / highest) * 100


def _vcp_pivot_contractions(contractions: list[Contraction], cfg: VCPConfig) -> list[Contraction]:
    if not contractions:
        return []
    # The actionable Minervini pivot is the right-side resistance/tight area.
    # The first contraction can begin from a wider left-side high, so using all
    # contraction highs can incorrectly reject otherwise clean 2C/3C structures.
    return contractions[-2:] if len(contractions) >= 2 else contractions


def _base_depth_pct(base: list[Candle]) -> float:
    highest = max(c.high for c in base)
    lowest = min(c.low for c in base)
    if highest <= 0:
        return 100.0
    return ((highest - lowest) / highest) * 100


def _volume_dry_up_ratio(
    candles: list[Candle],
    base_start: int,
    contractions: list[Contraction],
) -> float | None:
    if not contractions:
        return None
    base_volumes = [c.volume for c in candles[base_start:contractions[0].start_index] if c.volume > 0]
    if len(base_volumes) < 5:
        base_volumes = [c.volume for c in candles[base_start:] if c.volume > 0]
    late_start = contractions[-1].start_index
    late_volumes = [c.volume for c in candles[late_start:] if c.volume > 0]
    if len(base_volumes) < 5 or len(late_volumes) < 3:
        return None
    return mean(late_volumes) / mean(base_volumes)


def _window_volume_ratio(candles: list[Candle], recent_start: int) -> float | None:
    prior = [c.volume for c in candles[max(0, recent_start - 30) : recent_start] if c.volume > 0]
    recent = [c.volume for c in candles[recent_start:] if c.volume > 0]
    if len(prior) < 5 or len(recent) < 3:
        return None
    return mean(recent) / mean(prior)


def _prior_uptrend_pct(pre_base: list[Candle], base: list[Candle]) -> float | None:
    if len(pre_base) < 10 or not base:
        return None
    reference_low = min(c.low for c in pre_base)
    base_start_close = base[0].close
    if reference_low <= 0:
        return None
    return ((base_start_close - reference_low) / reference_low) * 100


def _score(
    qualified: bool,
    contractions: list[Contraction],
    distance_to_pivot_pct: float,
    volume_ratio: float | None,
    prior_uptrend_pct: float | None,
    cfg: VCPConfig,
) -> float:
    if not qualified:
        return 0.0
    contraction_bonus = min(len(contractions), cfg.max_contractions) * 10
    proximity_bonus = max(0.0, (cfg.near_pivot_pct - distance_to_pivot_pct) / cfg.near_pivot_pct) * 25
    volume_bonus = 20 if volume_ratio is not None else 0
    if volume_ratio is not None:
        volume_bonus = max(0.0, (cfg.volume_dry_up_ratio - volume_ratio) / cfg.volume_dry_up_ratio) * 20
    uptrend_bonus = min((prior_uptrend_pct or 0) / cfg.min_prior_uptrend_pct, 2.0) * 10
    return min(100.0, 35 + contraction_bonus + proximity_bonus + volume_bonus + uptrend_bonus)


def _nhathoai_score(
    qualified: bool,
    reasons: list[str],
    failures: list[str],
    distance_to_boundary_pct: float,
    compression_range_pct: float,
    cfg: VCPConfig,
) -> float:
    if not qualified:
        return 0.0
    proximity_bonus = max(0.0, (cfg.max_boundary_distance_pct - distance_to_boundary_pct) / cfg.max_boundary_distance_pct) * 20
    compression_bonus = max(0.0, (cfg.max_compression_range_pct - compression_range_pct) / cfg.max_compression_range_pct) * 20
    structure_bonus = min(len(reasons), 10) * 3
    penalty = len(failures) * 12
    return min(95.0, max(0.0, 40 + proximity_bonus + compression_bonus + structure_bonus - penalty))


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    ema_values = [values[0]]
    for value in values[1:]:
        ema_values.append((value - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


def _boundary_touches(candles: list[Candle], boundary: float, tolerance_pct: float) -> int:
    if boundary <= 0:
        return 0
    lower = boundary * (1 - tolerance_pct / 100)
    return sum(1 for candle in candles if lower <= candle.high <= boundary * 1.002)


def _support_touches(candles: list[Candle], boundary: float, tolerance_pct: float) -> int:
    if boundary <= 0:
        return 0
    upper = boundary * (1 + tolerance_pct / 100)
    return sum(1 for candle in candles if boundary * 0.998 <= candle.low <= upper)


def _atr(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < 2:
        return None
    true_ranges: list[float] = []
    for previous, current in zip(candles, candles[1:], strict=False):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    if not true_ranges:
        return None
    return mean(true_ranges[-period:])


def _not_qualified(message: str) -> VCPEvidence:
    return VCPEvidence(
        qualified=False,
        status="rejected",
        score=0.0,
        pivot=None,
        current_close=None,
        distance_to_pivot_pct=None,
        contractions=[],
        reasons=[],
        failures=[message],
    )


def _not_configured(message: str) -> VCPEvidence:
    return VCPEvidence(
        qualified=False,
        status="not_configured",
        score=0.0,
        pivot=None,
        current_close=None,
        distance_to_pivot_pct=None,
        contractions=[],
        reasons=[],
        failures=[message],
    )
