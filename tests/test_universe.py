from __future__ import annotations

from collections import Counter

from filter_pattern.universe import _crypto_from_exchange_markets, default_universe, expand_crypto_universe, get_universe


def test_default_universe_covers_multiple_markets_with_substantial_non_us_lists() -> None:
    counts = Counter(item.market for item in default_universe())

    assert counts["US stock"] >= 60
    assert counts["Vietnam stock"] >= 300
    assert counts["Forex"] >= 30
    assert counts["Crypto"] >= 200
    assert counts["Commodity"] + counts["Commodity ETF"] >= 50


def test_broad_universe_includes_sp500_plus_cross_market_symbols() -> None:
    universe = get_universe("broad")
    counts = Counter(item.market for item in universe)

    assert len(universe) >= 900
    assert counts["US stock"] >= 500
    assert counts["Vietnam stock"] >= 300
    assert counts["Forex"] >= 80
    assert counts["Crypto"] >= 200
    assert counts["Commodity"] >= 30


def test_crypto_universe_uses_usdt_pairs_and_exchange_specific_tradingview_ids() -> None:
    crypto = [item for item in get_universe("default") if item.market == "Crypto"]
    by_symbol = {item.symbol: item for item in crypto}

    assert len(crypto) >= 200
    assert all(item.symbol.endswith("USDT") for item in crypto)
    assert by_symbol["BTCUSDT"].tradingview_symbol == "BINANCE:BTCUSDT"
    assert by_symbol["KASUSDT"].tradingview_symbol == "BYBIT:KASUSDT"


def test_dynamic_crypto_universe_dedupes_by_exchange_priority_and_filters_noise() -> None:
    crypto = _crypto_from_exchange_markets(
        [
            ("binance", {"symbol": "BTC/USDT", "base": "BTC", "quote": "USDT", "spot": True, "active": True}),
            ("mexc", {"symbol": "BTC/USDT", "base": "BTC", "quote": "USDT", "spot": True, "active": True}),
            ("mexc", {"symbol": "EARLY/USDT", "base": "EARLY", "quote": "USDT", "spot": True, "active": True}),
            ("bybit", {"symbol": "PEPE/USDT", "base": "PEPE", "quote": "USDT", "type": "spot", "active": True}),
            ("okx", {"symbol": "USDC/USDT", "base": "USDC", "quote": "USDT", "spot": True, "active": True}),
            ("mexc", {"symbol": "BTC3L/USDT", "base": "BTC3L", "quote": "USDT", "spot": True, "active": True}),
            ("mexc", {"symbol": "ETH/USDT:USDT", "base": "ETH", "quote": "USDT", "swap": True, "active": True}),
        ]
    )
    by_symbol = {item.symbol: item for item in crypto}

    assert list(by_symbol) == ["BTCUSDT", "EARLYUSDT", "PEPEUSDT"]
    assert by_symbol["BTCUSDT"].tradingview_symbol == "BINANCE:BTCUSDT"
    assert by_symbol["EARLYUSDT"].tradingview_symbol == "MEXC:EARLYUSDT"
    assert by_symbol["PEPEUSDT"].tradingview_symbol == "BYBIT:PEPEUSDT"


def test_dynamic_crypto_perp_universe_uses_swap_markets_and_tradingview_p_suffix() -> None:
    crypto = _crypto_from_exchange_markets(
        [
            ("binance", {"symbol": "BTC/USDT", "base": "BTC", "quote": "USDT", "spot": True, "active": True}),
            ("binance", {"symbol": "BTC/USDT:USDT", "base": "BTC", "quote": "USDT", "swap": True, "active": True}),
            ("bybit", {"symbol": "PEPE/USDT:USDT", "base": "PEPE", "quote": "USDT", "type": "swap", "active": True}),
            ("okx", {"symbol": "ETH/USD:USD", "base": "ETH", "quote": "USD", "swap": True, "active": True}),
            ("mexc", {"symbol": "BTC3L/USDT:USDT", "base": "BTC3L", "quote": "USDT", "swap": True, "active": True}),
        ],
        market_type="perp",
    )
    by_symbol = {item.symbol: item for item in crypto}

    assert list(by_symbol) == ["BTCUSDT", "PEPEUSDT"]
    assert by_symbol["BTCUSDT"].tradingview_symbol == "BINANCE:BTCUSDT.P"
    assert by_symbol["PEPEUSDT"].tradingview_symbol == "BYBIT:PEPEUSDT.P"


