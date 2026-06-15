from __future__ import annotations

from filter_pattern import rrg_dashboard
from filter_pattern.rrg_dashboard import RRGSelection, rrg_confidence, rrg_intent


def test_rrg_intent_accepts_improving_with_rising_head() -> None:
    points = [
        {"x": 98.6, "y": 99.2},
        {"x": 98.9, "y": 99.7},
        {"x": 99.2, "y": 100.2},
        {"x": 99.5, "y": 100.7},
    ]

    intent = rrg_intent(points)

    assert intent["accepted"] is True
    assert intent["quadrant"] == "IMPROVING"
    assert intent["dy1"] > 0


def test_rrg_intent_rejects_leading_when_head_falls_two_steps() -> None:
    points = [
        {"x": 101.0, "y": 103.0},
        {"x": 101.4, "y": 102.4},
        {"x": 101.8, "y": 101.9},
        {"x": 102.0, "y": 101.5},
    ]

    intent = rrg_intent(points)

    assert intent["accepted"] is False
    assert intent["quadrant"] == "LEADING"
    assert intent["two_steps_down"] is True


def test_rrg_confidence_treats_lagging_rising_head_as_early_reference() -> None:
    points = [
        {"x": 96.8, "y": 98.4},
        {"x": 97.0, "y": 98.6},
        {"x": 97.4, "y": 98.9},
        {"x": 97.9, "y": 99.3},
    ]

    intent = rrg_intent(points)
    confidence = rrg_confidence(intent)

    assert intent["accepted"] is False
    assert confidence["label"] == "RRG Early Reference"
    assert confidence["blocks_pattern"] is False


def test_stockcharts_auth_can_come_from_environment(monkeypatch) -> None:
    seen: dict[str, str] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"rrgdata": []}

    def fake_get(url: str, **kwargs) -> FakeResponse:
        seen["url"] = url
        seen["headers"] = kwargs.get("headers", {})
        return FakeResponse()

    monkeypatch.setenv("STOCKCHARTS_RRG_AUTH", "env-token")
    monkeypatch.setattr(rrg_dashboard.requests, "get", fake_get)

    rrg_dashboard._fetch_stockcharts_rrg(["XLF"], "SPY")

    assert "auth=env-token" in seen["url"]
    assert "_=" in seen["url"]
    assert seen["headers"]["Cache-Control"] == "no-cache"
    assert seen["headers"]["Pragma"] == "no-cache"


def test_fialda_rrg_series_uses_ratio_and_momentum_fields() -> None:
    payload = {
        "result": [
            {"date": "20260528", "rrgdata": {"FPT": {"price": 75.0, "ratio": 99.2, "mom": 100.1}}},
            {"date": "20260529", "rrgdata": {"FPT": {"price": 76.0, "ratio": 99.7, "mom": 100.4}}},
        ]
    }

    series = rrg_dashboard._series_from_fialda(payload, ["FPT"])

    assert series == {
        "FPT": [
            {"x": 99.2, "y": 100.1, "price": 75.0, "date": "20260528"},
            {"x": 99.7, "y": 100.4, "price": 76.0, "date": "20260529"},
        ]
    }


def test_crypto_symbol_mapping_for_stockcharts_rrg() -> None:
    assert rrg_dashboard._crypto_stockcharts_symbol("BTCUSDT") == "$BTCUSD"
    assert rrg_dashboard._crypto_stockcharts_symbol("ATOMUSDT.P") == "$ATOMUSD"
    assert rrg_dashboard._crypto_from_stockcharts_symbol("$ATOMUSD") == "ATOMUSDT"
    assert rrg_dashboard._crypto_rrg_period("D1") == "d"
    assert rrg_dashboard._crypto_rrg_period("H4") == "240"


def test_cross_market_stockcharts_rrg_symbol_mapping() -> None:
    assert rrg_dashboard._forex_stockcharts_symbol("EURUSD") == "$EURUSD"
    assert rrg_dashboard._commodity_stockcharts_symbol("XAUUSD", "Commodity") == "$GOLD"
    assert rrg_dashboard._commodity_stockcharts_symbol("USOIL", "Commodity") == "$WTIC"
    assert rrg_dashboard._commodity_stockcharts_symbol("GOLD_ETF", "Commodity ETF") == "GLD"
    assert rrg_dashboard._commodity_stockcharts_symbol("DBC", "Commodity ETF") == "DBC"


