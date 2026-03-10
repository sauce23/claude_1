import sys

from . import storage
from .display import show_comparison, show_portfolio, show_targets
from .models import Holding, Portfolio

HELP_TEXT = """
Portfolio Tracker — Commands:

  Holdings:
    add <symbol> <shares> [price]   Add shares (accumulates if existing; omit price to fetch live)
    set <symbol> <shares> [price]   Set exact shares & price (overwrites; omit price to fetch live)
    shares <symbol> <qty>           Update quantity only (keeps current price)
    remove <symbol>                 Remove a holding entirely
    price <symbol> <price>          Manually update price for a holding

  Real-time Prices:
    refresh                         Fetch live prices for all holdings (requires yfinance)
    refresh <symbol>                Fetch live price for one holding

  Targets:
    target <symbol> <pct>           Set target allocation % for a symbol
    rmtarget <symbol>               Remove a target

  Views:
    show                            Show portfolio grouped by exchange (ASX / US)
    targets                         Show target allocations
    compare                         Compare actual vs target allocations

  Other:
    help                            Show this help message
    quit / exit                     Save and exit

  Notes:
    - ASX stocks: use the .AX suffix, e.g. BHP.AX, CBA.AX
    - US stocks: use the ticker directly, e.g. AAPL, MSFT
    - Install yfinance for live prices: pip install yfinance
"""


def _parse_float(val: str, name: str) -> float | None:
    try:
        return float(val)
    except ValueError:
        print(f"Error: {name} must be a number, got '{val}'")
        return None


def _fetch_one_price(symbol: str, exchange: str) -> float | None:
    from .prices import fetch_prices
    from .models import Holding as _H

    dummy = {symbol: _H(symbol=symbol, shares=1, price=0, exchange=exchange)}
    try:
        results = fetch_prices(dummy)
        price = results.get(symbol)
        if price is None:
            print(f"  Could not fetch price for {symbol} — enter price manually.")
        return price
    except ImportError as e:
        print(f"  {e}")
        return None
    except RuntimeError as e:
        print(f"  {e}")
        return None


def _do_refresh(portfolio: Portfolio, symbol: str | None, kwargs: dict):
    from .prices import fetch_prices, fetch_aud_usd_rate

    targets = (
        {symbol: portfolio.holdings[symbol]}
        if symbol
        else portfolio.holdings
    )
    if not targets:
        print("No holdings to refresh.")
        return

    print(f"Fetching live prices for {len(targets)} holding(s)...")
    try:
        results = fetch_prices(targets)
    except ImportError as e:
        print(f"Error: {e}")
        return
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    updated = 0
    for sym, price in results.items():
        if price is not None:
            portfolio.update_price(sym, price)
            currency = portfolio.holdings[sym].currency
            print(f"  {sym}: {price:,.4f} {currency}")
            updated += 1
        else:
            print(f"  {sym}: failed to fetch price")

    # Also refresh the AUD/USD rate if we have mixed holdings
    exchanges = set(h.exchange for h in portfolio.holdings.values())
    if "ASX" in exchanges and "US" in exchanges and not symbol:
        rate = fetch_aud_usd_rate()
        if rate:
            portfolio.aud_usd_rate = rate
            print(f"  AUD/USD rate: {rate:.4f}")

    if updated:
        storage.save(portfolio, **kwargs)
        print(f"Updated {updated} price(s).")
    else:
        print("No prices were updated.")


