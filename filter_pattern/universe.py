from __future__ import annotations

from dataclasses import dataclass


CRYPTO_EXCHANGE_PRIORITY = ("binance", "bybit", "okx", "mexc")
CRYPTO_TRADINGVIEW_EXCHANGES = {
    "binance": "BINANCE",
    "bybit": "BYBIT",
    "okx": "OKX",
    "mexc": "MEXC",
}
CRYPTO_STABLE_BASES = {
    "USDT",
    "USDC",
    "FDUSD",
    "BUSD",
    "DAI",
    "TUSD",
    "USDE",
    "USDD",
    "PYUSD",
    "EUR",
    "USD",
}
CRYPTO_LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR", "3L", "3S", "5L", "5S")


@dataclass(frozen=True)
class UniverseSymbol:
    symbol: str
    market: str
    tradingview_symbol: str
    yahoo_symbol: str


def default_universe() -> list[UniverseSymbol]:
    return [
        *_us_stocks(),
        *_vietnam_stocks(),
        *_commodities(),
        *_forex(),
        *_crypto(),
    ]


def get_universe(name: str) -> list[UniverseSymbol]:
    normalized = name.lower()
    if normalized == "default":
        return default_universe()
    if normalized == "sp500":
        return sp500_universe()
    if normalized == "broad":
        return _dedupe_symbols([*default_universe(), *sp500_universe()])
    raise ValueError("unknown universe. Choose one of: default, sp500, broad")


def expand_crypto_universe(
    items: list[UniverseSymbol],
    exchange_id: str = ",".join(CRYPTO_EXCHANGE_PRIORITY),
    market_type: str = "spot",
    max_symbols: int | None = None,
) -> list[UniverseSymbol]:
    if not any(item.market == "Crypto" for item in items):
        return items
    dynamic_crypto = discover_crypto_universe(exchange_id, market_type)
    if not dynamic_crypto:
        if max_symbols is None or max_symbols <= 0:
            return items
        crypto_items = [item for item in items if item.market == "Crypto"][:max_symbols]
        non_crypto = [item for item in items if item.market != "Crypto"]
        return _dedupe_symbols([*non_crypto, *crypto_items])
    if max_symbols is not None and max_symbols > 0:
        dynamic_crypto = dynamic_crypto[:max_symbols]
    non_crypto = [item for item in items if item.market != "Crypto"]
    return _dedupe_symbols([*non_crypto, *dynamic_crypto])


def discover_crypto_universe(
    exchange_id: str = ",".join(CRYPTO_EXCHANGE_PRIORITY),
    market_type: str = "spot",
) -> list[UniverseSymbol]:
    try:
        import ccxt
    except ImportError:
        return []

    exchange_markets: list[tuple[str, dict]] = []
    for active_exchange_id in _crypto_exchange_ids(exchange_id):
        exchange_class = getattr(ccxt, active_exchange_id, None)
        if exchange_class is None:
            continue
        exchange = exchange_class({"enableRateLimit": True})
        try:
            markets = exchange.load_markets()
        except Exception:  # noqa: BLE001 - keep fallback exchanges available.
            markets = {}
        finally:
            close = getattr(exchange, "close", None)
            if callable(close):
                close()
        for market in markets.values():
            exchange_markets.append((active_exchange_id, market))
    return _crypto_from_exchange_markets(exchange_markets, market_type)


def _crypto_exchange_ids(exchange_id: str) -> list[str]:
    requested = [item.strip().lower() for item in exchange_id.split(",") if item.strip()]
    return requested or list(CRYPTO_EXCHANGE_PRIORITY)


def _crypto_from_exchange_markets(exchange_markets: list[tuple[str, dict]], market_type: str = "spot") -> list[UniverseSymbol]:
    symbols: list[UniverseSymbol] = []
    seen: set[str] = set()
    for exchange_id, market in exchange_markets:
        item = _crypto_symbol_from_market(exchange_id, market, market_type)
        if item is None or item.symbol in seen:
            continue
        seen.add(item.symbol)
        symbols.append(item)
    return symbols


def _crypto_symbol_from_market(exchange_id: str, market: dict, market_type: str = "spot") -> UniverseSymbol | None:
    normalized_market_type = _normalize_crypto_market_type(market_type)
    if not _is_supported_crypto_market(market, normalized_market_type):
        return None
    base = str(market.get("base") or "").upper().replace("/", "").replace("-", "")
    if not base:
        symbol_text = str(market.get("symbol") or "").upper()
        if not symbol_text.endswith("/USDT"):
            return None
        base = symbol_text.removesuffix("/USDT").replace("/", "").replace("-", "")
    symbol = f"{base}USDT"
    tradingview_exchange = CRYPTO_TRADINGVIEW_EXCHANGES.get(exchange_id.lower(), exchange_id.upper())
    tv_suffix = ".P" if normalized_market_type == "perp" else ""
    return UniverseSymbol(
        symbol=symbol,
        market="Crypto",
        tradingview_symbol=f"{tradingview_exchange}:{symbol}{tv_suffix}",
        yahoo_symbol=f"{base}-USD",
    )


