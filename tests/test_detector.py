from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from filter_pattern.detector import detect_ema21_compression, detect_pattern, detect_vcp
from filter_pattern.models import Candle, VCPConfig


NHATHOAI_SETUP_NAMES = ["dd", "fb", "sb", "bb", "rb", "irb", "arb", "vcp"]


def test_valid_vcp_with_three_contractions_is_ready_near_pivot() -> None:
    candles = make_series([20, 13, 6], current_close=96, late_volume=80_000)

    evidence = detect_vcp(candles, make_config())

    assert evidence.qualified
    assert evidence.status == "ready_near_pivot"
    assert len(evidence.contractions) == 3
    assert evidence.pivot is not None
    assert 0 < evidence.distance_to_pivot_pct <= 5


def test_valid_vcp_with_two_contractions() -> None:
    candles = make_series([18, 8], current_close=96, late_volume=80_000)

    evidence = detect_vcp(candles, make_config())

    assert evidence.qualified
    assert len(evidence.contractions) == 2


def test_valid_vcp_with_four_contractions() -> None:
    candles = make_series([22, 15, 9, 5], current_close=96, late_volume=80_000)

    evidence = detect_vcp(candles, make_config())

    assert evidence.qualified
    assert len(evidence.contractions) == 4


def test_rejects_expanding_contractions() -> None:
    candles = make_series([8, 13, 18], current_close=96, late_volume=80_000)

    evidence = detect_vcp(candles, make_config())

    assert not evidence.qualified
    assert any("not tightening" in failure for failure in evidence.failures)


def test_rejects_missing_prior_uptrend() -> None:
    candles = make_series([20, 12, 6], current_close=96, late_volume=80_000, prior_start=79, prior_end=80)

    evidence = detect_vcp(candles, make_config())

    assert not evidence.qualified
    assert any("Prior uptrend" in failure for failure in evidence.failures)


def test_rejects_missing_volume_dry_up() -> None:
    candles = make_series([20, 12, 6], current_close=96, late_volume=220_000)

    evidence = detect_vcp(candles, make_config())

    assert not evidence.qualified
    assert any("volume ratio" in failure for failure in evidence.failures)


def test_rejects_already_broken_out() -> None:
    candles = make_series([20, 12, 6], current_close=101, late_volume=80_000)

    evidence = detect_vcp(candles, make_config())

    assert not evidence.qualified
    assert any("already at or above pivot" in failure for failure in evidence.failures)


def test_rejects_non_rising_contraction_lows() -> None:
    candles = make_series_from_points(
        [
            (0, 80),
            (6, 100),
            (14, 88),
            (24, 99),
            (32, 82),
            (42, 98),
            (50, 80),
            (89, 96),
        ],
        late_volume=80_000,
    )

    evidence = detect_vcp(candles, make_config())

    assert not evidence.qualified
    assert any("lows are not rising" in failure for failure in evidence.failures)


def test_experimental_ema21_compression_setup() -> None:
    candles = make_series([8, 6, 4], current_close=96, late_volume=160_000)
    for index in range(len(candles) - 12, len(candles)):
        candle = candles[index]
        candles[index] = Candle(
            datetime=candle.datetime,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=60_000,
        )

    evidence = detect_ema21_compression(candles, make_config())

    assert evidence.qualified
    assert evidence.status == "WAITING"
    assert any("EMA21" in reason for reason in evidence.reasons)
    assert any("Volume dry-up" in reason for reason in evidence.reasons)


@pytest.mark.parametrize("setup", NHATHOAI_SETUP_NAMES)
def test_each_nhathoai_setup_returns_rule_based_evidence(setup: str) -> None:
    candles = make_series([20, 12, 6], current_close=96, late_volume=80_000)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup=setup)

    assert evidence.status != "not_configured"
    assert evidence.current_close is not None or not evidence.qualified
    assert evidence.reasons or evidence.failures


