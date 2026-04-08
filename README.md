# 📈 K-Invest: AI Swing Trading Assistant

K-Invest is an automated stock trading assistant powered by Anthropic's Claude API. It evaluates your portfolio and watchlist to provide clear, actionable swing trading recommendations. By combining real-time market data (via yfinance) with recent news catalysts (via DuckDuckGo Search), the Streamlit-based agent helps you identify short-term trading opportunities while tracking API token usage seamlessly.

## ✨ Features

- **Automated AI Analysis**: Leverage Claude (Sonnet 4.6) to get strict `[BUY]`, `[HOLD]`, or `[SELL]` recommendations tailored for short-term swing trading.
- **Real-Time Market Data**: Fetches recent price action, 52-week highs/lows, trading volumes, and momentum metrics via `yfinance`.
- **Catalyst Detection**: Automatically searches for the latest market news and triggers using `ddgs` (DuckDuckGo Search) before making a trading decision.
- **Intuitive Interface**: Built with Streamlit for a clean, user-friendly experience. Easily manage your Depot (Portfolio) and Watchlist directly in the app.
- **Analysis History**: Keeps track of your previous analysis runs in a single session so you can easily compare results.
- **Automated Cost Tracking**: Calculates and displays accurate Anthropic API token usage (input/output) and the estimated cost in $ USD for every single analysis run.

## 🚀 Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/k-invest.git
   cd k-invest
   ```

2. **Create a virtual environment (recommended)**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. **Install the dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## ⚙️ Configuration

The AI agent requires an **Anthropic API Key** to function. You have two options to provide it:
1. Export it as an environment variable in your terminal before running the app:
   ```bash
   export ANTHROPIC_API_KEY="your-api-key-here"
   ```
2. Enter the key securely into the sidebar directly within the Streamlit UI.

## 💻 Usage

Run the Streamlit application from your terminal:

```bash
streamlit run app.py
```

A browser window will automatically open at `http://localhost:8501`. 
1. Add your desired stock tickers (e.g., `AAPL`, `TSLA` or Xetra stocks like `MBG.DE`) to your Depot or Watchlist.
2. Select whether you want to analyze the Depot, the Watchlist, or both.
3. Click "Agenten-Analyse Starten" and wait for the AI to dynamically research and construct your report.

## 🛠️ Tech Stack

- **[Streamlit](https://streamlit.io/)** - Frontend & State Management
- **[Anthropic API](https://docs.anthropic.com/)** - LLM Engine (Claude Sonnet 4.6)
- **[yfinance](https://pypi.org/project/yfinance/)** - Financial Data Provider
- **[ddgs](https://pypi.org/project/ddgs/)** - Web Search Tool for Recent News 
