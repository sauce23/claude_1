"""
Real-time price fetching via yfinance.

Requires: pip install yfinance

ASX stocks use the .AX suffix in Yahoo Finance (e.g. BHP.AX, CBA.AX).
US stocks use their ticker directly (e.g. AAPL, GOOG).

This module auto-handles the .AX suffix — you can pass either "BHP" or "BHP.AX"
for ASX stocks and it will resolve correctly.
"""

from __future__ import annotations


def _yf_ticker(symbol: str, exchange: str) -> str:
    """Return the Yahoo Finance ticker string for a given symbol and exchange."""
    if exchange == "ASX":
        return symbol if symbol.endswith(".AX") else symbol + ".AX"
    return symbol


def fetch_prices(holdings: dict) -> dict[str, float | None]:
    """
    Fetch live prices for all holdings.

    Args:
        holdings: dict mapping symbol -> Holding (from Portfolio.holdings)

    Returns:
        dict mapping symbol -> price (or None if fetch failed)
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError(
            "yfinance is not installed. Run: pip install yfinance"
        )

    if not holdings:
        return {}

    # Build symbol -> yf ticker mapping
    ticker_map: dict[str, str] = {}
    for symbol, holding in holdings.items():
        ticker_map[symbol] = _yf_ticker(symbol, holding.exchange)

    yf_tickers = list(set(ticker_map.values()))

    results: dict[str, float | None] = {s: None for s in holdings}

    try:
        if len(yf_tickers) == 1:
            ticker_obj = yf.Ticker(yf_tickers[0])
            info = ticker_obj.fast_info
            price = getattr(info, "last_price", None)
            if price is None:
                price = getattr(info, "regular_market_price", None)
            # Map back
            for symbol, yf_sym in ticker_map.items():
                if yf_sym == yf_tickers[0]:
                    results[symbol] = price
        else:
            tickers = yf.Tickers(" ".join(yf_tickers))
            for symbol, yf_sym in ticker_map.items():
                try:
                    t = tickers.tickers.get(yf_sym)
                    if t is None:
                        continue
                    info = t.fast_info
                    price = getattr(info, "last_price", None)
                    if price is None:
                        price = getattr(info, "regular_market_price", None)
                    results[symbol] = price
                except Exception:
                    pass
    except Exception as e:
        raise RuntimeError(f"Price fetch failed: {e}") from e

    return results


def fetch_aud_usd_rate() -> float | None:
    """Fetch the current AUD/USD exchange rate via Yahoo Finance."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        ticker = yf.Ticker("AUDUSD=X")
        info = ticker.fast_info
        rate = getattr(info, "last_price", None)
        if rate is None:
            rate = getattr(info, "regular_market_price", None)
        return float(rate) if rate is not None else None
    except Exception:
        return None
