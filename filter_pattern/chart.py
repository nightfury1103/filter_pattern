from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import ticker as mticker
from matplotlib.patches import Rectangle

from .models import Candle, ScanResult, VCPConfig
from .util import safe_filename


UP_CANDLE_FACE = "#ffffff"
DOWN_CANDLE_FACE = "#111111"
CANDLE_EDGE = "#111111"
VOLUME_UP = "#d9d9d9"
VOLUME_DOWN = "#737373"
EMA_COLOR = "#1d4ed8"
PIVOT_COLOR = "#111111"
TRIGGER_COLOR = "#047857"
STOP_COLOR = "#b91c1c"
OBSTACLE_COLOR = "#c2410c"
BASE_LINE_WIDTH = 2.4
PRIMARY_LINE_WIDTH = 3.0
EMA_LINE_WIDTH = 3.4
ANNOTATION_FONT_SIZE = 10


def render_chart(
    result: ScanResult,
    candles: list[Candle],
    out_dir: str | Path,
    config: VCPConfig,
) -> Path:
    chart_dir = Path(out_dir)
    chart_dir.mkdir(parents=True, exist_ok=True)
    output_name = f"{result.symbol.symbol}_{result.technique}_{result.setup}"
    output_path = chart_dir / f"{safe_filename(output_name)}.jpg"

    evidence = result.evidence
    plot_candles = candles[-_chart_window(result.timeframe):]
    offset = len(candles) - len(plot_candles)
    dates = _session_positions(plot_candles)
    candle_width = _candle_width(dates)

    fig, (price_ax, volume_ax) = plt.subplots(
        2,
        1,
        figsize=_figure_size(result.timeframe),
        sharex=True,
        gridspec_kw={"height_ratios": [4, 1], "hspace": 0.03},
        constrained_layout=True,
    )
    fig.patch.set_facecolor("#ffffff")
    price_ax.set_facecolor("#ffffff")
    volume_ax.set_facecolor("#ffffff")

    _draw_candles(price_ax, plot_candles, dates, candle_width)
    _draw_ema(price_ax, plot_candles, dates, config.ema_period)
    _draw_volume(volume_ax, plot_candles, dates, candle_width)

    if _is_arb_evidence(evidence):
        _draw_arb_annotations(price_ax, candles, plot_candles, dates, offset, result, config)
    elif _is_dd_evidence(evidence):
        _draw_dd_annotations(price_ax, candles, plot_candles, dates, offset, result, config)
    elif _is_sb_evidence(evidence):
        _draw_sb_annotations(price_ax, candles, plot_candles, dates, offset, result, config)
    elif _is_bb_evidence(evidence):
        _draw_bb_annotations(price_ax, candles, plot_candles, dates, offset, result, config)
    elif _is_rb_evidence(evidence):
        _draw_rb_annotations(price_ax, candles, plot_candles, dates, offset, result, config)
    elif _is_irb_evidence(evidence):
        _draw_irb_annotations(price_ax, candles, plot_candles, dates, offset, result, config)
    elif _is_pivot_ema21_compression_evidence(evidence):
        _draw_pivot_ema21_compression_annotations(price_ax, candles, plot_candles, dates, offset, result, config)
    elif evidence.pivot is not None:
        price_ax.axhline(evidence.pivot, color=PIVOT_COLOR, linewidth=PRIMARY_LINE_WIDTH, label=f"Pivot {_price_label(evidence.pivot)}")
        lower = evidence.pivot * (1 - config.near_pivot_pct / 100)
        price_ax.axhspan(lower, evidence.pivot, color="#e5e7eb", alpha=0.45, label="Entry watch zone")
    if evidence.current_close is not None:
        price_ax.axhline(
            evidence.current_close,
            color="#111827",
            linestyle="--",
            linewidth=BASE_LINE_WIDTH,
            label=f"Current close {_price_label(evidence.current_close)}",
        )

    for index, contraction in enumerate(evidence.contractions, start=1):
        if contraction.end_index < offset:
            continue
        start = max(0, contraction.start_index - offset)
        end = max(0, contraction.end_index - offset)
        price_ax.axvspan(dates[start], dates[end], color="#fde68a", alpha=0.25)
        mid = dates[(start + end) // 2]
        price_ax.annotate(
            f"C{index}: {contraction.depth_pct:.1f}%",
            xy=(mid, contraction.low),
            xytext=(0, -20),
            textcoords="offset points",
            ha="center",
            fontsize=ANNOTATION_FONT_SIZE,
            color="#92400e",
            arrowprops={"arrowstyle": "-", "color": "#92400e", "linewidth": BASE_LINE_WIDTH},
        )

    title = (
        f"{result.symbol.symbol} ({result.symbol.market}) - "
        f"{result.timeframe} {result.technique.upper()} {result.setup.upper()} {evidence.status}"
    )
    price_ax.set_title(title, loc="left", fontsize=16, fontweight="bold", pad=12)
    subtitle = " | ".join(evidence.reasons[:3]) if evidence.qualified else " | ".join(evidence.failures[:3])
    if subtitle:
        price_ax.set_xlabel(subtitle, fontsize=10, color="#374151", labelpad=10)

    _emphasize_chart_artists(price_ax)
    price_ax.grid(True, color="#e5e7eb", linewidth=1.0)
    volume_ax.grid(True, axis="y", color="#e5e7eb", linewidth=1.0)
    price_ax.legend(loc="upper left", fontsize=10, frameon=True, facecolor="#ffffff", edgecolor="#d1d5db")
    price_ax.set_ylabel("Price", fontsize=11, fontweight="bold")
    volume_ax.set_ylabel("Volume", fontsize=11, fontweight="bold")
    price_ax.yaxis.set_major_formatter(_price_axis_formatter(plot_candles))
    volume_ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=10, integer=True))
    volume_ax.xaxis.set_major_formatter(_date_formatter(result.timeframe, plot_candles))
    price_ax.tick_params(axis="both", labelsize=10, width=1.2, colors="#111111")
    volume_ax.tick_params(axis="both", labelsize=9, width=1.2, colors="#111111")
    fig.autofmt_xdate()
    fig.savefig(
        output_path,
        dpi=120,
        format="jpg",
        pil_kwargs={"quality": 82, "optimize": True, "progressive": True},
    )
    plt.close(fig)
    return output_path