def test_nhathoai_rejects_unknown_setup() -> None:
    candles = make_series([20, 12, 6], current_close=96, late_volume=80_000)

    try:
        detect_pattern(candles, "nhathoai", make_config(), setup="unknown")
    except ValueError as exc:
        assert "unknown setup" in str(exc)
    else:
        raise AssertionError("expected ValueError")


@pytest.mark.parametrize("setup", ["dd", "fb", "sb", "bb", "rb", "irb", "arb"])
def test_nhathoai_rejects_flat_loose_market_for_each_price_action_setup(setup: str) -> None:
    candles = make_flat_series()

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup=setup)

    assert not evidence.qualified
    assert evidence.status == "rejected"
    assert evidence.failures


def test_nhathoai_dd_requires_two_latest_doji_candles() -> None:
    candles = make_series([8, 6, 4], current_close=96, late_volume=80_000)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="dd")

    assert not evidence.qualified
    assert any("doji" in failure.lower() for failure in evidence.failures)


def test_nhathoai_vcp_detects_waiting_near_pivot_with_shrinking_contractions() -> None:
    candles = make_series([20, 10, 4], current_close=99, late_volume=60_000)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="vcp")

    assert evidence.qualified
    assert evidence.status == "WAITING"
    assert evidence.score >= 80
    output = "\n".join(evidence.reasons)
    assert "Pattern: VCP" in output
    assert "Contraction 1:" in output
    assert "Contraction 2:" in output
    assert "Contraction 3:" in output
    assert "Volume behavior:" in output


def test_nhathoai_vcp_detects_triggered_breakout_with_volume() -> None:
    candles = make_triggered_nhathoai_vcp_series()

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="vcp")

    assert evidence.qualified
    assert evidence.status == "TRIGGERED"
    assert evidence.score >= 80
    output = "\n".join(evidence.reasons)
    assert "Pattern: VCP" in output
    assert "Status: TRIGGERED" in output
    assert "breakout volume expands" in output


def test_nhathoai_vcp_rejects_single_contraction_as_not_actionable() -> None:
    candles = make_series([4], current_close=99, late_volume=60_000)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="vcp")

    assert not evidence.qualified
    assert len(evidence.contractions) == 1
    output = "\n".join(evidence.failures).lower()
    assert "at least 2" in output or "single contraction" in output


def test_nhathoai_vcp_rejects_expanding_contractions() -> None:
    candles = make_series([8, 13, 18], current_close=99, late_volume=60_000)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="vcp")

    assert not evidence.qualified
    assert evidence.score < 80


def test_dd_detects_bullish_triggered_pullback_to_ema21() -> None:
    candles = make_bullish_dd_series(triggered=True)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="dd")

    assert evidence.qualified
    assert evidence.status == "TRIGGERED"
    assert evidence.score >= 80
    output = "\n".join(evidence.reasons)
    assert "Pattern: DD" in output
    assert "Direction: Long" in output
    assert "Doji cluster:" in output
    assert "Signal level:" in output


def test_dd_detects_bullish_waiting_near_doji_signal() -> None:
    candles = make_bullish_dd_series(triggered=False)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="dd")

    assert evidence.qualified
    assert evidence.status == "WAITING"
    assert evidence.score >= 80
    assert any("waiting" in reason.lower() for reason in evidence.reasons)


def test_dd_rejects_sharp_pullback_that_breaks_trend() -> None:
    candles = make_bullish_dd_series(triggered=True, sharp_pullback=True)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="dd")

    assert not evidence.qualified
    reject_output = "\n".join(evidence.failures).lower()
    assert "pullback" in reject_output or "trend" in reject_output or "doji" in reject_output


def test_sb_detects_bullish_second_break_triggered() -> None:
    candles = make_bullish_sb_series(triggered=True)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="sb")

    assert evidence.qualified
    assert evidence.status == "TRIGGERED"
    assert evidence.score >= 80
    output = "\n".join(evidence.reasons)
    assert "Pattern: SB" in output
    assert "Direction: Long" in output
    assert "First break:" in output
    assert "First break failure:" in output
    assert "Second break trigger:" in output


