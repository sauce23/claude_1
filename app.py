import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from portfolio_tracker import storage
from portfolio_tracker.models import Holding, Portfolio, _detect_exchange

st.set_page_config(
    page_title="Portfolio Tracker",
    page_icon="📈",
    layout="wide",
)

DATA_FILE = os.path.join(os.path.dirname(__file__), "portfolio.json")

# ── Session state ─────────────────────────────────────────────────────────────

def _load() -> Portfolio:
    return storage.load(DATA_FILE)

def _save(portfolio: Portfolio):
    storage.save(portfolio, DATA_FILE)

if "portfolio" not in st.session_state:
    st.session_state.portfolio = _load()

portfolio: Portfolio = st.session_state.portfolio

# ── Helpers ───────────────────────────────────────────────────────────────────

def _currency(exchange: str) -> str:
    return "AUD" if exchange == "ASX" else "USD"

def _fmt(value: float, currency: str) -> str:
    sym = "A$" if currency == "AUD" else "$"
    return f"{sym}{value:,.2f}"

def _refresh_prices(symbol: str | None = None):
    try:
        from portfolio_tracker.prices import fetch_prices, fetch_aud_usd_rate
    except ImportError:
        st.error("yfinance not installed. Run: pip install yfinance")
        return

    targets = (
        {symbol: portfolio.holdings[symbol]}
        if symbol
        else portfolio.holdings
    )
    if not targets:
        st.warning("No holdings to refresh.")
        return

    with st.spinner("Fetching live prices…"):
        try:
            results = fetch_prices(targets)
        except Exception as e:
            st.error(f"Price fetch failed: {e}")
            return

    updated = []
    for sym, price in results.items():
        if price is not None:
            portfolio.update_price(sym, price)
            updated.append(sym)

    exchanges = set(h.exchange for h in portfolio.holdings.values())
    if "ASX" in exchanges and "US" in exchanges and not symbol:
        rate = fetch_aud_usd_rate()
        if rate:
            portfolio.aud_usd_rate = rate

    _save(portfolio)
    if updated:
        st.success(f"Updated: {', '.join(updated)}")
    else:
        st.warning("No prices could be fetched.")
    st.rerun()

# ── Sidebar — add holding ─────────────────────────────────────────────────────

with st.sidebar:
    st.header("Add / Update Holding")

    with st.form("add_holding_form", clear_on_submit=True):
        new_sym = st.text_input("Symbol", placeholder="e.g. AAPL or BHP.AX").strip().upper()
        new_shares = st.number_input("Shares", min_value=0.0, step=1.0, format="%.4g")
        new_price = st.number_input("Price (leave 0 to fetch live)", min_value=0.0, step=0.01, format="%.4f")
        submitted = st.form_submit_button("Add / Update", use_container_width=True)

    if submitted:
        if not new_sym:
            st.error("Symbol is required.")
        elif new_shares <= 0:
            st.error("Shares must be > 0.")
        else:
            price = new_price
            if price == 0.0:
                try:
                    from portfolio_tracker.prices import fetch_prices
                    exchange = _detect_exchange(new_sym)
                    dummy = {new_sym: Holding(symbol=new_sym, shares=1, price=0, exchange=exchange)}
                    results = fetch_prices(dummy)
                    price = results.get(new_sym)
                    if price is None:
                        st.error("Could not fetch live price. Enter price manually.")
                        price = None
                except Exception as e:
                    st.error(f"Price fetch error: {e}")
                    price = None

            if price is not None and price > 0:
                portfolio.add_holding(new_sym, new_shares, price)
                _save(portfolio)
                st.success(f"Added {new_shares:g} × {new_sym} @ {price:,.4f}")
                st.rerun()

    st.divider()

    st.header("Set Target %")
    with st.form("target_form", clear_on_submit=True):
        t_sym = st.selectbox(
            "Symbol",
            options=sorted(portfolio.holdings.keys()) or ["—"],
        )
        t_pct = st.number_input("Target %", min_value=0.0, max_value=100.0, step=1.0, format="%.1f")
        t_submitted = st.form_submit_button("Set Target", use_container_width=True)

    if t_submitted and t_sym and t_sym != "—":
        portfolio.set_target(t_sym, t_pct)
        _save(portfolio)
        st.success(f"Target set: {t_sym} = {t_pct:.1f}%")
        st.rerun()

    st.divider()

    if st.button("Refresh All Prices", use_container_width=True):
        _refresh_prices()

# ── Main ──────────────────────────────────────────────────────────────────────

st.title("📈 Portfolio Tracker")

if not portfolio.holdings:
    st.info("No holdings yet. Use the sidebar to add your first stock.")
    st.stop()

# ── Summary metrics ───────────────────────────────────────────────────────────

totals = portfolio.total_value_by_exchange()
exchanges = sorted(totals.keys())

cols = st.columns(len(exchanges) + (1 if portfolio.aud_usd_rate and len(exchanges) > 1 else 0))
for i, exchange in enumerate(exchanges):
    currency = _currency(exchange)
    cols[i].metric(
        label=f"{exchange} Total ({'AUD' if exchange == 'ASX' else 'USD'})",
        value=_fmt(totals[exchange], currency),
    )
if portfolio.aud_usd_rate and len(exchanges) > 1:
    usd_total = sum(
        v * portfolio.aud_usd_rate if ex == "ASX" else v
        for ex, v in totals.items()
    )
    cols[-1].metric(
        label=f"Combined (USD @ {portfolio.aud_usd_rate:.4f})",
        value=f"${usd_total:,.2f}",
    )

