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

# ── Session state ──────────────────────────────────────────────────────────────

def _load() -> Portfolio:
    return storage.load(DATA_FILE)

def _save(p: Portfolio):
    storage.save(p, DATA_FILE)

if "portfolio" not in st.session_state:
    st.session_state.portfolio = _load()
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "investment_thesis" not in st.session_state:
    st.session_state.investment_thesis = ""

portfolio: Portfolio = st.session_state.portfolio

# ── Helpers ────────────────────────────────────────────────────────────────────

def _value_aud(h: Holding) -> float:
    """Convert holding value to AUD."""
    if h.exchange == "ASX":
        return h.value
    rate = portfolio.aud_usd_rate or 1.0
    return h.value / rate  # USD → AUD

def _total_aud() -> float:
    return sum(_value_aud(h) for h in portfolio.holdings.values())

def _actual_pct_aud(symbol: str) -> float:
    total = _total_aud()
    if total == 0:
        return 0.0
    h = portfolio.holdings.get(symbol)
    return (_value_aud(h) / total * 100) if h else 0.0

def _refresh_prices(symbol: str | None = None):
    try:
        from portfolio_tracker.prices import fetch_prices, fetch_aud_usd_rate
    except ImportError:
        st.error("yfinance not installed. Run: pip install yfinance")
        return
    targets = {symbol: portfolio.holdings[symbol]} if symbol else portfolio.holdings
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
    if not symbol:
        exchanges = {h.exchange for h in portfolio.holdings.values()}
        if "ASX" in exchanges and "US" in exchanges:
            rate = fetch_aud_usd_rate()
            if rate:
                portfolio.aud_usd_rate = rate
    _save(portfolio)
    st.success(f"Updated: {', '.join(updated)}" if updated else "No prices fetched.")
    st.rerun()

def _extract_thesis_text(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    try:
        if name.endswith(".pdf"):
            import pypdf
            reader = pypdf.PdfReader(uploaded_file)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        elif name.endswith(".docx"):
            import docx
            doc = docx.Document(uploaded_file)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        st.error(f"Could not read file: {e}")
    return ""

# ── Agent ──────────────────────────────────────────────────────────────────────

_AGENT_TOOLS = [
    {
        "name": "get_portfolio",
        "description": "Get the current portfolio state: holdings, AUD values, actual %, and targets",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "update_shares",
        "description": "Update the number of shares for an existing holding",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker (e.g. VHY.AX or VONV)"},
                "shares": {"type": "number"},
            },
            "required": ["symbol", "shares"],
        },
    },
    {
        "name": "set_target",
        "description": "Set the target allocation percentage for a holding",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "target_pct": {"type": "number", "description": "Target % (0-100)"},
            },
            "required": ["symbol", "target_pct"],
        },
    },
    {
        "name": "add_holding",
        "description": "Add a new holding or update an existing one",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker (.AX suffix for ASX stocks)"},
                "shares": {"type": "number"},
                "price": {"type": "number", "description": "Price in local currency; 0 to fetch live"},
            },
            "required": ["symbol", "shares"],
        },
    },
    {
        "name": "remove_holding",
        "description": "Remove a holding from the portfolio",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
]


def _portfolio_summary_text() -> str:
    if not portfolio.holdings:
        return "Portfolio is empty."
    rate = portfolio.aud_usd_rate or 1.0
    lines = []
    for sym, h in sorted(portfolio.holdings.items()):
        val_aud = _value_aud(h)
        target = portfolio.targets.get(sym, 0.0)
        actual = _actual_pct_aud(sym)
        currency_label = "AUD" if h.exchange == "ASX" else "USD"
        lines.append(
            f"  {sym} ({h.exchange}): {h.shares:g} shares @ {h.price:,.2f} {currency_label}"
            f" = A${val_aud:,.2f} | actual {actual:.1f}%, target {target:.1f}%, diff {target - actual:+.1f}%"
        )
    total_aud = _total_aud()
    return (
        "\n".join(lines)
        + f"\n\nTotal (AUD): A${total_aud:,.2f}"
        + f"\nAUD/USD rate: {rate:.4f}"
        + f"\nTargets sum: {portfolio.targets_total():.1f}%"
    )


