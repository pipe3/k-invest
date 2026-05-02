import json
import anthropic
from podcast_tools import get_latest_video_id, get_video_transcript

SYSTEM_PROMPT = """<role>
Du bist ein spezialisierter Investment-Analyst für den "Doppelgänger Tech Talk" Podcast. Deine Aufgabe ist es, das Transkript der aktuellsten Folge für Swing-Trader zu analysieren.
</role>

<instructions>
1. Durchsuche das bereitgestellte Transkript gezielt nach Aktienanalysen, Tickersymbolen ($TKR) und Markteinschätzungen.
2. Filtere die Informationen auf Swing-Trading-Relevanz (kurzfristige Katalysatoren, Earnings, Momentum).
3. Achte besonders auf Pips Einschätzungen zu "Fair Value" vs. "Markt-Hype".
4. Erwähne explizit, wenn Termine für die kommende Woche (Earnings, Konferenzen) genannt werden.
5. Bleibe sachlich, präzise und direkt.
6. Berücksichtige die "Bisherige Watchlist" (falls vorhanden) und aktualisiere den Status bestehender Aktien basierend auf der neuen Folge, oder entferne sie, wenn die These "tot" ist.
7. DU MUSST ZWINGEND das Tool `save_doppelgaenger_watchlist` aufrufen, um die resultierende Watchlist strukturiert an das System zu übergeben.
</instructions>

<output_format>
Gib deine Analyse textuell als Markdown aus. (Du musst zusätzlich das Tool aufrufen!)

### 1. Analyse der aktuellen Folge
| Aktie (Ticker) | Empfehlung | Die These (Warum jetzt?) | Katalysator (Event/Datum) | Risiko |
| :--- | :--- | :--- | :--- | :--- |
| z.B. $META | BEOBACHTEN | Capex-Angst übertrieben | Bodenbildung abwarten | Hohe Zinsen |

### 2. Laufende Doppelgänger-Watchlist
Zeige diese Liste auch im Text noch einmal an.
| Ticker | Einstiegs-These | Aktueller Status | Letztes Update |
| :--- | :--- | :--- | :--- |
| z.B. $GOOGL | Cloud-Wachstum | BULLISH (Momentum hält) | Aktuelle Folge |
</output_format>
"""

TOOLS = [
    {
        "name": "save_doppelgaenger_watchlist",
        "description": "Speichert die aktualisierte Doppelgänger-Watchlist im System. Dieser Aufruf ist ZWINGEND ERFORDERLICH, damit die App die Aktien strukturiert speichern kann.",
        "input_schema": {
            "type": "object",
            "properties": {
                "watchlist": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string", "description": "Ticker Symbol, z.B. AAPL"},
                            "thesis": {"type": "string", "description": "Die Einstiegs-These kurz zusammengefasst."},
                            "status": {"type": "string", "description": "Aktueller Status, z.B. BULLISH, BEARISH, BEOBACHTEN"},
                            "last_update": {"type": "string", "description": "Wann wurde es zuletzt aktualisiert (z.B. Folge #558 oder Aktuelle Folge)"}
                        },
                        "required": ["ticker", "thesis", "status", "last_update"]
                    }
                }
            },
            "required": ["watchlist"]
        }
    }
]

def analyze_latest_podcast(youtube_api_key: str, anthropic_api_key: str, previous_watchlist: list) -> dict:
    if not youtube_api_key or not anthropic_api_key:
        return {"error": "API Keys für YouTube und Anthropic werden benötigt."}

    # 1. Get Latest Video
    video_info = get_latest_video_id(youtube_api_key, "@doppelgaengerio")
    if "error" in video_info:
        return {"error": video_info["error"]}
        
    video_id = video_info["video_id"]
    title = video_info["title"]
    
    # 2. Get Transcript
    transcript = get_video_transcript(video_id)
    if "Fehler" in transcript:
        return {"error": transcript}
        
    # 3. Call Anthropic
    client = anthropic.Anthropic(api_key=anthropic_api_key)
    
    user_content = f"""<context>
Hier ist die bisherige Watchlist:
{json.dumps(previous_watchlist, indent=2)}

Hier ist das Transkript der aktuellen Folge ('{title}'):
{transcript}
</context>
"""

    messages = [{"role": "user", "content": user_content}]
    
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=TOOLS,
            tool_choice={"type": "tool", "name": "save_doppelgaenger_watchlist"}
        )
        
        # We forced the tool choice, so we expect a tool use block
        result_text = ""
        new_watchlist = []
        
        for block in response.content:
            if block.type == "text":
                result_text += block.text + "\n"
            elif block.type == "tool_use":
                if block.name == "save_doppelgaenger_watchlist":
                    new_watchlist = block.input.get("watchlist", [])
                    
        # Since we used tool_choice, Claude might not have output text. 
        # If result_text is empty, we need a second turn to generate the text.
        if not result_text.strip():
            # Add assistant message with tool call
            messages.append({"role": "assistant", "content": response.content})
            # Add user message simulating tool result
            messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": response.content[0].id if response.content[0].type == "tool_use" else response.content[1].id, "content": "Gespeichert. Bitte gib nun die finale Markdown-Tabelle aus."}]})
            
            # Request second turn
            text_response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=messages
            )
            
            for block in text_response.content:
                if block.type == "text":
                    result_text += block.text + "\n"
        
        return {
            "success": True,
            "title": title,
            "text": result_text,
            "new_watchlist": new_watchlist
        }
    except Exception as e:
        return {"error": f"Anthropic API Fehler: {str(e)}"}