def test_sb_detects_bullish_second_break_waiting() -> None:
    candles = make_bullish_sb_series(triggered=False)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="sb")

    assert evidence.qualified
    assert evidence.status == "WAITING"
    assert evidence.score >= 80
    assert any("waiting" in reason.lower() for reason in evidence.reasons)


def test_sb_rejects_first_break_without_failure() -> None:
    candles = make_bullish_sb_first_break_only_series()

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="sb")

    assert not evidence.qualified
    reject_output = "\n".join(evidence.failures).lower()
    assert "failure" in reject_output or "second-break" in reject_output or "structure" in reject_output


def test_bb_detects_bullish_type1_block_break_triggered() -> None:
    candles = make_bullish_bb_type1_series(triggered=True)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="bb")

    assert evidence.qualified
    assert evidence.status == "TRIGGERED"
    assert evidence.score >= 80
    output = "\n".join(evidence.reasons)
    assert "Pattern: BB" in output
    assert "Direction: Long" in output
    assert "BB Type: Type 1 block at end of diagonal pullback" in output
    assert "Block description:" in output
    assert "Signal boundary:" in output


def test_bb_detects_bullish_type1_block_break_waiting() -> None:
    candles = make_bullish_bb_type1_series(triggered=False)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="bb")

    assert evidence.qualified
    assert evidence.status == "WAITING"
    assert evidence.score >= 80
    assert any("Breakout trigger is close" in reason for reason in evidence.reasons)


def test_bb_rejects_wide_random_block() -> None:
    candles = make_bullish_bb_type1_series(triggered=True, wide_block=True)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="bb")

    assert not evidence.qualified
    reject_output = "\n".join(evidence.failures).lower()
    assert "block" in reject_output


def test_rb_detects_bullish_true_range_break_triggered() -> None:
    candles = make_bullish_rb_series(triggered=True)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="rb")

    assert evidence.qualified
    assert evidence.status == "TRIGGERED"
    assert evidence.score >= 80
    output = "\n".join(evidence.reasons)
    assert "Pattern: RB" in output
    assert "Direction: Long" in output
    assert "Breakout type:" in output
    assert "- TRUE_RB" in output
    assert "Upper range boundary:" in output
    assert "Build-up description:" in output


def test_rb_detects_bullish_true_range_break_waiting() -> None:
    candles = make_bullish_rb_series(triggered=False)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="rb")

    assert evidence.qualified
    assert evidence.status == "WAITING"
    assert evidence.score >= 80
    assert any("Breakout trigger is close" in reason for reason in evidence.reasons)


def test_rb_rejects_bait_tease_break_with_buildup_far_from_boundary() -> None:
    candles = make_bullish_rb_series(triggered=True, bait=True)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="rb")

    assert not evidence.qualified
    output = "\n".join(evidence.failures)
    assert "WATCH_BAIT_BREAK" in output or "BAIT_TEASE_BREAK" in output


def test_irb_detects_bullish_inner_range_break_triggered() -> None:
    candles = make_bullish_irb_series(triggered=True)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="irb")

    assert evidence.qualified
    assert evidence.status == "TRIGGERED"
    assert evidence.score >= 80
    output = "\n".join(evidence.reasons)
    assert "Pattern: IRB" in output
    assert "Direction: Long" in output
    assert "Inner buildup/block description:" in output
    assert "Target boundary:" in output


def test_irb_detects_bullish_inner_range_break_waiting() -> None:
    candles = make_bullish_irb_series(triggered=False)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="irb")

    assert evidence.qualified
    assert evidence.status == "WAITING"
    assert evidence.score >= 80
    assert any("Break trigger is close" in reason for reason in evidence.reasons)


