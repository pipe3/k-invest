import os
import anthropic
import json
from tools import get_stock_price_and_momentum, search_recent_news, ANTHROPIC_TOOLS

SYSTEM_PROMPT = """Du bist ein strikter, erfahrener und risiko-bewusster Swing-Trader. 
Deine Aufgabe ist es, für die Aktien im Portfolio oder auf der Watchlist harte Empfehlungen auszusprechen.
Dein Anlagehorizont ist kurzfristig (Tage bis wenige Wochen). Du suchst nach schnellen Gewinnen durch Momentum und kurzfristige Katalysatoren (News, Earnings).

BEWERTE JEDE AKTIE nach diesen Kriterien:
1. Hat sie kurzfristiges Momentum? (Was sagt der Preis/Volumen?)
2. Gibt es fundamentale News/Katalysatoren, die den aktuellen Trade rechtfertigen?

DEIN OUTPUT:
Für jede analysierte Aktie MUSST DU zwingend mit einem der folgenden Tags starten:
[KAUFEN]
[VERKAUFEN]
[HALTEN]

Darunter MUSST DU exakt 3 kurze und prägnante Stichpunkte (Bullet Points) liefern, die deine Entscheidung als Swing-Trader hart begründen. Keine weichen Formulierungen. Sei entscheidungsfreudig. Erkläre in einem der Stichpunkte auch, auf welcher Annahme / welchem Trigger die Entscheidung basiert.
Nutze die bereitgestellten Tools, um Fakten zu sammeln, bevor du antwortest! Wenn eine News zu alt ist, merke das an.
"""

def analyze_portfolio(depot, watchlist, api_key):
    if not api_key:
        return {"text": "Fehler: Anthropic API Key fehlt.", "input_tokens": 0, "output_tokens": 0}
    
    client = anthropic.Anthropic(api_key=api_key)
    
    stocks_to_analyze = depot + watchlist
    if not stocks_to_analyze:
        return {"text": "Keine Aktien zum Analysieren gefunden.", "input_tokens": 0, "output_tokens": 0}

    user_message = f"Bitte analysiere diese Aktien für mein Swing-Trading: {', '.join(stocks_to_analyze)}."
    
    messages = [{"role": "user", "content": user_message}]
    
    try:
        total_input_tokens = 0
        total_output_tokens = 0
        
        while True:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=ANTHROPIC_TOOLS
            )
            
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens
            
            if response.stop_reason != "tool_use":
                for block in response.content:
                    if block.type == "text":
                        return {
                            "text": block.text,
                            "input_tokens": total_input_tokens,
                            "output_tokens": total_output_tokens
                        }
                return {
                    "text": "Keine finale Text-Antwort erhalten.",
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens
                }
                
            messages.append({"role": "assistant", "content": response.content})
            
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_args = block.input
                    
                    if tool_name == "get_stock_price_and_momentum":
                        result = get_stock_price_and_momentum(tool_args.get("ticker_symbol"))
                    elif tool_name == "search_recent_news":
                        result = search_recent_news(tool_args.get("query"), tool_args.get("max_results", 5))
                    else:
                        result = f"Unbekanntes tool: {tool_name}"
                        
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result)
                    })
            
            messages.append({"role": "user", "content": tool_results})
            
    except Exception as e:
        return {"text": f"Fehler bei der Anthropic-API Kommunikation: {str(e)}", "input_tokens": 0, "output_tokens": 0}