def _is_supported_crypto_market(market: dict, market_type: str = "spot") -> bool:
    if market.get("active") is False:
        return False
    quote = str(market.get("quote") or "").upper()
    symbol_text = str(market.get("symbol") or "").upper()
    if quote != "USDT" and not symbol_text.endswith("/USDT"):
        return False
    requested_market_type = _normalize_crypto_market_type(market_type)
    exchange_market_type = str(market.get("type") or "").lower()
    if requested_market_type == "perp":
        if market.get("swap") is not True and exchange_market_type != "swap":
            return False
    else:
        if market.get("contract") is True or market.get("swap") is True or market.get("future") is True:
            return False
        if exchange_market_type and exchange_market_type != "spot":
            return False
        if market.get("spot") is False and exchange_market_type != "spot":
            return False
    base = str(market.get("base") or symbol_text.removesuffix("/USDT")).upper().replace("/", "").replace("-", "")
    if not base or base in CRYPTO_STABLE_BASES:
        return False
    return not base.endswith(CRYPTO_LEVERAGED_SUFFIXES)


def _normalize_crypto_market_type(market_type: str) -> str:
    normalized = str(market_type or "").strip().lower()
    if normalized in {"perp", "perpetual", "future", "futures", "swap"}:
        return "perp"
    return "spot"


def sp500_universe() -> list[UniverseSymbol]:
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("requests and beautifulsoup4 are required to load the S&P 500 universe") from exc

    response = requests.get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        headers={"User-Agent": "filter-pattern/0.1"},
        timeout=20,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", id="constituents")
    if table is None:
        raise ValueError("Could not find S&P 500 constituents table")

    symbols: list[UniverseSymbol] = []
    for row in table.find_all("tr")[1:]:
        cells = [cell.get_text(strip=True) for cell in row.find_all("td")]
        if not cells:
            continue
        yahoo_symbol = cells[0].replace(".", "-")
        symbol = yahoo_symbol.replace("-", ".")
        symbols.append(
            UniverseSymbol(
                symbol=symbol,
                market="US stock",
                tradingview_symbol=symbol,
                yahoo_symbol=yahoo_symbol,
            )
        )
    return symbols