def test_irb_rejects_inner_block_with_poor_reward_to_boundary() -> None:
    candles = make_bullish_irb_series(triggered=True, poor_reward=True)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="irb")

    assert not evidence.qualified
    output = "\n".join(evidence.failures).lower()
    assert "risk/reward" in output or "target" in output


def test_arb_detects_bullish_type1_after_first_breakout_and_buildup() -> None:
    candles = make_bullish_arb_type1_series(triggered=True)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="arb")

    assert evidence.qualified
    assert evidence.status == "TRIGGERED"
    assert evidence.score >= 80
    output = "\n".join(evidence.reasons)
    assert "Pattern: ARB" in output
    assert "Direction: Long" in output
    assert "ARB Type: Outside Build-up" in output
    assert "First breakout candle:" in output
    assert "Second trigger level:" in output


def test_arb_detects_bullish_type1_waiting_near_second_trigger() -> None:
    candles = make_bullish_arb_type1_series(triggered=False)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="arb")

    assert evidence.qualified
    assert evidence.status == "WAITING"
    assert evidence.score >= 80
    assert any("Second trigger is close" in reason for reason in evidence.reasons)


def test_arb_detects_type2a_pullback_from_far_after_first_breakout() -> None:
    candles = make_bullish_arb_type2a_series()

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="arb")

    assert evidence.qualified
    assert evidence.status == "TRIGGERED"
    output = "\n".join(evidence.reasons)
    assert "Pattern: ARB" in output
    assert "ARB Type: Type 2A Pullback from far" in output
    assert "Second trigger level:" in output


def test_fb_detects_first_pullback_break_to_ema21() -> None:
    candles = make_bullish_fb_series(triggered=True)

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="fb")

    assert evidence.qualified
    assert evidence.status == "TRIGGERED"
    assert evidence.score >= 80
    output = "\n".join(evidence.reasons)
    assert "Pattern: FB" in output
    assert "Direction: Long" in output
    assert "First pullback" in output
    assert "First break trigger:" in output


def test_arb_rejects_first_breakout_only() -> None:
    candles = make_arb_first_breakout_only_series()

    evidence = detect_pattern(candles, "nhathoai", make_config(), setup="arb")

    assert not evidence.qualified
    assert evidence.status == "rejected"
    reject_output = "\n".join(evidence.failures).lower()
    assert "first breakout" in reject_output or "build-up" in reject_output or "pullback" in reject_output


