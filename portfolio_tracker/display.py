from .models import Portfolio

EXCHANGE_LABELS = {"ASX": "ASX (AUD)", "US": "US (USD)"}


def _fmt_money(value: float, currency: str = "") -> str:
    symbol = "A$" if currency == "AUD" else "$"
    return f"{symbol}{value:,.2f}"


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
        return text.rjust(width) if align == "r" else text.ljust(width)

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

    exchanges = sorted(set(h.exchange for h in portfolio.holdings.values()))
    totals_by_exchange = portfolio.total_value_by_exchange()

    for exchange in exchanges:
        exchange_holdings = {
            s: h for s, h in portfolio.holdings.items() if h.exchange == exchange
        }
        exchange_total = totals_by_exchange.get(exchange, 0.0)
        currency = "AUD" if exchange == "ASX" else "USD"
        label = EXCHANGE_LABELS.get(exchange, exchange)

        print(f"\n{label}  —  Total: {_fmt_money(exchange_total, currency)}")
        print()
        rows = []
        for symbol in sorted(exchange_holdings):
            h = exchange_holdings[symbol]
            pct_overall = portfolio.actual_pct(symbol)
            pct_exchange = portfolio.actual_pct_within_exchange(symbol)
            rows.append([
                symbol,
                f"{h.shares:g}",
                _fmt_money(h.price, currency),
                _fmt_money(h.value, currency),
                _fmt_pct(pct_exchange),
                _fmt_pct(pct_overall),
            ])
        _table(
            ["Symbol", "Shares", "Price", "Value", f"% of {exchange}", "% Overall"],
            rows,
            ["l", "r", "r", "r", "r", "r"],
        )

    # Exchange breakdown summary
    if len(exchanges) > 1:
        print()
        _print_exchange_breakdown(portfolio)

    print()


def _print_exchange_breakdown(portfolio: Portfolio):
    totals_by_exchange = portfolio.total_value_by_exchange()
    overall_total = portfolio.total_value
    print("Exchange Breakdown:")
    rows = []
    for exchange in sorted(totals_by_exchange):
        currency = "AUD" if exchange == "ASX" else "USD"
        val = totals_by_exchange[exchange]
        label = EXCHANGE_LABELS.get(exchange, exchange)
        count = sum(1 for h in portfolio.holdings.values() if h.exchange == exchange)
        rows.append([label, _fmt_money(val, currency), f"{count} holdings"])
    _table(["Exchange", "Total Value", "Holdings"], rows, ["l", "r", "l"])
    if portfolio.aud_usd_rate:
        # Convert everything to USD for a combined total
        usd_total = 0.0
        for exchange, val in totals_by_exchange.items():
            if exchange == "ASX":
                usd_total += val * portfolio.aud_usd_rate
            else:
                usd_total += val
        print(f"  Combined (USD @ AUD/USD {portfolio.aud_usd_rate:.4f}): {_fmt_money(usd_total)} USD")


def show_targets(portfolio: Portfolio):
    if not portfolio.targets:
        print("No targets set. Use 'target <symbol> <pct>' to set allocation targets.")
        return

    rows = []
    for symbol in sorted(portfolio.targets):
        holding = portfolio.holdings.get(symbol)
        exchange = holding.exchange if holding else "?"
        rows.append([symbol, EXCHANGE_LABELS.get(exchange, exchange), _fmt_pct(portfolio.targets[symbol])])

    total = portfolio.targets_total()
    print(f"\nTargets (Total: {_fmt_pct(total)})")
    if abs(total - 100.0) > 0.01:
        print(f"  Warning: Targets sum to {_fmt_pct(total)}, not 100%")
    print()
    _table(["Symbol", "Exchange", "Target %"], rows, ["l", "l", "r"])
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
            status = f"Over   +{_fmt_pct(abs(diff))}"
        elif diff < -0.05:
            status = f"Under  -{_fmt_pct(abs(diff))}"
        else:
            status = "On target"

        holding = portfolio.holdings.get(symbol)
        currency = holding.currency if holding else "USD"
        exchange = holding.exchange if holding else "?"
        value = _fmt_money(holding.value, currency) if holding else _fmt_money(0)

        rows.append([
            symbol,
            EXCHANGE_LABELS.get(exchange, exchange),
            value,
            _fmt_pct(actual),
            _fmt_pct(target),
            f"{diff:+.1f}%",
            status,
        ])

    target_total = portfolio.targets_total()
    print(f"\nPortfolio vs Targets  (Total value across all holdings)")
    if abs(target_total - 100.0) > 0.01:
        print(f"  Warning: Targets sum to {_fmt_pct(target_total)}, not 100%")
    print()
    _table(
        ["Symbol", "Exchange", "Value", "Actual %", "Target %", "Diff", "Status"],
        rows,
        ["l", "l", "r", "r", "r", "r", "l"],
    )

    # Rebalance suggestions
    if total > 0 and portfolio.targets:
        print()
        print("Rebalance suggestions:")
        for symbol in all_symbols:
            actual = portfolio.actual_pct(symbol)
            target = portfolio.targets.get(symbol, 0.0)
            diff_pct = target - actual
            diff_value = (diff_pct / 100) * total
            if abs(diff_value) > 0.01:
                holding = portfolio.holdings.get(symbol)
                currency = holding.currency if holding else "USD"
                if diff_value > 0:
                    print(f"  {symbol}: Buy {_fmt_money(abs(diff_value), currency)}")
                else:
                    print(f"  {symbol}: Sell {_fmt_money(abs(diff_value), currency)}")
    print()