def _dedupe_symbols(items: list[UniverseSymbol]) -> list[UniverseSymbol]:
    seen: set[str] = set()
    deduped: list[UniverseSymbol] = []
    for item in items:
        key = item.symbol
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _us_stocks() -> list[UniverseSymbol]:
    tickers = [
        ("AAPL", "NASDAQ:AAPL"),
        ("MSFT", "NASDAQ:MSFT"),
        ("NVDA", "NASDAQ:NVDA"),
        ("AMZN", "NASDAQ:AMZN"),
        ("META", "NASDAQ:META"),
        ("GOOGL", "NASDAQ:GOOGL"),
        ("TSLA", "NASDAQ:TSLA"),
        ("AVGO", "NASDAQ:AVGO"),
        ("NFLX", "NASDAQ:NFLX"),
        ("AMD", "NASDAQ:AMD"),
        ("COST", "NASDAQ:COST"),
        ("PLTR", "NASDAQ:PLTR"),
        ("CRWD", "NASDAQ:CRWD"),
        ("PANW", "NASDAQ:PANW"),
        ("NOW", "NYSE:NOW"),
        ("ORCL", "NYSE:ORCL"),
        ("CRM", "NYSE:CRM"),
        ("ADBE", "NASDAQ:ADBE"),
        ("ADP", "NASDAQ:ADP"),
        ("INTC", "NASDAQ:INTC"),
        ("QCOM", "NASDAQ:QCOM"),
        ("MU", "NASDAQ:MU"),
        ("ARM", "NASDAQ:ARM"),
        ("SMCI", "NASDAQ:SMCI"),
        ("ANET", "NYSE:ANET"),
        ("SHOP", "NASDAQ:SHOP"),
        ("UBER", "NYSE:UBER"),
        ("ABNB", "NASDAQ:ABNB"),
        ("COIN", "NASDAQ:COIN"),
        ("MSTR", "NASDAQ:MSTR"),
        ("HOOD", "NASDAQ:HOOD"),
        ("JPM", "NYSE:JPM"),
        ("BAC", "NYSE:BAC"),
        ("GS", "NYSE:GS"),
        ("V", "NYSE:V"),
        ("MA", "NYSE:MA"),
        ("AXP", "NYSE:AXP"),
        ("LLY", "NYSE:LLY"),
        ("UNH", "NYSE:UNH"),
        ("ABBV", "NYSE:ABBV"),
        ("MRK", "NYSE:MRK"),
        ("ISRG", "NASDAQ:ISRG"),
        ("TMO", "NYSE:TMO"),
        ("GE", "NYSE:GE"),
        ("CAT", "NYSE:CAT"),
        ("DE", "NYSE:DE"),
        ("BA", "NYSE:BA"),
        ("BABA", "NYSE:BABA"),
        ("BIDU", "NASDAQ:BIDU"),
        ("BILI", "NASDAQ:BILI"),
        ("LMT", "NYSE:LMT"),
        ("XOM", "NYSE:XOM"),
        ("CVX", "NYSE:CVX"),
        ("COP", "NYSE:COP"),
        ("SLB", "NYSE:SLB"),
        ("WMT", "NYSE:WMT"),
        ("HD", "NYSE:HD"),
        ("MCD", "NYSE:MCD"),
        ("NKE", "NYSE:NKE"),
        ("SBUX", "NASDAQ:SBUX"),
        ("DIS", "NYSE:DIS"),
        ("FTNT", "NASDAQ:FTNT"),
        ("NTES", "NASDAQ:NTES"),
        ("TMUS", "NASDAQ:TMUS"),
        ("ZTO", "NYSE:ZTO"),
        ("SPY", "AMEX:SPY"),
        ("QQQ", "NASDAQ:QQQ"),
        ("IWM", "AMEX:IWM"),
        ("SMH", "NASDAQ:SMH"),
        ("XLK", "AMEX:XLK"),
        ("XLF", "AMEX:XLF"),
        ("XLE", "AMEX:XLE"),
    ]
    return [UniverseSymbol(symbol=ticker, market="US stock", tradingview_symbol=tv, yahoo_symbol=ticker) for ticker, tv in tickers]