def run(data_file: str | None = None):
    kwargs = {"path": data_file} if data_file else {}
    portfolio = storage.load(**kwargs)

    print("Portfolio Tracker")
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
            # add <symbol> <shares> [price]
            if len(args) < 2 or len(args) > 3:
                print("Usage: add <symbol> <shares> [price]")
                continue
            symbol = args[0].upper()
            shares = _parse_float(args[1], "shares")
            if shares is None:
                continue

            if len(args) == 3:
                price = _parse_float(args[2], "price")
                if price is None:
                    continue
            else:
                from .models import _detect_exchange
                exchange = _detect_exchange(symbol)
                print(f"Fetching live price for {symbol}...")
                price = _fetch_one_price(symbol, exchange)
                if price is None:
                    print("Use: add <symbol> <shares> <price>  to set manually.")
                    continue

            portfolio.add_holding(symbol, shares, price)
            currency = portfolio.holdings[symbol].currency
            exchange = portfolio.holdings[symbol].exchange
            print(f"Added {shares:g} shares of {symbol} ({exchange}) @ {price:,.4f} {currency}")
            storage.save(portfolio, **kwargs)

        elif cmd == "set":
            # set <symbol> <shares> [price]
            if len(args) < 2 or len(args) > 3:
                print("Usage: set <symbol> <shares> [price]")
                continue
            symbol = args[0].upper()
            shares = _parse_float(args[1], "shares")
            if shares is None:
                continue

            if len(args) == 3:
                price = _parse_float(args[2], "price")
                if price is None:
                    continue
            else:
                from .models import _detect_exchange
                exchange = _detect_exchange(symbol)
                print(f"Fetching live price for {symbol}...")
                price = _fetch_one_price(symbol, exchange)
                if price is None:
                    print("Use: set <symbol> <shares> <price>  to set manually.")
                    continue

            from .models import _detect_exchange
            exchange = portfolio.holdings[symbol].exchange if symbol in portfolio.holdings else _detect_exchange(symbol)
            portfolio.holdings[symbol] = Holding(symbol=symbol, shares=shares, price=price, exchange=exchange)
            currency = portfolio.holdings[symbol].currency
            print(f"Set {symbol} ({exchange}) to {shares:g} shares @ {price:,.4f} {currency}")
            storage.save(portfolio, **kwargs)

        elif cmd == "shares":
            # shares <symbol> <qty>  — quick quantity update
            if len(args) != 2:
                print("Usage: shares <symbol> <qty>")
                continue
            symbol = args[0].upper()
            qty = _parse_float(args[1], "qty")
            if qty is None:
                continue
            if symbol not in portfolio.holdings:
                print(f"{symbol} not found. Use 'add' to add a new holding.")
                continue
            portfolio.update_shares(symbol, qty)
            h = portfolio.holdings[symbol]
            print(f"Updated {symbol} quantity to {qty:g} shares (value: {h.value:,.2f} {h.currency})")
            storage.save(portfolio, **kwargs)

        elif cmd == "remove":
            if len(args) != 1:
                print("Usage: remove <symbol>")
                continue
            symbol = args[0].upper()
            if portfolio.remove_holding(symbol):
                print(f"Removed {symbol}")
                storage.save(portfolio, **kwargs)
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
                currency = portfolio.holdings[symbol].currency
                print(f"Updated {symbol} price to {price:,.4f} {currency}")
                storage.save(portfolio, **kwargs)
            else:
                print(f"{symbol} not found in portfolio")

        elif cmd == "refresh":
            if len(args) == 0:
                _do_refresh(portfolio, None, kwargs)
            elif len(args) == 1:
                symbol = args[0].upper()
                if symbol not in portfolio.holdings:
                    print(f"{symbol} not found in portfolio")
                else:
                    _do_refresh(portfolio, symbol, kwargs)
            else:
                print("Usage: refresh [symbol]")

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
            storage.save(portfolio, **kwargs)

        elif cmd == "rmtarget":
            if len(args) != 1:
                print("Usage: rmtarget <symbol>")
                continue
            symbol = args[0].upper()
            if portfolio.remove_target(symbol):
                print(f"Removed target for {symbol}")
                storage.save(portfolio, **kwargs)
            else:
                print(f"No target found for {symbol}")

        elif cmd == "show":
            show_portfolio(portfolio)

        elif cmd == "targets":
            show_targets(portfolio)

        elif cmd == "compare":
            show_comparison(portfolio)

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