def _resolve_symbol(sym: str) -> str:
    """Fuzzy-match a symbol to the actual key in portfolio holdings.

    Handles the common case where Claude omits or adds the '.AX' suffix.
    """
    sym = sym.upper()
    if sym in portfolio.holdings:
        return sym
    # Try appending .AX (e.g. "NDQ" → "NDQ.AX")
    if sym + ".AX" in portfolio.holdings:
        return sym + ".AX"
    # Try stripping .AX (e.g. "VONV.AX" → "VONV")
    if sym.endswith(".AX") and sym[:-3] in portfolio.holdings:
        return sym[:-3]
    return sym  # return as-is; caller handles the miss


def _run_agent_tool(name: str, inputs: dict, actions: list) -> str:
    if name == "get_portfolio":
        return _portfolio_summary_text()

    if name == "update_shares":
        sym = _resolve_symbol(inputs["symbol"])
        shares = float(inputs["shares"])
        if portfolio.update_shares(sym, shares):
            _save(portfolio)
            actions.append(f"Updated {sym} to {shares:g} shares")
            return f"Updated {sym} to {shares:g} shares"
        return f"Error: {sym} not found in portfolio. Known symbols: {', '.join(sorted(portfolio.holdings))}"

    if name == "set_target":
        sym = _resolve_symbol(inputs["symbol"])
        if sym not in portfolio.holdings:
            return f"Error: {sym} not found in portfolio. Known symbols: {', '.join(sorted(portfolio.holdings))}"
        pct = float(inputs["target_pct"])
        portfolio.set_target(sym, pct)
        _save(portfolio)
        actions.append(f"Set {sym} target to {pct:.1f}%")
        return f"Set {sym} target to {pct:.1f}%"

    if name == "add_holding":
        sym = inputs["symbol"].upper()
        shares = float(inputs["shares"])
        price = float(inputs.get("price", 0))
        if price == 0:
            try:
                from portfolio_tracker.prices import fetch_prices
                exchange = _detect_exchange(sym)
                dummy = {sym: Holding(symbol=sym, shares=1, price=0, exchange=exchange)}
                price = fetch_prices(dummy).get(sym) or 0
            except Exception as e:
                return f"Error fetching price for {sym}: {e}"
        if price > 0:
            portfolio.add_holding(sym, shares, price)
            _save(portfolio)
            actions.append(f"Added {shares:g} × {sym} @ {price:,.2f}")
            return f"Added {shares:g} shares of {sym} at {price:,.2f}"
        return f"Error: no valid price for {sym}"

    if name == "remove_holding":
        sym = _resolve_symbol(inputs["symbol"])
        if portfolio.remove_holding(sym):
            portfolio.remove_target(sym)
            _save(portfolio)
            actions.append(f"Removed {sym}")
            return f"Removed {sym}"
        return f"Error: {sym} not found"

    return f"Unknown tool: {name}"