def _vietnam_stocks() -> list[UniverseSymbol]:
    tickers = [
        "AAA",
        "ABS",
        "ABT",
        "ACB",
        "ACC",
        "ACL",
        "ADG",
        "ADS",
        "AGG",
        "AGR",
        "ANV",
        "APG",
        "APH",
        "ASM",
        "AST",
        "BAF",
        "BCE",
        "BCG",
        "BCM",
        "BFC",
        "BHN",
        "BIC",
        "BID",
        "BMI",
        "BMP",
        "BRC",
        "BSI",
        "BTP",
        "BVH",
        "BWE",
        "C32",
        "C47",
        "CCI",
        "CCL",
        "CDC",
        "CHP",
        "CII",
        "CKG",
        "CLC",
        "CLL",
        "CMG",
        "CRC",
        "CRE",
        "CSV",
        "CTD",
        "CTF",
        "CTG",
        "CTR",
        "CTS",
        "CVT",
        "D2D",
        "DAG",
        "DBC",
        "DBD",
        "DC4",
        "DCL",
        "DCM",
        "DGC",
        "DGW",
        "DHA",
        "DHC",
        "DHG",
        "DIG",
        "DLG",
        "DMC",
        "DPG",
        "DPM",
        "DPR",
        "DRC",
        "DRH",
        "DRL",
        "DSN",
        "DTA",
        "DTL",
        "DVP",
        "DXG",
        "DXS",
        "EIB",
        "ELC",
        "EVF",
        "FCN",
        "FIR",
        "FIT",
        "FMC",
        "FPT",
        "FRT",
        "FTS",
        "GAS",
        "GDT",
        "GEG",
        "GEX",
        "GIL",
        "GMD",
        "GSP",
        "GTA",
        "GVR",
        "HAG",
        "HAH",
        "HAP",
        "HAR",
        "HAX",
        "HBC",
        "HCD",
        "HCM",
        "HDB",
        "HDC",
        "HDG",
        "HHV",
        "HHS",
        "HID",
        "HII",
        "HMC",
        "HPG",
        "HQC",
        "HRC",
        "HSG",
        "HT1",
        "HTI",
        "HTN",
        "HVH",
        "HVN",
        "IMP",
        "ITA",
        "ITC",
        "KBC",
        "KDC",
        "KDH",
        "KHP",
        "KMR",
        "KOS",
        "KSB",
        "L10",
        "LBM",
        "LCG",
        "LDG",
        "LHG",
        "LIX",
        "LPB",
        "LSS",
        "MBB",
        "MCP",
        "MDG",
        "MSB",
        "MSH",
        "MSN",
        "MWG",
        "NAF",
        "NAV",
        "NBB",
        "NCT",
        "NHA",
        "NKG",
        "NLG",
        "NNC",
        "NSC",
        "NT2",
        "NTL",
        "NVL",
        "OCB",
        "OPC",
        "ORS",
        "PAC",
        "PAN",
        "PC1",
        "PDN",
        "PDR",
        "PET",
        "PGC",
        "PHC",
        "PHR",
        "PIT",
        "PLP",
        "PLX",
        "PME",
        "PNC",
        "PNJ",
        "POW",
        "PPC",
        "PSH",
        "PTB",
        "PVD",
        "PVT",
        "RAL",
        "REE",
        "S4A",
        "SAB",
        "SAM",
        "SAV",
        "SBA",
        "SBT",
        "SBV",
        "SC5",
        "SCR",
        "SCS",
        "SFC",
        "SGN",
        "SHP",
        "SJS",
        "SKG",
        "SMB",
        "SMC",
        "SPM",
        "SRC",
        "SRF",
        "SSB",
        "SSI",
        "ST8",
        "STB",
        "SZC",
        "TBC",
        "TCB",
        "TCD",
        "TCH",
        "TCL",
        "TCM",
        "TCO",
        "TCR",
        "TCT",
        "TDC",
        "TDG",
        "TDH",
        "TDM",
        "TDP",
        "TGG",
        "THG",
        "TIP",
        "TIX",
        "TLD",
        "TLG",
        "TLH",
        "TMP",
        "TMS",
        "TMT",
        "TN1",
        "TNA",
        "TNC",
        "TNH",
        "TNI",
        "TNT",
        "TPB",
        "TRA",
        "TRC",
        "TSC",
        "TTB",
        "TV2",
        "TVB",
        "TVS",
        "TVT",
        "TYA",
        "UIC",
        "VAF",
        "VCB",
        "VCF",
        "VCG",
        "VCI",
        "VDP",
        "VDS",
        "VFG",
        "VGC",
        "VHC",
        "VHM",
        "VIB",
        "VIC",
        "VID",
        "VIP",
        "VIX",
        "VJC",
        "VMD",
        "VND",
        "VNE",
        "VNG",
        "VNM",
        "VNS",
        "VPB",
        "VPD",
        "VPG",
        "VPH",
        "VPI",
        "VPS",
        "VRC",
        "VRE",
        "VSC",
        "VSH",
        "VSI",
        "VTB",
        "VTO",
        "YBM",
        "YEG",
        # Liquid HNX/UPCOM names are included for visibility, but Yahoo often lacks data for them.
        "ACV",
        "BAB",
        "BVS",
        "CEO",
        "DDV",
        "DTD",
        "HUT",
        "IDC",
        "IDJ",
        "MBS",
        "MPC",
        "NTP",
        "PVS",
        "QNS",
        "SHS",
        "TNG",
        "VCS",
        "VGI",
        "VTP",
        "FOX",
        "FPT",
        "VNM",
        "VCB",
        "VIC",
        "VHM",
        "HPG",
        "MWG",
        "GAS",
        "MSN",
        "SSI",
        "STB",
        "MBB",
        "TCB",
        "ACB",
        "VRE",
        "GEX",
        "GVR",
        "VJC",
        "POW",
        "PLX",
        "BID",
        "CTG",
        "HDB",
        "LPB",
        "SHB",
        "TPB",
        "VPB",
        "VIB",
        "EIB",
        "OCB",
        "SAB",
        "BVH",
        "BCM",
        "DGC",
        "DPM",
        "DCM",
        "DIG",
        "DXG",
        "KDH",
        "NLG",
        "NVL",
        "PDR",
        "KBC",
        "SZC",
        "HSG",
        "NKG",
        "PVD",
        "PVS",
        "BSR",
        "VND",
        "VCI",
        "HCM",
        "FTS",
        "DHC",
        "DGW",
        "PNJ",
        "REE",
        "PC1",
        "CTR",
        "CMG",
        "VTP",
        "ANV",
        "VHC",
        "FMC",
        "HAG",
        "HNG",
        "DBC",
        "PAN",
        "SBT",
        "QNS",
        "BMP",
        "NTP",
        "AAA",
        "DPR",
        "PHR",
        "TCH",
        "HHS",
        "CII",
        "HHV",
        "FCN",
        "VGC",
        "IDC",
        "ITA",
        "LHG",
        "NT2",
        "PPC",
        "GMD",
        "HAH",
        "VSC",
        "SCS",
        "ACV",
        "HVN",
        "SIP",
        "VGI",
        "FOX",
    ]
    return [
        UniverseSymbol(
            symbol=ticker,
            market="Vietnam stock",
            tradingview_symbol=f"HOSE:{ticker}",
            yahoo_symbol=f"{ticker}.VN",
        )
        for ticker in dict.fromkeys(tickers)
    ]


