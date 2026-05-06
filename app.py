import streamlit as st
import json
import os
import time
import threading
import requests
import yfinance as yf
from datetime import datetime
from agent import analyze_portfolio
from podcast_agent import analyze_latest_podcast
from podcast_tools import get_recent_videos
from discovery_agent import discover_stocks

# ─── File paths ───────────────────────────────────────────────────────────────

PORTFOLIO_FILE         = os.environ.get("PORTFOLIO_FILE",         "portfolio.json")
HISTORY_FILE           = os.environ.get("HISTORY_FILE",           "history.json")
PODCAST_WATCHLIST_FILE = os.environ.get("PODCAST_WATCHLIST_FILE", "doppelgaenger_watchlist.json")
PODCAST_HISTORY_FILE   = os.environ.get("PODCAST_HISTORY_FILE",   "podcast_history.json")
PODCAST_JOB_FILE       = os.environ.get("PODCAST_JOB_FILE",       "podcast_job.json")
DEPOT_JOB_FILE         = os.environ.get("DEPOT_JOB_FILE",         "depot_job.json")
SETTINGS_FILE          = os.environ.get("SETTINGS_FILE",          "settings.json")
DISCOVERY_HISTORY_FILE = os.environ.get("DISCOVERY_HISTORY_FILE", "discovery_history.json")
DISCOVERY_JOB_FILE     = os.environ.get("DISCOVERY_JOB_FILE",     "discovery_job.json")

MAX_HISTORY = 10

CLAUDE_INPUT_PRICE_PER_M  = 3.00
CLAUDE_OUTPUT_PRICE_PER_M = 15.00

PREDEFINED_SECTORS = [
    ("ki",           "KI & Agentic AI",                    True),
    ("energie",      "Energie & Rechenzentrum-Versorger",   True),
    ("robotik",      "Robotik & Automatisierung",           True),
    ("halbleiter",   "Halbleiter & Chips",                  False),
    ("cybersecurity","Cybersecurity",                       False),
    ("biotech",      "Biotech & Medtech",                   False),
]

# ─── Generic helpers ──────────────────────────────────────────────────────────