def test_commodity_rrg_references_keep_all_alias_symbols(monkeypatch) -> None:
    payload = {
        "rrgdata": [
            {"rrgdata": {"$WTIC": {"jdkratio": 99.0, "jdkmom": 99.6, "price": 75.0}}},
            {"rrgdata": {"$WTIC": {"jdkratio": 99.5, "jdkmom": 99.8, "price": 76.0}}},
            {"rrgdata": {"$WTIC": {"jdkratio": 100.1, "jdkmom": 100.0, "price": 77.0}}},
            {"rrgdata": {"$WTIC": {"jdkratio": 100.8, "jdkmom": 100.4, "price": 78.0}}},
        ]
    }

    def fake_fetch(symbols: list[str], benchmark: str) -> dict:
        assert symbols == ["$WTIC"]
        assert benchmark == "$ONE"
        return payload

    monkeypatch.setattr(rrg_dashboard, "_fetch_stockcharts_rrg", fake_fetch)
    monkeypatch.setattr(rrg_dashboard.time, "sleep", lambda _seconds: None)

    selections = rrg_dashboard._commodity_rrg_references(["USOIL", "WTI"], "Commodity")

    assert set(selections) == {"USOIL", "WTI"}
    assert selections["USOIL"].rrg_series == selections["WTI"].rrg_series


def test_rrg_reference_attaches_to_review_setup_rows(tmp_path, monkeypatch) -> None:
    review_row = {
        "symbol": "XZNUSD",
        "market": "Commodity",
        "tradingview_symbol": "EXNESS:XZNUSD",
        "timeframe": "D1",
        "technique": "nhathoai",
        "setup": "compression",
        "chart_path": str(tmp_path / "charts/xznusd.jpg"),
        "evidence": {"score": 85, "status": "rejected"},
    }
    selection = RRGSelection(
        symbol="XZNUSD",
        sector="Commodity",
        benchmark="$ONE",
        latest={"x": 101.0, "y": 102.0},
        intent={"quadrant": "LEADING", "dx1": 0.2, "dy1": 0.4, "dx2": 0.1, "dy2": 0.2, "two_steps_down": False},
        sector_latest={},
        sector_intent={},
        rrg_series=[{"x": 99.8, "y": 99.9}, {"x": 100.0, "y": 100.2}, {"x": 100.4, "y": 101.0}, {"x": 101.0, "y": 102.0}],
    )

    def fake_commodity_rrg_references(symbols: list[str], market: str) -> dict[str, RRGSelection]:
        assert symbols == ["XZNUSD"]
        assert market == "Commodity"
        return {"XZNUSD": selection}

    def fake_render_rrg_proof(selected: RRGSelection, selections: list[RRGSelection], out_dir):
        path = out_dir / "xznusd-rrg-proof.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake jpg")
        return path

    monkeypatch.setattr(rrg_dashboard, "_commodity_rrg_references", fake_commodity_rrg_references)
    monkeypatch.setattr(rrg_dashboard, "_render_stock_rrg_proof", fake_render_rrg_proof)

    payload = rrg_dashboard.attach_rrg_references({"review_setups": [review_row]}, tmp_path, "D1")

    assert payload["rrg_reference"]["status"] == "attached"
    assert payload["review_setups"][0]["rrg"]["rrg_chart_path"].endswith("xznusd-rrg-proof.jpg")


