from __future__ import annotations

from pathlib import Path


def test_pages_workflow_uses_broad_d1_universe_for_sp500_coverage() -> None:
    workflow = Path(".github/workflows/scanner-pages-v2.yml").read_text()

    assert "D1_UNIVERSE: broad" in workflow


def test_pages_workflow_enables_parallel_chart_rendering() -> None:
    workflow = Path(".github/workflows/scanner-pages-v2.yml").read_text()

    assert 'CHART_RENDER_WORKERS: "4"' in workflow
    assert "--chart-workers \"$CHART_RENDER_WORKERS\"" in workflow


def test_pages_workflow_splits_d1_crypto_into_parallel_shards() -> None:
    workflow = Path(".github/workflows/scanner-pages-v2.yml").read_text()

    assert "id: crypto-0" in workflow
    assert "label: Crypto 1/3" in workflow
    assert "id: crypto-1" in workflow
    assert "label: Crypto 2/3" in workflow
    assert "id: crypto-2" in workflow
    assert "label: Crypto 3/3" in workflow
    assert workflow.count('markets: "Crypto"') >= 6
    assert workflow.count("shard_count: 3") >= 6
