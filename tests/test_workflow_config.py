from __future__ import annotations

from pathlib import Path


def test_pages_workflow_uses_broad_d1_universe_for_sp500_coverage() -> None:
    workflow = Path(".github/workflows/scanner-pages-v2.yml").read_text()

    assert "D1_UNIVERSE: broad" in workflow


def test_pages_workflow_enables_parallel_chart_rendering() -> None:
    workflow = Path(".github/workflows/scanner-pages-v2.yml").read_text()

    assert 'CHART_RENDER_WORKERS: "4"' in workflow
    assert "--chart-workers \"$CHART_RENDER_WORKERS\"" in workflow
