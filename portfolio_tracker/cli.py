import sys

from . import storage
from .display import (
    refresh_prices,
    show_comparison,
    show_live_dashboard,
    show_portfolio,
    show_targets,
    watch_portfolio,
)
from .models import VALID_MARKETS, Portfolio

HELP_TEXT = """
Portfolio Tracker — Commands:

  Holdings:
    add <symbol> <shares> [market]    Add shares (market: US or ASX, default US)
    set <symbol> <shares> [market]    Set exact shares (overwrites)
    remove <symbol>                   Remove a holding entirely

  Targets:
    target <symbol> <pct>             Set target allocation % for a symbol
    rmtarget <symbol>                 Remove a target

  Prices:
    refresh                           Fetch live prices for all holdings
    watch [interval]                  Live dashboard with auto-refresh (default 30s)

  Views:
    show                              Show current portfolio
    targets                           Show target allocations
    compare                           Compare actual vs target allocations

  Other:
    help                              Show this help message
    quit / exit                       Save and exit
"""


def _parse_float(val: str, name: str) -> float | None:
    try:
        return float(val)
    except ValueError:
        print(f"Error: {name} must be a number, got '{val}'")
        return None


def _parse_market(val: str) -> str | None:
    val = val.upper()
    if val not in VALID_MARKETS:
        print(f"Error: market must be one of {VALID_MARKETS}, got '{val}'")
        return None
    return val


def run(data_file: str | None = None):
    kwargs = {"path": data_file} if data_file else {}
    portfolio = storage.load(**kwargs)

    def _save():
        storage.save(portfolio, **kwargs)

    print("Portfolio Tracker (with live prices)")
    print("Type 'help' for commands, 'quit' to exit.\n")

    while True:
        try:
            line = input("portfolio> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("quit", "exit"):
            break

        elif cmd == "help":
            print(HELP_TEXT)

        elif cmd == "add":
            if len(args) < 2 or len(args) > 3:
                print("Usage: add <symbol> <shares> [market]")
                print("  market: US (default) or ASX")
                continue
            shares = _parse_float(args[1], "shares")
            if shares is None:
                continue
            market = "US"
            if len(args) == 3:
                market = _parse_market(args[2])
                if market is None:
                    continue
            symbol = args[0].upper()
            # Fetch live price on add
            print(f"Fetching live price for {symbol} ({market})...")
            from .prices import fetch_quote
            quote = fetch_quote(symbol, market)
            if quote:
                price = quote.price
                currency = "AUD" if market == "ASX" else "USD"
                prefix = "A$" if currency == "AUD" else "$"
                portfolio.add_holding(symbol, shares, price, market)
                print(f"Added {shares:g} shares of {symbol} @ {prefix}{price:,.2f} ({market})")
            else:
                print(f"Could not fetch price for {symbol}. Adding with price $0.00")
                print("Use 'refresh' later or 'price <symbol> <price>' to set manually.")
                portfolio.add_holding(symbol, shares, 0.0, market)
            _save()

        elif cmd == "set":
            if len(args) < 2 or len(args) > 3:
                print("Usage: set <symbol> <shares> [market]")
                continue
            shares = _parse_float(args[1], "shares")
            if shares is None:
                continue
            market = "US"
            if len(args) == 3:
                market = _parse_market(args[2])
                if market is None:
                    continue
            symbol = args[0].upper()
            print(f"Fetching live price for {symbol} ({market})...")
            from .prices import fetch_quote
            quote = fetch_quote(symbol, market)
            if quote:
                price = quote.price
                currency = "AUD" if market == "ASX" else "USD"
                prefix = "A$" if currency == "AUD" else "$"
            else:
                price = 0.0
                prefix = "$"
                print(f"Could not fetch price. Setting price to $0.00")
            from .models import Holding
            portfolio.holdings[symbol] = Holding(
                symbol=symbol, shares=shares, price=price, market=market
            )
            print(f"Set {symbol} to {shares:g} shares @ {prefix}{price:,.2f} ({market})")
            _save()

        elif cmd == "remove":
            if len(args) != 1:
                print("Usage: remove <symbol>")
                continue
            symbol = args[0].upper()
            if portfolio.remove_holding(symbol):
                print(f"Removed {symbol}")
                _save()
            else:
                print(f"{symbol} not found in portfolio")

        elif cmd == "price":
            if len(args) != 2:
                print("Usage: price <symbol> <price>")
                continue
            price = _parse_float(args[1], "price")
            if price is None:
                continue
            symbol = args[0].upper()
            if portfolio.update_price(symbol, price):
                print(f"Updated {symbol} price to ${price:,.2f}")
                _save()
            else:
                print(f"{symbol} not found in portfolio")

        elif cmd == "target":
            if len(args) != 2:
                print("Usage: target <symbol> <pct>")
                continue
            pct = _parse_float(args[1], "percentage")
            if pct is None:
                continue
            symbol = args[0].upper()
            portfolio.set_target(symbol, pct)
            total = portfolio.targets_total()
            print(f"Set {symbol} target to {pct:.1f}% (targets total: {total:.1f}%)")
            _save()

        elif cmd == "rmtarget":
            if len(args) != 1:
                print("Usage: rmtarget <symbol>")
                continue
            symbol = args[0].upper()
            if portfolio.remove_target(symbol):
                print(f"Removed target for {symbol}")
                _save()
            else:
                print(f"No target found for {symbol}")

        elif cmd == "show":
            show_portfolio(portfolio)

        elif cmd == "targets":
            show_targets(portfolio)

        elif cmd == "compare":
            show_comparison(portfolio)

        elif cmd == "refresh":
            if not portfolio.holdings:
                print("No holdings to refresh.")
                continue
            print("Fetching live prices...")
            quotes = refresh_prices(portfolio)
            if quotes:
                _save()
                show_live_dashboard(portfolio, quotes)
            else:
                print("Could not fetch any prices. Check your connection.")

        elif cmd == "watch":
            if not portfolio.holdings:
                print("No holdings to watch.")
                continue
            interval = 30
            if args:
                parsed = _parse_float(args[0], "interval")
                if parsed is None:
                    continue
                interval = max(10, int(parsed))  # minimum 10s
            watch_portfolio(portfolio, interval=interval, save_fn=_save)

        else:
            print(f"Unknown command: {cmd}. Type 'help' for available commands.")


def main():
    data_file = None
    if len(sys.argv) > 1 and sys.argv[1] == "--file":
        if len(sys.argv) > 2:
            data_file = sys.argv[2]
        else:
            print("Error: --file requires a path argument")
            sys.exit(1)
    run(data_file)