def _commodities() -> list[UniverseSymbol]:
    items = [
        ("XAUUSD", "Commodity", "OANDA:XAUUSD", "GC=F"),
        ("XAGUSD", "Commodity", "OANDA:XAGUSD", "SI=F"),
        ("XALUSD", "Commodity", "EXNESS:XALUSD", "ALI=F"),
        ("XCUUSD", "Commodity", "EXNESS:XCUUSD", "HG=F"),
        ("XNIUSD", "Commodity", "EXNESS:XNIUSD", "NICKEL=F"),
        ("XPBUSD", "Commodity", "EXNESS:XPBUSD", "PB=F"),
        ("XZNUSD", "Commodity", "EXNESS:XZNUSD", "ZNC=F"),
        ("WTI", "Commodity", "NYMEX:CL1!", "CL=F"),
        ("BRENT", "Commodity", "TVC:UKOIL", "BZ=F"),
        ("NATGAS", "Commodity", "NYMEX:NG1!", "NG=F"),
        ("USOIL", "Commodity", "EXNESS:USOIL", "CL=F"),
        ("UKOIL", "Commodity", "EXNESS:UKOIL", "BZ=F"),
        ("XNGUSD", "Commodity", "EXNESS:XNGUSD", "NG=F"),
        ("XPTUSD", "Commodity", "EXNESS:XPTUSD", "PL=F"),
        ("XPDUSD", "Commodity", "EXNESS:XPDUSD", "PA=F"),
        ("COPPER", "Commodity", "COMEX:HG1!", "HG=F"),
        ("PLATINUM", "Commodity", "NYMEX:PL1!", "PL=F"),
        ("PALLADIUM", "Commodity", "NYMEX:PA1!", "PA=F"),
        ("RBOB_GASOLINE", "Commodity", "NYMEX:RB1!", "RB=F"),
        ("HEATING_OIL", "Commodity", "NYMEX:HO1!", "HO=F"),
        ("CORN", "Commodity", "CBOT:ZC1!", "ZC=F"),
        ("WHEAT", "Commodity", "CBOT:ZW1!", "ZW=F"),
        ("SOYBEANS", "Commodity", "CBOT:ZS1!", "ZS=F"),
        ("SOYBEAN_OIL", "Commodity", "CBOT:ZL1!", "ZL=F"),
        ("SOYBEAN_MEAL", "Commodity", "CBOT:ZM1!", "ZM=F"),
        ("OATS", "Commodity", "CBOT:ZO1!", "ZO=F"),
        ("COFFEE", "Commodity", "ICEUS:KC1!", "KC=F"),
        ("COCOA", "Commodity", "ICEUS:CC1!", "CC=F"),
        ("SUGAR", "Commodity", "ICEUS:SB1!", "SB=F"),
        ("COTTON", "Commodity", "ICEUS:CT1!", "CT=F"),
        ("ORANGE_JUICE", "Commodity", "ICEUS:OJ1!", "OJ=F"),
        ("LIVE_CATTLE", "Commodity", "CME:LE1!", "LE=F"),
        ("FEEDER_CATTLE", "Commodity", "CME:GF1!", "GF=F"),
        ("LEAN_HOGS", "Commodity", "CME:HE1!", "HE=F"),
        ("GOLD_ETF", "Commodity ETF", "AMEX:GLD", "GLD"),
        ("SILVER_ETF", "Commodity ETF", "AMEX:SLV", "SLV"),
        ("GDX", "Commodity ETF", "AMEX:GDX", "GDX"),
        ("GDXJ", "Commodity ETF", "AMEX:GDXJ", "GDXJ"),
        ("USO", "Commodity ETF", "AMEX:USO", "USO"),
        ("UNG", "Commodity ETF", "AMEX:UNG", "UNG"),
        ("DBA", "Commodity ETF", "AMEX:DBA", "DBA"),
        ("DBC", "Commodity ETF", "AMEX:DBC", "DBC"),
        ("CORN", "Commodity ETF", "AMEX:CORN", "CORN"),
        ("WEAT", "Commodity ETF", "AMEX:WEAT", "WEAT"),
        ("SOYB", "Commodity ETF", "AMEX:SOYB", "SOYB"),
        ("CANE", "Commodity ETF", "AMEX:CANE", "CANE"),
        ("CPER", "Commodity ETF", "AMEX:CPER", "CPER"),
        ("URA", "Commodity ETF", "AMEX:URA", "URA"),
        ("COPX", "Commodity ETF", "AMEX:COPX", "COPX"),
        ("LIT", "Commodity ETF", "AMEX:LIT", "LIT"),
        ("WOOD", "Commodity ETF", "NASDAQ:WOOD", "WOOD"),
        ("JJG", "Commodity ETF", "AMEX:JJG", "JJG"),
        ("IAU", "Commodity ETF", "AMEX:IAU", "IAU"),
        ("SGOL", "Commodity ETF", "AMEX:SGOL", "SGOL"),
        ("PPLT", "Commodity ETF", "AMEX:PPLT", "PPLT"),
        ("PALL", "Commodity ETF", "AMEX:PALL", "PALL"),
        ("BNO", "Commodity ETF", "AMEX:BNO", "BNO"),
        ("UGA", "Commodity ETF", "AMEX:UGA", "UGA"),
        ("DBE", "Commodity ETF", "AMEX:DBE", "DBE"),
        ("DBB", "Commodity ETF", "AMEX:DBB", "DBB"),
        ("DBP", "Commodity ETF", "AMEX:DBP", "DBP"),
        ("SLX", "Commodity ETF", "AMEX:SLX", "SLX"),
        ("XME", "Commodity ETF", "AMEX:XME", "XME"),
        ("PICK", "Commodity ETF", "BATS:PICK", "PICK"),
        ("REMX", "Commodity ETF", "AMEX:REMX", "REMX"),
        ("KRBN", "Commodity ETF", "AMEX:KRBN", "KRBN"),
        ("TAN", "Commodity ETF", "AMEX:TAN", "TAN"),
        ("FAN", "Commodity ETF", "AMEX:FAN", "FAN"),
        ("ICLN", "Commodity ETF", "NASDAQ:ICLN", "ICLN"),
    ]
    return [UniverseSymbol(*item) for item in items]