def _draw_candles(ax, candles: list[Candle], dates: list[float], width: float) -> None:
    body_floor = _minimum_body_height(candles)
    for candle, date in zip(candles, dates, strict=True):
        up = candle.close >= candle.open
        face = UP_CANDLE_FACE if up else DOWN_CANDLE_FACE
        ax.vlines(date, candle.low, candle.high, color=CANDLE_EDGE, linewidth=1.45, zorder=2)
        body_low = min(candle.open, candle.close)
        body_height = max(abs(candle.close - candle.open), body_floor)
        ax.add_patch(
            Rectangle(
                (date - width / 2, body_low),
                width,
                body_height,
                facecolor=face,
                edgecolor=CANDLE_EDGE,
                linewidth=1.15,
                zorder=3,
            )
        )
    padding = _date_step(dates) * 4
    ax.set_xlim(dates[0] - padding, dates[-1] + padding)


def _draw_volume(ax, candles: list[Candle], dates: list[float], width: float) -> None:
    colors = [VOLUME_UP if c.close >= c.open else VOLUME_DOWN for c in candles]
    ax.bar(dates, [c.volume for c in candles], color=colors, width=width)


def _draw_ema(ax, candles: list[Candle], dates: list[float], period: int) -> None:
    closes = [c.close for c in candles]
    if not closes:
        return
    multiplier = 2 / (period + 1)
    values = [closes[0]]
    for close in closes[1:]:
        values.append((close - values[-1]) * multiplier + values[-1])
    ax.plot(dates, values, color=EMA_COLOR, linewidth=EMA_LINE_WIDTH, label=f"EMA{period}", zorder=4)


def _chart_window(timeframe: str) -> int:
    return 96 if timeframe.upper() == "H4" else 140


def _figure_size(timeframe: str) -> tuple[float, float]:
    return (18, 9.5) if timeframe.upper() == "H4" else (16, 9)


def _session_positions(candles: list[Candle]) -> list[float]:
    return [float(index) for index, _ in enumerate(candles)]


def _emphasize_chart_artists(ax) -> None:
    for line in ax.lines:
        line.set_linewidth(max(line.get_linewidth(), BASE_LINE_WIDTH))
    for collection in ax.collections:
        if hasattr(collection, "set_linewidth"):
            collection.set_linewidth(max(BASE_LINE_WIDTH, 2.0))
    for patch in ax.patches:
        if isinstance(patch, Rectangle):
            if patch.get_zorder() == 3:
                continue
            patch.set_linewidth(max(patch.get_linewidth(), BASE_LINE_WIDTH))
    for text in ax.texts:
        text.set_fontsize(max(text.get_fontsize(), ANNOTATION_FONT_SIZE))


