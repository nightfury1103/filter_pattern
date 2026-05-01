from __future__ import annotations

from filter_pattern.exness import filter_exness_supported
from filter_pattern.universe import UniverseSymbol, get_universe


def test_exness_filter_limits_us_forex_and_commodities_but_keeps_other_markets() -> None:
    items = [
        UniverseSymbol("AAPL", "US stock", "NASDAQ:AAPL", "AAPL"),
        UniverseSymbol("SPY", "US stock", "AMEX:SPY", "SPY"),
        UniverseSymbol("EURUSD", "Forex", "OANDA:EURUSD", "EURUSD=X"),
        UniverseSymbol("EURHUF", "Forex", "OANDA:EURHUF", "EURHUF=X"),
        UniverseSymbol("XAUUSD", "Commodity", "OANDA:XAUUSD", "GC=F"),
        UniverseSymbol("XNIUSD", "Commodity", "EXNESS:XNIUSD", "NICKEL=F"),
        UniverseSymbol("CORN", "Commodity", "CBOT:ZC1!", "ZC=F"),
        UniverseSymbol("FPT", "Vietnam stock", "HOSE:FPT", "FPT.VN"),
        UniverseSymbol("BTCUSDT", "Crypto", "BINANCE:BTCUSDT", "BTC-USD"),
    ]

    filtered = filter_exness_supported(items)

    assert [item.symbol for item in filtered] == ["AAPL", "EURUSD", "EURHUF", "XAUUSD", "XNIUSD", "FPT", "BTCUSDT"]


def test_exness_filtered_broad_universe_includes_base_metals_and_more_forex() -> None:
    filtered = filter_exness_supported(get_universe("broad"))
    commodity_symbols = {item.symbol for item in filtered if item.market == "Commodity"}
    forex_symbols = {item.symbol for item in filtered if item.market == "Forex"}

    assert {"XALUSD", "XCUUSD", "XNIUSD", "XPBUSD", "XZNUSD"}.issubset(commodity_symbols)
    assert len(forex_symbols) >= 80