def _load_json_file(path: str, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read().strip()
        if content:
            return json.loads(content)
    return default


def _save_json_file(path: str, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ─── Settings ─────────────────────────────────────────────────────────────────

def load_settings() -> dict:
    defaults = {"model": "claude-sonnet-4-6", "search_engine": "duckduckgo", "cached_models": ["claude-sonnet-4-6"]}
    saved = _load_json_file(SETTINGS_FILE, {})
    return {**defaults, **saved}


def save_settings(data: dict):
    _save_json_file(SETTINGS_FILE, data)


# ─── Portfolio ────────────────────────────────────────────────────────────────

def fetch_name_for_ticker(ticker: str) -> str:
    try:
        info = yf.Ticker(ticker).info
        return info.get("shortName", ticker)
    except Exception:
        return ticker


def load_portfolio():
    data = _load_json_file(PORTFOLIO_FILE, {"depot": [], "watchlist": []})
    migrated = False
    for key in ("depot", "watchlist"):
        if data.get(key) and isinstance(data[key][0], str):
            data[key] = [{"ticker": t, "name": fetch_name_for_ticker(t)} for t in data[key]]
            migrated = True
    if migrated:
        save_portfolio(data)
    return data


def save_portfolio(data):
    _save_json_file(PORTFOLIO_FILE, data)


# ─── Depot analysis history ───────────────────────────────────────────────────

def load_history() -> list:
    return _load_json_file(HISTORY_FILE, [])


def save_history(entry: dict):
    history = load_history()
    history.insert(0, entry)
    history = history[:MAX_HISTORY]
    _save_json_file(HISTORY_FILE, history)


def clear_history():
    _save_json_file(HISTORY_FILE, [])


# ─── Podcast helpers ──────────────────────────────────────────────────────────

def load_podcast_watchlist() -> list:
    return _load_json_file(PODCAST_WATCHLIST_FILE, [])


def save_podcast_watchlist(data: list):
    _save_json_file(PODCAST_WATCHLIST_FILE, data)


def load_podcast_history() -> list:
    return _load_json_file(PODCAST_HISTORY_FILE, [])


def save_podcast_history(entry: dict):
    history = load_podcast_history()
    history.insert(0, entry)
    history = history[:MAX_HISTORY]
    _save_json_file(PODCAST_HISTORY_FILE, history)


def clear_podcast_history():
    _save_json_file(PODCAST_HISTORY_FILE, [])


def load_podcast_job() -> dict:
    return _load_json_file(PODCAST_JOB_FILE, {"status": "idle"})


def save_podcast_job(data: dict):
    _save_json_file(PODCAST_JOB_FILE, data)


# ─── Depot job ────────────────────────────────────────────────────────────────

def load_depot_job() -> dict:
    return _load_json_file(DEPOT_JOB_FILE, {"status": "idle"})


def save_depot_job(data: dict):
    _save_json_file(DEPOT_JOB_FILE, data)


# ─── Discovery helpers ────────────────────────────────────────────────────────

def load_discovery_history() -> list:
    return _load_json_file(DISCOVERY_HISTORY_FILE, [])


def save_discovery_history(entry: dict):
    history = load_discovery_history()
    history.insert(0, entry)
    history = history[:MAX_HISTORY]
    _save_json_file(DISCOVERY_HISTORY_FILE, history)


def clear_discovery_history():
    _save_json_file(DISCOVERY_HISTORY_FILE, [])


def load_discovery_job() -> dict:
    return _load_json_file(DISCOVERY_JOB_FILE, {"status": "idle"})


def save_discovery_job(data: dict):
    _save_json_file(DISCOVERY_JOB_FILE, data)


# ─── Search config ────────────────────────────────────────────────────────────

def get_search_config(settings: dict) -> dict:
    return {
        "engine":         settings.get("search_engine", "duckduckgo"),
        "google_api_key": st.session_state.get("google_api_key", ""),
        "google_cx_id":   st.session_state.get("google_cx_id", ""),
        "tavily_api_key": st.session_state.get("tavily_api_key", ""),
    }


# ─── Background workers ───────────────────────────────────────────────────────

def _depot_analysis_worker(depot_tickers, watch_tickers, target_label,
                            api_key, model, search_config):
    try:
        result = analyze_portfolio(depot_tickers, watch_tickers, api_key, model, search_config)
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
        save_depot_job({"status": "done"})
    except Exception as e:
        save_depot_job({"status": "error", "error": str(e)})


def _podcast_analysis_worker(youtube_api_key, api_key, podcast_wl, model, search_config,
                              video_id=None, title=None):
    try:
        result = analyze_latest_podcast(youtube_api_key, api_key, podcast_wl,
                                        video_id=video_id, title=title, model=model)
        if "error" in result:
            save_podcast_job({"status": "error", "error": result["error"]})
        else:
            if result.get("new_watchlist"):
                save_podcast_watchlist(result["new_watchlist"])
            save_podcast_history({
                "timestamp":          datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "video_id":           result["video_id"],
                "title":              result["title"],
                "result_text":        result["text"],
                "watchlist_snapshot": result.get("new_watchlist", []),
            })
            save_podcast_job({"status": "done"})
    except Exception as e:
        save_podcast_job({"status": "error", "error": str(e)})


def _discovery_worker(sectors, n_picks, excluded_tickers, api_key, model, search_config):
    try:
        result = discover_stocks(sectors, n_picks, excluded_tickers, api_key, model, search_config)
        if "error" in result:
            save_discovery_job({"status": "error", "error": result["error"]})
        else:
            save_discovery_history({
                "timestamp":          datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "sectors":            sectors,
                "n_picks":            n_picks,
                "result_text":        result.get("text", ""),
                "discovered_tickers": result.get("tickers", []),
                "input_tokens":       result.get("input_tokens",  0),
                "output_tokens":      result.get("output_tokens", 0),
            })
            save_discovery_job({"status": "done"})
    except Exception as e:
        save_discovery_job({"status": "error", "error": str(e)})


# ─── Search & list widgets ────────────────────────────────────────────────────

def search_yahoo_finance(query: str):
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


def render_search_and_add(list_key: str, uid: str, portfolio_data: dict):
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


def render_entry_list(list_key: str, uid_prefix: str, portfolio_data: dict):
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
                    if any(e["ticker"] == ticker for e in portfolio_data[target_key]):
                        st.toast(f"⚠️ {name} ({ticker}) ist bereits in {target_name}!", icon="⚠️")
                    else:
                        prev = st.session_state.get(pending_key)
                        if prev and prev != ticker:
                            portfolio_data[list_key] = [e for e in portfolio_data[list_key] if e["ticker"] != prev]
                        portfolio_data[target_key].append(entry)
                        portfolio_data[list_key] = [e for e in portfolio_data[list_key] if e["ticker"] != ticker]
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
                    prev = st.session_state.get(pending_key)
                    if prev and prev != ticker:
                        portfolio_data[list_key] = [e for e in portfolio_data[list_key] if e["ticker"] != prev]
                        save_portfolio(portfolio_data)
                    st.session_state[pending_key] = ticker
                    st.rerun()


# ─── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="K-Invest | Swing Trading Agent", page_icon="📈", layout="wide")

st.markdown("""
<style>
html { overflow-x: hidden !important; }
body { overflow-x: hidden !important; width: 100% !important; }
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
.main { overflow-x: hidden !important; max-width: 100vw !important; }
.main .block-container {
    max-width: 100% !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}
table { display: block !important; overflow-x: auto !important; max-width: 100% !important; }
section[data-testid="stSidebar"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

st.title("📈 K-Invest: Swing Trading Assistant")
st.markdown(
    "Dieser KI-Agent nutzt Anthropic Claude, um dein Portfolio und Watchlist systematisch "
    "nach fundamentalem Momentum für kurzfristiges Swing-Trading zu analysieren."
)

# ─── Session state initialisation from env vars ───────────────────────────────

_env_defaults = {
    "api_key":        "ANTHROPIC_API_KEY",
    "youtube_api_key":"YOUTUBE_API_KEY",
    "google_api_key": "GOOGLE_SEARCH_API_KEY",
    "google_cx_id":   "GOOGLE_CX_ID",
    "tavily_api_key": "TAVILY_API_KEY",
}
for ss_key, env_var in _env_defaults.items():
    if ss_key not in st.session_state:
        st.session_state[ss_key] = os.environ.get(env_var, "")

# Sector checkbox defaults
for key, _label, default in PREDEFINED_SECTORS:
    skey = f"sector_{key}"
    if skey not in st.session_state:
        st.session_state[skey] = default

# ─── Load persistent state ────────────────────────────────────────────────────

settings      = load_settings()
portfolio_data = load_portfolio()

# ─── Tabs ─────────────────────────────────────────────────────────────────────

tab_analyse, tab_depot, tab_watchlist, tab_podcast, tab_discovery, tab_settings = st.tabs([
    "🚀 Analyse", "💼 Depot", "🔭 Watchlist", "🎧 Podcast", "🔍 Discovery", "⚙️ Einstellungen"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB: ANALYSE
# ══════════════════════════════════════════════════════════════════════════════
with tab_analyse:
    api_key = st.session_state.api_key

    n_depot = len(portfolio_data["depot"])
    n_watch = len(portfolio_data["watchlist"])

    depot_job = load_depot_job()
    depot_job_status = depot_job.get("status", "idle")

    if depot_job_status == "running":
        st.info("⏳ Analyse läuft im Hintergrund — du kannst das Handy weglegen, das Ergebnis erscheint automatisch in der Historie.")
        st.caption(f"Gestartet um {depot_job.get('started_at', '...')}")
        time.sleep(4)
        st.rerun()

    elif depot_job_status == "error":
        st.error(f"Fehler bei der Analyse: {depot_job.get('error', 'Unbekannter Fehler')}")
        if st.button("❌ Fehler quittieren & erneut versuchen", use_container_width=True):
            save_depot_job({"status": "idle"})
            st.rerun()

    else:
        if depot_job_status == "done":
            st.success("Analyse abgeschlossen — Ergebnis in der Historie gespeichert.")
            save_depot_job({"status": "idle"})

        def _start_analysis(depot_tickers, watch_tickers, target_label):
            model = settings.get("model", "claude-sonnet-4-6")
            sc = get_search_config(settings)
            save_depot_job({"status": "running", "started_at": datetime.now().strftime("%H:%M:%S")})
            threading.Thread(
                target=_depot_analysis_worker,
                args=(depot_tickers, watch_tickers, target_label, api_key, model, sc),
                daemon=True,
            ).start()
            st.rerun()

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button(f"🚀 Depot analysieren ({n_depot})", disabled=not api_key or n_depot == 0, use_container_width=True, type="primary"):
                _start_analysis([e["ticker"] for e in portfolio_data["depot"]], [], "Nur Depot")
        with btn_col2:
            if st.button(f"🔭 Watchlist analysieren ({n_watch})", disabled=not api_key or n_watch == 0, use_container_width=True, type="primary"):
                _start_analysis([], [e["ticker"] for e in portfolio_data["watchlist"]], "Nur Watchlist")

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
            ts     = entry.get("timestamp", "")
            target = entry.get("target", "")
            in_tok = entry.get("input_tokens",  0)
            out_tok= entry.get("output_tokens", 0)
            try:
                dt_label = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").strftime("%d.%m.%Y %H:%M")
            except Exception:
                dt_label = ts
            with st.expander(f"🔎 {dt_label} — {target}", expanded=(i == 0)):
                st.markdown(entry.get("result_text", "").replace("$", "&#36;"), unsafe_allow_html=True)
                if in_tok > 0 or out_tok > 0:
                    cost_usd = (in_tok / 1_000_000) * CLAUDE_INPUT_PRICE_PER_M + (out_tok / 1_000_000) * CLAUDE_OUTPUT_PRICE_PER_M
                    st.caption(f"🪙 **Token-Verbrauch:** {in_tok:,} Input | {out_tok:,} Output | **Geschätzte Kosten:** ${cost_usd:.4f}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB: DEPOT
# ══════════════════════════════════════════════════════════════════════════════
with tab_depot:
    st.subheader("💼 Mein Depot")

    pending_depot = st.session_state.get("pending_delete_depot")
    if pending_depot:
        portfolio_data["depot"] = [e for e in portfolio_data["depot"] if e["ticker"] != pending_depot]
        save_portfolio(portfolio_data)
        st.session_state["pending_delete_depot"] = None

    render_search_and_add("depot", "depot", portfolio_data)
    st.markdown("---")

    if portfolio_data["depot"]:
        render_entry_list("depot", "d", portfolio_data)
    else:
        st.info("Noch keine Einträge im Depot. Nutze die Suche oben um Aktien hinzuzufügen.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB: WATCHLIST
# ══════════════════════════════════════════════════════════════════════════════
with tab_watchlist:
    st.subheader("🔭 Watchlist")

    pending_watch = st.session_state.get("pending_delete_watchlist")
    if pending_watch:
        portfolio_data["watchlist"] = [e for e in portfolio_data["watchlist"] if e["ticker"] != pending_watch]
        save_portfolio(portfolio_data)
        st.session_state["pending_delete_watchlist"] = None

    render_search_and_add("watchlist", "watch", portfolio_data)
    st.markdown("---")

    if portfolio_data["watchlist"]:
        render_entry_list("watchlist", "w", portfolio_data)
    else:
        st.info("Noch keine Einträge in der Watchlist. Nutze die Suche oben um Aktien hinzuzufügen.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB: PODCAST
# ══════════════════════════════════════════════════════════════════════════════
with tab_podcast:
    st.subheader("🎧 Doppelgänger Tech Talk Scanner")
    st.markdown("Analysiert die neueste Folge von @doppelgaengerio auf Swing-Trading-Chancen.")

    api_key         = st.session_state.api_key
    youtube_api_key = st.session_state.youtube_api_key

    job = load_podcast_job()
    job_status = job.get("status", "idle")

    if job_status == "running":
        st.info("⏳ Analyse läuft im Hintergrund — du kannst das Handy weglegen, das Ergebnis erscheint automatisch in der Historie.")
        st.caption(f"Gestartet um {job.get('started_at', '...')}")
        time.sleep(4)
        st.rerun()

    elif job_status == "error":
        st.error(f"Fehler bei der Analyse: {job.get('error', 'Unbekannter Fehler')}")
        if st.button("❌ Fehler quittieren & erneut versuchen", use_container_width=True):
            save_podcast_job({"status": "idle"})
            st.rerun()

    else:
        if job_status == "done":
            st.success("Analyse abgeschlossen — Ergebnis in der Historie gespeichert.")
            save_podcast_job({"status": "idle"})

        keys_present = api_key and youtube_api_key

        def _start_podcast_job(vid_id=None, vid_title=None):
            podcast_wl = load_podcast_watchlist()
            model = settings.get("model", "claude-sonnet-4-6")
            sc = get_search_config(settings)
            save_podcast_job({"status": "running", "started_at": datetime.now().strftime("%H:%M:%S")})
            threading.Thread(
                target=_podcast_analysis_worker,
                args=(youtube_api_key, api_key, podcast_wl, model, sc),
                kwargs={"video_id": vid_id, "title": vid_title},
                daemon=True,
            ).start()

        if st.button("🚀 Neueste Folge analysieren", type="primary", use_container_width=True, disabled=not keys_present):
            _start_podcast_job()
            st.rerun()

        st.markdown("---")
        st.markdown("**Oder frühere Folge analysieren:**")

        if st.button("📋 Verfügbare Folgen laden", use_container_width=True, disabled=not keys_present):
            videos = get_recent_videos(youtube_api_key, n=15)
            if videos and "error" in videos[0]:
                st.error(videos[0]["error"])
            else:
                st.session_state["podcast_recent_videos"] = videos

        recent = st.session_state.get("podcast_recent_videos", [])
        if recent:
            podcast_history_ids = {e.get("video_id") for e in load_podcast_history() if e.get("video_id")}
            options = {f"{v['published_at']} — {v['title']}": v for v in recent}
            selected_label = st.selectbox("Folge wählen", list(options.keys()), label_visibility="collapsed")
            selected = options[selected_label]

            already_analyzed = selected["video_id"] in podcast_history_ids
            if already_analyzed:
                existing = next((e for e in load_podcast_history() if e.get("video_id") == selected["video_id"]), None)
                ts_str = existing.get("timestamp", "")
                try:
                    dt_str = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S").strftime("%d.%m.%Y %H:%M")
                except Exception:
                    dt_str = ts_str
                st.warning(f"Diese Folge wurde bereits am {dt_str} analysiert. Du kannst sie trotzdem erneut analysieren.")

            btn_label = "🔄 Erneut analysieren" if already_analyzed else "🔍 Analyse starten"
            if st.button(btn_label, use_container_width=True, type="primary"):
                _start_podcast_job(vid_id=selected["video_id"], vid_title=selected["title"])
                st.session_state.pop("podcast_recent_videos", None)
                st.rerun()

    podcast_history = load_podcast_history()
    if podcast_history:
        ph_col1, ph_col2 = st.columns([8, 2])
        with ph_col1:
            st.subheader("📊 Analyse-Historie")
        with ph_col2:
            if st.button("🗑️ Alle löschen", key="clear_podcast_history"):
                clear_podcast_history()
                st.rerun()

        for i, entry in enumerate(podcast_history):
            ts = entry.get("timestamp", "")
            try:
                dt_label = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").strftime("%d.%m.%Y %H:%M")
            except Exception:
                dt_label = ts
            with st.expander(f"🎙️ {dt_label} — {entry.get('title', '')}", expanded=(i == 0)):
                st.markdown(entry.get("result_text", "").replace("$", "&#36;"), unsafe_allow_html=True)
                snapshot = entry.get("watchlist_snapshot", [])
                if snapshot:
                    st.divider()
                    st.caption("📋 Watchlist-Snapshot dieser Analyse")
                    st.dataframe(snapshot, use_container_width=True)

    st.divider()
    st.markdown("### 📋 Laufende Doppelgänger-Watchlist")
    podcast_wl = load_podcast_watchlist()
    if podcast_wl:
        st.dataframe(podcast_wl, use_container_width=True)
    else:
        st.info("Die Watchlist ist aktuell leer. Führe eine Analyse aus, um sie zu füllen.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB: DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════
with tab_discovery:
    st.subheader("🔍 Stock Discovery")
    st.markdown(
        "Findet neue Swing-Trading-Kandidaten in deinen Fokus-Sektoren — "
        "ausschließlich Titel, die noch nicht in deinem Depot oder deiner Watchlist sind."
    )

    api_key = st.session_state.api_key

    disc_job = load_discovery_job()
    disc_job_status = disc_job.get("status", "idle")

    if disc_job_status == "running":
        st.info("⏳ Discovery läuft im Hintergrund — du kannst das Handy weglegen, das Ergebnis erscheint automatisch in der Historie.")
        st.caption(f"Gestartet um {disc_job.get('started_at', '...')}")
        time.sleep(4)
        st.rerun()

    elif disc_job_status == "error":
        st.error(f"Fehler bei der Discovery: {disc_job.get('error', 'Unbekannter Fehler')}")
        if st.button("❌ Fehler quittieren & erneut versuchen", use_container_width=True, key="disc_err_btn"):
            save_discovery_job({"status": "idle"})
            st.rerun()

    else:
        if disc_job_status == "done":
            st.success("Discovery abgeschlossen — Ergebnis in der Historie gespeichert.")
            save_discovery_job({"status": "idle"})

        # Sector selection
        st.markdown("**Sektoren (mind. 1 auswählen):**")
        cols = st.columns(3)
        for idx, (key, label, _default) in enumerate(PREDEFINED_SECTORS):
            with cols[idx % 3]:
                st.checkbox(label, key=f"sector_{key}")

        custom_sector = st.text_input("Eigener Sektor (optional):", key="custom_sector_input", placeholder="z.B. Quantencomputer")

        # Picks count
        n_picks = st.radio(
            "Anzahl Picks:",
            [3, 5, 10],
            format_func=lambda x: f"Top {x}",
            index=1,
            horizontal=True,
            key="disc_n_picks",
        )

        # Collect selected sectors
        selected_sectors = [label for key, label, _ in PREDEFINED_SECTORS if st.session_state.get(f"sector_{key}")]
        if custom_sector.strip():
            selected_sectors.append(custom_sector.strip())

        can_start = api_key and len(selected_sectors) > 0

        if not api_key:
            st.warning("Bitte trage deinen Anthropic API Key im Tab ⚙️ Einstellungen ein.")
        elif not selected_sectors:
            st.warning("Bitte wähle mindestens einen Sektor aus.")

        if st.button("🔍 Discovery starten", disabled=not can_start, use_container_width=True, type="primary"):
            excluded = [e["ticker"] for e in portfolio_data["depot"]] + [e["ticker"] for e in portfolio_data["watchlist"]]
            model = settings.get("model", "claude-sonnet-4-6")
            sc = get_search_config(settings)
            save_discovery_job({"status": "running", "started_at": datetime.now().strftime("%H:%M:%S")})
            threading.Thread(
                target=_discovery_worker,
                args=(selected_sectors, n_picks, excluded, api_key, model, sc),
                daemon=True,
            ).start()
            st.rerun()

    # Discovery history
    disc_history = load_discovery_history()
    if disc_history:
        dh_col1, dh_col2 = st.columns([8, 2])
        with dh_col1:
            st.subheader("📊 Discovery-Historie")
        with dh_col2:
            if st.button("🗑️ Alle löschen", key="clear_disc_history"):
                clear_discovery_history()
                st.rerun()

        for i, entry in enumerate(disc_history):
            ts = entry.get("timestamp", "")
            try:
                dt_label = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").strftime("%d.%m.%Y %H:%M")
            except Exception:
                dt_label = ts
            sectors_label = ", ".join(entry.get("sectors", []))
            n_label = entry.get("n_picks", "?")
            with st.expander(f"🔍 {dt_label} — Top {n_label} | {sectors_label}", expanded=(i == 0)):
                st.markdown(entry.get("result_text", "").replace("$", "&#36;"), unsafe_allow_html=True)

                in_tok  = entry.get("input_tokens",  0)
                out_tok = entry.get("output_tokens", 0)
                if in_tok > 0 or out_tok > 0:
                    cost_usd = (in_tok / 1_000_000) * CLAUDE_INPUT_PRICE_PER_M + (out_tok / 1_000_000) * CLAUDE_OUTPUT_PRICE_PER_M
                    st.caption(f"🪙 **Token-Verbrauch:** {in_tok:,} Input | {out_tok:,} Output | **Geschätzte Kosten:** ${cost_usd:.4f}")

                discovered = entry.get("discovered_tickers", [])
                if discovered:
                    st.divider()
                    st.markdown("**Gefundene Titel übernehmen:**")
                    for item in discovered:
                        ticker = item.get("ticker", "")
                        name   = item.get("name", ticker)
                        in_wl  = any(e["ticker"] == ticker for e in portfolio_data["watchlist"])
                        in_dep = any(e["ticker"] == ticker for e in portfolio_data["depot"])

                        col_name, col_w, col_d = st.columns([6, 2, 2])
                        with col_name:
                            st.markdown(f"**{name}** ({ticker})")
                        with col_w:
                            if in_wl:
                                st.caption("✓ Watchlist")
                            else:
                                if st.button("+ Watchlist", key=f"disc_w_{i}_{ticker}"):
                                    portfolio_data["watchlist"].append({"ticker": ticker, "name": name})
                                    save_portfolio(portfolio_data)
                                    st.toast(f"✅ {name} zur Watchlist hinzugefügt!")
                                    st.rerun()
                        with col_d:
                            if in_dep:
                                st.caption("✓ Depot")
                            else:
                                if st.button("+ Depot", key=f"disc_d_{i}_{ticker}"):
                                    portfolio_data["depot"].append({"ticker": ticker, "name": name})
                                    save_portfolio(portfolio_data)
                                    st.toast(f"✅ {name} ins Depot hinzugefügt!")
                                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB: EINSTELLUNGEN
# ══════════════════════════════════════════════════════════════════════════════
with tab_settings:
    st.subheader("⚙️ Einstellungen")

    # ── API Keys ──────────────────────────────────────────────────────────────
    st.markdown("### API Keys")
    st.info("API Keys werden nicht gespeichert. Sie werden aus den Umgebungsvariablen vorbelegt und gelten nur für die aktuelle Sitzung.", icon="ℹ️")

    st.text_input("Anthropic API Key", type="password", key="api_key")
    st.text_input("YouTube API Key (Podcast)", type="password", key="youtube_api_key")

    # ── Such-Engine ───────────────────────────────────────────────────────────
    st.markdown("### Such-Engine")
    st.markdown("Die gewählte Such-Engine wird für alle Analysen (Depot, Podcast, Discovery) verwendet.")

    engine_options  = ["duckduckgo", "google", "tavily"]
    engine_labels   = {
        "duckduckgo": "DuckDuckGo (kostenlos, kein Key nötig)",
        "google":     "Google Custom Search",
        "tavily":     "Tavily (KI-optimiert)",
    }
    current_engine  = settings.get("search_engine", "duckduckgo")
    engine_idx      = engine_options.index(current_engine) if current_engine in engine_options else 0

    selected_engine = st.radio(
        "Such-Engine auswählen:",
        engine_options,
        format_func=lambda x: engine_labels[x],
        index=engine_idx,
        key="settings_engine_radio",
    )

    if selected_engine == "google":
        st.text_input("Google API Key", type="password", key="google_api_key",
                      help="Google Custom Search API Key (console.cloud.google.com)")
        st.text_input("Google CX-ID", key="google_cx_id",
                      help="Custom Search Engine ID (programmablesearchengine.google.com)")
    elif selected_engine == "tavily":
        st.text_input("Tavily API Key", type="password", key="tavily_api_key",
                      help="Tavily API Key (tavily.com) — 1.000 Abfragen/Monat kostenlos")

    # ── Modell-Auswahl ────────────────────────────────────────────────────────
    st.markdown("### Modell")

    cached_models = settings.get("cached_models", ["claude-sonnet-4-6"])
    current_model = settings.get("model", "claude-sonnet-4-6")
    model_idx     = cached_models.index(current_model) if current_model in cached_models else 0

    col_model, col_refresh = st.columns([3, 1])
    with col_model:
        selected_model = st.selectbox(
            "Claude Modell:",
            cached_models,
            index=model_idx,
            key="settings_model_select",
        )
    with col_refresh:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Laden", help="Verfügbare Modelle vom Anthropic API abrufen"):
            _key = st.session_state.api_key
            if _key:
                try:
                    import anthropic as _anthropic
                    _client = _anthropic.Anthropic(api_key=_key)
                    _page = _client.models.list()
                    _ids = sorted([m.id for m in _page.data], reverse=True)
                    if _ids:
                        settings["cached_models"] = _ids
                        save_settings(settings)
                        st.success(f"{len(_ids)} Modelle geladen.")
                        st.rerun()
                    else:
                        st.warning("Keine Modelle zurückgegeben.")
                except Exception as _e:
                    st.error(f"Fehler: {_e}")
            else:
                st.warning("Bitte zuerst den Anthropic API Key eingeben.")

    st.caption(f"Aktuell aktiv: **{current_model}**")

    # ── Speichern ─────────────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("💾 Einstellungen speichern", type="primary", use_container_width=True):
        settings["search_engine"] = selected_engine
        settings["model"]         = selected_model
        save_settings(settings)
        st.success("Einstellungen gespeichert.")
        st.rerun()

    st.caption(f"Version: `{os.environ.get('APP_VERSION', 'dev')}`")
