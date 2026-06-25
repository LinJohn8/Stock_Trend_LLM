# Quick Start

## 1. Clone

```bash
git clone https://github.com/LinJohn8/Stock_Trend_LLM.git
cd Stock_Trend_LLM
```

## 2. Configure

```bash
cp .env.sample .env
```

Edit `.env` and fill in your own email SMTP authorization code and DeepSeek API key.

Do not commit `.env`.

## 3. Start With Docker

```bash
docker compose up --build
```

Open:

- Dashboard: http://localhost:8501
- API health check: http://localhost:8000/health

## 4. macOS Double-Click Start

```bash
chmod +x start.command start_api.command
open start.command
```

## 5. Local Python Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
python -c "from database.db import init_db; init_db()"
streamlit run dashboard/streamlit_app.py
```

## 6. Add Stocks

Open http://localhost:8501:

- Add watchlist stocks in `自选股管理`.
- Add positions in `持仓管理`.
- Run `手动触发每日分析` from the dashboard home page.

## 7. Scheduled Email

Default sample schedule:

```env
EMAIL_SEND_TIMES=08:50,14:20
```

The scheduler runs in the FastAPI service. With Docker Compose, it starts automatically as `stock-ai-api`.

## 8. Manual Commands

```bash
python -m tasks.daily_job
python -m tasks.send_daily_email
python -m tasks.update_market_data 600519
python -m backtest.runner
python -m tasks.generate_learning_memory
pytest
```

## 9. Learning Memory

After signals have real forward data, generate memory records:

```bash
python -m tasks.generate_learning_memory
```

Open the dashboard page `学习记忆` to review possible causes, evidence snapshots, and proposed rule changes.

## Reminder

This project is for information collection, indicator calculation, simulated review, and AI-assisted explanation. It is not an auto-trading system and does not provide investment advice or profit guarantees.