st.divider()

# ── Holdings tables + per-exchange pie charts ─────────────────────────────────

left, right = st.columns([3, 2])

with left:
    st.subheader("Holdings")
    for exchange in exchanges:
        currency = _currency(exchange)
        ex_holdings = {s: h for s, h in portfolio.holdings.items() if h.exchange == exchange}
        ex_total = totals.get(exchange, 0)

        st.markdown(f"**{exchange} ({currency}) — {_fmt(ex_total, currency)}**")

        rows = []
        for symbol in sorted(ex_holdings):
            h = ex_holdings[symbol]
            rows.append({
                "Symbol": symbol,
                "Shares": h.shares,
                "Price": h.price,
                "Value": h.value,
                "% of Exchange": round(portfolio.actual_pct_within_exchange(symbol), 2),
                "% Overall": round(portfolio.actual_pct(symbol), 2),
                "Target %": portfolio.targets.get(symbol, 0.0),
            })

        df = pd.DataFrame(rows)

        # Editable shares column
        edited = st.data_editor(
            df,
            key=f"table_{exchange}",
            column_config={
                "Symbol": st.column_config.TextColumn(disabled=True),
                "Shares": st.column_config.NumberColumn(format="%.4g", step=1),
                "Price": st.column_config.NumberColumn(format="%.4f", disabled=True),
                "Value": st.column_config.NumberColumn(format="%.2f", disabled=True),
                "% of Exchange": st.column_config.NumberColumn(format="%.2f%%", disabled=True),
                "% Overall": st.column_config.NumberColumn(format="%.2f%%", disabled=True),
                "Target %": st.column_config.NumberColumn(format="%.1f%%"),
            },
            hide_index=True,
            use_container_width=True,
        )

        # Apply any edits the user made to Shares or Target %
        for _, row in edited.iterrows():
            sym = row["Symbol"]
            new_shares = float(row["Shares"])
            new_target = float(row["Target %"])
            current_shares = portfolio.holdings[sym].shares
            current_target = portfolio.targets.get(sym, 0.0)
            if abs(new_shares - current_shares) > 1e-9:
                portfolio.update_shares(sym, new_shares)
                _save(portfolio)
            if abs(new_target - current_target) > 1e-9:
                portfolio.set_target(sym, new_target)
                _save(portfolio)

        # Per-holding refresh buttons
        btn_cols = st.columns(len(ex_holdings))
        for i, symbol in enumerate(sorted(ex_holdings)):
            if btn_cols[i].button(f"↻ {symbol}", key=f"refresh_{symbol}"):
                _refresh_prices(symbol)

        st.markdown("")

    # Remove holding
    with st.expander("Remove a holding"):
        rem_sym = st.selectbox("Select holding to remove", options=sorted(portfolio.holdings.keys()), key="remove_sym")
        if st.button("Remove", type="primary"):
            portfolio.remove_holding(rem_sym)
            if rem_sym in portfolio.targets:
                portfolio.remove_target(rem_sym)
            _save(portfolio)
            st.rerun()

with right:
    st.subheader("Allocation")

    tab1, tab2 = st.tabs(["By Exchange", "Actual vs Target"])

    with tab1:
        # Pie per exchange, then overall
        for exchange in exchanges:
            currency = _currency(exchange)
            ex_holdings = {s: h for s, h in portfolio.holdings.items() if h.exchange == exchange}
            if not ex_holdings:
                continue
            labels = list(sorted(ex_holdings.keys()))
            values = [ex_holdings[s].value for s in labels]
            fig = px.pie(
                names=labels,
                values=values,
                title=f"{exchange} Allocation ({currency})",
                hole=0.4,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(margin=dict(t=40, b=0, l=0, r=0), showlegend=False, height=280)
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        all_symbols = sorted(
            set(list(portfolio.holdings.keys()) + list(portfolio.targets.keys()))
        )
        actual_vals = [portfolio.actual_pct(s) for s in all_symbols]
        target_vals = [portfolio.targets.get(s, 0.0) for s in all_symbols]

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(name="Actual %", x=all_symbols, y=actual_vals, marker_color="#636efa"))
        fig2.add_trace(go.Bar(name="Target %", x=all_symbols, y=target_vals, marker_color="#ef553b"))
        fig2.update_layout(
            barmode="group",
            yaxis_title="Portfolio %",
            margin=dict(t=20, b=0, l=0, r=0),
            legend=dict(orientation="h", y=1.1),
            height=320,
        )
        st.plotly_chart(fig2, use_container_width=True)

        # Rebalance table
        if portfolio.targets:
            st.markdown("**Rebalance suggestions**")
            total = portfolio.total_value
            rebal_rows = []
            for sym in all_symbols:
                diff_pct = portfolio.targets.get(sym, 0.0) - portfolio.actual_pct(sym)
                diff_val = (diff_pct / 100) * total
                if abs(diff_val) > 0.01:
                    holding = portfolio.holdings.get(sym)
                    currency = holding.currency if holding else "USD"
                    rebal_rows.append({
                        "Symbol": sym,
                        "Action": "Buy" if diff_val > 0 else "Sell",
                        "Amount": f"{'A$' if currency == 'AUD' else '$'}{abs(diff_val):,.2f}",
                        "Diff %": f"{diff_pct:+.1f}%",
                    })
            if rebal_rows:
                st.dataframe(pd.DataFrame(rebal_rows), hide_index=True, use_container_width=True)
            else:
                st.success("Portfolio is on target!")
