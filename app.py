import streamlit as st
import json
import os
from agent import analyze_portfolio

PORTFOLIO_FILE = "portfolio.json"

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r") as f:
            return json.load(f)
    return {"depot": [], "watchlist": []}

def save_portfolio(data):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=4)

st.set_page_config(page_title="K-Invest | Swing Trading Agent", page_icon="📈", layout="wide")

st.title("📈 K-Invest: Swing Trading Assistant")
st.markdown("Dieser KI-Agent nutzt Anthropic Claude, um dein Portfolio und Watchlist systematisch nach fundamentalem Momentum für kurzfristiges Swing-Trading zu analysieren.")

# API Key config
api_key = st.sidebar.text_input("Anthropic API Key", type="password", value=os.environ.get("ANTHROPIC_API_KEY", ""))
if not api_key:
    st.sidebar.warning("Bitte gib einen Anthropic API Key ein (oder setze ANTHROPIC_API_KEY in den Umgebungsvariablen).")

portfolio_data = load_portfolio()

col1, col2 = st.columns(2)

with col1:
    st.subheader("💼 Mein Depot")
    depot_input = st.text_input("Neuer Ticker für Depot (z.B. AAPL)", key="depot_in")
    if st.button("Ins Depot aufnehmen"):
        if depot_input and depot_input.upper() not in portfolio_data['depot']:
            portfolio_data['depot'].append(depot_input.upper())
            save_portfolio(portfolio_data)
            st.rerun()
            
    for item in portfolio_data['depot']:
        if st.checkbox(f"{item} entfernen", key=f"d_del_{item}"):
            portfolio_data['depot'].remove(item)
            save_portfolio(portfolio_data)
            st.rerun()

with col2:
    st.subheader("🔭 Watchlist")
    watch_input = st.text_input("Neuer Ticker für Watchlist (z.B. TSLA)", key="watch_in")
    if st.button("Auf Watchlist setzen"):
        if watch_input and watch_input.upper() not in portfolio_data['watchlist']:
            portfolio_data['watchlist'].append(watch_input.upper())
            save_portfolio(portfolio_data)
            st.rerun()

    for item in portfolio_data['watchlist']:
        if st.checkbox(f"{item} entfernen", key=f"w_del_{item}"):
            portfolio_data['watchlist'].remove(item)
            save_portfolio(portfolio_data)
            st.rerun()

if "analysis_history" not in st.session_state:
    st.session_state.analysis_history = []

st.divider()

target_selection = st.radio("Was möchtest du analysieren?", ["Nur Depot", "Nur Watchlist", "Beides"], horizontal=True)

if st.button("🚀 Agenten-Analyse Starten", disabled=not api_key, use_container_width=True, type="primary"):
    depot_list = portfolio_data['depot'] if target_selection in ["Nur Depot", "Beides"] else []
    watch_list = portfolio_data['watchlist'] if target_selection in ["Nur Watchlist", "Beides"] else []

    if not depot_list and not watch_list:
        st.error(f"Für die Auswahl '{target_selection}' sind keine Aktien hinterlegt!")
    else:
        with st.spinner("Agent durchsucht das Web und analysiert Kurse... (Dies kann ca 10-30 Sekunden dauern)"):
            result = analyze_portfolio(depot_list, watch_list, api_key)
            st.session_state.analysis_history.append({"target": target_selection, "result": result})

if st.session_state.analysis_history:
    st.subheader("📊 Agenten-Reports Historie")
    if st.button("Historie leeren"):
        st.session_state.analysis_history = []
        st.rerun()
    
    for i, entry in enumerate(reversed(st.session_state.analysis_history)):
        st.markdown(f"#### 🔎 Analyse-Lauf: {entry['target']}")
        
        if isinstance(entry['result'], dict):
            res_text = entry['result'].get('text', '')
            in_tok = entry['result'].get('input_tokens', 0)
            out_tok = entry['result'].get('output_tokens', 0)
        else:
            res_text = str(entry['result'])
            in_tok = 0
            out_tok = 0
            
        st.markdown(res_text)
        
        if in_tok > 0 or out_tok > 0:
            cost_usd = (in_tok / 1_000_000) * 3.00 + (out_tok / 1_000_000) * 15.00
            st.caption(f"🪙 **Token-Verbrauch:** {in_tok:,} Input | {out_tok:,} Output | **Geschätzte Kosten:** ${cost_usd:.4f}")

        if i < len(st.session_state.analysis_history) - 1:
            st.divider()