def _agent_stream(chat_history: list, actions: list):
    """Generator that streams text chunks; executes tool calls silently."""
    try:
        import anthropic as ant
    except ImportError:
        yield "Install the `anthropic` package: `pip install anthropic`"
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        yield "Set the `ANTHROPIC_API_KEY` environment variable to enable Claude."
        return

    client = ant.Anthropic(api_key=api_key)

    thesis_section = ""
    if st.session_state.investment_thesis:
        thesis_section = (
            "\n\nThe investor has provided their investment thesis below. "
            "Use it to frame all advice, flag alignment or conflicts, and personalise feedback.\n\n"
            "--- INVESTMENT THESIS ---\n"
            + st.session_state.investment_thesis[:10000]
            + "\n--- END THESIS ---"
        )

    system_text = (
        "You are a portfolio management assistant for an Australian investor managing an ETF portfolio.\n\n"
        "Current portfolio (all values in AUD):\n"
        + _portfolio_summary_text()
        + thesis_section
        + "\n\nUse tools to read or update the portfolio when asked. "
        "ASX stocks use .AX suffix; US stock prices are in USD, ASX in AUD. "
        "Targets should sum to 100%."
    )
    # Cache the system prompt — avoids reprocessing the full portfolio context
    # on every streaming request, cutting time-to-first-token significantly.
    system = [{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}]

    api_messages = [{"role": m["role"], "content": m["content"]} for m in chat_history]

    for _ in range(8):
        in_tool_block = False

        try:
            with client.messages.stream(
                model="claude-haiku-4-5",
                max_tokens=1024,
                system=system,
                tools=_AGENT_TOOLS,
                messages=api_messages,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_start":
                        in_tool_block = (event.content_block.type == "tool_use")
                    elif event.type == "content_block_delta":
                        if not in_tool_block and event.delta.type == "text_delta":
                            yield event.delta.text

                final_msg = stream.get_final_message()
        except Exception as e:
            yield f"\n\n_Error: {e}_"
            return

        if final_msg.stop_reason == "end_turn":
            return

        if final_msg.stop_reason == "tool_use":
            api_messages.append({"role": "assistant", "content": final_msg.content})
            tool_results = []
            for block in final_msg.content:
                if block.type == "tool_use":
                    result = _run_agent_tool(block.name, block.input, actions)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            api_messages.append({"role": "user", "content": tool_results})
        else:
            return

# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Add / Update Holding")
    with st.form("add_holding_form", clear_on_submit=True):
        new_sym = st.text_input("Symbol", placeholder="e.g. NDQ.AX or VONV").strip().upper()
        new_shares = st.number_input("Shares", min_value=0.0, step=1.0, format="%.4g")
        new_price = st.number_input("Price (0 = fetch live)", min_value=0.0, step=0.01, format="%.4f")
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
                    price = fetch_prices(dummy).get(new_sym)
                    if price is None:
                        st.error("Could not fetch price. Enter manually.")
                except Exception as e:
                    st.error(f"Price fetch error: {e}")
                    price = None
            if price and price > 0:
                portfolio.add_holding(new_sym, new_shares, price)
                _save(portfolio)
                st.success(f"Added {new_shares:g} × {new_sym} @ {price:,.4f}")
                st.rerun()

    st.divider()

    if st.button("↻ Refresh All Prices", use_container_width=True):
        _refresh_prices()

    st.divider()

    st.header("Investment Thesis")
    st.caption("Upload your thesis to personalise Claude's advice.")
    thesis_file = st.file_uploader(
        "thesis",
        type=["pdf", "docx"],
        label_visibility="collapsed",
        help="PDF or Word document",
    )
    if thesis_file:
        text = _extract_thesis_text(thesis_file)
        if text.strip():
            st.session_state.investment_thesis = text
            st.success(f"Loaded ({len(text):,} chars)")
        else:
            st.warning("Could not extract text from file.")

    if st.session_state.investment_thesis:
        st.caption(f"✅ Thesis active — {len(st.session_state.investment_thesis):,} chars")
        if st.button("Clear thesis", use_container_width=True):
            st.session_state.investment_thesis = ""
            st.rerun()

# ── Main layout: portfolio (left) + chat (right) ───────────────────────────────

st.title("📈 Portfolio Tracker")

if not portfolio.holdings:
    st.info("No holdings yet. Use the sidebar to add your first stock.")
    st.stop()

left_col, chat_col = st.columns([3, 2], gap="large")

# ══════════════════════════════════════════════════════════════════════════════
# LEFT: metrics, holdings table, charts
# ══════════════════════════════════════════════════════════════════════════════

with left_col:

    # ── Summary metrics ────────────────────────────────────────────────────────
    rate = portfolio.aud_usd_rate or 1.0
    totals = portfolio.total_value_by_exchange()
    asx_aud = totals.get("ASX", 0.0)
    us_usd = totals.get("US", 0.0)
    us_aud = us_usd / rate
    total_aud = asx_aud + us_aud

    m1, m2, m3 = st.columns(3)
    m1.metric("Combined (AUD)", f"A${total_aud:,.2f}")
    m2.metric("ASX (AUD)", f"A${asx_aud:,.2f}")
    m3.metric(
        "US (AUD equiv.)",
        f"A${us_aud:,.2f}",
        help=f"${us_usd:,.2f} USD converted @ {rate:.4f}",
    )

    st.divider()

    # ── Holdings table ─────────────────────────────────────────────────────────
    st.subheader("Holdings")

    exchanges = sorted(totals.keys())
    COL_W = [1.5, 0.85, 0.85, 1.1, 0.7, 0.7, 0.32, 0.32]

    for exchange in exchanges:
        ex_holdings = {s: h for s, h in portfolio.holdings.items() if h.exchange == exchange}
        ex_aud = sum(_value_aud(h) for h in ex_holdings.values())
        st.markdown(f"**{exchange} — A${ex_aud:,.2f}**")

        # Header row
        hdr = st.columns(COL_W)
        for col, label in zip(
            hdr, ["Symbol", "Shares", "Price", "Value (AUD)", "Actual %", "Target %", "", ""]
        ):
            col.markdown(f"<small><b>{label}</b></small>", unsafe_allow_html=True)

        for symbol in sorted(ex_holdings):
            h = ex_holdings[symbol]
            val_aud = _value_aud(h)
            actual = _actual_pct_aud(symbol)
            current_target = float(portfolio.targets.get(symbol, 0.0))

            row = st.columns(COL_W)
            row[0].markdown(f"**{symbol}**")

            new_shares = row[1].number_input(
                "shares",
                value=float(h.shares),
                min_value=0.0,
                step=1.0,
                key=f"sh_{symbol}",
                label_visibility="collapsed",
                format="%.4g",
            )
            row[2].markdown(
                f"<small>{h.price:,.2f}<br><span style='color:#888'>{h.currency}</span></small>",
                unsafe_allow_html=True,
            )
            row[3].markdown(f"A${val_aud:,.0f}")
            row[4].markdown(f"{actual:.1f}%")

            new_target = row[5].number_input(
                "target",
                value=current_target,
                min_value=0.0,
                max_value=100.0,
                step=1.0,
                key=f"tgt_{symbol}",
                label_visibility="collapsed",
                format="%.1f",
            )

            if row[6].button("↻", key=f"ref_{symbol}", help=f"Refresh {symbol} price"):
                _refresh_prices(symbol)

            if row[7].button("🗑", key=f"del_{symbol}", help=f"Delete {symbol}"):
                st.session_state[f"confirm_del_{symbol}"] = True

            # Apply inline edits
            if abs(new_shares - h.shares) > 1e-9:
                portfolio.update_shares(symbol, new_shares)
                _save(portfolio)
            if abs(new_target - current_target) > 1e-9:
                portfolio.set_target(symbol, new_target)
                _save(portfolio)

            # Delete confirmation inline
            if st.session_state.get(f"confirm_del_{symbol}"):
                st.warning(f"⚠️ Delete **{symbol}**? This cannot be undone.")
                c1, c2, _ = st.columns([1, 1, 4])
                if c1.button("Yes, delete", key=f"yes_{symbol}", type="primary"):
                    portfolio.remove_holding(symbol)
                    portfolio.remove_target(symbol)
                    _save(portfolio)
                    st.session_state.pop(f"confirm_del_{symbol}", None)
                    st.rerun()
                if c2.button("Cancel", key=f"no_{symbol}"):
                    st.session_state.pop(f"confirm_del_{symbol}", None)
                    st.rerun()

        st.markdown("")

    st.divider()

    # ── Charts ─────────────────────────────────────────────────────────────────
    tab1, tab2 = st.tabs(["Allocation (AUD)", "Actual vs Target"])

    with tab1:
        labels = sorted(portfolio.holdings.keys())
        values = [_value_aud(portfolio.holdings[s]) for s in labels]
        fig = px.pie(
            names=labels,
            values=values,
            title="Portfolio Allocation (AUD)",
            hole=0.4,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(margin=dict(t=40, b=0, l=0, r=0), showlegend=False, height=300)
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        all_symbols = sorted(
            set(list(portfolio.holdings.keys()) + list(portfolio.targets.keys()))
        )
        actual_vals = [_actual_pct_aud(s) for s in all_symbols]
        target_vals = [portfolio.targets.get(s, 0.0) for s in all_symbols]

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(name="Actual %", x=all_symbols, y=actual_vals, marker_color="#636efa"))
        fig2.add_trace(go.Bar(name="Target %", x=all_symbols, y=target_vals, marker_color="#ef553b"))
        fig2.update_layout(
            barmode="group",
            yaxis_title="Portfolio %",
            margin=dict(t=10, b=0, l=0, r=0),
            legend=dict(orientation="h", y=1.1),
            height=280,
        )
        st.plotly_chart(fig2, use_container_width=True)

        if portfolio.targets:
            st.markdown("**Rebalance suggestions**")
            rebal_rows = []
            for sym in all_symbols:
                diff_pct = portfolio.targets.get(sym, 0.0) - _actual_pct_aud(sym)
                diff_val = (diff_pct / 100) * total_aud
                if abs(diff_val) > 0.01:
                    rebal_rows.append({
                        "Symbol": sym,
                        "Action": "Buy" if diff_val > 0 else "Sell",
                        "Amount (AUD)": f"A${abs(diff_val):,.2f}",
                        "Diff %": f"{diff_pct:+.1f}%",
                    })
            if rebal_rows:
                st.dataframe(pd.DataFrame(rebal_rows), hide_index=True, use_container_width=True)
            else:
                st.success("Portfolio is on target!")

# ══════════════════════════════════════════════════════════════════════════════
# RIGHT: Claude chat panel
# ══════════════════════════════════════════════════════════════════════════════

with chat_col:
    header_cols = st.columns([4, 1])
    header_cols[0].subheader("🤖 Claude Assistant")
    if header_cols[1].button("Clear", key="clear_chat", help="Clear conversation"):
        st.session_state.chat_history = []
        st.rerun()

    if st.session_state.investment_thesis:
        st.caption("📄 Investment thesis active — Claude will reference it in responses.")
    else:
        st.caption("Tip: upload your investment thesis in the sidebar to personalise advice.")

    # Scrollable message history
    messages_area = st.container(height=580, border=True)
    with messages_area:
        if not st.session_state.chat_history:
            st.markdown(
                "<div style='color:#888;font-size:0.88em;padding:6px'>"
                "Ask me anything: analyse allocation gaps, update holdings, "
                "compare against your thesis, or suggest rebalancing trades."
                "</div>",
                unsafe_allow_html=True,
            )
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    if prompt := st.chat_input("e.g. 'Am I overweight in NDQ?' or 'Add 10 VHY.AX'"):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        actions: list[str] = []

        with messages_area:
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                placeholder = st.empty()
                full_text = ""
                for chunk in _agent_stream(st.session_state.chat_history, actions):
                    full_text += chunk
                    placeholder.markdown(full_text + "▌")
                placeholder.markdown(full_text)
                reply = full_text

        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        # Reload portfolio from disk so the next turn's system prompt is current.
        st.session_state.portfolio = _load()
        # Clear widget session-state for all editable cells so their values
        # reinitialise from the freshly loaded portfolio on the next render.
        # Without this, Streamlit's inline-edit detection sees the stale widget
        # value as a "user change" and immediately reverts the agent's update.
        for k in list(st.session_state.keys()):
            if k.startswith("tgt_") or k.startswith("sh_"):
                del st.session_state[k]
        st.rerun()
