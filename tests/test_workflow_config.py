from __future__ import annotations

from pathlib import Path

import yaml


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


def test_pages_workflow_scans_exness_indices_in_a_parallel_d1_shard() -> None:
    workflow = Path(".github/workflows/scanner-pages-v2.yml").read_text()

    assert "id: index" in workflow
    assert "label: Index CFD" in workflow
    assert 'markets: "Index"' in workflow


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


def test_pages_workflow_builds_lightweight_site_index() -> None:
    workflow = Path(".github/workflows/scanner-pages-v2.yml").read_text()

    assert "Build site entry report" in workflow
    assert "python -m filter_pattern.cli site-index" in workflow


def test_pages_workflow_validates_asset_integrity_and_size_before_upload() -> None:
    workflow = Path(".github/workflows/scanner-pages-v2.yml").read_text()

    validation = "python -m filter_pattern.cli validate-site --root public --max-bytes 1000000000"
    assert "Validate Pages size and chart assets" in workflow
    assert validation in workflow
    assert workflow.index(validation) < workflow.index("actions/upload-pages-artifact")


def test_pages_workflow_uses_unique_trigger_commits_for_scheduled_refreshes() -> None:
    workflow = Path(".github/workflows/scanner-pages-v2.yml").read_text()

    assert "actions: write" in workflow
    assert "- scanner-trigger" in workflow
    assert "trigger_scan:" in workflow
    assert "github.event_name != 'push'" in workflow
    assert 'git push --force origin "HEAD:scanner-trigger"' in workflow
    assert workflow.count("if: github.event_name == 'push'") >= 2


def test_pages_workflow_verifies_the_served_deployment_marker() -> None:
    workflow = Path(".github/workflows/scanner-pages-v2.yml").read_text()

    assert "public/deployment.json" in workflow
    assert '"run_id": "${{ github.run_id }}"' in workflow
    assert "Verify served deployment" in workflow
    assert (
        "PAGE_URL: ${{ steps.deployment.outputs.page_url || steps.deployment_retry.outputs.page_url"
        " || steps.deployment_retry2.outputs.page_url }}"
    ) in workflow
    assert 'MARKER_URL="${PAGE_URL%/}/deployment.json"' in workflow
    assert workflow.index("public/deployment.json") < workflow.index("actions/upload-pages-artifact")
    assert workflow.index("actions/deploy-pages@v5") < workflow.index("Verify served deployment")


def test_pages_workflow_retries_transient_deploy_failures() -> None:
    workflow = Path(".github/workflows/scanner-pages-v2.yml").read_text()
    steps = yaml.safe_load(workflow)["jobs"]["deploy"]["steps"]
    by_name = {step["name"]: step for step in steps}
    names = [step["name"] for step in steps]

    assert by_name["Upload Pages artifact"]["uses"] == "actions/upload-pages-artifact@v5"
    assert by_name["Upload Pages artifact"]["with"]["include-hidden-files"] is True
    attempts = ["Deploy to GitHub Pages", "Deploy to GitHub Pages (attempt 2)", "Deploy to GitHub Pages (attempt 3)"]
    order = ["Upload Pages artifact", attempts[0], "Wait before Pages deploy attempt 2", attempts[1],
             "Wait before Pages deploy attempt 3", attempts[2], "Verify served deployment"]
    assert [names.index(name) for name in order] == sorted(names.index(name) for name in order)
    assert all(by_name[name]["uses"] == "actions/deploy-pages@v5" for name in attempts)
    assert by_name[attempts[0]].get("continue-on-error") is True
    assert by_name[attempts[1]].get("continue-on-error") is True
    assert "continue-on-error" not in by_name[attempts[2]]
    assert by_name[attempts[1]]["if"] == "${{ steps.deployment.outcome == 'failure' }}"
    assert "steps.deployment_retry.outcome == 'failure'" in by_name[attempts[2]]["if"]
    assert "Wait for Pages artifact" not in names
    assert "actions/deploy-pages@v4" not in workflow

    first, second, third = (by_name[name]["id"] for name in attempts)
    assert len({first, second, third}) == 3
    assert by_name["Wait before Pages deploy attempt 2"]["if"] == f"${{{{ steps.{first}.outcome == 'failure' }}}}"
    assert by_name[attempts[1]]["if"] == f"${{{{ steps.{first}.outcome == 'failure' }}}}"
    both_failed = f"${{{{ steps.{first}.outcome == 'failure' && steps.{second}.outcome == 'failure' }}}}"
    assert by_name["Wait before Pages deploy attempt 3"]["if"] == both_failed
    assert by_name[attempts[2]]["if"] == both_failed
    page_url = (
        f"${{{{ steps.{first}.outputs.page_url || steps.{second}.outputs.page_url"
        f" || steps.{third}.outputs.page_url }}}}"
    )
    deploy_job = yaml.safe_load(workflow)["jobs"]["deploy"]
    assert deploy_job["environment"]["url"] == page_url
    assert by_name["Verify served deployment"]["env"]["PAGE_URL"] == page_url


def test_pages_deploy_attempts_fit_inside_the_job_timeout() -> None:
    deploy_job = yaml.safe_load(Path(".github/workflows/scanner-pages-v2.yml").read_text())["jobs"]["deploy"]
    attempts = [step for step in deploy_job["steps"] if step.get("uses") == "actions/deploy-pages@v5"]

    assert len(attempts) == 3
    for step in attempts:
        assert step["with"]["timeout"] <= 300000
        assert step["timeout-minutes"] <= 6
    pauses = sum(
        int(step["run"].split()[-1]) for step in deploy_job["steps"] if step["name"].startswith("Wait before Pages deploy")
    )
    verify_minutes = 12
    build_minutes = 15
    worst_case = build_minutes + sum(step["timeout-minutes"] for step in attempts) + pauses / 60 + verify_minutes
    assert worst_case <= deploy_job["timeout-minutes"]
