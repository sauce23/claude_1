import sys

from . import storage
from .display import show_comparison, show_portfolio, show_targets
from .models import Portfolio

HELP_TEXT = """
Portfolio Tracker — Commands:

  Holdings:
    add <symbol> <shares> <price>   Add shares (accumulates if existing)
    set <symbol> <shares> <price>   Set exact shares & price (overwrites)
    remove <symbol>                 Remove a holding entirely
    price <symbol> <price>          Update price for a holding

  Targets:
    target <symbol> <pct>           Set target allocation % for a symbol
    rmtarget <symbol>               Remove a target

  Views:
    show                            Show current portfolio
    targets                         Show target allocations
    compare                         Compare actual vs target allocations

  Other:
    help                            Show this help message
    quit / exit                     Save and exit
"""


def _parse_float(val: str, name: str) -> float | None:
    try:
        return float(val)
    except ValueError:
        print(f"Error: {name} must be a number, got '{val}'")
        return None


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
            if len(args) != 3:
                print("Usage: add <symbol> <shares> <price>")
                continue
            shares = _parse_float(args[1], "shares")
            price = _parse_float(args[2], "price")
            if shares is None or price is None:
                continue
            symbol = args[0].upper()
            portfolio.add_holding(symbol, shares, price)
            print(f"Added {shares:g} shares of {symbol} @ ${price:,.2f}")
            storage.save(portfolio, **kwargs)

        elif cmd == "set":
            if len(args) != 3:
                print("Usage: set <symbol> <shares> <price>")
                continue
            shares = _parse_float(args[1], "shares")
            price = _parse_float(args[2], "price")
            if shares is None or price is None:
                continue
            symbol = args[0].upper()
            from .models import Holding
            portfolio.holdings[symbol] = Holding(symbol=symbol, shares=shares, price=price)
            print(f"Set {symbol} to {shares:g} shares @ ${price:,.2f}")
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
                print(f"Updated {symbol} price to ${price:,.2f}")
                storage.save(portfolio, **kwargs)
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
