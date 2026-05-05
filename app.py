import streamlit as st
import json
import os
import requests
import yfinance as yf
from datetime import datetime
from agent import analyze_portfolio
from podcast_agent import analyze_latest_podcast

PORTFOLIO_FILE = os.environ.get("PORTFOLIO_FILE", "portfolio.json")
HISTORY_FILE   = os.environ.get("HISTORY_FILE",   "history.json")
PODCAST_WATCHLIST_FILE = os.environ.get("PODCAST_WATCHLIST_FILE", "doppelgaenger_watchlist.json")
MAX_HISTORY    = 10

CLAUDE_INPUT_PRICE_PER_M  = 3.00   # USD per million tokens (claude-sonnet-4-6)
CLAUDE_OUTPUT_PRICE_PER_M = 15.00  # USD per million tokens (claude-sonnet-4-6)

# ─── Data helpers ─────────────────────────────────────────────────────────────

def _load_json_file(path: str, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read().strip()
        if content:
            return json.loads(content)
    return default


def fetch_name_for_ticker(ticker: str) -> str:
    """Fetch the short name from yfinance for a given ticker (used during migration)."""
    try:
        info = yf.Ticker(ticker).info
        return info.get("shortName", ticker)
    except Exception:
        return ticker


def load_portfolio():
    data = _load_json_file(PORTFOLIO_FILE, {"depot": [], "watchlist": []})
    # --- Migration: old format was plain string lists, new format is list of dicts ---
    migrated = False
    for key in ("depot", "watchlist"):
        if data.get(key) and isinstance(data[key][0], str):
            data[key] = [{"ticker": t, "name": fetch_name_for_ticker(t)} for t in data[key]]
            migrated = True
    if migrated:
        save_portfolio(data)
    return data


def save_portfolio(data):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_history() -> list:
    return _load_json_file(HISTORY_FILE, [])


def save_history(entry: dict):
    history = load_history()
    history.insert(0, entry)          # newest first
    history = history[:MAX_HISTORY]   # keep max 10
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4, ensure_ascii=False)


def clear_history():
    with open(HISTORY_FILE, "w") as f:
        json.dump([], f)

def load_podcast_watchlist() -> list:
    return _load_json_file(PODCAST_WATCHLIST_FILE, [])

def save_podcast_watchlist(data: list):
    with open(PODCAST_WATCHLIST_FILE, "w") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ─── Search widget ────────────────────────────────────────────────────────────

