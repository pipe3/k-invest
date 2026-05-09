import yfinance as yf
from ddgs import DDGS


def get_stock_price_and_momentum(ticker_symbol: str) -> str:
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period='1mo')
        if hist.empty:
            return f'Keine Daten für {ticker_symbol} gefunden.'

        current_price = hist['Close'].iloc[-1]
        price_1_week_ago = hist['Close'].iloc[-6] if len(hist) > 5 else hist['Close'].iloc[0]
        momentum_1w = ((current_price - price_1_week_ago) / price_1_week_ago) * 100

        info = stock.info
        name = info.get('shortName', ticker_symbol)

        report = [
            f'Aktie: {name} ({ticker_symbol})',
            f'Aktueller Preis: {current_price:.2f} USD',
            f'Performance (letzte 5 Tage): {momentum_1w:.2f}%',
            f'52-Wochen-Hoch: {info.get("fiftyTwoWeekHigh", "N/A")}',
            f'52-Wochen-Tief: {info.get("fiftyTwoWeekLow", "N/A")}',
            f'Ø Volumen (10 Tage): {info.get("averageDailyVolume10Day", "N/A")}',
        ]
        return '\n'.join(report)
    except Exception as e:
        return f'Fehler bei yfinance für {ticker_symbol}: {str(e)}'


def _search_duckduckgo(query: str, max_results: int) -> str:
    try:
        ddgs = DDGS()
        results = ddgs.text(query, max_results=max_results, safesearch='Moderate', timelimit='w')
        if not results:
            return f'Keine News für {query} gefunden.'
        report = []
        for r in results:
            report.append(f'Titel: {r.get("title")}')
            report.append(f'Auszug: {r.get("body")}\n')
        return '\n'.join(report)
    except Exception as e:
        return f'Fehler bei DuckDuckGo für {query}: {str(e)}'


def _search_google(query: str, max_results: int, api_key: str, cx_id: str) -> str:
    try:
        from googleapiclient.discovery import build
        service = build("customsearch", "v1", developerKey=api_key)
        res = service.cse().list(q=query, cx=cx_id, num=min(max_results, 10)).execute()
        items = res.get("items", [])
        if not items:
            return f'Keine Ergebnisse für {query} gefunden.'
        report = []
        for item in items:
            report.append(f'Titel: {item.get("title")}')
            report.append(f'Auszug: {item.get("snippet")}\n')
        return '\n'.join(report)
    except Exception as e:
        return f'Fehler bei Google Search für {query}: {str(e)}'


def _search_tavily(query: str, max_results: int, api_key: str) -> str:
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        response = client.search(query, max_results=max_results)
        results = response.get("results", [])
        if not results:
            return f'Keine Ergebnisse für {query} gefunden.'
        report = []
        for r in results:
            report.append(f'Titel: {r.get("title")}')
            report.append(f'Auszug: {r.get("content")}\n')
        return '\n'.join(report)
    except Exception as e:
        return f'Fehler bei Tavily für {query}: {str(e)}'


def search_recent_news(query: str, max_results: int = 5,
                       search_engine: str = "duckduckgo",
                       google_api_key: str = None, google_cx_id: str = None,
                       tavily_api_key: str = None) -> str:
    if search_engine == "google" and google_api_key and google_cx_id:
        return _search_google(query, max_results, google_api_key, google_cx_id)
    elif search_engine == "tavily" and tavily_api_key:
        return _search_tavily(query, max_results, tavily_api_key)
    else:
        return _search_duckduckgo(query, max_results)


ANTHROPIC_TOOLS = [
    {
        'name': 'save_price_targets',
        'description': 'Speichert Kursziel und Stop-Loss für Depot-Aktien. Nach der Analyse aufrufen — ein Eintrag pro Depot-Aktie.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'targets': {
                    'type': 'array',
                    'description': 'Liste der Kursziele und Stop-Loss für alle Depot-Aktien',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'ticker': {'type': 'string', 'description': 'Ticker-Symbol, z.B. NVDA'},
                            'kursziel': {'type': 'number', 'description': 'Kursziel in EUR'},
                            'stop_loss': {'type': 'number', 'description': 'Stop-Loss-Kurs in EUR'},
                        },
                        'required': ['ticker', 'kursziel', 'stop_loss'],
                    },
                }
            },
            'required': ['targets'],
        }
    },
    {
        'name': 'get_stock_price_and_momentum',
        'description': 'Holt aktuelle Marktdaten, Preise und kurzfristiges Momentum (Performance letzte 5 Tage, Volumina) für eine Aktie.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'ticker_symbol': {
                    'type': 'string',
                    'description': 'Das Ticker-Symbol der Aktie (z.B. AAPL)',
                }
            },
            'required': ['ticker_symbol'],
        }
    },
    {
        'name': 'search_recent_news',
        'description': 'Sucht im Web nach den aktuellsten Nachrichten zu einem Unternehmen oder Sektor.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {
                    'type': 'string',
                    'description': 'Der Suchbegriff, z.B. "NVIDIA AI infrastructure stock 2025"',
                },
                'max_results': {
                    'type': 'integer',
                    'description': 'Anzahl der Suchergebnisse (Standard: 5)',
                }
            },
            'required': ['query'],
        }
    },
]
