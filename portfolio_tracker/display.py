import os
import sys
import time
from datetime import datetime

from .models import Portfolio
from .prices import Quote, fetch_quotes


def _fmt_money(value: float, currency: str = "USD") -> str:
    if currency == "AUD":
        return f"A${value:,.2f}"
    return f"${value:,.2f}"


def _fmt_pct(value: float) -> str:
    return f"{value:.1f}%"


def _table(headers: list[str], rows: list[list[str]], col_align: list[str] | None = None):
    """Print a simple aligned table. col_align: 'l' or 'r' per column."""
    if not rows:
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    if col_align is None:
        col_align = ["l"] * len(headers)

    def _pad(text: str, width: int, align: str) -> str:
        if align == "r":
            return text.rjust(width)
        return text.ljust(width)

    header_line = "  ".join(_pad(h, widths[i], col_align[i]) for i, h in enumerate(headers))
    sep = "  ".join("-" * w for w in widths)
    print(header_line)
    print(sep)
    for row in rows:
        print("  ".join(_pad(cell, widths[i], col_align[i]) for i, cell in enumerate(row)))


def show_portfolio(portfolio: Portfolio):
    if not portfolio.holdings:
        print("Portfolio is empty. Use 'add' to add holdings.")
        return

    total = portfolio.total_value
    rows = []
    for symbol in sorted(portfolio.holdings):
        h = portfolio.holdings[symbol]
        pct = portfolio.actual_pct(symbol)
        rows.append([
            symbol,
            h.market,
            f"{h.shares:g}",
            _fmt_money(h.price, "AUD" if h.market == "ASX" else "USD"),
            _fmt_money(h.value, "AUD" if h.market == "ASX" else "USD"),
            _fmt_pct(pct),
        ])

    print(f"\nPortfolio (Total: {_fmt_money(total)})")
    print()
    _table(
        ["Symbol", "Mkt", "Shares", "Price", "Value", "Weight"],
        rows,
        ["l", "l", "r", "r", "r", "r"],
    )
    print()


def show_targets(portfolio: Portfolio):
    if not portfolio.targets:
        print("No targets set. Use 'target' to set allocation targets.")
        return

    rows = []
    for symbol in sorted(portfolio.targets):
        rows.append([symbol, _fmt_pct(portfolio.targets[symbol])])

    total = portfolio.targets_total()
    print(f"\nTargets (Total: {_fmt_pct(total)})")
    if abs(total - 100.0) > 0.01:
        print(f"  Warning: Targets do not sum to 100%")
    print()
    _table(["Symbol", "Target %"], rows, ["l", "r"])
    print()


def show_comparison(portfolio: Portfolio):
    if not portfolio.holdings and not portfolio.targets:
        print("No holdings or targets to compare.")
        return

    all_symbols = sorted(set(list(portfolio.holdings.keys()) + list(portfolio.targets.keys())))
    total = portfolio.total_value

    rows = []
    for symbol in all_symbols:
        actual = portfolio.actual_pct(symbol)
        target = portfolio.targets.get(symbol, 0.0)
        diff = actual - target

        if diff > 0.05:
            action = f"Over  +{_fmt_pct(abs(diff))}"
        elif diff < -0.05:
            action = f"Under -{_fmt_pct(abs(diff))}"
        else:
            action = "On target"

        holding = portfolio.holdings.get(symbol)
        value = _fmt_money(holding.value) if holding else _fmt_money(0)

        rows.append([
            symbol,
            value,
            _fmt_pct(actual),
            _fmt_pct(target),
            f"{diff:+.1f}%",
            action,
        ])

    target_total = portfolio.targets_total()
    print(f"\nPortfolio vs Targets (Total value: {_fmt_money(total)})")
    if abs(target_total - 100.0) > 0.01:
        print(f"  Warning: Targets sum to {_fmt_pct(target_total)}, not 100%")
    print()
    _table(
        ["Symbol", "Value", "Actual %", "Target %", "Diff", "Status"],
        rows,
        ["l", "r", "r", "r", "r", "l"],
    )

    # Show rebalance suggestions
    if total > 0 and portfolio.targets:
        print()
        print("Rebalance suggestions:")
        for symbol in all_symbols:
            actual = portfolio.actual_pct(symbol)
            target = portfolio.targets.get(symbol, 0.0)
            diff_pct = target - actual
            diff_value = (diff_pct / 100) * total
            if abs(diff_value) > 0.01:
                if diff_value > 0:
                    print(f"  {symbol}: Buy {_fmt_money(diff_value)} to reach target")
                else:
                    print(f"  {symbol}: Sell {_fmt_money(abs(diff_value))} to reach target")
    print()


def _clear_screen():
    """Clear the terminal screen."""
    if sys.stdout.isatty():
        os.system("clear" if os.name != "nt" else "cls")


