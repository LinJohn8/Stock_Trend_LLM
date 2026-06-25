# Stock Trend LLM

Stock Trend LLM is a local-first A-share market assistant for collecting stock information, calculating explainable indicators, reviewing watchlists and holdings, generating conservative AI-assisted summaries, sending scheduled email reports, and tracking simulated signal performance.

This is **not** an auto-trading system, a broker integration, or a profit-guarantee tool. It is designed for research, information organization, paper trading review, and human confirmation.

Public repository target:

```bash
git clone https://github.com/LinJohn8/Stock_Trend_LLM.git
```

Chinese docs: [README-CN.md](README-CN.md)  
Fast setup: [QUICKSTART.md](QUICKSTART.md)

## What It Does

- Manage A-share watchlists and holdings.
- Fetch historical and realtime market data through AKShare.
- Calculate MA5/MA10/MA20/MA60, RSI, MACD, ATR, volatility, returns, volume ratio, and max drawdown.
- Score technical, fundamental, valuation, capital, news, and risk dimensions.
- Generate conservative actions: `watch`, `buy_candidate`, `hold`, `reduce`, `sell`, `avoid`, `uncertain`.
- Save every signal for paper-trading review.
- Track 1/5/20/60-day forward returns for historical signals.
- Create learning memories from failed or uncertain simulated decisions, including possible causes, evidence snapshots, and proposed rule changes.
- Run selectable LLM review skills after deterministic calculations, such as conservative decision review, technical signal explanation, news risk checking, and learning-memory review.
- Run selectable deterministic analysis algorithms from the dashboard after pulling stock data.
- Send HTML email reports at configurable times. Default sample: `08:50,14:20`.
- Provide a Streamlit dashboard for watchlists, holdings, daily analysis, stock details, backtest review, email settings, and system settings.
- Run with Docker Compose for long-running local use.

## Safety Boundaries

- No automatic real-money trading.
- No broker order API.
- No guaranteed profit claims.
- High-risk stocks are not allowed to receive strong buy output.
- Every recommendation should include evidence, risks, invalidation conditions, and confidence.
- Final investment decisions remain with the user.

## Quick Start

```bash
cp .env.sample .env
docker compose up --build
```

Open:

- Dashboard: http://localhost:8501
- API health check: http://localhost:8000/health

On macOS you can also double-click:

```bash
open start.command
```

## Local Python Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
python -c "from database.db import init_db; init_db()"
streamlit run dashboard/streamlit_app.py
```

## Environment Variables

Never commit your real `.env`. It is ignored by `.gitignore`.

Use `.env.sample` for public configuration examples:

```env
EMAIL_SEND_TIMES=08:50,14:20
EMAIL_HOST=smtp.qq.com
EMAIL_PORT=465
EMAIL_USERNAME=your_email@qq.com
EMAIL_PASSWORD=your_smtp_auth_code
EMAIL_FROM=your_email@qq.com
EMAIL_TO=your_receive_email@qq.com

AI_ENABLED=true
AI_PROVIDER=deepseek
AI_API_KEY=your_deepseek_api_key
AI_MODEL=deepseek-chat
AI_BASE_URL=https://api.deepseek.com/v1
```

The app also accepts legacy variable names:

```env
SMTP_SERVER=smtp.qq.com
SMTP_PORT=465
SENDER_EMAIL=your_email@qq.com
SENDER_PASS=your_smtp_auth_code
RECEIVER_EMAIL=your_receive_email@qq.com
```

## Common Commands

```bash
# Run dashboard
streamlit run dashboard/streamlit_app.py

# Run FastAPI and scheduler
uvicorn main:app --host 0.0.0.0 --port 8000

# Run daily analysis manually
python -m tasks.daily_job

# Send today's report manually
python -m tasks.send_daily_email

# Update one stock
python -m tasks.update_market_data 600519

# Update signal tracking
python -m backtest.runner

# Generate learning memories from failed simulated signals
python -m tasks.generate_learning_memory

# Record successful signals too
python -m tasks.generate_learning_memory --include-success

# Test
pytest
```

## Long-Running Use

`docker-compose.yml` starts two services:

- `stock-ai-dashboard`: Streamlit dashboard on port `8501`.
- `stock-ai-api`: FastAPI plus APScheduler on port `8000`.

The scheduler registers one daily job per configured send time. For example:

```env
EMAIL_SEND_TIMES=08:50,14:20
```

Reports only include currently active watchlist stocks and active holdings.

## Learning Memory

The project records an auditable memory trail for model and rule improvement:

- `ai_signals` stores the original recommendation, scores, risks, and reasoning.
- `signal_tracking` stores future 1/5/20/60-day outcomes.
- `learning_memories` stores failed or uncertain cases with:
  - original action and confidence
  - actual forward return and max drawdown
  - failure type
  - possible causes
  - evidence snapshot
  - proposed rule or data-source changes
  - review status: `open`, `reviewed`, `applied`, `ignored`

This memory does not silently change trading rules. It gives you a structured backlog for future project updates.

## LLM Review Skills

The dashboard includes an `LLM Skill 查看` page. It first builds a computed context snapshot, then optionally runs a selected LLM skill:

- No skill: inspect raw computed context only.
- `1. 保守决策复核`
- `2. 技术信号解释`
- `3. 新闻风险核查`
- `4. 历史错误记忆复盘`

Each skill review is saved in `stock_skill_reviews` with the input snapshot, selected skill, model, provider, and output text.

## Selectable Algorithms

The dashboard includes an `算法分析` page:

1. Enter a stock code.
2. Pull or refresh historical data.
3. Select algorithms.
4. Run and save the result to `algorithm_runs`.

Built-in algorithms:

- Trend following
- Momentum
- Mean reversion
- Valuation
- Capital/volume
- News risk
- Holding review
- Learning memory

## Logs

- `logs/app.log`
- `logs/scheduler.log`
- `logs/email.log`
- `logs/data_fetch.log`
- `logs/ai_analysis.log`

## Disclaimer

This project is for personal research, information collection, indicator calculation, paper trading review, and AI-assisted explanation only. It does not provide investment advice, trading instructions, or profit guarantees. Markets are risky; invest carefully.