def test_detect_pattern_rejects_unknown_technique() -> None:
    candles = make_series([20, 12, 6], current_close=96, late_volume=80_000)

    try:
        detect_pattern(candles, "unknown", make_config())
    except ValueError as exc:
        assert "unknown technique" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def make_series(
    depths: list[float],
    current_close: float,
    late_volume: float,
    prior_start: float = 48,
    prior_end: float = 80,
) -> list[Candle]:
    start = datetime(2025, 1, 1)
    closes: list[float] = []
    volumes: list[float] = []

    for index in range(60):
        progress = index / 59
        closes.append(prior_start + (prior_end - prior_start) * progress)
        volumes.append(180_000)

    base_points: list[tuple[int, float]] = [(0, 80)]
    high_price = 100.0
    day = 6
    for depth in depths:
        base_points.append((day, high_price))
        low_price = high_price * (1 - depth / 100)
        base_points.append((day + 8, low_price))
        high_price -= 1.0
        day += 18
    base_points.append((89, current_close))

    base_closes = interpolate_points(base_points, length=90)
    for index, close in enumerate(base_closes):
        closes.append(close)
        volumes.append(220_000 if index < 12 else late_volume)

    candles = []
    for index, (close, volume) in enumerate(zip(closes, volumes, strict=True)):
        open_price = close * 0.995
        high = close * 1.004
        low = close * 0.996
        candles.append(
            Candle(
                datetime=start + timedelta(days=index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
    return candles


def make_series_from_points(points: list[tuple[int, float]], late_volume: float) -> list[Candle]:
    start = datetime(2025, 1, 1)
    closes: list[float] = []
    volumes: list[float] = []

    for index in range(60):
        progress = index / 59
        closes.append(48 + (80 - 48) * progress)
        volumes.append(180_000)

    for index, close in enumerate(interpolate_points(points, length=90)):
        closes.append(close)
        volumes.append(220_000 if index < 12 else late_volume)

    candles = []
    for index, (close, volume) in enumerate(zip(closes, volumes, strict=True)):
        candles.append(
            Candle(
                datetime=start + timedelta(days=index),
                open=close * 0.995,
                high=close * 1.004,
                low=close * 0.996,
                close=close,
                volume=volume,
            )
        )
    return candles


def make_triggered_nhathoai_vcp_series() -> list[Candle]:
    candles = make_series([20, 10, 4], current_close=99, late_volume=60_000)
    last = candles[-1]
    candles.append(
        Candle(
            datetime=last.datetime + timedelta(days=1),
            open=99.5,
            high=102.0,
            low=99.2,
            close=101.2,
            volume=300_000,
        )
    )
    return candles


def make_flat_series() -> list[Candle]:
    start = datetime(2025, 1, 1)
    candles = []
    for index in range(160):
        close = 100 + (0.3 if index % 2 else -0.3)
        candles.append(
            Candle(
                datetime=start + timedelta(days=index),
                open=close,
                high=close * 1.002,
                low=close * 0.998,
                close=close,
                volume=100_000,
            )
        )
    return candles


def make_bullish_dd_series(triggered: bool, sharp_pullback: bool = False) -> list[Candle]:
    start = datetime(2025, 1, 1)
    candles: list[Candle] = []

    def add(index: int, open_price: float, high: float, low: float, close: float) -> None:
        candles.append(
            Candle(
                datetime=start + timedelta(days=index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=150_000,
            )
        )

    index = 0
    for step in range(98):
        close = 70 + (20 * step / 97)
        add(index, close * 0.996, close * 1.006, close * 0.994, close)
        index += 1

    for step in range(16):
        close = 90 + (20 * step / 15)
        add(index, close * 0.996, close * 1.008, close * 0.994, close)
        index += 1

    if sharp_pullback:
        pullback = [
            (109.0, 109.3, 104.0, 104.6),
            (104.4, 104.8, 99.0, 100.2),
            (100.1, 101.0, 96.5, 97.4),
            (97.5, 98.2, 95.8, 96.6),
        ]
    else:
        pullback = [
            (109.5, 110.1, 107.6, 108.2),
            (108.1, 108.5, 106.4, 107.0),
            (106.9, 107.2, 105.3, 106.0),
            (105.9, 106.1, 104.4, 105.0),
            (105.0, 105.2, 103.7, 104.4),
        ]
    for open_price, high, low, close in pullback:
        add(index, open_price, high, low, close)
        index += 1

    dojis = [
        (104.25, 105.05, 103.75, 104.35),
        (104.35, 105.10, 103.85, 104.45),
    ]
    for open_price, high, low, close in dojis:
        add(index, open_price, high, low, close)
        index += 1

    if triggered:
        add(index, 104.8, 106.4, 104.6, 105.9)
    else:
        add(index, 104.45, 105.00, 103.95, 104.7)
    return candles


def make_bullish_sb_series(triggered: bool) -> list[Candle]:
    start = datetime(2025, 1, 1)
    candles: list[Candle] = []

    def add(index: int, open_price: float, high: float, low: float, close: float) -> None:
        candles.append(
            Candle(
                datetime=start + timedelta(days=index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=150_000,
            )
        )

    index = 0
    for step in range(98):
        close = 70 + (20 * step / 97)
        add(index, close * 0.996, close * 1.006, close * 0.994, close)
        index += 1

    for step in range(16):
        close = 90 + (20 * step / 15)
        add(index, close * 0.996, close * 1.008, close * 0.994, close)
        index += 1

    pullback = [
        (109.5, 110.1, 106.8, 107.5),
        (107.4, 107.8, 104.3, 105.2),
        (105.1, 105.4, 102.3, 103.1),
        (103.0, 103.2, 100.8, 101.5),
        (101.5, 101.9, 100.2, 101.0),
    ]
    for open_price, high, low, close in pullback:
        add(index, open_price, high, low, close)
        index += 1

    add(index, 101.0, 102.6, 100.7, 102.0)  # first break above previous high
    index += 1
    add(index, 101.8, 102.0, 99.8, 100.4)  # first break failure below previous low
    index += 1
    if triggered:
        add(index, 100.5, 103.2, 100.3, 102.8)  # second break above previous high
    else:
        add(index, 100.4, 102.4, 100.1, 102.0)  # waiting near trigger
    return candles


def make_bullish_sb_first_break_only_series() -> list[Candle]:
    candles = make_bullish_sb_series(triggered=False)[:-2]
    start = datetime(2025, 1, 1)
    index = len(candles)
    candles.append(
        Candle(
            datetime=start + timedelta(days=index),
            open=101.0,
            high=102.6,
            low=100.7,
            close=102.0,
            volume=150_000,
        )
    )
    return candles


def make_bullish_fb_series(triggered: bool) -> list[Candle]:
    start = datetime(2025, 1, 1)
    candles: list[Candle] = []

    def add(index: int, open_price: float, high: float, low: float, close: float) -> None:
        candles.append(
            Candle(
                datetime=start + timedelta(days=index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=150_000,
            )
        )

    index = 0
    for step in range(105):
        close = 74 + (14 * step / 104)
        add(index, close * 0.996, close * 1.006, close * 0.994, close)
        index += 1

    # New impulse before the first pullback.
    for step in range(10):
        close = 88 + (21 * step / 9)
        add(index, close * 0.996, close * 1.009, close * 0.994, close)
        index += 1

    # First clean one-wave pullback toward EMA21.
    pullback = [
        (108.7, 109.2, 105.8, 106.8),
        (106.7, 107.2, 102.8, 104.4),
        (104.2, 104.7, 100.8, 102.2),
        (102.1, 102.4, 99.7, 101.0),
    ]
    for open_price, high, low, close in pullback:
        add(index, open_price, high, low, close)
        index += 1

    if triggered:
        add(index, 101.4, 104.0, 101.1, 103.2)
    else:
        add(index, 101.1, 102.3, 100.2, 101.9)
    return candles


def make_bullish_bb_type1_series(triggered: bool, wide_block: bool = False) -> list[Candle]:
    start = datetime(2025, 1, 1)
    candles: list[Candle] = []

    def add(index: int, open_price: float, high: float, low: float, close: float) -> None:
        candles.append(
            Candle(
                datetime=start + timedelta(days=index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=150_000,
            )
        )

    index = 0
    for step in range(98):
        close = 70 + (20 * step / 97)
        add(index, close * 0.996, close * 1.006, close * 0.994, close)
        index += 1

    for step in range(16):
        close = 90 + (20 * step / 15)
        add(index, close * 0.996, close * 1.008, close * 0.994, close)
        index += 1

    pullback = [
        (109.4, 109.9, 107.2, 108.1),
        (108.0, 108.3, 105.9, 106.7),
        (106.6, 106.9, 104.9, 105.5),
        (105.4, 105.7, 103.8, 104.7),
    ]
    for open_price, high, low, close in pullback:
        add(index, open_price, high, low, close)
        index += 1

    block = (
        [
            (104.4, 107.8, 101.2, 106.8),
            (106.8, 108.3, 100.7, 102.1),
            (102.0, 107.4, 100.2, 106.9),
            (106.8, 109.2, 101.0, 102.6),
            (102.6, 108.4, 100.4, 106.4),
        ]
        if wide_block
        else [
            (104.45, 105.35, 103.95, 104.75),
            (104.75, 105.40, 104.05, 104.95),
            (104.90, 105.38, 104.12, 105.05),
            (105.00, 105.42, 104.20, 105.10),
            (105.05, 105.45, 104.30, 105.18),
        ]
    )
    for open_price, high, low, close in block:
        add(index, open_price, high, low, close)
        index += 1

    if triggered:
        add(index, 105.25, 106.8, 105.10, 106.15)
    else:
        add(index, 105.05, 105.42, 104.45, 105.25)
    return candles


def make_bullish_rb_series(triggered: bool, bait: bool = False) -> list[Candle]:
    start = datetime(2025, 1, 1)
    candles: list[Candle] = []

    def add(index: int, open_price: float, high: float, low: float, close: float) -> None:
        candles.append(
            Candle(
                datetime=start + timedelta(days=index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=150_000,
            )
        )

    index = 0
    for step in range(75):
        close = 96 + (0.25 if step % 2 else -0.25)
        add(index, close - 0.1, close + 0.5, close - 0.5, close)
        index += 1

    range_closes = [95.0, 99.0, 96.0, 100.0, 97.0, 94.2, 98.4, 95.5] * 6
    for step, close in enumerate(range_closes):
        high = 100.0 if step % 6 in {1, 3} else close + 0.65
        low = 94.0 if step % 8 in {5, 7} else close - 0.65
        add(index, close - 0.2, high, low, close)
        index += 1

    buildup = (
        [
            (97.3, 97.55, 97.20, 97.40),
            (97.4, 97.58, 97.25, 97.44),
            (97.42, 97.60, 97.28, 97.48),
            (97.45, 97.62, 97.30, 97.50),
            (97.48, 97.64, 97.32, 97.54),
        ]
        if bait
        else [
            (98.8, 99.60, 98.20, 99.15),
            (99.1, 99.70, 98.35, 99.30),
            (99.2, 99.75, 98.45, 99.35),
            (99.3, 99.82, 98.55, 99.45),
            (99.4, 99.86, 98.65, 99.55),
        ]
    )
    for open_price, high, low, close in buildup:
        add(index, open_price, high, low, close)
        index += 1

    if triggered:
        add(index, 99.7, 101.4, 99.4, 100.9)
    else:
        add(index, 99.45, 99.88, 98.80, 99.65)
    return candles


def make_bullish_irb_series(triggered: bool, poor_reward: bool = False) -> list[Candle]:
    start = datetime(2025, 1, 1)
    candles: list[Candle] = []

    def add(index: int, open_price: float, high: float, low: float, close: float) -> None:
        candles.append(
            Candle(
                datetime=start + timedelta(days=index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=150_000,
            )
        )

    index = 0
    for step in range(75):
        close = 97 + (0.25 if step % 2 else -0.25)
        add(index, close - 0.1, close + 0.5, close - 0.5, close)
        index += 1

    range_closes = [95.0, 99.0, 96.0, 100.0, 97.0, 94.2, 98.4, 95.5] * 6
    for step, close in enumerate(range_closes):
        high = 100.0 if step % 6 in {1, 3} else close + 0.65
        low = 94.0 if step % 8 in {5, 7} else close - 0.65
        add(index, close - 0.2, high, low, close)
        index += 1

    inner_block = (
        [
            (99.62, 99.98, 99.36, 99.78),
            (99.76, 100.02, 99.40, 99.84),
            (99.82, 100.05, 99.44, 99.88),
            (99.86, 100.08, 99.48, 99.92),
            (99.90, 100.10, 99.50, 99.96),
        ]
        if poor_reward
        else [
            (96.05, 96.85, 95.55, 96.35),
            (96.30, 96.95, 95.65, 96.50),
            (96.45, 97.00, 95.75, 96.65),
            (96.60, 97.08, 95.82, 96.78),
            (96.75, 97.12, 95.88, 96.90),
        ]
    )
    for open_price, high, low, close in inner_block:
        add(index, open_price, high, low, close)
        index += 1

    if triggered:
        if poor_reward:
            add(index, 100.02, 100.42, 99.88, 100.25)
        else:
            add(index, 96.95, 98.15, 96.80, 97.95)
    else:
        add(index, 96.85, 97.10, 96.40, 96.98)
    return candles


def make_bullish_arb_type1_series(triggered: bool) -> list[Candle]:
    start = datetime(2025, 1, 1)
    candles: list[Candle] = []

    def add(index: int, open_price: float, high: float, low: float, close: float) -> None:
        candles.append(
            Candle(
                datetime=start + timedelta(days=index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=150_000,
            )
        )

    index = 0
    for step in range(95):
        close = 70 + (25 * step / 94)
        add(index, close * 0.997, close * 1.006, close * 0.994, close)
        index += 1

    range_closes = [96.2, 98.9, 97.1, 99.1] * 6
    for step, close in enumerate(range_closes):
        high = 100.0 if step % 3 == 0 else close + 0.7
        low = 94.0 if step % 4 == 0 else close - 0.8
        add(index, close - 0.25, high, low, close)
        index += 1

    add(index, 99.3, 102.4, 98.9, 101.6)
    index += 1

    buildup = [
        (101.0, 102.0, 99.6, 101.4),
        (101.3, 102.3, 99.8, 101.7),
        (101.5, 102.4, 100.0, 101.9),
        (101.6, 102.5, 100.2, 102.0),
        (101.9, 102.6, 100.3, 102.1),
    ]
    for open_price, high, low, close in buildup:
        add(index, open_price, high, low, close)
        index += 1

    if triggered:
        add(index, 102.1, 104.0, 101.8, 103.4)
    else:
        add(index, 101.9, 102.55, 100.9, 102.2)
    return candles


def make_bullish_arb_type2a_series() -> list[Candle]:
    candles = make_bullish_arb_type1_series(triggered=False)[:-6]
    start = datetime(2025, 1, 1)
    index = len(candles)

    def add(open_price: float, high: float, low: float, close: float) -> None:
        nonlocal index
        candles.append(
            Candle(
                datetime=start + timedelta(days=index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=150_000,
            )
        )
        index += 1

    add(99.3, 102.4, 98.9, 101.6)
    add(101.8, 104.8, 101.5, 104.2)
    add(104.1, 106.8, 103.8, 106.1)
    add(106.0, 108.2, 105.4, 107.4)
    add(107.0, 107.5, 103.0, 104.0)
    add(104.0, 104.8, 101.0, 102.4)
    add(102.2, 103.5, 99.8, 101.8)
    add(101.8, 102.9, 100.4, 101.5)
    add(101.6, 102.6, 100.1, 101.7)
    add(102.0, 105.3, 101.7, 104.8)
    return candles


def make_arb_first_breakout_only_series() -> list[Candle]:
    candles = make_bullish_arb_type1_series(triggered=False)[:-6]
    index = len(candles)
    start = datetime(2025, 1, 1)
    candles.append(
        Candle(
            datetime=start + timedelta(days=index),
            open=99.3,
            high=102.4,
            low=98.9,
            close=101.6,
            volume=150_000,
        )
    )
    return candles


def interpolate_points(points: list[tuple[int, float]], length: int) -> list[float]:
    values = [points[0][1]] * length
    for (start_day, start_price), (end_day, end_price) in zip(points, points[1:], strict=False):
        span = end_day - start_day
        for day in range(start_day, min(end_day + 1, length)):
            progress = 0 if span == 0 else (day - start_day) / span
            values[day] = start_price + (end_price - start_price) * progress
    return values


def make_config() -> VCPConfig:
    return VCPConfig(
        min_history_days=120,
        max_base_days=90,
        pre_base_days=60,
        swing_window=2,
        min_prior_uptrend_pct=15,
        near_pivot_pct=5,
        volume_dry_up_ratio=0.7,
        max_final_contraction_depth_pct=12,
        low_tolerance_pct=1.5,
        max_pivot_spread_pct=10,
        max_base_depth_pct=45,
    )
