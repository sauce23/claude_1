from .models import Portfolio


def _fmt_money(value: float) -> str:
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
        rows.append([symbol, f"{h.shares:g}", _fmt_money(h.price), _fmt_money(h.value), _fmt_pct(pct)])

    print(f"\nPortfolio (Total: {_fmt_money(total)})")
    print()
    _table(
        ["Symbol", "Shares", "Price", "Value", "Weight"],
        rows,
        ["l", "r", "r", "r", "r"],
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
        print(f"  ⚠ Targets do not sum to 100%")
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

        if diff > 0:
            action = f"Over  +{_fmt_pct(abs(diff))}"
        elif diff < 0:
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
        print(f"  ⚠ Targets sum to {_fmt_pct(target_total)}, not 100%")
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