def test_rrg_reference_adds_daily_market_representatives(tmp_path, monkeypatch) -> None:
    candidate = {
        "symbol": "AAPL",
        "market": "US stock",
        "timeframe": "H4",
        "setup": "rb",
        "evidence": {"score": 91, "status": "WAITING"},
    }
    symbol_selection = RRGSelection(
        symbol="AAPL",
        sector="Information Technology",
        benchmark="XLK",
        latest={"x": 100.5, "y": 101.0},
        intent={"quadrant": "LEADING", "dx1": 0.4, "dy1": 0.8},
        sector_latest={},
        sector_intent={},
        rrg_series=[{"x": 99.8, "y": 100.1}, {"x": 100.5, "y": 101.0}],
    )
    spy_selection = RRGSelection(
        symbol="SPY",
        sector="US stock",
        benchmark="SPY",
        latest={"x": 101.4, "y": 101.2},
        intent={"quadrant": "LEADING", "dx1": 1.2, "dy1": 1.1},
        sector_latest={},
        sector_intent={},
        rrg_series=[{"x": 99.0, "y": 98.6}, {"x": 101.4, "y": 101.2}],
    )

    calls: list[list[str]] = []

    def fake_usstock_rrg_references(symbols: list[str]) -> dict[str, RRGSelection]:
        calls.append(symbols)
        return {selection.symbol: selection for selection in (symbol_selection, spy_selection) if selection.symbol in symbols}

    monkeypatch.setattr(rrg_dashboard, "_usstock_rrg_references", fake_usstock_rrg_references)
    monkeypatch.setattr(rrg_dashboard, "_render_stock_rrg_proof", lambda _selected, _selections, out_dir: out_dir / "aapl-rrg-proof.jpg")

    payload = rrg_dashboard.attach_rrg_references({"candidates": [candidate]}, tmp_path, "H4")

    assert ["AAPL"] in calls
    assert ["SPY"] in calls
    representatives = payload["rrg_reference"]["market_representatives"]
    assert representatives[0]["symbol"] == "SPY"
    assert representatives[0]["market"] == "US stock"
    assert representatives[0]["timeframe"] == "D1"
    assert representatives[0]["rrg"]["stock_intent"]["quadrant"] == "LEADING"


def test_rrg_reference_adds_btc_and_eth_crypto_market_representatives(tmp_path, monkeypatch) -> None:
    candidate = {
        "symbol": "SOLUSDT",
        "market": "Crypto",
        "timeframe": "H4",
        "setup": "vcp",
        "evidence": {"score": 82, "status": "WAITING"},
    }
    btc_selection = RRGSelection(
        symbol="BTCUSDT",
        sector="Crypto",
        benchmark="$ONE",
        latest={"x": 101.4, "y": 101.2},
        intent={"quadrant": "LEADING", "dx1": 1.2, "dy1": 1.1},
        sector_latest={},
        sector_intent={},
        rrg_series=[{"x": 99.0, "y": 98.6}, {"x": 101.4, "y": 101.2}],
    )
    eth_selection = RRGSelection(
        symbol="ETHUSDT",
        sector="Crypto",
        benchmark="$ONE",
        latest={"x": 100.8, "y": 100.5},
        intent={"quadrant": "LEADING", "dx1": 0.8, "dy1": 0.6},
        sector_latest={},
        sector_intent={},
        rrg_series=[{"x": 99.4, "y": 99.7}, {"x": 100.8, "y": 100.5}],
    )

    calls: list[tuple[list[str], str]] = []

    def fake_crypto_rrg_references(symbols: list[str], timeframe: str) -> dict[str, RRGSelection]:
        calls.append((symbols, timeframe))
        return {
            selection.symbol: selection
            for selection in (btc_selection, eth_selection)
            if selection.symbol in symbols
        }

    monkeypatch.setattr(rrg_dashboard, "_crypto_rrg_references", fake_crypto_rrg_references)

    payload = rrg_dashboard.attach_rrg_references({"candidates": [candidate]}, tmp_path, "H4")

    assert (["SOLUSDT"], "H4") in calls
    assert (["BTCUSDT", "ETHUSDT"], "D1") in calls
    representatives = payload["rrg_reference"]["market_representatives"]
    crypto_representatives = [row for row in representatives if row["market"] == "Crypto"]
    assert [row["symbol"] for row in crypto_representatives] == ["BTC", "ETH"]
    assert all(row["timeframe"] == "D1" for row in crypto_representatives)


