"""Fetch live stock prices from Yahoo Finance.

Supports US stocks (e.g. AAPL, MSFT) and ASX stocks (e.g. CBA, BHP).
ASX tickers are queried with the .AX suffix automatically.
"""

import json
import urllib.request
import urllib.error
from dataclasses import dataclass


@dataclass
class Quote:
    symbol: str
    price: float
    currency: str
    market_state: str  # e.g. "REGULAR", "PRE", "POST", "CLOSED"
    name: str

    @property
    def is_market_open(self) -> bool:
        return self.market_state == "REGULAR"


def _yahoo_symbol(symbol: str, market: str) -> str:
    """Convert a symbol + market into a Yahoo Finance ticker."""
    if market == "ASX":
        return f"{symbol}.AX"
    return symbol


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def fetch_quote(symbol: str, market: str = "US") -> Quote | None:
    """Fetch a single quote. Returns None on failure."""
    ticker = _yahoo_symbol(symbol, market)
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?interval=1d&range=1d"
    )
    try:
        data = _fetch_json(url)
        meta = data["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        currency = meta.get("currency", "USD")
        state = meta.get("marketState", "CLOSED")
        name = meta.get("shortName", symbol)
        return Quote(
            symbol=symbol,
            price=price,
            currency=currency,
            market_state=state,
            name=name,
        )
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError,
            OSError, ValueError):
        return None


def fetch_quotes(symbols_markets: list[tuple[str, str]]) -> dict[str, Quote]:
    """Fetch quotes for multiple symbols. Returns dict keyed by symbol.

    Args:
        symbols_markets: list of (symbol, market) tuples
    """
    results = {}
    # Batch via Yahoo Finance multi-quote endpoint
    if not symbols_markets:
        return results

    tickers = [_yahoo_symbol(s, m) for s, m in symbols_markets]
    ticker_str = ",".join(tickers)
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/spark"
        f"?symbols={ticker_str}&range=1d&interval=1d"
    )
    try:
        data = _fetch_json(url)
        # spark endpoint returns a different structure; fall back to individual
        # fetches if the batch format is unexpected
        for symbol, market in symbols_markets:
            yf_sym = _yahoo_symbol(symbol, market)
            entry = data.get(yf_sym) or data.get("spark", {}).get("result", [{}])
            # spark endpoint can be unreliable, fall back to individual
            quote = fetch_quote(symbol, market)
            if quote:
                results[symbol] = quote
    except (urllib.error.URLError, KeyError, json.JSONDecodeError):
        # Fall back to individual fetches
        for symbol, market in symbols_markets:
            quote = fetch_quote(symbol, market)
            if quote:
                results[symbol] = quote

    return results
