import json
import os
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

INDEX_CACHE_FILE = os.environ.get("INDEX_CACHE_FILE", "index_cache.json")

_WIKI_CONFIG = {
    "Nasdaq 100": {
        "url": "https://en.wikipedia.org/wiki/Nasdaq-100",
        "col_hints": ["ticker symbol", "ticker"],
    },
    "S&P 500": {
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "col_hints": ["symbol"],
    },
}


def _load_cache() -> dict:
    if os.path.exists(INDEX_CACHE_FILE):
        try:
            with open(INDEX_CACHE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(data: dict):
    with open(INDEX_CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_index_tickers(index: str) -> list:
    cache = _load_cache()
    entry = cache.get(index, {})
    cached_at = entry.get("cached_at")
    if cached_at and entry.get("tickers"):
        try:
            age = datetime.now() - datetime.fromisoformat(cached_at)
            if age < timedelta(hours=24):
                return entry["tickers"]
        except Exception:
            pass

    config = _WIKI_CONFIG.get(index)
    if not config:
        return entry.get("tickers", [])

    try:
        tables = pd.read_html(config["url"])
        hints = config["col_hints"]
        tickers = []
        for table in tables:
            for col in table.columns:
                col_lower = str(col).lower()
                if any(h in col_lower for h in hints):
                    raw = table[col].dropna().tolist()
                    candidates = [
                        str(t).strip().replace(".", "-")
                        for t in raw
                        if isinstance(t, str) and 1 <= len(str(t).strip()) <= 6
                    ]
                    if len(candidates) > 50:
                        tickers = candidates
                        break
            if tickers:
                break

        if tickers:
            cache[index] = {"tickers": tickers, "cached_at": datetime.now().isoformat()}
            _save_cache(cache)
            return tickers
    except Exception:
        pass

    return entry.get("tickers", [])


def get_eurusd_rate() -> float:
    try:
        info = yf.Ticker("EURUSD=X").fast_info
        rate = getattr(info, "last_price", None)
        if rate and rate > 0:
            return float(rate)
    except Exception:
        pass
    try:
        info = yf.Ticker("EURUSD=X").info
        rate = info.get("regularMarketPrice")
        if rate and rate > 0:
            return float(rate)
    except Exception:
        pass
    return 1.0


def _is_hammer(row: pd.Series) -> bool:
    body = abs(row["Close"] - row["Open"])
    total_range = row["High"] - row["Low"]
    if total_range == 0 or body == 0:
        return False
    lower_shadow = min(row["Close"], row["Open"]) - row["Low"]
    upper_shadow = row["High"] - max(row["Close"], row["Open"])
    return lower_shadow >= 2 * body and upper_shadow <= 0.1 * total_range


def _detect_pullback(df: pd.DataFrame) -> bool:
    if len(df) < 6:
        return False
    last5 = df.iloc[-5:]
    red_count = int((last5["Close"] < last5["Open"]).sum())
    lower_high = bool(df.iloc[-1]["High"] < df.iloc[-5]["High"])
    return red_count >= 3 and lower_high


def _detect_stabilization(df: pd.DataFrame) -> bool:
    last = df.iloc[-1]
    green = bool(last["Close"] > last["Open"])
    return green or _is_hammer(last)


def _find_swing_low(df: pd.DataFrame) -> float:
    return float(df.iloc[-10:]["Low"].min())


def _find_take_profit(df: pd.DataFrame) -> float:
    if len(df) < 26:
        return float(df["High"].max())
    return float(df.iloc[-25:-5]["High"].max())


def _screen_ticker(ticker: str, df: pd.DataFrame, capital: float,
                   risk_pct: float, min_crv: float, eurusd: float):
    if len(df) < 200:
        return None

    df = df.copy()
    df["SMA50"]   = df["Close"].rolling(50).mean()
    df["SMA200"]  = df["Close"].rolling(200).mean()
    df["EMA20"]   = df["Close"].ewm(span=20, adjust=False).mean()
    df["AvgVol20"] = df["Volume"].rolling(20).mean()

    last = df.iloc[-1]

    if pd.isna(last["SMA200"]) or pd.isna(last["SMA50"]) or pd.isna(last["EMA20"]):
        return None

    if last["Close"] <= last["SMA50"]:
        return None
    if last["Close"] <= last["SMA200"]:
        return None

    # EMA20 touch: close must be within 0.5% above EMA20 (or below)
    if last["Close"] > last["EMA20"] * 1.005:
        return None

    if pd.isna(last["AvgVol20"]) or last["AvgVol20"] < 500_000:
        return None

    if not _detect_pullback(df):
        return None
    if not _detect_stabilization(df):
        return None

    entry = float(last["Close"])
    sl    = _find_swing_low(df)
    tp    = _find_take_profit(df)

    if sl >= entry or tp <= entry:
        return None

    crv = (tp - entry) / (entry - sl)
    if crv < min_crv:
        return None

    entry_eur       = entry / eurusd
    sl_eur          = sl / eurusd
    tp_eur          = tp / eurusd
    r_per_share_eur = entry_eur - sl_eur
    if r_per_share_eur <= 0:
        return None

    r_eur      = capital * risk_pct
    shares     = int(r_eur / r_per_share_eur)
    if shares <= 0:
        return None
    volume_eur   = shares * entry_eur
    max_loss_eur = shares * r_per_share_eur

    hammer = _is_hammer(last)

    return {
        "ticker":       ticker,
        "entry_eur":    round(entry_eur, 2),
        "sl_eur":       round(sl_eur, 2),
        "tp_eur":       round(tp_eur, 2),
        "crv":          round(crv, 2),
        "shares":       shares,
        "volume_eur":   round(volume_eur, 2),
        "max_loss_eur": round(max_loss_eur, 2),
        "pattern":      "Hammer" if hammer else "Grüne Kerze",
        "eurusd":       round(eurusd, 4),
        "sma50_eur":    round(float(last["SMA50"]) / eurusd, 2),
        "sma200_eur":   round(float(last["SMA200"]) / eurusd, 2),
        "ema20_eur":    round(float(last["EMA20"]) / eurusd, 2),
        "outcome":      None,
        "closed_at":    None,
    }


def run_screener(index: str, capital: float, risk_pct: float, min_crv: float) -> dict:
    tickers = get_index_tickers(index)
    if not tickers:
        return {
            "error": f"Keine Ticker für {index} geladen — Wikipedia nicht erreichbar?",
            "signals": [], "scanned": 0,
        }

    eurusd  = get_eurusd_rate()
    signals = []
    errors  = 0

    for ticker in tickers:
        try:
            df = yf.Ticker(ticker).history(period="1y", interval="1d")
            if df.empty:
                continue
            signal = _screen_ticker(ticker, df, capital, risk_pct, min_crv, eurusd)
            if signal:
                signals.append(signal)
        except Exception:
            errors += 1

    return {
        "signals":  signals,
        "scanned":  len(tickers),
        "errors":   errors,
        "eurusd":   round(eurusd, 4),
        "index":    index,
        "capital":  capital,
        "risk_pct": risk_pct,
        "min_crv":  min_crv,
    }