def test_dynamic_crypto_universe_rejects_tokenized_stock_and_commodity_markets() -> None:
    crypto = _crypto_from_exchange_markets(
        [
            ("mexc", {"symbol": "AAPLSTOCK/USDT:USDT", "base": "AAPLSTOCK", "quote": "USDT", "swap": True, "active": True}),
            ("mexc", {"symbol": "XAUT/USDT:USDT", "base": "XAUT", "quote": "USDT", "swap": True, "active": True}),
            ("mexc", {"symbol": "GOLD/USDT:USDT", "base": "GOLD", "quote": "USDT", "swap": True, "active": True}),
            ("mexc", {"symbol": "OIL/USDT:USDT", "base": "OIL", "quote": "USDT", "swap": True, "active": True}),
            ("mexc", {"symbol": "ATOM/USDT:USDT", "base": "ATOM", "quote": "USDT", "swap": True, "active": True}),
        ],
        market_type="perp",
    )

    assert [item.symbol for item in crypto] == ["ATOMUSDT"]


def test_dynamic_crypto_perp_universe_rejects_spot_only_markets() -> None:
    crypto = _crypto_from_exchange_markets(
        [
            ("binance", {"symbol": "BTC/USDT", "base": "BTC", "quote": "USDT", "spot": True, "active": True}),
            ("bybit", {"symbol": "ETH/USDT", "base": "ETH", "quote": "USDT", "type": "spot", "active": True}),
        ],
        market_type="perp",
    )

    assert crypto == []


def test_dynamic_crypto_spot_universe_rejects_swap_markets() -> None:
    crypto = _crypto_from_exchange_markets(
        [
            ("binance", {"symbol": "BTC/USDT:USDT", "base": "BTC", "quote": "USDT", "swap": True, "active": True}),
            ("bybit", {"symbol": "ETH/USDT", "base": "ETH", "quote": "USDT", "type": "spot", "active": True}),
        ],
        market_type="spot",
    )

    assert [item.symbol for item in crypto] == ["ETHUSDT"]
    assert crypto[0].tradingview_symbol == "BYBIT:ETHUSDT"


def test_expand_crypto_universe_can_limit_dynamic_crypto_symbols(monkeypatch) -> None:
    base = [
        _crypto_from_exchange_markets(
            [("binance", {"symbol": "BTC/USDT", "base": "BTC", "quote": "USDT", "spot": True, "active": True})]
        )[0],
    ]
    dynamic = _crypto_from_exchange_markets(
        [
            ("binance", {"symbol": "BTC/USDT", "base": "BTC", "quote": "USDT", "spot": True, "active": True}),
            ("binance", {"symbol": "ETH/USDT", "base": "ETH", "quote": "USDT", "spot": True, "active": True}),
            ("mexc", {"symbol": "PEPE/USDT", "base": "PEPE", "quote": "USDT", "spot": True, "active": True}),
        ]
    )
    seen: dict[str, str] = {}

    def fake_discover(exchange_id: str, market_type: str = "spot"):
        seen["exchange_id"] = exchange_id
        seen["market_type"] = market_type
        return dynamic

    monkeypatch.setattr("filter_pattern.universe.discover_crypto_universe", fake_discover)

    expanded = expand_crypto_universe(base, exchange_id="binance,mexc", market_type="perp", max_symbols=2)

    assert seen["exchange_id"] == "binance,mexc"
    assert seen["market_type"] == "perp"
    assert [item.symbol for item in expanded] == ["BTCUSDT", "ETHUSDT"]


def test_expand_crypto_universe_limits_static_fallback_when_discovery_fails(monkeypatch) -> None:
    base = _crypto_from_exchange_markets(
        [
            ("binance", {"symbol": "BTC/USDT", "base": "BTC", "quote": "USDT", "spot": True, "active": True}),
            ("binance", {"symbol": "ETH/USDT", "base": "ETH", "quote": "USDT", "spot": True, "active": True}),
            ("bybit", {"symbol": "PEPE/USDT", "base": "PEPE", "quote": "USDT", "type": "spot", "active": True}),
        ]
    )

    monkeypatch.setattr("filter_pattern.universe.discover_crypto_universe", lambda exchange_id, market_type="spot": [])

    expanded = expand_crypto_universe(base, exchange_id="binance,bybit", market_type="perp", max_symbols=2)

    assert [item.symbol for item in expanded] == ["BTCUSDT", "ETHUSDT"]
