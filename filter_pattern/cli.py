from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .report import write_combined_html_report, write_html_report
from .scanner import scan_all_csv, scan_all_market, scan_csv, scan_market
from .techniques import NHATHOAI_SETUP_CHOICES, TECHNIQUE_CHOICES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D1/H4 pattern scanner and proof report")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="scan configured symbols and generate report artifacts")
    scan_parser.add_argument("--config", required=True, help="YAML config path")
    scan_parser.add_argument("--timeframe", default="D1", choices=["D1", "H4"], help="timeframe to scan")
    scan_parser.add_argument("--out", required=True, help="output directory")
    scan_parser.add_argument(
        "--technique",
        default=None,
        choices=TECHNIQUE_CHOICES,
        help="pattern technique to scan; defaults to config.yml technique, or minervini-vcp",
    )
    scan_parser.add_argument(
        "--setup",
        default=None,
        choices=NHATHOAI_SETUP_CHOICES,
        help="setup name for --technique nhathoai; defaults to config.yml setup, or all",
    )

    all_csv_parser = subparsers.add_parser(
        "scan-all",
        help="scan TradingView CSV exports once for original VCP plus every implemented setup",
    )
    all_csv_parser.add_argument("--config", required=True, help="YAML config path with TradingView CSV exports")
    all_csv_parser.add_argument("--timeframe", default="D1", choices=["D1", "H4"], help="timeframe to scan")
    all_csv_parser.add_argument("--out", required=True, help="output directory")

    market_parser = subparsers.add_parser("scan-market", help="download and scan a curated cross-market universe")
    market_parser.add_argument("--config", help="optional YAML config; VCP thresholds plus technique/setup defaults are used")
    market_parser.add_argument("--timeframe", default="D1", choices=["D1", "H4"], help="timeframe to scan")
    market_parser.add_argument("--out", required=True, help="output directory")
    market_parser.add_argument("--period", default="2y", help="Yahoo Finance history period, for example 1y, 2y, 5y")
    market_parser.add_argument(
        "--universe",
        default="default",
        choices=["default", "sp500", "broad"],
        help="symbol universe to scan",
    )
    market_parser.add_argument(
        "--broker",
        default="all",
        choices=["all", "exness"],
        help="filter selected markets to symbols supported by a broker",
    )
    market_parser.add_argument(
        "--data-provider",
        default="yahoo",
        choices=["yahoo", "mixed", "ccxt", "vnstock"],
        help="market data provider: yahoo, mixed (VNStock for Vietnam + CCXT for crypto), ccxt, or vnstock",
    )
    market_parser.add_argument(
        "--markets",
        default="all",
        help="comma-separated market filter, for example: 'US stock,Commodity,Forex,Crypto'",
    )
    market_parser.add_argument(
        "--near-match-chart-limit",
        type=int,
        default=20,
        help="maximum number of rejected near-match proof charts to render",
    )
    market_parser.add_argument(
        "--previous-results",
        help="previous results.json to compare against for watchlist change tracking",
    )
    market_parser.add_argument(
        "--technique",
        default=None,
        choices=TECHNIQUE_CHOICES,
        help="pattern technique to scan; defaults to config.yml technique, or minervini-vcp",
    )
    market_parser.add_argument(
        "--setup",
        default=None,
        choices=NHATHOAI_SETUP_CHOICES,
        help="setup name for --technique nhathoai; defaults to config.yml setup, or all",
    )
    market_parser.add_argument("--limit", type=int, help="scan only the first N universe symbols")

    all_market_parser = subparsers.add_parser(
        "scan-all-market",
        help="download once and scan original VCP plus every implemented Nhật Hoài setup",
    )
    all_market_parser.add_argument("--config", help="optional YAML config; VCP thresholds are used")
    all_market_parser.add_argument("--timeframe", default="D1", choices=["D1", "H4"], help="timeframe to scan")
    all_market_parser.add_argument("--out", required=True, help="output directory")
    all_market_parser.add_argument("--period", default="2y", help="Yahoo Finance history period, for example 1y, 2y, 5y")
    all_market_parser.add_argument(
        "--universe",
        default="default",
        choices=["default", "sp500", "broad"],
        help="symbol universe to scan",
    )
    all_market_parser.add_argument(
        "--broker",
        default="all",
        choices=["all", "exness"],
        help="filter selected markets to symbols supported by a broker",
    )
    all_market_parser.add_argument(
        "--data-provider",
        default="yahoo",
        choices=["yahoo", "mixed", "ccxt", "vnstock"],
        help="market data provider: yahoo, mixed (VNStock for Vietnam + CCXT for crypto), ccxt, or vnstock",
    )
    all_market_parser.add_argument(
        "--markets",
        default="all",
        help="comma-separated market filter, for example: 'US stock,Commodity,Forex,Crypto'",
    )
    all_market_parser.add_argument(
        "--near-match-chart-limit",
        type=int,
        default=20,
        help="maximum number of rejected near-match proof charts to render",
    )
    all_market_parser.add_argument(
        "--previous-results",
        help="previous results.json to compare against for watchlist change tracking",
    )
    all_market_parser.add_argument("--limit", type=int, help="scan only the first N universe symbols")

    init_parser = subparsers.add_parser("init-config", help="create a starter config.yml from the example")
    init_parser.add_argument("--out", default="config.yml", help="config path to create")
    init_parser.add_argument("--force", action="store_true", help="overwrite the output file if it exists")

    report_parser = subparsers.add_parser("report", help="regenerate HTML report from results.json")
    report_parser.add_argument("--input", required=True, help="results.json path")
    report_parser.add_argument("--out", required=True, help="HTML output path")

    combine_parser = subparsers.add_parser("combine-report", help="combine multiple results.json files into one HTML report")
    combine_parser.add_argument("--inputs", nargs="+", required=True, help="results.json files to combine")
    combine_parser.add_argument("--out", required=True, help="combined HTML output path")

    args = parser.parse_args(argv)
    try:
        if args.command == "init-config":
            output_path = _init_config(args.out, args.force)
            print(f"Wrote {output_path}")
            print("Edit csv_path values so they point to your TradingView D1 or H4 CSV exports.")
            return 0
        if args.command == "scan":
            results_path = scan_csv(args.config, args.out, args.timeframe, args.technique, args.setup)
            print(f"Wrote {results_path}")
            print(f"Wrote {Path(args.out) / 'index.html'}")
            return 0
        if args.command == "scan-all":
            results_path = scan_all_csv(args.config, args.out, args.timeframe)
            print(f"Wrote {results_path}")
            print(f"Wrote {Path(args.out) / 'index.html'}")
            return 0
        if args.command == "scan-market":
            results_path = scan_market(
                args.out,
                args.timeframe,
                args.config,
                args.period,
                args.limit,
                args.universe,
                args.broker,
                args.technique,
                args.setup,
                args.data_provider,
                args.markets,
                args.near_match_chart_limit,
                args.previous_results,
            )
            print(f"Wrote {results_path}")
            print(f"Wrote {Path(args.out) / 'index.html'}")
            return 0
        if args.command == "scan-all-market":
            results_path = scan_all_market(
                args.out,
                args.timeframe,
                args.config,
                args.period,
                args.limit,
                args.universe,
                args.broker,
                args.data_provider,
                args.markets,
                args.near_match_chart_limit,
                args.previous_results,
            )
            print(f"Wrote {results_path}")
            print(f"Wrote {Path(args.out) / 'index.html'}")
            return 0
        if args.command == "report":
            output_path = write_html_report(args.input, args.out)
            print(f"Wrote {output_path}")
            return 0
        if args.command == "combine-report":
            output_path = write_combined_html_report(args.inputs, args.out)
            print(f"Wrote {output_path}")
            return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 1


def _init_config(out: str, force: bool = False) -> Path:
    output_path = Path(out)
    if output_path.exists() and not force:
        raise ValueError(f"Config already exists: {output_path}. Use --force to overwrite it.")

    example_path = Path(__file__).resolve().parent.parent / "examples" / "config.example.yml"
    if not example_path.exists():
        raise FileNotFoundError(f"Example config not found: {example_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example_path, output_path)
    return output_path


if __name__ == "__main__":
    raise SystemExit(main())
