import anthropic

from tools import ANTHROPIC_TOOLS, get_stock_price_and_momentum, search_recent_news

MAX_TOKENS = 8192

SYSTEM_PROMPT = """Du bist ein strikter, erfahrener und risiko-bewusster Swing-Trader.
Deine Aufgabe ist es, für die Aktien im Portfolio oder auf der Watchlist harte Empfehlungen auszusprechen.
Dein Anlagehorizont ist kurzfristig (Tage bis wenige Wochen). Du suchst nach schnellen Gewinnen durch Momentum und kurzfristige Katalysatoren (News, Earnings).

BEWERTE JEDE AKTIE nach diesen Kriterien:
1. Hat sie kurzfristiges Momentum? (Was sagt der Preis/Volumen?)
2. Gibt es fundamentale News/Katalysatoren, die den aktuellen Trade rechtfertigen?

WÄHRUNG: Alle Kurse, Preise, Kursziele und Stop-Loss-Werte IMMER in Euro (€) angeben. Niemals USD oder das Dollar-Zeichen ($) verwenden.

KURSZIELE & STOP-LOSS:
Falls Depot-Aktien analysiert werden, MUSST du am Ende — nach der Textanalyse — das Tool `save_price_targets` aufrufen.
Setze für jede Depot-Aktie ein realistisches Kursziel und einen Stop-Loss basierend auf der Analyse (technische Level, Unterstützung/Widerstand, ATR).
Falls bereits Werte existieren: überprüfe sie und passe sie an die aktuelle Marktlage an.

DEIN OUTPUT:
Beginne DIREKT mit der Zusammenfassungs-Tabelle — kein einleitender Satz, keine Begrüßung.

Schreibe zuerst diese Zusammenfassungs-Tabelle:
| Name | Empfehlung | Kurzfazit |
| :--- | :--- | :--- |
| z.B. Apple Inc. | 🟢 KAUFEN | Momentum intakt, Breakout bestätigt |

Verwende zwingend diese Symbole in der Empfehlung-Spalte:
- KAUFEN → 🟢 KAUFEN
- HALTEN → 🟡 HALTEN
- VERKAUFEN → 🔴 VERKAUFEN

Danach folgen die detaillierten Einzelanalysen — ZWINGEND in dieser Reihenfolge: zuerst alle KAUFEN, dann alle HALTEN, dann alle VERKAUFEN.

Für jede Aktie MUSST DU zwingend mit einem der folgenden Tags starten:
[KAUFEN]
[VERKAUFEN]
[HALTEN]

Darunter MUSST DU exakt 3 kurze und prägnante Stichpunkte (Bullet Points) liefern, die deine Entscheidung als Swing-Trader hart begründen. Keine weichen Formulierungen. Sei entscheidungsfreudig. Erkläre in einem der Stichpunkte auch, auf welcher Annahme / welchem Trigger die Entscheidung basiert.
Nutze die bereitgestellten Tools, um Fakten zu sammeln, bevor du antwortest! Wenn eine News zu alt ist, merke das an.
"""


def analyze_portfolio(depot: list, watchlist: list, api_key: str,
                      model: str, search_config: dict,
                      current_targets: dict = None) -> dict:
    if not api_key:
        return {"text": "Fehler: Anthropic API Key fehlt.", "input_tokens": 0, "output_tokens": 0}

    client = anthropic.Anthropic(api_key=api_key)

    stocks_to_analyze = depot + watchlist
    if not stocks_to_analyze:
        return {"text": "Keine Aktien zum Analysieren gefunden.", "input_tokens": 0, "output_tokens": 0}

    engine = search_config.get("engine", "duckduckgo")
    google_api_key = search_config.get("google_api_key", "")
    google_cx_id = search_config.get("google_cx_id", "")
    tavily_api_key = search_config.get("tavily_api_key", "")

    parts = []
    if depot:
        parts.append(f"Depot (meine aktuellen Positionen): {', '.join(depot)}")
    if watchlist:
        parts.append(f"Watchlist (zur Beobachtung): {', '.join(watchlist)}")
    if depot:
        target_lines = []
        for ticker in depot:
            t = (current_targets or {}).get(ticker, {})
            if t.get("kursziel") is not None:
                target_lines.append(f"  - {ticker}: Kursziel {t['kursziel']:.2f} €, Stop-Loss {t['stop_loss']:.2f} €")
            else:
                target_lines.append(f"  - {ticker}: noch kein Kursziel gesetzt")
        parts.append("Aktuelle Kursziele und Stop-Loss:\n" + "\n".join(target_lines))
        parts.append(
            f"Analysiere alle Aktien, dann rufe `save_price_targets` auf und setze für jede "
            f"Depot-Aktie ({', '.join(depot)}) ein Kursziel und Stop-Loss in EUR."
        )
    user_message = "\n\n".join(parts)
    messages = [{"role": "user", "content": user_message}]

    try:
        total_input_tokens = 0
        total_output_tokens = 0
        saved_targets = {}
        accumulated_text = []

        while True:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=ANTHROPIC_TOOLS,
            )

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            for block in response.content:
                if block.type == "text" and block.text.strip():
                    accumulated_text.append(block.text)

            if response.stop_reason != "tool_use":
                return {
                    "text": "\n\n".join(accumulated_text) if accumulated_text else "Keine finale Text-Antwort erhalten.",
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "price_targets": saved_targets,
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
                    elif block.name == "save_price_targets":
                        for t in block.input.get("targets", []):
                            saved_targets[t["ticker"]] = {
                                "kursziel": t.get("kursziel"),
                                "stop_loss": t.get("stop_loss"),
                            }
                        result = "Kursziele und Stop-Loss gespeichert."
                    else:
                        result = f"Unbekanntes Tool: {block.name}"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })

            messages.append({"role": "user", "content": tool_results})

    except Exception as e:
        return {"text": f"Fehler bei der Anthropic-API Kommunikation: {str(e)}", "input_tokens": 0, "output_tokens": 0, "price_targets": {}}