def _build_dashboard_lines(portfolio: Portfolio, quotes: dict[str, Quote]) -> list[str]:
    """Build the dashboard output as a list of lines."""
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"Live Portfolio Dashboard  |  Updated: {now}")
    lines.append("=" * 80)

    if not portfolio.holdings:
        lines.append("Portfolio is empty. Use 'add' to add holdings.")
        return lines

    total = portfolio.total_value

    # Build table data
    headers = ["Symbol", "Mkt", "Shares", "Price", "Value", "Current %", "Target %", "Diff"]
    col_align = ["l", "l", "r", "r", "r", "r", "r", "r"]

    rows = []
    all_symbols = sorted(set(list(portfolio.holdings.keys()) + list(portfolio.targets.keys())))

    for symbol in all_symbols:
        holding = portfolio.holdings.get(symbol)
        quote = quotes.get(symbol)
        target = portfolio.targets.get(symbol)

        if holding:
            mkt = holding.market
            shares = f"{holding.shares:g}"
            currency = "AUD" if mkt == "ASX" else "USD"
            price = _fmt_money(holding.price, currency)
            value = _fmt_money(holding.value, currency)
            actual = portfolio.actual_pct(symbol)
            actual_str = _fmt_pct(actual)
        else:
            mkt = ""
            shares = "-"
            price = "-"
            value = _fmt_money(0)
            actual = 0.0
            actual_str = _fmt_pct(0)

        target_pct = target if target is not None else 0.0
        target_str = _fmt_pct(target_pct) if target is not None else "-"
        diff = actual - target_pct
        diff_str = f"{diff:+.1f}%" if target is not None else "-"

        # Add market state indicator from live quote
        status = ""
        if quote and quote.is_market_open:
            status = " *"

        rows.append([symbol + status, mkt, shares, price, value, actual_str, target_str, diff_str])

    # Render table into lines
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def _pad(text: str, width: int, align: str) -> str:
        if align == "r":
            return text.rjust(width)
        return text.ljust(width)

    lines.append("")
    lines.append(f"Total Value: {_fmt_money(total)}")

    target_total = portfolio.targets_total()
    if portfolio.targets and abs(target_total - 100.0) > 0.01:
        lines.append(f"Warning: Targets sum to {_fmt_pct(target_total)}, not 100%")

    lines.append("")
    lines.append("  ".join(_pad(h, widths[i], col_align[i]) for i, h in enumerate(headers)))
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        lines.append("  ".join(_pad(cell, widths[i], col_align[i]) for i, cell in enumerate(row)))

    lines.append("")

    # Market status
    open_markets = set()
    for quote in quotes.values():
        if quote.is_market_open:
            holding = portfolio.holdings.get(quote.symbol)
            if holding:
                open_markets.add(holding.market)
    if open_markets:
        lines.append(f"Markets open: {', '.join(sorted(open_markets))}  (* = market open)")
    else:
        lines.append("All markets closed")

    # Rebalance summary
    if total > 0 and portfolio.targets:
        lines.append("")
        lines.append("Rebalance:")
        for symbol in all_symbols:
            actual = portfolio.actual_pct(symbol)
            target_pct = portfolio.targets.get(symbol, 0.0)
            diff_pct = target_pct - actual
            diff_value = (diff_pct / 100) * total
            if abs(diff_value) > 1.0:
                if diff_value > 0:
                    lines.append(f"  {symbol}: Buy {_fmt_money(diff_value)}")
                else:
                    lines.append(f"  {symbol}: Sell {_fmt_money(abs(diff_value))}")

    return lines


def refresh_prices(portfolio: Portfolio) -> dict[str, Quote]:
    """Fetch latest prices and update portfolio holdings. Returns quotes."""
    pairs = portfolio.symbols_with_markets()
    if not pairs:
        return {}

    quotes = fetch_quotes(pairs)
    updated = []
    for symbol, quote in quotes.items():
        if portfolio.update_price(symbol, quote.price):
            updated.append(symbol)

    return quotes


def show_live_dashboard(portfolio: Portfolio, quotes: dict[str, Quote]):
    """Print the dashboard once (no loop)."""
    lines = _build_dashboard_lines(portfolio, quotes)
    for line in lines:
        print(line)


def watch_portfolio(portfolio: Portfolio, interval: int = 30, save_fn=None):
    """Continuously refresh prices and display the dashboard.

    Args:
        portfolio: The portfolio to watch.
        interval: Seconds between refreshes.
        save_fn: Optional callback to persist portfolio after price updates.
    """
    print(f"Starting live watch (refresh every {interval}s). Press Ctrl+C to stop.\n")
    try:
        while True:
            quotes = refresh_prices(portfolio)
            _clear_screen()
            lines = _build_dashboard_lines(portfolio, quotes)
            for line in lines:
                print(line)
            print(f"\nRefreshing every {interval}s. Press Ctrl+C to stop.")
            if save_fn:
                save_fn()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped live watch.")