def _date_step(dates: list[float]) -> float:
    if len(dates) < 2:
        return 1.0
    gaps = [right - left for left, right in zip(dates, dates[1:], strict=False) if right > left]
    if not gaps:
        return 1.0
    gaps.sort()
    return gaps[len(gaps) // 2]


def _candle_width(dates: list[float]) -> float:
    return max(_date_step(dates) * 0.62, 0.015)


def _minimum_body_height(candles: list[Candle]) -> float:
    if not candles:
        return 1e-12
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [abs(c.close) for c in candles if c.close]
    visible_range = max(max(highs) - min(lows), max(closes or [1.0]) * 1e-6, 1e-12)
    return visible_range * 0.004


def _price_axis_formatter(candles: list[Candle]):
    reference = max((abs(c.close) for c in candles if c.close), default=1.0)

    def format_price(value: float, _position: int) -> str:
        return _price_label(value, reference)

    return mticker.FuncFormatter(format_price)


def _price_label(value: float | None, reference: float | None = None) -> str:
    if value is None:
        return "n/a"
    magnitude = abs(reference if reference is not None and reference != 0 else value)
    if magnitude >= 1000:
        return f"{value:,.2f}"
    if magnitude >= 1:
        return _trim_float(value, 4)
    if magnitude >= 0.01:
        return _trim_float(value, 6)
    if magnitude >= 0.0001:
        return _trim_float(value, 8)
    if magnitude >= 0.000001:
        return _trim_float(value, 10)
    return f"{value:.10g}"


def _trim_float(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}".rstrip("0").rstrip(".")


def _range_width(dates: list[float], start: int, end: int) -> float:
    return max(dates[end] - dates[start] + _candle_width(dates), _candle_width(dates))


def _date_formatter(timeframe: str, candles: list[Candle]):
    active_timeframe = timeframe.upper()

    def format_position(value: float, _position: int) -> str:
        index = int(round(value))
        if abs(value - index) > 0.2 or index < 0 or index >= len(candles):
            return ""
        dt = candles[index].datetime
        if active_timeframe == "H4":
            return dt.strftime("%m-%d %H:%M")
        return dt.strftime("%Y-%m-%d")

    return mticker.FuncFormatter(format_position)


def _draw_arb_annotations(
    ax,
    all_candles: list[Candle],
    plot_candles: list[Candle],
    dates: list[float],
    offset: int,
    result: ScanResult,
    config: VCPConfig,
) -> None:
    evidence = result.evidence
    lines = evidence.reasons + evidence.failures
    old_high = _parse_price(_line_value(lines, "Old range high:"))
    old_low = _parse_price(_line_value(lines, "Old range low:"))
    first_break_date = _parse_date(_line_value(lines, "First breakout candle:"))
    area_start_date, area_end_date = _parse_date_range(_line_value(lines, "Build-up or pullback candles:"))
    area_low, area_high = _parse_price_range(_line_value(lines, "Build-up or pullback area:"))
    stop = _parse_price(_line_value(lines, "Stop-loss area:"))
    trigger = evidence.pivot

    first_break_index = _date_index(all_candles, first_break_date)
    area_start_index = _date_index(all_candles, area_start_date)
    area_end_index = _date_index(all_candles, area_end_date)
    range_start_index = evidence.base_start_index

    if old_high is not None and old_low is not None and range_start_index is not None and first_break_index is not None:
        start = max(0, range_start_index - offset)
        end = min(len(plot_candles) - 1, first_break_index - offset)
        if 0 <= end and start < len(plot_candles):
            start = max(0, start)
            width = _range_width(dates, start, end)
            ax.add_patch(
                Rectangle(
                    (dates[start], old_low),
                    width,
                    old_high - old_low,
                    facecolor="#f3f4f6",
                    edgecolor="#111827",
                    linestyle="--",
                    linewidth=1.2,
                    alpha=0.28,
                    label="Old range",
                )
            )
            ax.hlines(
                [old_high, old_low],
                dates[start],
                dates[end],
                colors="#111827",
                linestyles="--",
                linewidth=1.1,
            )
            ax.text(dates[start], old_high, " old upper boundary", fontsize=8, va="bottom", color="#111827")
            ax.text(dates[start], old_low, " old lower boundary", fontsize=8, va="top", color="#111827")

    if first_break_index is not None:
        local = first_break_index - offset
        if 0 <= local < len(plot_candles):
            candle = plot_candles[local]
            ax.axvline(dates[local], color="#f97316", linestyle=":", linewidth=1.4, label="First breakout - skip")
            ax.annotate(
                "First breakout\nskip",
                xy=(dates[local], candle.high),
                xytext=(12, 26),
                textcoords="offset points",
                fontsize=8,
                color="#c2410c",
                arrowprops={"arrowstyle": "->", "color": "#c2410c", "linewidth": 1.0},
            )

    if (
        area_low is not None
        and area_high is not None
        and area_start_index is not None
        and area_end_index is not None
    ):
        start = max(0, area_start_index - offset)
        end = min(len(plot_candles) - 1, area_end_index - offset)
        if 0 <= end and start < len(plot_candles):
            start = max(0, start)
            width = _range_width(dates, start, end)
            ax.add_patch(
                Rectangle(
                    (dates[start], area_low),
                    width,
                    area_high - area_low,
                    facecolor="#dcfce7",
                    edgecolor="#16a34a",
                    linestyle="--",
                    linewidth=1.3,
                    alpha=0.30,
                    label="Build-up/retest",
                )
            )
            ax.text(dates[start], area_high, " build-up/retest", fontsize=8, va="bottom", color="#15803d")

    if trigger is not None:
        ax.axhline(trigger, color="#16a34a", linewidth=1.7, label=f"Second trigger {_price_label(trigger)}")
        if result.evidence.status == "WAITING":
            lower = trigger * (1 - config.max_boundary_distance_pct / 100)
            ax.axhspan(lower, trigger, color="#bbf7d0", alpha=0.20, label="Trigger watch zone")
    if stop is not None:
        ax.axhline(stop, color="#dc2626", linestyle="--", linewidth=1.2, label=f"Stop area {_price_label(stop)}")


def _draw_dd_annotations(
    ax,
    all_candles: list[Candle],
    plot_candles: list[Candle],
    dates: list[float],
    offset: int,
    result: ScanResult,
    config: VCPConfig,
) -> None:
    evidence = result.evidence
    lines = evidence.reasons + evidence.failures
    impulse_start, impulse_end = _parse_date_range(_line_value(lines, "Impulse wave:"))
    pullback_start, pullback_end = _parse_date_range(_line_value(lines, "Pullback description:"))
    cluster_value = _line_value(lines, "Doji cluster:")
    cluster_dates, cluster_area = _split_dd_cluster(cluster_value)
    cluster_start, cluster_end = _parse_date_range(cluster_dates)
    cluster_low, cluster_high = _parse_price_range(cluster_area)
    stop = _parse_price(_line_value(lines, "Stop-loss area:"))
    obstacle = _parse_price(_line_value(lines, "Nearest obstacle:"))
    signal = evidence.pivot

    impulse_start_index = _date_index(all_candles, impulse_start)
    impulse_end_index = _date_index(all_candles, impulse_end)
    pullback_start_index = _date_index(all_candles, pullback_start)
    pullback_end_index = _date_index(all_candles, pullback_end)
    cluster_start_index = _date_index(all_candles, cluster_start)
    cluster_end_index = _date_index(all_candles, cluster_end)

    _span_dates(ax, dates, offset, impulse_start_index, impulse_end_index, "#dcfce7", "Impulse wave")
    _span_dates(ax, dates, offset, pullback_start_index, pullback_end_index, "#fef3c7", "Clean pullback")

    if (
        cluster_low is not None
        and cluster_high is not None
        and cluster_start_index is not None
        and cluster_end_index is not None
    ):
        start = max(0, cluster_start_index - offset)
        end = min(len(plot_candles) - 1, cluster_end_index - offset)
        if 0 <= end and start < len(plot_candles):
            start = max(0, start)
            width = _range_width(dates, start, end)
            ax.add_patch(
                Rectangle(
                    (dates[start], cluster_low),
                    width,
                    cluster_high - cluster_low,
                    facecolor="#ede9fe",
                    edgecolor="#7c3aed",
                    linestyle="--",
                    linewidth=1.3,
                    alpha=0.34,
                    label="Doji cluster",
                )
            )
            ax.text(dates[start], cluster_high, " 2+ doji near EMA21", fontsize=8, va="bottom", color="#5b21b6")

    if signal is not None:
        ax.axhline(signal, color="#16a34a", linewidth=1.7, label=f"DD signal {_price_label(signal)}")
        if result.evidence.status == "WAITING":
            if _line_value(lines, "Direction:") == "Short":
                upper = signal * (1 + config.max_boundary_distance_pct / 100)
                ax.axhspan(signal, upper, color="#bbf7d0", alpha=0.20, label="Signal watch zone")
            else:
                lower = signal * (1 - config.max_boundary_distance_pct / 100)
                ax.axhspan(lower, signal, color="#bbf7d0", alpha=0.20, label="Signal watch zone")
    if stop is not None:
        ax.axhline(stop, color="#dc2626", linestyle="--", linewidth=1.2, label=f"Stop area {_price_label(stop)}")
    if obstacle is not None:
        ax.axhline(obstacle, color="#f97316", linestyle=":", linewidth=1.1, label=f"Nearest obstacle {_price_label(obstacle)}")


def _draw_sb_annotations(
    ax,
    all_candles: list[Candle],
    plot_candles: list[Candle],
    dates: list[float],
    offset: int,
    result: ScanResult,
    config: VCPConfig,
) -> None:
    evidence = result.evidence
    lines = evidence.reasons + evidence.failures
    impulse_start, impulse_end = _parse_date_range(_line_value(lines, "Impulse wave:"))
    pullback_start, pullback_end = _parse_date_range(_line_value(lines, "Pullback description:"))
    first_break_date = _parse_date(_line_value(lines, "First break:"))
    failure_date = _parse_date(_line_value(lines, "First break failure:"))
    second_break_text = _line_value(lines, "Second break trigger:")
    second_break_date = _parse_date(second_break_text.split(";", maxsplit=1)[0].strip()) if second_break_text else None
    stop = _parse_price(_line_value(lines, "Stop-loss area:"))
    obstacle = _parse_price(_line_value(lines, "Nearest obstacle:"))
    trigger = evidence.pivot

    impulse_start_index = _date_index(all_candles, impulse_start)
    impulse_end_index = _date_index(all_candles, impulse_end)
    pullback_start_index = _date_index(all_candles, pullback_start)
    pullback_end_index = _date_index(all_candles, pullback_end)
    first_break_index = _date_index(all_candles, first_break_date)
    failure_index = _date_index(all_candles, failure_date)
    second_break_index = _date_index(all_candles, second_break_date)

    _span_dates(ax, dates, offset, impulse_start_index, impulse_end_index, "#dcfce7", "Impulse wave")
    _span_dates(ax, dates, offset, pullback_start_index, pullback_end_index, "#fef3c7", "Clean pullback")
    _mark_event(ax, plot_candles, dates, offset, first_break_index, "1st break\nskip", "#f97316", above=True)
    _mark_event(ax, plot_candles, dates, offset, failure_index, "failure", "#dc2626", above=False)
    _mark_event(ax, plot_candles, dates, offset, second_break_index, "2nd break", "#16a34a", above=True)

    if trigger is not None:
        ax.axhline(trigger, color="#16a34a", linewidth=1.7, label=f"SB trigger {_price_label(trigger)}")
        if result.evidence.status == "WAITING":
            direction = _line_value(lines, "Direction:")
            if direction == "Short":
                upper = trigger * (1 + config.max_boundary_distance_pct / 100)
                ax.axhspan(trigger, upper, color="#bbf7d0", alpha=0.20, label="Trigger watch zone")
            else:
                lower = trigger * (1 - config.max_boundary_distance_pct / 100)
                ax.axhspan(lower, trigger, color="#bbf7d0", alpha=0.20, label="Trigger watch zone")
    if stop is not None:
        ax.axhline(stop, color="#dc2626", linestyle="--", linewidth=1.2, label=f"Stop area {_price_label(stop)}")
    if obstacle is not None:
        ax.axhline(obstacle, color="#f97316", linestyle=":", linewidth=1.1, label=f"Nearest obstacle {_price_label(obstacle)}")


def _draw_bb_annotations(
    ax,
    all_candles: list[Candle],
    plot_candles: list[Candle],
    dates: list[float],
    offset: int,
    result: ScanResult,
    config: VCPConfig,
) -> None:
    evidence = result.evidence
    lines = evidence.reasons + evidence.failures
    context_start, context_end = _parse_date_range(_line_value(lines, "Trend/context:"))
    pullback_start, pullback_end = _parse_date_range(_line_value(lines, "Pullback description:"))
    block_value = _line_value(lines, "Block description:")
    block_dates, block_area = _split_dd_cluster(block_value)
    block_start, block_end = _parse_date_range(block_dates)
    block_low, block_high = _parse_price_range(block_area)
    stop = _parse_price(_line_value(lines, "Stop-loss area:"))
    obstacle = _parse_price(_line_value(lines, "Nearest obstacle:"))
    trigger = evidence.pivot

    context_start_index = _date_index(all_candles, context_start)
    context_end_index = _date_index(all_candles, context_end)
    pullback_start_index = _date_index(all_candles, pullback_start)
    pullback_end_index = _date_index(all_candles, pullback_end)
    block_start_index = _date_index(all_candles, block_start)
    block_end_index = _date_index(all_candles, block_end)

    _span_dates(ax, dates, offset, context_start_index, context_end_index, "#dcfce7", "Trend impulse")
    _span_dates(ax, dates, offset, pullback_start_index, pullback_end_index, "#fef3c7", "Pullback/block context")

    if (
        block_low is not None
        and block_high is not None
        and block_start_index is not None
        and block_end_index is not None
    ):
        start = max(0, block_start_index - offset)
        end = min(len(plot_candles) - 1, block_end_index - offset)
        if 0 <= end and start < len(plot_candles):
            start = max(0, start)
            width = _range_width(dates, start, end)
            ax.add_patch(
                Rectangle(
                    (dates[start], block_low),
                    width,
                    block_high - block_low,
                    facecolor="#bfdbfe",
                    edgecolor="#2563eb",
                    linestyle="--",
                    linewidth=2.0,
                    alpha=0.40,
                    label="BB block",
                )
            )
            ax.hlines(
                [block_high, block_low],
                dates[start],
                dates[end],
                colors="#1d4ed8",
                linestyles="--",
                linewidth=1.4,
            )
            ax.text(dates[start], block_high, " BB block", fontsize=9, va="bottom", color="#1d4ed8", fontweight="bold")
            direction = _line_value(lines, "Direction:")
            signal_y = block_low if direction == "Short" else block_high
            ax.annotate(
                "signal boundary",
                xy=(dates[end], signal_y),
                xytext=(12, 10 if direction != "Short" else -20),
                textcoords="offset points",
                fontsize=8,
                color="#15803d",
                arrowprops={"arrowstyle": "->", "color": "#15803d", "linewidth": 1.0},
            )

    if trigger is not None:
        ax.axhline(trigger, color="#16a34a", linewidth=2.0, label=f"BB signal {_price_label(trigger)}")
        if result.evidence.status == "WAITING":
            direction = _line_value(lines, "Direction:")
            if direction == "Short":
                upper = trigger * (1 + config.max_boundary_distance_pct / 100)
                ax.axhspan(trigger, upper, color="#bbf7d0", alpha=0.20, label="Signal watch zone")
            else:
                lower = trigger * (1 - config.max_boundary_distance_pct / 100)
                ax.axhspan(lower, trigger, color="#bbf7d0", alpha=0.20, label="Signal watch zone")
    if stop is not None:
        ax.axhline(stop, color="#dc2626", linestyle="--", linewidth=1.2, label=f"Stop area {_price_label(stop)}")
    if obstacle is not None:
        ax.axhline(obstacle, color="#f97316", linestyle=":", linewidth=1.1, label=f"Nearest obstacle {_price_label(obstacle)}")


def _draw_rb_annotations(
    ax,
    all_candles: list[Candle],
    plot_candles: list[Candle],
    dates: list[float],
    offset: int,
    result: ScanResult,
    config: VCPConfig,
) -> None:
    evidence = result.evidence
    lines = evidence.reasons + evidence.failures
    range_start, range_end = _parse_date_range(_line_value(lines, "Range description:"))
    upper = _parse_price(_line_value(lines, "Upper range boundary:"))
    lower = _parse_price(_line_value(lines, "Lower range boundary:"))
    buildup_value = _line_value(lines, "Build-up description:")
    buildup_dates, buildup_area = _split_dd_cluster(buildup_value)
    buildup_start, buildup_end = _parse_date_range(buildup_dates)
    buildup_low, buildup_high = _parse_price_range(buildup_area)
    stop = _parse_price(_line_value(lines, "Stop-loss area:"))
    trigger = evidence.pivot

    range_start_index = _date_index(all_candles, range_start)
    range_end_index = _date_index(all_candles, range_end)
    buildup_start_index = _date_index(all_candles, buildup_start)
    buildup_end_index = _date_index(all_candles, buildup_end)

    if (
        upper is not None
        and lower is not None
        and range_start_index is not None
        and range_end_index is not None
    ):
        start = max(0, range_start_index - offset)
        end = min(len(plot_candles) - 1, range_end_index - offset)
        if 0 <= end and start < len(plot_candles):
            start = max(0, start)
            width = _range_width(dates, start, end)
            ax.add_patch(
                Rectangle(
                    (dates[start], lower),
                    width,
                    upper - lower,
                    facecolor="#f3f4f6",
                    edgecolor="#111827",
                    linestyle="--",
                    linewidth=1.5,
                    alpha=0.25,
                    label="Long range",
                )
            )
            ax.hlines([upper, lower], dates[start], dates[end], colors="#111827", linestyles="--", linewidth=1.3)
            ax.text(dates[start], upper, " upper range boundary", fontsize=8, va="bottom", color="#111827")
            ax.text(dates[start], lower, " lower range boundary", fontsize=8, va="top", color="#111827")

    if (
        buildup_low is not None
        and buildup_high is not None
        and buildup_start_index is not None
        and buildup_end_index is not None
    ):
        start = max(0, buildup_start_index - offset)
        end = min(len(plot_candles) - 1, buildup_end_index - offset)
        if 0 <= end and start < len(plot_candles):
            start = max(0, start)
            width = _range_width(dates, start, end)
            ax.add_patch(
                Rectangle(
                    (dates[start], buildup_low),
                    width,
                    buildup_high - buildup_low,
                    facecolor="#bbf7d0",
                    edgecolor="#16a34a",
                    linestyle="--",
                    linewidth=2.0,
                    alpha=0.42,
                    label="Near-boundary build-up",
                )
            )
            ax.text(dates[start], buildup_high, " build-up", fontsize=9, va="bottom", color="#15803d", fontweight="bold")

    if trigger is not None:
        ax.axhline(trigger, color="#16a34a", linewidth=2.0, label=f"RB breakout boundary {_price_label(trigger)}")
        if result.evidence.status == "WAITING":
            direction = _line_value(lines, "Direction:")
            if direction == "Short":
                upper_zone = trigger * (1 + config.max_boundary_distance_pct / 100)
                ax.axhspan(trigger, upper_zone, color="#bbf7d0", alpha=0.18, label="Boundary watch zone")
            else:
                lower_zone = trigger * (1 - config.max_boundary_distance_pct / 100)
                ax.axhspan(lower_zone, trigger, color="#bbf7d0", alpha=0.18, label="Boundary watch zone")
    if stop is not None:
        ax.axhline(stop, color="#dc2626", linestyle="--", linewidth=1.2, label=f"Stop area {_price_label(stop)}")


def _draw_irb_annotations(
    ax,
    all_candles: list[Candle],
    plot_candles: list[Candle],
    dates: list[float],
    offset: int,
    result: ScanResult,
    config: VCPConfig,
) -> None:
    evidence = result.evidence
    lines = evidence.reasons + evidence.failures
    range_start, range_end = _parse_date_range(_line_value(lines, "Range description:"))
    upper = _parse_price(_line_value(lines, "Upper range boundary:"))
    lower = _parse_price(_line_value(lines, "Lower range boundary:"))
    block_value = _line_value(lines, "Inner buildup/block description:")
    block_dates, block_area = _split_dd_cluster(block_value)
    block_start, block_end = _parse_date_range(block_dates)
    block_low, block_high = _parse_price_range(block_area)
    target = _parse_price(_line_value(lines, "Target boundary:"))
    stop = _parse_price(_line_value(lines, "Stop-loss area:"))
    trigger = evidence.pivot

    range_start_index = _date_index(all_candles, range_start)
    range_end_index = _date_index(all_candles, range_end)
    block_start_index = _date_index(all_candles, block_start)
    block_end_index = _date_index(all_candles, block_end)

    if (
        upper is not None
        and lower is not None
        and range_start_index is not None
        and range_end_index is not None
    ):
        start = max(0, range_start_index - offset)
        end = min(len(plot_candles) - 1, range_end_index - offset)
        if 0 <= end and start < len(plot_candles):
            start = max(0, start)
            width = _range_width(dates, start, end)
            ax.add_patch(
                Rectangle(
                    (dates[start], lower),
                    width,
                    upper - lower,
                    facecolor="#eff6ff",
                    edgecolor="#1d4ed8",
                    linestyle="--",
                    linewidth=1.4,
                    alpha=0.22,
                    label="Outer range",
                )
            )
            ax.hlines([upper, lower], dates[start], dates[end], colors="#1d4ed8", linestyles="--", linewidth=1.2)
            ax.text(dates[start], upper, " upper target boundary", fontsize=8, va="bottom", color="#1d4ed8")
            ax.text(dates[start], lower, " lower target boundary", fontsize=8, va="top", color="#1d4ed8")

    if (
        block_low is not None
        and block_high is not None
        and block_start_index is not None
        and block_end_index is not None
    ):
        start = max(0, block_start_index - offset)
        end = min(len(plot_candles) - 1, block_end_index - offset)
        if 0 <= end and start < len(plot_candles):
            start = max(0, start)
            width = _range_width(dates, start, end)
            ax.add_patch(
                Rectangle(
                    (dates[start], block_low),
                    width,
                    block_high - block_low,
                    facecolor="#fef3c7",
                    edgecolor="#d97706",
                    linestyle="--",
                    linewidth=2.0,
                    alpha=0.45,
                    label="Inner block",
                )
            )
            ax.text(dates[start], block_high, " inner block", fontsize=9, va="bottom", color="#b45309", fontweight="bold")

    if trigger is not None:
        ax.axhline(trigger, color="#16a34a", linewidth=2.0, label=f"IRB inner trigger {_price_label(trigger)}")
        if result.evidence.status == "WAITING":
            direction = _line_value(lines, "Direction:")
            if direction == "Short":
                upper_zone = trigger * (1 + config.max_boundary_distance_pct / 100)
                ax.axhspan(trigger, upper_zone, color="#bbf7d0", alpha=0.18, label="Inner trigger watch zone")
            else:
                lower_zone = trigger * (1 - config.max_boundary_distance_pct / 100)
                ax.axhspan(lower_zone, trigger, color="#bbf7d0", alpha=0.18, label="Inner trigger watch zone")
    if target is not None:
        ax.axhline(target, color="#2563eb", linestyle="-.", linewidth=1.4, label=f"Target boundary {_price_label(target)}")
    if stop is not None:
        ax.axhline(stop, color="#dc2626", linestyle="--", linewidth=1.2, label=f"Stop area {_price_label(stop)}")


def _draw_pivot_ema21_compression_annotations(
    ax,
    all_candles: list[Candle],
    plot_candles: list[Candle],
    dates: list[float],
    offset: int,
    result: ScanResult,
    config: VCPConfig,
) -> None:
    evidence = result.evidence
    lines = evidence.reasons + evidence.failures
    direction = _line_value(lines, "Direction:")
    pivot_type = _line_value(lines, "Pivot type:")
    pivot_start_date, pivot_start_value, pivot_end_date, pivot_end_value = _parse_dated_price_line(
        _line_value(lines, "Pivot line values:")
    )
    compression_dates, compression_area = _split_dd_cluster(_line_value(lines, "Compression zone:"))
    compression_start, compression_end = _parse_date_range(compression_dates)
    zone_low, zone_high = _parse_price_range(compression_area.removeprefix("area ").strip() if compression_area else None)
    stop = _parse_price(_line_value(lines, "Stop-loss area:"))
    trigger = evidence.pivot

    pivot_start_index = _date_index(all_candles, pivot_start_date)
    pivot_end_index = _date_index(all_candles, pivot_end_date)
    compression_start_index = _date_index(all_candles, compression_start)
    compression_end_index = _date_index(all_candles, compression_end)

    if (
        pivot_start_index is not None
        and pivot_end_index is not None
        and pivot_start_value is not None
        and pivot_end_value is not None
    ):
        start = max(0, pivot_start_index - offset)
        end = min(len(plot_candles) - 1, max(pivot_end_index, len(all_candles) - 1) - offset)
        if 0 <= end and start < len(plot_candles):
            start = max(0, start)
            if pivot_type == "Diagonal":
                local_start_index = offset + start
                local_end_index = offset + end
                y_start = _line_between_points(pivot_start_index, pivot_start_value, pivot_end_index, pivot_end_value, local_start_index)
                y_end = _line_between_points(pivot_start_index, pivot_start_value, pivot_end_index, pivot_end_value, local_end_index)
                ax.plot([dates[start], dates[end]], [y_start, y_end], color="#111827", linestyle="--", linewidth=2.0, label="Diagonal pivot")
            else:
                ax.hlines(pivot_end_value, dates[start], dates[end], colors="#111827", linestyles="--", linewidth=2.0, label="Horizontal pivot")
            ax.text(dates[start], pivot_start_value, " pivot line", fontsize=8, va="bottom", color="#111827")

    if (
        zone_low is not None
        and zone_high is not None
        and compression_start_index is not None
        and compression_end_index is not None
    ):
        start = max(0, compression_start_index - offset)
        end = min(len(plot_candles) - 1, compression_end_index - offset)
        if 0 <= end and start < len(plot_candles):
            start = max(0, start)
            width = _range_width(dates, start, end)
            ax.add_patch(
                Rectangle(
                    (dates[start], zone_low),
                    width,
                    zone_high - zone_low,
                    facecolor="#fef3c7",
                    edgecolor="#f59e0b",
                    linestyle="--",
                    linewidth=1.4,
                    alpha=0.25,
                    label="Pivot-EMA21 compression zone",
                )
            )
            ax.text(dates[start], zone_high, " squeeze zone", fontsize=8, va="bottom", color="#b45309")

    if trigger is not None:
        ax.axhline(trigger, color="#16a34a", linewidth=1.5, alpha=0.75, label=f"Trigger {_price_label(trigger)}")
        if result.evidence.status == "WAITING":
            if direction == "Short":
                upper_zone = trigger * (1 + config.max_boundary_distance_pct / 100)
                ax.axhspan(trigger, upper_zone, color="#bbf7d0", alpha=0.16, label="Trigger watch zone")
            else:
                lower_zone = trigger * (1 - config.max_boundary_distance_pct / 100)
                ax.axhspan(lower_zone, trigger, color="#bbf7d0", alpha=0.16, label="Trigger watch zone")
    if stop is not None:
        ax.axhline(stop, color="#dc2626", linestyle="--", linewidth=1.2, label=f"Stop area {_price_label(stop)}")


def _mark_event(
    ax,
    plot_candles: list[Candle],
    dates: list[float],
    offset: int,
    index: int | None,
    label: str,
    color: str,
    *,
    above: bool,
) -> None:
    if index is None:
        return
    local = index - offset
    if not (0 <= local < len(plot_candles)):
        return
    candle = plot_candles[local]
    y = candle.high if above else candle.low
    y_offset = 24 if above else -28
    ax.axvline(dates[local], color=color, linestyle=":", linewidth=1.1)
    ax.annotate(
        label,
        xy=(dates[local], y),
        xytext=(10, y_offset),
        textcoords="offset points",
        fontsize=8,
        color=color,
        arrowprops={"arrowstyle": "->", "color": color, "linewidth": 0.9},
    )


def _span_dates(
    ax,
    dates: list[float],
    offset: int,
    start_index: int | None,
    end_index: int | None,
    color: str,
    label: str,
) -> None:
    if start_index is None or end_index is None:
        return
    start = max(0, start_index - offset)
    end = min(len(dates) - 1, end_index - offset)
    if 0 <= end and start < len(dates):
        ax.axvspan(dates[max(0, start)], dates[end], color=color, alpha=0.22, label=label)


def _is_arb_evidence(evidence) -> bool:
    return any(line.strip() == "Pattern: ARB" for line in evidence.reasons + evidence.failures)


def _is_dd_evidence(evidence) -> bool:
    return any(line.strip() == "Pattern: DD" for line in evidence.reasons + evidence.failures)


def _is_sb_evidence(evidence) -> bool:
    return any(line.strip() == "Pattern: SB" for line in evidence.reasons + evidence.failures)


def _is_bb_evidence(evidence) -> bool:
    return any(line.strip() == "Pattern: BB" for line in evidence.reasons + evidence.failures)


def _is_rb_evidence(evidence) -> bool:
    return any(line.strip() == "Pattern: RB" for line in evidence.reasons + evidence.failures)


def _is_irb_evidence(evidence) -> bool:
    return any(line.strip() == "Pattern: IRB" for line in evidence.reasons + evidence.failures)


def _is_pivot_ema21_compression_evidence(evidence) -> bool:
    return any(line.strip() == "Pattern: Pivot-EMA21 Compression" for line in evidence.reasons + evidence.failures)


def _split_dd_cluster(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    parts = [part.strip() for part in value.split(";", maxsplit=1)]
    dates = parts[0]
    if len(parts) == 1 or "area" not in parts[1]:
        return dates, None
    return dates, parts[1].split("area", maxsplit=1)[1].strip()


def _line_value(lines: list[str], prefix: str) -> str | None:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped.removeprefix(prefix).strip()
    return None


def _parse_price(value: str | None) -> float | None:
    if not value or value == "n/a":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_price_range(value: str | None) -> tuple[float | None, float | None]:
    if not value or "->" in value:
        return None, None
    parts = [part.strip() for part in value.split(" - ", maxsplit=1)]
    if len(parts) != 2:
        return None, None
    return _parse_price(parts[0]), _parse_price(parts[1])


def _parse_date(value: str | None) -> date | None:
    if not value or value == "n/a":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_date_range(value: str | None) -> tuple[date | None, date | None]:
    if not value:
        return None, None
    parts = [part.strip() for part in value.split("->", maxsplit=1)]
    if len(parts) != 2:
        return None, None
    return _parse_date(parts[0]), _parse_date(parts[1])


def _parse_dated_price_line(value: str | None) -> tuple[date | None, float | None, date | None, float | None]:
    if not value or "->" not in value:
        return None, None, None, None
    left, right = [part.strip() for part in value.split("->", maxsplit=1)]
    left_parts = left.split()
    right_parts = right.split()
    if len(left_parts) < 2 or len(right_parts) < 2:
        return None, None, None, None
    return _parse_date(left_parts[0]), _parse_price(left_parts[1]), _parse_date(right_parts[0]), _parse_price(right_parts[1])


def _line_between_points(
    start_index: int,
    start_value: float,
    end_index: int,
    end_value: float,
    target_index: int,
) -> float:
    span = end_index - start_index
    if span == 0:
        return end_value
    return start_value + ((end_value - start_value) / span) * (target_index - start_index)


def _date_index(candles: list[Candle], target: date | None) -> int | None:
    if target is None:
        return None
    for index, candle in enumerate(candles):
        if candle.datetime.date() == target:
            return index
    return None
