import anthropic

from tools import get_stock_price_and_momentum, search_recent_news

MAX_TOKENS = 8192

_SAVE_VERDICTS_TOOL = {
    "name": "save_signal_verdicts",
    "description": "Speichert die Urteile für alle analysierten Screener-Signale. Nach Abschluss der Recherche aufrufen.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker":     {"type": "string", "description": "Ticker-Symbol"},
                        "verdict":    {"type": "string", "enum": ["bestätigt", "vorsicht", "abgelehnt"]},
                        "hauptgrund": {"type": "string", "description": "Ein-Satz-Zusammenfassung des Urteils"},
                        "punkte":     {
                            "type": "array",
                            "description": "2–3 konkrete Stichpunkte die das Urteil begründen",
                            "items": {"type": "string"},
                            "minItems": 2,
                            "maxItems": 3,
                        },
                    },
                    "required": ["ticker", "verdict", "hauptgrund", "punkte"],
                },
            }
        },
        "required": ["verdicts"],
    },
}

_TOOLS = [
    _SAVE_VERDICTS_TOOL,
    {
        "name": "get_stock_price_and_momentum",
        "description": "Holt aktuelle Marktdaten und kurzfristiges Momentum für eine Aktie.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker_symbol": {"type": "string", "description": "Ticker-Symbol, z.B. AAPL"},
            },
            "required": ["ticker_symbol"],
        },
    },
    {
        "name": "search_recent_news",
        "description": "Sucht im Web nach aktuellen Nachrichten zu einem Unternehmen oder Sektor.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string"},
                "max_results": {"type": "integer", "description": "Anzahl Ergebnisse (Standard: 5)"},
            },
            "required": ["query"],
        },
    },
]

SYSTEM_PROMPT = """Du bist ein erfahrener Swing-Trader-Assistent, der technisch bereits validierte Handelssignale auf fundamentale Risiken prüft.

KONTEXT: Alle vorgelegten Aktien haben einen strikten technischen EMA-20 Pullback Screen bestanden:
- Kurs über SMA 50 und SMA 200 (intakter Aufwärtstrend)
- Kurs an den EMA 20 zurückgekehrt (Pullback-Zone)
- Chancen-Risiko-Verhältnis (CRV) bereits geprüft und ausreichend

DEINE AUFGABE: Prüfe AUSSCHLIESSLICH fundamentale und nachrichtenbasierte Gegenargumente.
Beurteile das technische Setup NICHT neu — es ist bereits maschinell bestätigt.

KONKRETE PRÜFPUNKTE (in dieser Priorität):
1. Earnings: Liegt ein Quartalsbericht in den nächsten 10 Tagen? → sofort ABGELEHNT
2. Negative News: Gewinnwarnung, Klage, CEO-Rücktritt, Produktrückruf?
3. Sektor-Druck: Makroökonomische oder regulatorische Faktoren die den gesamten Sektor belasten?
4. Positive Katalysatoren: Gibt es News die den technischen Bounce verstärken könnten?

URTEILE:
- bestätigt: Keine wesentlichen fundamentalen Gegenargumente — Setup kann eingegangen werden
- vorsicht: Ein Risikofaktor vorhanden, Trade möglich aber mit erhöhter Aufmerksamkeit
- abgelehnt: Klarer Dealbreaker — Setup technisch ok aber fundamental nicht vertretbar

Nutze die Tools um aktuelle Daten zu sammeln. Rufe danach ZWINGEND save_signal_verdicts auf.
Antworte auf Deutsch."""


def _build_user_message(signals: list) -> str:
    lines = [f"Analysiere folgende {len(signals)} technisch validierte EMA-20 Pullback Signal(e) auf fundamentale Risiken:\n"]
    for s in signals:
        lines.append(f"**{s['ticker']} — {s.get('name', s['ticker'])}**")
        lines.append(f"- Einstieg: {s['entry_eur']:.2f} €")
        lines.append(f"- Stop-Loss: {s['sl_eur']:.2f} €")
        lines.append(f"- Take Profit: {s['tp_eur']:.2f} €")
        lines.append(f"- CRV: {s['crv']:.1f}")
        lines.append(f"- Muster: {s.get('pattern', 'n/a')}\n")
    return "\n".join(lines)


def analyze_screener_signals(signals: list, api_key: str, model: str,
                             search_config: dict) -> dict:
    if not api_key:
        return {"error": "Anthropic API Key fehlt.", "input_tokens": 0, "output_tokens": 0}
    if not signals:
        return {"error": "Keine Signale zur Analyse.", "input_tokens": 0, "output_tokens": 0}

    client   = anthropic.Anthropic(api_key=api_key)
    engine   = search_config.get("engine", "duckduckgo")
    g_key    = search_config.get("google_api_key", "")
    g_cx     = search_config.get("google_cx_id", "")
    t_key    = search_config.get("tavily_api_key", "")

    messages = [{"role": "user", "content": _build_user_message(signals)}]

    total_input  = 0
    total_output = 0
    verdicts     = []
    result_text  = ""

    try:
        while True:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=_TOOLS,
            )

            total_input  += response.usage.input_tokens
            total_output += response.usage.output_tokens

            if response.stop_reason != "tool_use":
                for block in response.content:
                    if block.type == "text":
                        result_text = block.text
                break

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                if block.name == "save_signal_verdicts":
                    verdicts = block.input.get("verdicts", [])
                    result = "Urteile gespeichert."

                elif block.name == "get_stock_price_and_momentum":
                    result = get_stock_price_and_momentum(block.input.get("ticker_symbol"))

                elif block.name == "search_recent_news":
                    result = search_recent_news(
                        block.input.get("query"),
                        block.input.get("max_results", 5),
                        search_engine=engine,
                        google_api_key=g_key,
                        google_cx_id=g_cx,
                        tavily_api_key=t_key,
                    )
                else:
                    result = f"Unbekanntes Tool: {block.name}"

                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     str(result),
                })

            messages.append({"role": "user", "content": tool_results})

    except Exception as e:
        return {"error": str(e), "input_tokens": total_input, "output_tokens": total_output}

    return {
        "verdicts":      verdicts,
        "text":          result_text,
        "input_tokens":  total_input,
        "output_tokens": total_output,
    }