def _forex() -> list[UniverseSymbol]:
    pairs = [
        ("EURUSD", "OANDA:EURUSD", "EURUSD=X"),
        ("GBPUSD", "OANDA:GBPUSD", "GBPUSD=X"),
        ("USDJPY", "OANDA:USDJPY", "JPY=X"),
        ("USDCHF", "OANDA:USDCHF", "CHF=X"),
        ("AUDUSD", "OANDA:AUDUSD", "AUDUSD=X"),
        ("AUDDKK", "OANDA:AUDDKK", "AUDDKK=X"),
        ("AUDHUF", "OANDA:AUDHUF", "AUDHUF=X"),
        ("NZDUSD", "OANDA:NZDUSD", "NZDUSD=X"),
        ("USDCAD", "OANDA:USDCAD", "CAD=X"),
        ("EURJPY", "OANDA:EURJPY", "EURJPY=X"),
        ("GBPJPY", "OANDA:GBPJPY", "GBPJPY=X"),
        ("AUDJPY", "OANDA:AUDJPY", "AUDJPY=X"),
        ("CADJPY", "OANDA:CADJPY", "CADJPY=X"),
        ("CHFJPY", "OANDA:CHFJPY", "CHFJPY=X"),
        ("NZDJPY", "OANDA:NZDJPY", "NZDJPY=X"),
        ("AUDMXN", "OANDA:AUDMXN", "AUDMXN=X"),
        ("AUDPLN", "OANDA:AUDPLN", "AUDPLN=X"),
        ("AUDSEK", "OANDA:AUDSEK", "AUDSEK=X"),
        ("AUDSGD", "OANDA:AUDSGD", "AUDSGD=X"),
        ("AUDZAR", "OANDA:AUDZAR", "AUDZAR=X"),
        ("CADMXN", "OANDA:CADMXN", "CADMXN=X"),
        ("CADNOK", "OANDA:CADNOK", "CADNOK=X"),
        ("CADPLN", "OANDA:CADPLN", "CADPLN=X"),
        ("CHFDKK", "OANDA:CHFDKK", "CHFDKK=X"),
        ("CHFHUF", "OANDA:CHFHUF", "CHFHUF=X"),
        ("CHFMXN", "OANDA:CHFMXN", "CHFMXN=X"),
        ("CHFNOK", "OANDA:CHFNOK", "CHFNOK=X"),
        ("CHFPLN", "OANDA:CHFPLN", "CHFPLN=X"),
        ("CHFSEK", "OANDA:CHFSEK", "CHFSEK=X"),
        ("CHFSGD", "OANDA:CHFSGD", "CHFSGD=X"),
        ("CHFZAR", "OANDA:CHFZAR", "CHFZAR=X"),
        ("EURGBP", "OANDA:EURGBP", "EURGBP=X"),
        ("EURDKK", "OANDA:EURDKK", "EURDKK=X"),
        ("EURHKD", "OANDA:EURHKD", "EURHKD=X"),
        ("EURHUF", "OANDA:EURHUF", "EURHUF=X"),
        ("EURMXN", "OANDA:EURMXN", "EURMXN=X"),
        ("EURNOK", "OANDA:EURNOK", "EURNOK=X"),
        ("EURPLN", "OANDA:EURPLN", "EURPLN=X"),
        ("EURSEK", "OANDA:EURSEK", "EURSEK=X"),
        ("EURSGD", "OANDA:EURSGD", "EURSGD=X"),
        ("EURTRY", "OANDA:EURTRY", "EURTRY=X"),
        ("EURZAR", "OANDA:EURZAR", "EURZAR=X"),
        ("EURAUD", "OANDA:EURAUD", "EURAUD=X"),
        ("EURCAD", "OANDA:EURCAD", "EURCAD=X"),
        ("EURCHF", "OANDA:EURCHF", "EURCHF=X"),
        ("EURNZD", "OANDA:EURNZD", "EURNZD=X"),
        ("GBPAUD", "OANDA:GBPAUD", "GBPAUD=X"),
        ("GBPCAD", "OANDA:GBPCAD", "GBPCAD=X"),
        ("GBPCHF", "OANDA:GBPCHF", "GBPCHF=X"),
        ("GBPNZD", "OANDA:GBPNZD", "GBPNZD=X"),
        ("GBPDKK", "OANDA:GBPDKK", "GBPDKK=X"),
        ("GBPHUF", "OANDA:GBPHUF", "GBPHUF=X"),
        ("GBPMXN", "OANDA:GBPMXN", "GBPMXN=X"),
        ("GBPNOK", "OANDA:GBPNOK", "GBPNOK=X"),
        ("GBPPLN", "OANDA:GBPPLN", "GBPPLN=X"),
        ("GBPSEK", "OANDA:GBPSEK", "GBPSEK=X"),
        ("GBPSGD", "OANDA:GBPSGD", "GBPSGD=X"),
        ("GBPZAR", "OANDA:GBPZAR", "GBPZAR=X"),
        ("AUDCAD", "OANDA:AUDCAD", "AUDCAD=X"),
        ("AUDCHF", "OANDA:AUDCHF", "AUDCHF=X"),
        ("AUDNZD", "OANDA:AUDNZD", "AUDNZD=X"),
        ("CADCHF", "OANDA:CADCHF", "CADCHF=X"),
        ("NZDCAD", "OANDA:NZDCAD", "NZDCAD=X"),
        ("NZDCHF", "OANDA:NZDCHF", "NZDCHF=X"),
        ("NZDMXN", "OANDA:NZDMXN", "NZDMXN=X"),
        ("NZDPLN", "OANDA:NZDPLN", "NZDPLN=X"),
        ("NZDSEK", "OANDA:NZDSEK", "NZDSEK=X"),
        ("NZDSGD", "OANDA:NZDSGD", "NZDSGD=X"),
        ("NZDZAR", "OANDA:NZDZAR", "NZDZAR=X"),
        ("USDSGD", "OANDA:USDSGD", "SGD=X"),
        ("USDHKD", "OANDA:USDHKD", "HKD=X"),
        ("USDCNH", "OANDA:USDCNH", "CNH=X"),
        ("USDHUF", "OANDA:USDHUF", "HUF=X"),
        ("USDPLN", "OANDA:USDPLN", "PLN=X"),
        ("USDSEK", "OANDA:USDSEK", "SEK=X"),
        ("USDNOK", "OANDA:USDNOK", "NOK=X"),
        ("USDDKK", "OANDA:USDDKK", "DKK=X"),
        ("USDZAR", "OANDA:USDZAR", "ZAR=X"),
        ("USDMXN", "OANDA:USDMXN", "MXN=X"),
        ("USDTRY", "OANDA:USDTRY", "TRY=X"),
        ("USDTHB", "OANDA:USDTHB", "THB=X"),
    ]
    return [UniverseSymbol(symbol=symbol, market="Forex", tradingview_symbol=tv, yahoo_symbol=yahoo) for symbol, tv, yahoo in pairs]


