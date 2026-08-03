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


def test_pages_workflow_uses_compact_per_shard_state_instead_of_restoring_full_site() -> None:
    workflow = Path(".github/workflows/scanner-pages-v2.yml").read_text()

    assert "STATE_BRANCH: scanner-state" in workflow
    assert "Restore previous D1 shard state" in workflow
    assert "Restore previous H4 shard state" in workflow
    assert "watchlist-state" in workflow
    assert "git archive origin/gh-pages" not in workflow
    assert 'public/previous/d1-shard-${{ matrix.shard.id }}.json' in workflow
    assert 'public/previous/h4-shard-${{ matrix.shard.id }}.json' in workflow


def test_pages_workflow_deploys_public_directly_without_pushing_generated_site() -> None:
    workflow = Path(".github/workflows/scanner-pages-v2.yml").read_text()

    assert "Save compact scanner state" in workflow
    assert "Save generated site branch" not in workflow
    assert "git branch -M gh-pages" not in workflow
    assert 'if ! git push --force origin "HEAD:${STATE_BRANCH}"' in workflow
    assert "path: public" in workflow
    assert "pages-public" not in workflow
