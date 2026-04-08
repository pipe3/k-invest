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
        
        report = []
        report.append(f'Aktie: {name} ({ticker_symbol})')
        report.append(f'Aktueller Preis: {current_price:.2f} USD')
        report.append(f'Performance (letzte 5 Tage): {momentum_1w:.2f}%')
        report.append(f'52-Wochen-Hoch: {info.get("fiftyTwoWeekHigh", "N/A")}')
        report.append(f'52-Wochen-Tief: {info.get("fiftyTwoWeekLow", "N/A")}')
        report.append(f'Ø Volumen (10 Tage): {info.get("averageDailyVolume10Day", "N/A")}')
        return '\n'.join(report)
    except Exception as e:
        return f'Fehler bei yfinance für {ticker_symbol}: {str(e)}'

def search_recent_news(query: str, max_results: int = 5) -> str:
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
        return f'Fehler bei DDGS für {query}: {str(e)}'

ANTHROPIC_TOOLS = [
    {
        'name': 'get_stock_price_and_momentum',
        'description': 'Holt aktuelle Marktdaten, Preise und kurzfristiges Momentum (Performance letzte 5 Tage, Volumina) für eine Aktie. Nützlich um zu sehen, ob die Aktie Momentum hat.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'ticker_symbol': {
                    'type': 'string',
                    'description': 'Das Ticker-Symbol der Aktie (z.B. AAPL)'
                }
            },
            'required': ['ticker_symbol']
        }
    },
    {
        'name': 'search_recent_news',
        'description': 'Sucht im Web nach den aktuellsten Nachrichten zu einem Unternehmen (die letzten 7 Tage).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {
                    'type': 'string',
                    'description': 'Der Suchbegriff, z.B. "Apple stock news"'
                },
                'max_results': {
                    'type': 'integer',
                    'description': 'Anzahl der Suchergebnisse (Standard: 5)'
                }
            },
            'required': ['query']
        }
    }
]