def _crypto() -> list[UniverseSymbol]:
    tickers = [
        "BTC",
        "ETH",
        "SOL",
        "BNB",
        "XRP",
        "DOGE",
        "ADA",
        "AVAX",
        "LINK",
        "DOT",
        "LTC",
        "BCH",
        "NEAR",
        "APT",
        "ARB",
        "OP",
        "SUI",
        "TON",
        "TRX",
        "XLM",
        "HBAR",
        "ICP",
        "FIL",
        "ETC",
        "ATOM",
        "INJ",
        "TIA",
        "SEI",
        "STX",
        "IMX",
        "RENDER",
        "FET",
        "GRT",
        "AAVE",
        "UNI",
        "MKR",
        "RUNE",
        "LDO",
        "ONDO",
        "JUP",
        "PYTH",
        "WIF",
        "PEPE",
        "SHIB",
        "BONK",
        "FLOKI",
        "ALGO",
        "VET",
        "MANA",
        "SAND",
        "AXS",
        "EGLD",
        "KAS",
        "WLD",
        "AR",
        "FLOW",
        "XTZ",
        "MINA",
        "QNT",
        "GALA",
        "APE",
        "DYDX",
        "JASMY",
        "ENS",
        "STRK",
        "MNT",
        "BEAMX",
        "ZEC",
        "DASH",
        "TAO",
        "PENDLE",
        "ENA",
        "EIGEN",
        "VIRTUAL",
        "ZEN",
        "STORJ",
        "PAXG",
        "TRUMP",
        "NEIRO",
        "NOT",
        "CFX",
        "BIO",
        "CHZ",
        "PUMP",
        "ARKM",
        "FTT",
        "ANKR",
        "ZRO",
        "PNUT",
        "BOME",
        "TURBO",
        "ORCA",
        "ACH",
        "HIGH",
        "ETHFI",
        "ZAMA",
        "S",
        "POL",
        "CRV",
        "BLUR",
        "JTO",
        "MEME",
        "AXL",
        "ACT",
        "IOTA",
        "ZK",
        "AI",
        "CAKE",
        "MOVR",
        "LPT",
        "COW",
        "PEOPLE",
        "BB",
        "ENJ",
        "RSR",
        "AIXBT",
        "CHR",
        "XVG",
        "TUT",
        "ZIL",
        "PORTAL",
        "CATI",
        "HOLO",
        "W",
        "RAY",
        "SKY",
        "PLUME",
        "BERA",
        "JST",
        "EDU",
        "PROM",
        "TRB",
        "LINEA",
        "RED",
        "DYM",
        "WAL",
        "WCT",
        "GLM",
        "ROSE",
        "REZ",
        "DEXE",
        "DUSK",
        "BANANA",
        "SAHARA",
        "NEO",
        "QTUM",
        "ONT",
        "ICX",
        "ZRX",
        "BAT",
        "IOST",
        "CELR",
        "THETA",
        "ONE",
        "COTI",
        "COMP",
        "SNX",
        "KSM",
        "UMA",
        "BEL",
        "XVS",
        "AUDIO",
        "SKL",
        "CELO",
        "RIF",
        "CKB",
        "TWT",
        "SFP",
        "DODO",
        "ALICE",
        "C98",
        "XEC",
        "YGG",
        "SYS",
        "API3",
        "WOO",
        "ASTR",
        "GMT",
        "GMX",
        "POLYX",
        "MAGIC",
        "RPL",
        "SSV",
        "LQTY",
        "GAS",
        "ID",
        "MAV",
        "CYBER",
        "ORDI",
        "VANRY",
        "ACE",
        "IO",
        "DOGS",
        "HMSTR",
        "MORPHO",
        "VANA",
        "MAVIA",
        "NFP",
        "ALT",
        "PIXEL",
        "MANTA",
        "METIS",
        "AEVO",
        "SAGA",
        "OMNI",
        "TNSR",
        "REZ",
        "ZKJ",
        "LISTA",
        "BANANAS31",
        "CAT",
        "1INCH",
        "1000SATS",
        "1MBABYDOGE",
    ]
    tradingview_overrides = {
        # These are not Binance spot markets, but are available through the CCXT fallback exchanges.
        "KAS": "BYBIT:KASUSDT",
        "MNT": "BYBIT:MNTUSDT",
        "MAVIA": "BYBIT:MAVIAUSDT",
        "ZKJ": "BYBIT:ZKJUSDT",
        "CAT": "BYBIT:CATUSDT",
    }
    return [
        UniverseSymbol(
            symbol=f"{ticker}USDT",
            market="Crypto",
            tradingview_symbol=tradingview_overrides.get(ticker, f"BINANCE:{ticker}USDT"),
            yahoo_symbol=f"{ticker}-USD",
        )
        for ticker in dict.fromkeys(tickers)
    ]
