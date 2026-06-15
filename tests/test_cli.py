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
        shard_index: int,
        shard_count: int,
        universe: str,
        broker: str,
        technique: str,
        setup: str,
        data_provider: str,
        markets: str,
        near_match_chart_limit: int,
        previous_results: str,
        chart_workers: int,
    ) -> Path:
        seen.update(
            {
                "out": out,
                "timeframe": timeframe,
                "config": config,
                "period": period,
                "limit": limit,
                "shard_index": shard_index,
                "shard_count": shard_count,
                "universe": universe,
                "broker": broker,
                "technique": technique,
                "setup": setup,
                "data_provider": data_provider,
                "markets": markets,
                "near_match_chart_limit": near_match_chart_limit,
                "previous_results": previous_results,
                "chart_workers": chart_workers,
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
            "--chart-workers",
            "4",
            "--previous-results",
            "reports/previous.json",
            "--technique",
            "nhathoai",
            "--setup",
            "rb",
            "--limit",
            "5",
            "--shard-index",
            "1",
            "--shard-count",
            "3",
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
    assert seen["chart_workers"] == 4
    assert seen["limit"] == 5
    assert seen["shard_index"] == 1
    assert seen["shard_count"] == 3
    assert "Wrote" in captured.out


def test_scan_all_market_cli_passes_chart_workers_to_scanner(tmp_path: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_scan_all_market(
        out: str,
        timeframe: str,
        config: str,
        period: str,
        limit: int,
        shard_index: int,
        shard_count: int,
        universe: str,
        broker: str,
        data_provider: str,
        markets: str,
        near_match_chart_limit: int,
        previous_results: str,
        chart_workers: int,
    ) -> Path:
        seen.update(
            {
                "out": out,
                "timeframe": timeframe,
                "config": config,
                "period": period,
                "limit": limit,
                "shard_index": shard_index,
                "shard_count": shard_count,
                "universe": universe,
                "broker": broker,
                "data_provider": data_provider,
                "markets": markets,
                "near_match_chart_limit": near_match_chart_limit,
                "previous_results": previous_results,
                "chart_workers": chart_workers,
            }
        )
        return tmp_path / "results.json"

    monkeypatch.setattr("filter_pattern.cli.scan_all_market", fake_scan_all_market)

    exit_code = main(
        [
            "scan-all-market",
            "--config",
            "config.yml",
            "--timeframe",
            "D1",
            "--out",
            str(tmp_path / "reports/all-market"),
            "--period",
            "180d",
            "--universe",
            "broad",
            "--broker",
            "exness",
            "--data-provider",
            "mixed",
            "--markets",
            "US stock",
            "--near-match-chart-limit",
            "5",
            "--chart-workers",
            "4",
            "--previous-results",
            "reports/previous.json",
            "--limit",
            "10",
            "--shard-index",
            "0",
            "--shard-count",
            "2",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert seen["universe"] == "broad"
    assert seen["broker"] == "exness"
    assert seen["data_provider"] == "mixed"
    assert seen["markets"] == "US stock"
    assert seen["near_match_chart_limit"] == 5
    assert seen["chart_workers"] == 4
    assert seen["previous_results"] == "reports/previous.json"
    assert seen["limit"] == 10
    assert seen["shard_count"] == 2
    assert "Wrote" in captured.out


def test_direction_backtest_cli_passes_options_to_runner(tmp_path: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_run_direction_backtest(
        out: str,
        timeframe: str,
        period: str,
        universe: str,
        markets: str,
        data_provider: str,
        limit: int,
        horizon: int,
        step: int,
        min_history: int,
    ) -> Path:
        seen.update(
            {
                "out": out,
                "timeframe": timeframe,
                "period": period,
                "universe": universe,
                "markets": markets,
                "data_provider": data_provider,
                "limit": limit,
                "horizon": horizon,
                "step": step,
                "min_history": min_history,
            }
        )
        return tmp_path / "direction-backtest/results.json"

    monkeypatch.setattr("filter_pattern.cli.run_direction_backtest", fake_run_direction_backtest)

    exit_code = main(
        [
            "direction-backtest",
            "--out",
            str(tmp_path / "direction-backtest"),
            "--timeframe",
            "D1",
            "--period",
            "5y",
            "--universe",
            "broad",
            "--markets",
            "Crypto,Commodity",
            "--data-provider",
            "mixed",
            "--limit",
            "20",
            "--horizon",
            "15",
            "--step",
            "3",
            "--min-history",
            "180",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert seen["out"] == str(tmp_path / "direction-backtest")
    assert seen["universe"] == "broad"
    assert seen["markets"] == "Crypto,Commodity"
    assert seen["data_provider"] == "mixed"
    assert seen["limit"] == 20
    assert seen["horizon"] == 15
    assert seen["step"] == 3
    assert seen["min_history"] == 180
    assert "Wrote" in captured.out


def test_usstock_rrg_demo_cli_passes_options_to_runner(tmp_path: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_runner(
        out: str,
        timeframe: str,
        config: str,
        period: str,
        technique: str,
        setup: str,
        max_sectors: int,
        max_symbols: int,
    ) -> Path:
        seen.update(
            {
                "out": out,
                "timeframe": timeframe,
                "config": config,
                "period": period,
                "technique": technique,
                "setup": setup,
                "max_sectors": max_sectors,
                "max_symbols": max_symbols,
            }
        )
        return tmp_path / "results.json"

    monkeypatch.setattr("filter_pattern.cli.build_usstock_rrg_demo", fake_runner)

    exit_code = main(
        [
            "usstock-rrg-demo",
            "--out",
            str(tmp_path / "reports/rrg"),
            "--timeframe",
            "D1",
            "--config",
            "config.yml",
            "--period",
            "2y",
            "--technique",
            "nhathoai",
            "--setup",
            "all",
            "--max-sectors",
            "3",
            "--max-symbols",
            "40",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert seen["out"] == str(tmp_path / "reports/rrg")
    assert seen["timeframe"] == "D1"
    assert seen["config"] == "config.yml"
    assert seen["period"] == "2y"
    assert seen["technique"] == "nhathoai"
    assert seen["setup"] == "all"
    assert seen["max_sectors"] == 3
    assert seen["max_symbols"] == 40
    assert "Wrote" in captured.out


def test_vnstock_rrg_demo_cli_passes_options_to_runner(tmp_path: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_runner(
        out: str,
        timeframe: str,
        config: str,
        period: str,
        technique: str,
        setup: str,
        max_sectors: int,
        max_symbols: int,
    ) -> Path:
        seen.update(
            {
                "out": out,
                "timeframe": timeframe,
                "config": config,
                "period": period,
                "technique": technique,
                "setup": setup,
                "max_sectors": max_sectors,
                "max_symbols": max_symbols,
            }
        )
        return tmp_path / "reports/vn-rrg/results.json"

    monkeypatch.setattr("filter_pattern.cli.build_vnstock_rrg_demo", fake_runner)

    exit_code = main(
        [
            "vnstock-rrg-demo",
            "--out",
            str(tmp_path / "reports/vn-rrg"),
            "--timeframe",
            "D1",
            "--config",
            "config.yml",
            "--period",
            "2y",
            "--technique",
            "nhathoai",
            "--setup",
            "all",
            "--max-sectors",
            "3",
            "--max-symbols",
            "40",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert seen["out"] == str(tmp_path / "reports/vn-rrg")
    assert seen["timeframe"] == "D1"
    assert seen["config"] == "config.yml"
    assert seen["period"] == "2y"
    assert seen["technique"] == "nhathoai"
    assert seen["setup"] == "all"
    assert seen["max_sectors"] == 3
    assert seen["max_symbols"] == 40
    assert "Wrote" in captured.out


def test_crypto_rrg_demo_cli_passes_options_to_runner(tmp_path: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_runner(
        out: str,
        timeframe: str,
        config: str,
        period: str,
        technique: str,
        setup: str,
        max_symbols: int,
    ) -> Path:
        seen.update(
            {
                "out": out,
                "timeframe": timeframe,
                "config": config,
                "period": period,
                "technique": technique,
                "setup": setup,
                "max_symbols": max_symbols,
            }
        )
        return tmp_path / "reports/crypto-rrg/results.json"

    monkeypatch.setattr("filter_pattern.cli.build_crypto_rrg_demo", fake_runner)

    exit_code = main(
        [
            "crypto-rrg-demo",
            "--out",
            str(tmp_path / "reports/crypto-rrg"),
            "--timeframe",
            "H4",
            "--config",
            "config.yml",
            "--period",
            "2y",
            "--technique",
            "nhathoai",
            "--setup",
            "all",
            "--max-symbols",
            "40",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert seen["out"] == str(tmp_path / "reports/crypto-rrg")
    assert seen["timeframe"] == "H4"
    assert seen["config"] == "config.yml"
    assert seen["period"] == "2y"
    assert seen["technique"] == "nhathoai"
    assert seen["setup"] == "all"
    assert seen["max_symbols"] == 40
    assert "Wrote" in captured.out


def test_crypto_rrg_overview_cli_passes_options_to_runner(tmp_path: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_runner(out: str, timeframe: str, max_symbols: int) -> Path:
        seen.update({"out": out, "timeframe": timeframe, "max_symbols": max_symbols})
        return tmp_path / "reports/crypto-rrg-overview/results.json"

    monkeypatch.setattr("filter_pattern.cli.build_crypto_rrg_overview", fake_runner)

    exit_code = main(
        [
            "crypto-rrg-overview",
            "--out",
            str(tmp_path / "reports/crypto-rrg-overview"),
            "--timeframe",
            "D1",
            "--max-symbols",
            "80",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert seen["out"] == str(tmp_path / "reports/crypto-rrg-overview")
    assert seen["timeframe"] == "D1"
    assert seen["max_symbols"] == 80
    assert "Wrote" in captured.out


def test_combine_report_cli_passes_inputs_to_report_writer(tmp_path: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_write_combined_outputs(inputs: list[str], out: str, results_out: str | None, copy_assets: bool):
        seen["inputs"] = inputs
        seen["out"] = out
        seen["results_out"] = results_out
        seen["copy_assets"] = copy_assets
        return tmp_path / "combined/index.html", None

    monkeypatch.setattr("filter_pattern.cli.write_combined_outputs", fake_write_combined_outputs)

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
    assert seen["results_out"] is None
    assert seen["copy_assets"] is False
    assert "Wrote" in captured.out


def test_combine_report_cli_can_write_combined_results_json(tmp_path: Path, monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_write_combined_outputs(inputs: list[str], out: str, results_out: str | None, copy_assets: bool):
        seen["inputs"] = inputs
        seen["out"] = out
        seen["results_out"] = results_out
        seen["copy_assets"] = copy_assets
        return tmp_path / "combined/index.html", tmp_path / "combined/results.json"

    monkeypatch.setattr("filter_pattern.cli.write_combined_outputs", fake_write_combined_outputs)

    exit_code = main(
        [
            "combine-report",
            "--inputs",
            "reports/us/results.json",
            "reports/crypto/results.json",
            "--out",
            str(tmp_path / "combined/index.html"),
            "--results-out",
            str(tmp_path / "combined/results.json"),
            "--copy-assets",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert seen["inputs"] == ["reports/us/results.json", "reports/crypto/results.json"]
    assert seen["results_out"] == str(tmp_path / "combined/results.json")
    assert seen["copy_assets"] is True
    assert "results.json" in captured.out