def test_vn_symbol_sector_map_uses_top_level_icb() -> None:
    icb_tree = [
        {
            "icbId": 138,
            "icbCode": "8300",
            "icbName": "Tài chính (8300 - Cấp 1)",
            "childs": [{"icbId": 139, "icbCode": "8350", "icbName": "Ngân hàng (8350 - Cấp 2)", "childs": []}],
        }
    ]
    symbols = [
        {"symbol": "VCB", "type": "Stock", "exchange": "HSX", "icbCode": "8350", "icbCode_Lvl4": "8355"},
        {"symbol": "CACB2516", "type": "CoveredWarrant", "exchange": "HSX", "icbCode": None},
    ]

    sector_map = rrg_dashboard._vn_symbol_sector_map(icb_tree, symbols, {"VCB", "FPT"})

    assert sector_map["VCB"]["sector_id"] == "138"
    assert sector_map["VCB"]["sector"] == "Tài chính"
    assert sector_map["VCB"]["exchange"] == "HSX"


def test_usstock_rrg_selections_are_limited_to_exness_supported_symbols() -> None:
    supported = RRGSelection(
        symbol="AAPL",
        sector="Information Technology",
        benchmark="XLK",
        latest={"x": 101, "y": 102},
        intent={"score": 10},
        sector_latest={},
        sector_intent={},
        rrg_series=[],
    )
    unsupported = RRGSelection(
        symbol="FDS",
        sector="Financials",
        benchmark="XLF",
        latest={"x": 101, "y": 102},
        intent={"score": 20},
        sector_latest={},
        sector_intent={},
        rrg_series=[],
    )

    filtered = rrg_dashboard._filter_exness_supported_us_stocks([unsupported, supported])

    assert [item.symbol for item in filtered] == ["AAPL"]


def test_candidate_card_uses_large_same_line_chart_layout(tmp_path) -> None:
    html = rrg_dashboard._candidate_card(
        {
            "symbol": "AAPL",
            "setup": "rb",
            "chart_path": str(tmp_path / "charts/AAPL.jpg"),
            "evidence": {"score": 98},
            "rrg": {
                "sector": "Information Technology",
                "benchmark": "XLK",
                "rrg_chart_path": str(tmp_path / "rrg/aapl.jpg"),
                "stock_intent": {"quadrant": "LEADING", "dy1": 0.42},
            },
        },
        tmp_path,
    )

    assert 'class="chart-row"' in html
    assert 'class="shot shot-main"' in html
    assert 'class="shot shot-rrg"' in html


def test_dashboard_omits_left_feature_selection(tmp_path) -> None:
    output = tmp_path / "index.html"
    rrg_dashboard._write_usstock_rrg_dashboard(
        {
            "generated_at": "2026-05-29T00:00:00+00:00",
            "candidates": [],
            "rrg_filter": {"sector_count": 0, "approved_symbol_count": 0, "sectors": []},
        },
        output,
    )

    html = output.read_text()
    assert "<aside class=\"sidebar\">" not in html
    assert ".sidebar" not in html
    assert "Feature" not in html
    assert "Sector Filter" not in html


def test_dashboard_keeps_filters_on_top(tmp_path) -> None:
    output = tmp_path / "index.html"
    rrg_dashboard._write_usstock_rrg_dashboard(
        {
            "generated_at": "2026-05-29T00:00:00+00:00",
            "timeframe": "D1",
            "candidates": [
                {
                    "symbol": "AAPL",
                    "timeframe": "D1",
                    "setup": "rb",
                    "chart_path": str(tmp_path / "charts/AAPL.jpg"),
                    "evidence": {"score": 98},
                    "rrg": {
                        "sector": "Information Technology",
                        "benchmark": "XLK",
                        "rrg_chart_path": str(tmp_path / "rrg/aapl.jpg"),
                        "stock_intent": {"quadrant": "LEADING", "dy1": 0.42},
                    },
                }
            ],
            "rrg_filter": {"sector_count": 1, "approved_symbol_count": 1, "sectors": []},
            "config": {"broker_filter": "exness"},
        },
        output,
    )

    html = output.read_text()
    assert 'class="toolbar"' in html
    assert 'id="search"' in html
    assert 'id="setupFilter"' in html
    assert 'id="sectorFilter"' in html
    assert 'id="quadrantFilter"' in html
    assert 'id="filterCount"' in html
    assert "Broker: Exness" in html


