from __future__ import annotations

from pathlib import Path

from filter_pattern.cli import main


def test_scan_missing_config_returns_clean_error(capsys) -> None:
    exit_code = main(["scan", "--config", "missing.yml", "--timeframe", "D1", "--out", "reports/latest"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Error: Config file not found" in captured.err
    assert "examples/config.example.yml" in captured.err
    assert "Traceback" not in captured.err


def test_init_config_writes_example_config(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.yml"

    exit_code = main(["init-config", "--out", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert config_path.exists()
    assert "timeframe: D1" in config_path.read_text()
    assert "Wrote" in captured.out


def test_init_config_does_not_overwrite_without_force(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text("custom: true\n")

    exit_code = main(["init-config", "--out", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert config_path.read_text() == "custom: true\n"
    assert "Use --force" in captured.err


def test_scan_cli_passes_technique_and_setup_to_scanner(tmp_path: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_scan_csv(config: str, out: str, timeframe: str, technique: str, setup: str) -> Path:
        seen.update(
            {
                "config": config,
                "out": out,
                "timeframe": timeframe,
                "technique": technique,
                "setup": setup,
            }
        )
        return tmp_path / "results.json"

    monkeypatch.setattr("filter_pattern.cli.scan_csv", fake_scan_csv)

    exit_code = main(
        [
            "scan",
            "--config",
            "config.yml",
            "--timeframe",
            "D1",
            "--out",
            str(tmp_path / "reports/latest"),
            "--technique",
            "nhathoai",
            "--setup",
            "rb",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert seen["technique"] == "nhathoai"
    assert seen["setup"] == "rb"
    assert "Wrote" in captured.out


def test_scan_all_cli_passes_tradingview_csv_config_to_scanner(tmp_path: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_scan_all_csv(config: str, out: str, timeframe: str) -> Path:
        seen.update({"config": config, "out": out, "timeframe": timeframe})
        return tmp_path / "results.json"

    monkeypatch.setattr("filter_pattern.cli.scan_all_csv", fake_scan_all_csv)

    exit_code = main(
        [
            "scan-all",
            "--config",
            "config.yml",
            "--timeframe",
            "H4",
            "--out",
            str(tmp_path / "reports/tv"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert seen["config"] == "config.yml"
    assert seen["timeframe"] == "H4"
    assert "Wrote" in captured.out


def test_scan_market_cli_passes_technique_and_setup_to_scanner(tmp_path: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_scan_market(
        out: str,
        timeframe: str,
        config: str,
        period: str,
        limit: int,
        universe: str,
        broker: str,
        technique: str,
        setup: str,
        data_provider: str,
        markets: str,
        near_match_chart_limit: int,
        previous_results: str,
    ) -> Path:
        seen.update(
            {
                "out": out,
                "timeframe": timeframe,
                "config": config,
                "period": period,
                "limit": limit,
                "universe": universe,
                "broker": broker,
                "technique": technique,
                "setup": setup,
                "data_provider": data_provider,
                "markets": markets,
                "near_match_chart_limit": near_match_chart_limit,
                "previous_results": previous_results,
            }
        )
        return tmp_path / "results.json"

    monkeypatch.setattr("filter_pattern.cli.scan_market", fake_scan_market)

    exit_code = main(
        [
            "scan-market",
            "--config",
            "config.yml",
            "--timeframe",
            "D1",
            "--out",
            str(tmp_path / "reports/market"),
            "--period",
            "2y",
            "--universe",
            "broad",
            "--broker",
            "exness",
            "--data-provider",
            "mixed",
            "--markets",
            "US stock,Forex",
            "--near-match-chart-limit",
            "3",
            "--previous-results",
            "reports/previous.json",
            "--technique",
            "nhathoai",
            "--setup",
            "rb",
            "--limit",
            "5",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert seen["technique"] == "nhathoai"
    assert seen["setup"] == "rb"
    assert seen["universe"] == "broad"
    assert seen["broker"] == "exness"
    assert seen["data_provider"] == "mixed"
    assert seen["markets"] == "US stock,Forex"
    assert seen["near_match_chart_limit"] == 3
    assert seen["previous_results"] == "reports/previous.json"
    assert seen["limit"] == 5
    assert "Wrote" in captured.out


def test_combine_report_cli_passes_inputs_to_report_writer(tmp_path: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_write_combined_html_report(inputs: list[str], out: str) -> Path:
        seen["inputs"] = inputs
        seen["out"] = out
        return tmp_path / "combined/index.html"

    monkeypatch.setattr("filter_pattern.cli.write_combined_html_report", fake_write_combined_html_report)

    exit_code = main(
        [
            "combine-report",
            "--inputs",
            "reports/vcp/results.json",
            "reports/ema/results.json",
            "--out",
            str(tmp_path / "combined/index.html"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert seen["inputs"] == ["reports/vcp/results.json", "reports/ema/results.json"]
    assert seen["out"] == str(tmp_path / "combined/index.html")
    assert "Wrote" in captured.out
