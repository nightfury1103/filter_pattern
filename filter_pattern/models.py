from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Candle:
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    market: str
    tradingview_symbol: str
    csv_path: Path


@dataclass(frozen=True)
class VCPConfig:
    min_history_days: int = 120
    max_base_days: int = 90
    pre_base_days: int = 60
    min_contractions: int = 2
    max_contractions: int = 4
    min_contraction_depth_pct: float = 3.0
    max_first_contraction_depth_pct: float = 35.0
    max_later_contraction_depth_pct: float = 22.0
    max_final_contraction_depth_pct: float = 12.0
    depth_tolerance_pct: float = 1.0
    low_tolerance_pct: float = 1.5
    max_pivot_spread_pct: float = 10.0
    max_base_depth_pct: float = 45.0
    near_pivot_pct: float = 5.0
    min_prior_uptrend_pct: float = 20.0
    min_avg_volume: float = 0.0
    volume_dry_up_ratio: float = 0.70
    swing_window: int = 2
    ema_period: int = 21
    ema_slope_lookback: int = 10
    compression_lookback: int = 12
    setup_lookback: int = 35
    max_ema_distance_pct: float = 4.0
    max_compression_range_pct: float = 8.0
    max_boundary_distance_pct: float = 3.0
    boundary_touch_tolerance_pct: float = 1.5
    min_boundary_touches: int = 2
    doji_body_ratio: float = 0.30
    trend_above_ema_ratio: float = 0.55
    max_pullback_ema_distance_pct: float = 3.5
    max_signal_range_pct: float = 5.0
    max_double_level_spread_pct: float = 1.5
    min_range_depth_pct: float = 6.0
    max_block_range_pct: float = 10.0
    max_inside_range_pct: float = 12.0
    max_retest_distance_pct: float = 2.5


@dataclass(frozen=True)
class AppConfig:
    timeframe: str
    symbols: list[SymbolSpec]
    vcp: VCPConfig = field(default_factory=VCPConfig)
    technique: str = "minervini-vcp"
    setup: str = "all"


@dataclass(frozen=True)
class Contraction:
    start_index: int
    end_index: int
    start_date: datetime
    end_date: datetime
    high: float
    low: float
    depth_pct: float

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["start_date"] = self.start_date.isoformat()
        data["end_date"] = self.end_date.isoformat()
        return data


@dataclass(frozen=True)
class VCPEvidence:
    qualified: bool
    status: str
    score: float
    pivot: float | None
    current_close: float | None
    distance_to_pivot_pct: float | None
    contractions: list[Contraction]
    reasons: list[str]
    failures: list[str]
    base_start_index: int | None = None
    base_end_index: int | None = None
    volume_dry_up_ratio: float | None = None
    prior_uptrend_pct: float | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "qualified": self.qualified,
            "status": self.status,
            "score": round(self.score, 2),
            "pivot": self.pivot,
            "current_close": self.current_close,
            "distance_to_pivot_pct": self.distance_to_pivot_pct,
            "contractions": [item.to_json() for item in self.contractions],
            "reasons": self.reasons,
            "failures": self.failures,
            "base_start_index": self.base_start_index,
            "base_end_index": self.base_end_index,
            "volume_dry_up_ratio": self.volume_dry_up_ratio,
            "prior_uptrend_pct": self.prior_uptrend_pct,
        }


@dataclass(frozen=True)
class ScanResult:
    symbol: SymbolSpec
    timeframe: str
    evidence: VCPEvidence
    chart_path: str | None = None
    technique: str = "minervini-vcp"
    setup: str = "all"

    def to_json(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol.symbol,
            "market": self.symbol.market,
            "tradingview_symbol": self.symbol.tradingview_symbol,
            "csv_path": str(self.symbol.csv_path),
            "timeframe": self.timeframe,
            "technique": self.technique,
            "setup": self.setup,
            "chart_path": self.chart_path,
            "evidence": self.evidence.to_json(),
        }