def search_yahoo_finance(query: str):
    """Query the Yahoo Finance search endpoint and return a list of equity/ETF quotes."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = (
            f"https://query2.finance.yahoo.com/v1/finance/search"
            f"?q={requests.utils.quote(query)}&lang=en-US&region=US&quotesCount=10&newsCount=0"
        )
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            quotes = r.json().get("quotes", [])
            return [q for q in quotes if q.get("quoteType") in ("EQUITY", "ETF", "MUTUALFUND", "INDEX")]
    except Exception as e:
        st.error(f"Suchfehler: {e}")
    return []


def render_search_and_add(list_key: str, uid: str):
    """Reusable two-step search widget: Search → Select from dropdown → Add."""
    with st.form(key=f"form_search_{uid}", enter_to_submit=True):
        search_term = st.text_input(
            "🔍 Name oder Ticker suchen (z.B. 'Apple', 'Mercedes', 'NVDA')",
            key=f"in_{uid}",
        )
        submitted = st.form_submit_button("Suchen")

    if submitted:
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

        if st.button("Hinzufügen ✚", key=f"btn_add_{uid}"):
            ticker = selected.get("symbol")
            name = selected.get("shortname") or selected.get("longname") or ticker
            if any(entry["ticker"] == ticker for entry in portfolio_data[list_key]):
                st.warning(f"{ticker} ist bereits in der Liste.")
            else:
                portfolio_data[list_key].append({"ticker": ticker, "name": name})
                save_portfolio(portfolio_data)
                st.session_state.pop(f"res_{uid}", None)
                st.rerun()


def render_entry_list(list_key: str, uid_prefix: str):
    """Render list entries with move icon, ❌ delete icon and undo mechanism."""
    pending_key = f"pending_delete_{list_key}"
    is_depot = list_key == "depot"
    target_key = "watchlist" if is_depot else "depot"
    move_icon = "➡️" if is_depot else "⬅️"
    move_help = "In Watchlist verschieben" if is_depot else "Ins Depot verschieben"
    target_name = "Watchlist" if is_depot else "Depot"

    for entry in list(portfolio_data[list_key]):
        ticker = entry["ticker"]
        name   = entry.get("name", ticker)
        is_pending = st.session_state.get(pending_key) == ticker

        col_name, col_move, col_btn = st.columns([9, 1, 1])

        with col_name:
            if is_pending:
                st.markdown(f"<span style='color: #888; text-decoration: line-through;'>**{name}** ({ticker})</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"**{name}** ({ticker})")

        with col_move:
            if not is_pending:
                if st.button(move_icon, key=f"move_{uid_prefix}_{ticker}", help=move_help):
                    # Check if already in target
                    if any(e["ticker"] == ticker for e in portfolio_data[target_key]):
                        st.toast(f"⚠️ {name} ({ticker}) ist bereits in {target_name}!", icon="⚠️")
                    else:
                        # Flush any previously pending delete first
                        prev = st.session_state.get(pending_key)
                        if prev and prev != ticker:
                            portfolio_data[list_key] = [
                                e for e in portfolio_data[list_key] if e["ticker"] != prev
                            ]
                        
                        # Execute move
                        portfolio_data[target_key].append(entry)
                        portfolio_data[list_key] = [
                            e for e in portfolio_data[list_key] if e["ticker"] != ticker
                        ]
                        save_portfolio(portfolio_data)
                        st.toast(f"✅ {name} ({ticker}) nach {target_name} verschoben!")
                        st.session_state[pending_key] = None
                        st.rerun()

        with col_btn:
            if is_pending:
                if st.button("↩", key=f"undo_{uid_prefix}_{ticker}", help="Rückgängig"):
                    st.session_state[pending_key] = None
                    st.rerun()
            else:
                if st.button("❌", key=f"del_{uid_prefix}_{ticker}", help="Entfernen"):
                    # Flush any previously pending delete first
                    prev = st.session_state.get(pending_key)
                    if prev and prev != ticker:
                        portfolio_data[list_key] = [
                            e for e in portfolio_data[list_key] if e["ticker"] != prev
                        ]
                        save_portfolio(portfolio_data)
                    st.session_state[pending_key] = ticker
                    st.rerun()

    # If there's a pending delete, a non-undo action finalises it.
    # We handle this at the top of each render cycle implicitly via session state.


# ─── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="K-Invest | Swing Trading Agent", page_icon="📈", layout="wide")
st.title("📈 K-Invest: Swing Trading Assistant")
st.markdown(
    "Dieser KI-Agent nutzt Anthropic Claude, um dein Portfolio und Watchlist systematisch "
    "nach fundamentalem Momentum für kurzfristiges Swing-Trading zu analysieren."
)

# Sidebar: API Key
api_key = st.sidebar.text_input(
    "Anthropic API Key", type="password", value=os.environ.get("ANTHROPIC_API_KEY", "")
)
youtube_api_key = st.sidebar.text_input(
    "YouTube API Key (Podcast)", type="password", value=os.environ.get("YOUTUBE_API_KEY", "")
)

if not api_key:
    st.sidebar.warning(
        "Bitte gib einen Anthropic API Key ein (oder setze ANTHROPIC_API_KEY in den Umgebungsvariablen)."
    )
if not youtube_api_key:
    st.sidebar.info(
        "Ein YouTube API Key wird für den Doppelgänger-Podcast Scanner benötigt."
    )

st.sidebar.caption(f"Version: `{os.environ.get('APP_VERSION', 'dev')}`")

portfolio_data = load_portfolio()

# ─── Tabs ─────────────────────────────────────────────────────────────────────

tab_analyse, tab_depot, tab_watchlist, tab_podcast = st.tabs(["🚀 Analyse", "💼 Depot", "🔭 Watchlist", "🎧 Podcast"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB: ANALYSE
# ══════════════════════════════════════════════════════════════════════════════
with tab_analyse:

    # ── Toggle chips: what to analyse ─────────────────────────────────────────
    n_depot = len(portfolio_data["depot"])
    n_watch = len(portfolio_data["watchlist"])

    if "analyse_depot"  not in st.session_state: st.session_state.analyse_depot  = True
    if "analyse_watch"  not in st.session_state: st.session_state.analyse_watch  = True

    st.markdown("#### Was soll analysiert werden?")
    chip_col1, chip_col2, spacer = st.columns([2, 2, 6])

    with chip_col1:
        depot_active = st.session_state.analyse_depot
        label_depot  = f"{'✅' if depot_active else '⬜'} Depot ({n_depot})"
        if st.button(label_depot, key="chip_depot", use_container_width=True):
            st.session_state.analyse_depot = not depot_active
            st.rerun()

    with chip_col2:
        watch_active = st.session_state.analyse_watch
        label_watch  = f"{'✅' if watch_active else '⬜'} Watchlist ({n_watch})"
        if st.button(label_watch, key="chip_watch", use_container_width=True):
            st.session_state.analyse_watch = not watch_active
            st.rerun()

    st.divider()

    # ── Start button ──────────────────────────────────────────────────────────
    if st.button(
        "🚀 Agenten-Analyse Starten",
        disabled=not api_key,
        use_container_width=True,
        type="primary",
    ):
        depot_tickers = [e["ticker"] for e in portfolio_data["depot"]]  if st.session_state.analyse_depot  else []
        watch_tickers = [e["ticker"] for e in portfolio_data["watchlist"]] if st.session_state.analyse_watch else []

        if not depot_tickers and not watch_tickers:
            st.error("Bitte wähle mindestens eine Gruppe aus und stelle sicher, dass sie Einträge enthält.")
        else:
            target_label = (
                "Depot + Watchlist" if depot_tickers and watch_tickers
                else ("Nur Depot" if depot_tickers else "Nur Watchlist")
            )
            with st.spinner("Agent durchsucht das Web und analysiert Kurse... (Dies kann ca. 10–30 Sekunden dauern)"):
                result = analyze_portfolio(depot_tickers, watch_tickers, api_key)

            entry = {
                "timestamp":     datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "target":        target_label,
                "depot_tickers": depot_tickers,
                "watch_tickers": watch_tickers,
                "result_text":   result.get("text", str(result)) if isinstance(result, dict) else str(result),
                "input_tokens":  result.get("input_tokens",  0) if isinstance(result, dict) else 0,
                "output_tokens": result.get("output_tokens", 0) if isinstance(result, dict) else 0,
            }
            save_history(entry)
            st.rerun()

    # ── History ───────────────────────────────────────────────────────────────
    history = load_history()

    if history:
        h_col1, h_col2 = st.columns([8, 2])
        with h_col1:
            st.subheader("📊 Analyse-Historie")
        with h_col2:
            if st.button("🗑️ Alle löschen", key="clear_history"):
                clear_history()
                st.rerun()

        for i, entry in enumerate(history):
            ts      = entry.get("timestamp", "")
            target  = entry.get("target", "")
            in_tok  = entry.get("input_tokens",  0)
            out_tok = entry.get("output_tokens", 0)

            # Format timestamp nicely
            try:
                dt_label = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").strftime("%d.%m.%Y %H:%M")
            except Exception:
                dt_label = ts

            label = f"🔎 {dt_label} — {target}"
            # Newest entry (i==0) expanded, rest collapsed
            with st.expander(label, expanded=(i == 0)):
                st.markdown(entry.get("result_text", ""))
                if in_tok > 0 or out_tok > 0:
                    cost_usd = (in_tok / 1_000_000) * CLAUDE_INPUT_PRICE_PER_M + (out_tok / 1_000_000) * CLAUDE_OUTPUT_PRICE_PER_M
                    st.caption(
                        f"🪙 **Token-Verbrauch:** {in_tok:,} Input | {out_tok:,} Output | "
                        f"**Geschätzte Kosten:** ${cost_usd:.4f}"
                    )

# ══════════════════════════════════════════════════════════════════════════════
# TAB: DEPOT
# ══════════════════════════════════════════════════════════════════════════════
with tab_depot:
    st.subheader("💼 Mein Depot")

    # Flush any pending depot delete when the user is actively in this tab
    pending_depot = st.session_state.get("pending_delete_depot")
    if pending_depot:
        portfolio_data["depot"] = [
            e for e in portfolio_data["depot"] if e["ticker"] != pending_depot
        ]
        save_portfolio(portfolio_data)
        st.session_state["pending_delete_depot"] = None

    render_search_and_add("depot", "depot")
    st.markdown("---")

    if portfolio_data["depot"]:
        render_entry_list("depot", "d")
    else:
        st.info("Noch keine Einträge im Depot. Nutze die Suche oben um Aktien hinzuzufügen.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB: WATCHLIST
# ══════════════════════════════════════════════════════════════════════════════
with tab_watchlist:
    st.subheader("🔭 Watchlist")

    # Flush any pending watchlist delete when the user is actively in this tab
    pending_watch = st.session_state.get("pending_delete_watchlist")
    if pending_watch:
        portfolio_data["watchlist"] = [
            e for e in portfolio_data["watchlist"] if e["ticker"] != pending_watch
        ]
        save_portfolio(portfolio_data)
        st.session_state["pending_delete_watchlist"] = None

    render_search_and_add("watchlist", "watch")
    st.markdown("---")

    if portfolio_data["watchlist"]:
        render_entry_list("watchlist", "w")
    else:
        st.info("Noch keine Einträge in der Watchlist. Nutze die Suche oben um Aktien hinzuzufügen.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB: PODCAST
# ══════════════════════════════════════════════════════════════════════════════
with tab_podcast:
    st.subheader("🎧 Doppelgänger Tech Talk Scanner")
    st.markdown("Analysiert die neueste Folge von @doppelgaengerio auf Swing-Trading-Chancen.")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("🚀 Neueste Folge analysieren", type="primary", use_container_width=True, disabled=not (api_key and youtube_api_key)):
            podcast_wl = load_podcast_watchlist()
            with st.spinner("Lade Video-Metadaten, Transkript und analysiere mit Claude... (Das kann ca. 30-60 Sekunden dauern)"):
                result = analyze_latest_podcast(youtube_api_key, api_key, podcast_wl)
                
            if "error" in result:
                st.error(result["error"])
            else:
                st.success(f"Erfolgreich analysiert: {result['title']}")
                # Save new watchlist if returned
                if result.get("new_watchlist"):
                    save_podcast_watchlist(result["new_watchlist"])
                
                # Show results temporarily (could also save to a history if we want)
                st.session_state["last_podcast_result"] = result["text"]
                st.rerun()
                
    if st.session_state.get("last_podcast_result"):
        st.markdown("### Claude Analyse")
        st.markdown(st.session_state["last_podcast_result"])
        
    st.divider()
    st.markdown("### 📋 Laufende Doppelgänger-Watchlist")
    podcast_wl = load_podcast_watchlist()
    if podcast_wl:
        st.dataframe(podcast_wl, use_container_width=True)
    else:
        st.info("Die Watchlist ist aktuell leer. Führe eine Analyse aus, um sie zu füllen.")

