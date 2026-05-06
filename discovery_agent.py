import anthropic
import json
import re
from tools import get_stock_price_and_momentum, search_recent_news, ANTHROPIC_TOOLS

MAX_TOKENS = 8192


def _build_system_prompt(sectors: list, n_picks: int, excluded_tickers: list) -> str:
    sector_str = ", ".join(sectors)
    excluded_str = ", ".join(excluded_tickers) if excluded_tickers else "keine"
    return f"""Du bist ein spezialisierter Finanzanalyst für Swing-Trading und Technologiewerte.
Dein Ziel: Identifiziere exakt {n_picks} konkrete Aktien-Picks mit überdurchschnittlichem Kurspotenzial für die nächsten 4–12 Wochen.

ANLAGEPROFIL:
- Risiko: Mittleres Risiko (keine Pennystocks, Fokus auf Mid- und Large-Caps mit solidem Handelsvolumen)
- Strategie: Reines Growth/Kurssteigerung — Dividenden irrelevant
- Zeithorizont: 4–12 Wochen (Swing-Trading)

FOKUS-SEKTOREN: {sector_str}

BEREITS BEKANNTE TITEL — DIESE DARFST DU NICHT VORSCHLAGEN: {excluded_str}

VORGEHEN (nutze die Tools):
1. Suche mit search_recent_news nach vielversprechenden Aktien in den genannten Sektoren (z.B. "best AI infrastructure stocks breakout 2025", "robotics automation stocks momentum")
2. Rufe für die besten Kandidaten Marktdaten ab mit get_stock_price_and_momentum
3. Suche nach aktuellen Nachrichten und Katalysatoren für die Finalisten
4. Wähle die {n_picks} überzeugendsten Titel — NUR solche, die NICHT in der Ausschluss-Liste stehen

PRO AKTIE analysiere:
- Katalysator: Welches spezifische Ereignis (Earnings, Konferenzen, neue Verträge) könnte den Kurs treiben?
- Technische Lage: Kurze Chart-Einschätzung (Ausbruch aus Konsolidierung, Relative Stärke)
- Fundamental-Check: Umsatzwachstum und Margen
- Exit-Strategie: Kursziel für 3 Monate + Stop-Loss zur Risikobegrenzung

WÄHRUNG: Alle Kurse IMMER in Euro (€) angeben. Niemals USD verwenden.

OUTPUT: Beginne DIREKT mit der Übersichtstabelle — kein einleitender Satz, keine Begrüßung:
| Ticker | Name | Sektor | Kurs (€) | Kursziel (€) | Stop-Loss (€) |
| :----- | :--- | :----- | -------: | -----------: | ------------: |

Dann für jeden Titel eine prägnante Begründung mit Katalysator, Technischer Lage, Fundamental-Check und Exit-Strategie.

PFLICHT — Am Ende ZWINGEND exakt diesen Block anfügen (valides JSON):
[TICKERS_JSON]
[{{"ticker": "XXXX", "name": "Vollständiger Firmenname"}}, ...]
[/TICKERS_JSON]"""


def _parse_tickers(text: str) -> list:
    match = re.search(r'\[TICKERS_JSON\]\s*(.*?)\s*\[/TICKERS_JSON\]', text, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group(1))
    except Exception:
        return []


def discover_stocks(sectors: list, n_picks: int, excluded_tickers: list,
                    api_key: str, model: str, search_config: dict) -> dict:
    if not api_key:
        return {"error": "Anthropic API Key fehlt.", "input_tokens": 0, "output_tokens": 0}

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _build_system_prompt(sectors, n_picks, excluded_tickers)

    engine = search_config.get("engine", "duckduckgo")
    google_api_key = search_config.get("google_api_key", "")
    google_cx_id = search_config.get("google_cx_id", "")
    tavily_api_key = search_config.get("tavily_api_key", "")

    sector_str = ", ".join(sectors)
    messages = [{
        "role": "user",
        "content": (
            f"Analysiere den Markt und finde {n_picks} Swing-Trading-Picks "
            f"in den Sektoren: {sector_str}. Starte sofort mit der Marktrecherche."
        ),
    }]

    try:
        total_input_tokens = 0
        total_output_tokens = 0

        while True:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=messages,
                tools=ANTHROPIC_TOOLS,
            )

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            if response.stop_reason != "tool_use":
                for block in response.content:
                    if block.type == "text":
                        tickers = _parse_tickers(block.text)
                        excluded_set = {t.upper() for t in excluded_tickers}
                        tickers = [t for t in tickers if t.get("ticker", "").upper() not in excluded_set]
                        return {
                            "text": block.text,
                            "tickers": tickers,
                            "input_tokens": total_input_tokens,
                            "output_tokens": total_output_tokens,
                        }
                return {
                    "text": "Keine finale Antwort erhalten.",
                    "tickers": [],
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                }

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    if block.name == "get_stock_price_and_momentum":
                        result = get_stock_price_and_momentum(block.input.get("ticker_symbol"))
                    elif block.name == "search_recent_news":
                        result = search_recent_news(
                            block.input.get("query"),
                            block.input.get("max_results", 5),
                            search_engine=engine,
                            google_api_key=google_api_key,
                            google_cx_id=google_cx_id,
                            tavily_api_key=tavily_api_key,
                        )
                    else:
                        result = f"Unbekanntes Tool: {block.name}"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })

            messages.append({"role": "user", "content": tool_results})

    except Exception as e:
        return {"error": str(e), "input_tokens": 0, "output_tokens": 0}
