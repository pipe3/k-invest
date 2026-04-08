import streamlit as st
import json
import os
import requests
import yfinance as yf
from agent import analyze_portfolio

PORTFOLIO_FILE = "portfolio.json"

def fetch_name_for_ticker(ticker: str) -> str:
    """Fetch the short name from yfinance for a given ticker (used during migration)."""
    try:
        info = yf.Ticker(ticker).info
        return info.get("shortName", ticker)
    except Exception:
        return ticker

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r") as f:
            data = json.load(f)
        # --- Migration: old format was plain string lists, new format is list of dicts ---
        migrated = False
        for key in ("depot", "watchlist"):
            if data.get(key) and isinstance(data[key][0], str):
                data[key] = [{"ticker": t, "name": fetch_name_for_ticker(t)} for t in data[key]]
                migrated = True
        if migrated:
            save_portfolio(data)
        return data
    return {"depot": [], "watchlist": []}

def save_portfolio(data):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=4)

def search_yahoo_finance(query: str):
    """Query the Yahoo Finance search endpoint and return a list of equity/ETF quotes."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={requests.utils.quote(query)}&lang=en-US&region=US&quotesCount=10&newsCount=0"
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            quotes = r.json().get("quotes", [])
            return [q for q in quotes if q.get("quoteType") in ("EQUITY", "ETF", "MUTUALFUND", "INDEX")]
    except Exception as e:
        st.error(f"Suchfehler: {e}")
    return []

# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="K-Invest | Swing Trading Agent", page_icon="📈", layout="wide")
st.title("📈 K-Invest: Swing Trading Assistant")
st.markdown("Dieser KI-Agent nutzt Anthropic Claude, um dein Portfolio und Watchlist systematisch nach fundamentalem Momentum für kurzfristiges Swing-Trading zu analysieren.")

# Sidebar: API Key
api_key = st.sidebar.text_input("Anthropic API Key", type="password", value=os.environ.get("ANTHROPIC_API_KEY", ""))
if not api_key:
    st.sidebar.warning("Bitte gib einen Anthropic API Key ein (oder setze ANTHROPIC_API_KEY in den Umgebungsvariablen).")

portfolio_data = load_portfolio()

def render_search_and_add(list_key: str, uid: str):
    """Reusable two-step search widget: Search → Select from dropdown → Add."""
    search_term = st.text_input("🔍 Name oder Ticker suchen (z.B. 'Apple', 'Mercedes', 'NVDA')", key=f"in_{uid}")

    if st.button("Suchen", key=f"btn_search_{uid}"):
        if search_term.strip():
            with st.spinner("Suche läuft..."):
                results = search_yahoo_finance(search_term.strip())
            if results:
                st.session_state[f"res_{uid}"] = results
            else:
                st.warning("Keine passenden Ergebnisse gefunden.")
                st.session_state.pop(f"res_{uid}", None)
        else:
            st.warning("Bitte einen Suchbegriff eingeben.")

    if st.session_state.get(f"res_{uid}"):
        options = st.session_state[f"res_{uid}"]

        def fmt(opt):
            name = opt.get("shortname") or opt.get("longname") or "Unbekannt"
            ticker = opt.get("symbol", "?")
            exch = opt.get("exchDisp", "")
            return f"{name} ({ticker}){' – ' + exch if exch else ''}"

        selected = st.selectbox("Ergebnis auswählen:", options, format_func=fmt, key=f"sel_{uid}")

        if st.button(f"Hinzufügen ✚", key=f"btn_add_{uid}"):
            ticker = selected.get("symbol")
            name = selected.get("shortname") or selected.get("longname") or ticker
            if any(entry["ticker"] == ticker for entry in portfolio_data[list_key]):
                st.warning(f"{ticker} ist bereits in der Liste.")
            else:
                portfolio_data[list_key].append({"ticker": ticker, "name": name})
                save_portfolio(portfolio_data)
                st.session_state.pop(f"res_{uid}", None)
                st.rerun()

col1, col2 = st.columns(2)

with col1:
    st.subheader("💼 Mein Depot")
    render_search_and_add("depot", "depot")
    st.markdown("---")
    for entry in list(portfolio_data["depot"]):
        ticker = entry["ticker"]
        name = entry.get("name", ticker)
        if st.checkbox(f"**{name}** ({ticker}) entfernen", key=f"d_del_{ticker}"):
            portfolio_data["depot"] = [e for e in portfolio_data["depot"] if e["ticker"] != ticker]
            save_portfolio(portfolio_data)
            st.rerun()

with col2:
    st.subheader("🔭 Watchlist")
    render_search_and_add("watchlist", "watch")
    st.markdown("---")
    for entry in list(portfolio_data["watchlist"]):
        ticker = entry["ticker"]
        name = entry.get("name", ticker)
        if st.checkbox(f"**{name}** ({ticker}) entfernen", key=f"w_del_{ticker}"):
            portfolio_data["watchlist"] = [e for e in portfolio_data["watchlist"] if e["ticker"] != ticker]
            save_portfolio(portfolio_data)
            st.rerun()

# ─── Analysis section ─────────────────────────────────────────────────────────
if "analysis_history" not in st.session_state:
    st.session_state.analysis_history = []

st.divider()

target_selection = st.radio("Was möchtest du analysieren?", ["Nur Depot", "Nur Watchlist", "Beides"], horizontal=True)

if st.button("🚀 Agenten-Analyse Starten", disabled=not api_key, use_container_width=True, type="primary"):
    depot_tickers  = [e["ticker"] for e in portfolio_data["depot"]]  if target_selection in ("Nur Depot",  "Beides") else []
    watch_tickers  = [e["ticker"] for e in portfolio_data["watchlist"]] if target_selection in ("Nur Watchlist", "Beides") else []

    if not depot_tickers and not watch_tickers:
        st.error(f"Für die Auswahl '{target_selection}' sind keine Aktien hinterlegt!")
    else:
        with st.spinner("Agent durchsucht das Web und analysiert Kurse... (Dies kann ca 10-30 Sekunden dauern)"):
            result = analyze_portfolio(depot_tickers, watch_tickers, api_key)
            st.session_state.analysis_history.append({"target": target_selection, "result": result})

if st.session_state.analysis_history:
    st.subheader("📊 Agenten-Reports Historie")
    if st.button("Historie leeren"):
        st.session_state.analysis_history = []
        st.rerun()

    for i, entry in enumerate(reversed(st.session_state.analysis_history)):
        st.markdown(f"#### 🔎 Analyse-Lauf: {entry['target']}")

        if isinstance(entry["result"], dict):
            res_text = entry["result"].get("text", "")
            in_tok   = entry["result"].get("input_tokens", 0)
            out_tok  = entry["result"].get("output_tokens", 0)
        else:
            res_text = str(entry["result"])
            in_tok = out_tok = 0

        st.markdown(res_text)

        if in_tok > 0 or out_tok > 0:
            cost_usd = (in_tok / 1_000_000) * 3.00 + (out_tok / 1_000_000) * 15.00
            st.caption(f"🪙 **Token-Verbrauch:** {in_tok:,} Input | {out_tok:,} Output | **Geschätzte Kosten:** ${cost_usd:.4f}")

        if i < len(st.session_state.analysis_history) - 1:
            st.divider()