def test_vn_dashboard_uses_vietnam_labels_without_broker_metric(tmp_path) -> None:
    output = tmp_path / "index.html"
    rrg_dashboard._write_usstock_rrg_dashboard(
        {
            "generated_at": "2026-05-29T00:00:00+00:00",
            "market": "Vietnam stock",
            "timeframe": "D1",
            "candidates": [],
            "rrg_filter": {"sector_count": 0, "approved_symbol_count": 0, "sectors": [], "benchmark": "VNINDEX"},
            "config": {"broker_filter": "none"},
        },
        output,
    )

    html = output.read_text()
    assert "Vietnam stock" in html
    assert "US stock demo" not in html
    assert "Exness-supported" not in html
    assert "Broker: NONE" not in html


def test_crypto_dashboard_uses_crypto_labels_without_sector_count(tmp_path) -> None:
    output = tmp_path / "index.html"
    rrg_dashboard._write_usstock_rrg_dashboard(
        {
            "generated_at": "2026-05-29T00:00:00+00:00",
            "market": "Crypto",
            "timeframe": "H4",
            "candidates": [],
            "rrg_filter": {"sector_count": 0, "approved_symbol_count": 0, "sectors": [], "benchmark": "$ONE"},
            "config": {"broker_filter": "none"},
        },
        output,
    )

    html = output.read_text()
    assert "Crypto" in html
    assert "Sector RRG Gate" not in html
    assert 'id="sectorFilter"' not in html
    assert "Sector RRG filters" not in html
    assert "RRG Symbols Scanned" in html


def test_candidate_card_keeps_setup_name_directly_above_chart_row(tmp_path) -> None:
    chart_path = tmp_path / "charts/AAPL.jpg"
    rrg_path = tmp_path / "rrg/aapl.jpg"
    chart_preview = chart_path.parent / "preview" / chart_path.name
    rrg_preview = rrg_path.parent / "preview" / rrg_path.name
    chart_preview.parent.mkdir(parents=True)
    rrg_preview.parent.mkdir(parents=True)
    chart_preview.write_bytes(b"preview")
    rrg_preview.write_bytes(b"preview")
    html = rrg_dashboard._candidate_card(
        {
            "symbol": "AAPL",
            "setup": "rb",
            "chart_path": str(chart_path),
            "evidence": {"score": 98},
            "rrg": {
                "sector": "Information Technology",
                "benchmark": "XLK",
                "rrg_chart_path": str(rrg_path),
                "stock_intent": {"quadrant": "LEADING", "dy1": 0.42},
            },
        },
        tmp_path,
    )

    assert 'class="setup-strip"' in html
    assert "RB setup" in html
    assert html.index('class="setup-strip"') < html.index('class="chart-row"')
    assert "CURRENT marker is latest position" in html
    assert 'href="charts/AAPL.jpg"' in html
    assert 'src="charts/preview/AAPL.jpg"' in html
    assert 'href="rrg/aapl.jpg"' in html
    assert 'src="rrg/preview/aapl.jpg"' in html


def test_selected_rrg_final_arrow_is_the_visual_head() -> None:
    final_props = rrg_dashboard._rrg_arrow_props("#16a34a", 0.96, is_selected=True, is_final=True)
    earlier_props = rrg_dashboard._rrg_arrow_props("#16a34a", 0.96, is_selected=True, is_final=False)

    assert final_props["arrowstyle"].startswith("-|>")
    assert final_props["mutation_scale"] > earlier_props["mutation_scale"]
    assert final_props["lw"] > earlier_props["lw"]


def test_rrg_proof_writes_fast_preview_image(tmp_path) -> None:
    selected = RRGSelection(
        symbol="AAPL",
        sector="Information Technology",
        benchmark="XLK",
        latest={"x": 101.4, "y": 102.2},
        intent={"quadrant": "LEADING", "dy1": 0.6},
        sector_latest={},
        sector_intent={},
        rrg_series=[
            {"x": 99.8, "y": 99.6},
            {"x": 100.2, "y": 100.4},
            {"x": 100.8, "y": 101.6},
            {"x": 101.4, "y": 102.2},
        ],
    )

    rrg_path = rrg_dashboard._render_stock_rrg_proof(selected, [selected], tmp_path / "rrg")

    preview_path = rrg_path.parent / "preview" / rrg_path.name
    assert rrg_path.exists()
    assert preview_path.exists()
    assert preview_path.stat().st_size < rrg_path.stat().st_size
