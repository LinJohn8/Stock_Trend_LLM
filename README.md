# Stock Trend LLM

<p>
  <img src="https://count.getloli.com/@stock_trend_llm?theme=minecraft&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto" alt="Project counter">
</p>

Stock Trend LLM is a local-first A-share market assistant for collecting stock information, calculating explainable indicators, reviewing watchlists and holdings, generating conservative AI-assisted summaries, sending scheduled email reports, and tracking simulated signal performance.

This is **not** an auto-trading system, a broker integration, or a profit-guarantee tool. It is designed for research, information organization, paper trading review, and human confirmation.

Public repository target:

```bash
git clone https://github.com/LinJohn8/Stock_Trend_LLM.git
```

Chinese docs: [README-CN.md](README-CN.md)  
Fast setup: [QUICKSTART.md](QUICKSTART.md)
License: [MIT](LICENSE)

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
- Collect and score stock news evidence before LLM review.
- Send HTML email reports at configurable times. Default sample: `08:50,14:20`.
- Provide a Streamlit dashboard for watchlists, holdings, daily analysis, stock details, backtest review, email settings, and system settings.
- Includes macOS command scripts for local-only or LAN-accessible startup.

## Safety Boundaries

- No automatic real-money trading.
- No broker order API.
- No guaranteed profit claims.
- High-risk stocks are not allowed to receive strong buy output.
- Every recommendation should include evidence, risks, invalidation conditions, and confidence.
- Final investment decisions remain with the user.

## Quick Start

Generic Python start:

```bash
cp .env.sample .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -c "from database.db import init_db; init_db()"
streamlit run dashboard/streamlit_app.py --server.address=127.0.0.1 --server.port=9696
```

Open:

- Dashboard: http://localhost:9696

## macOS Command Startup

Only macOS uses the command launchers:

```bash
chmod +x local.command LAN.command
```

- `local.command`: starts dashboard/API on `127.0.0.1`; only this Mac can access it.
- `LAN.command`: starts dashboard/API on `0.0.0.0`; devices on the same LAN can access it.

You can double-click either file in Finder, or run it from Terminal.

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

The dashboard process also starts APScheduler for daily jobs:

- Streamlit dashboard on port `9696`.
- Scheduled daily analysis and email jobs run in the same local process.

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

## News Evidence

The news module borrows the multi-source realtime aggregation idea from NewsNow and the RSS/keyword/AI-filtering workflow from TrendRadar, then adapts it to stock research:

1. Fetch stock-related news from AKShare/Eastmoney and RSS-style sources.
2. De-duplicate articles with a content hash.
3. Score keyword relevance using stock code, stock name, and custom keywords.
4. Compute a lightweight semantic-overlap score as a first-version RAG retrieval signal.
5. Score source credibility, recency, relevance, sentiment, risk keywords, and positive keywords.
6. Store auditable evidence in `news_articles` and `stock_news_evidence`.
7. Pass only scored evidence to LLM Skills.

Dashboard page: `新闻情报`.

## Logs

- `logs/app.log`
- `logs/scheduler.log`
- `logs/email.log`
- `logs/data_fetch.log`
- `logs/ai_analysis.log`

## Support

If this local research tool helps you, you can support ongoing maintenance with the QR codes below. The dashboard also includes a `支持项目` button in the top-right corner.

<p>
  <img src="assets/support/support_qr_1.jpg" alt="Support QR code 1" width="220">
  <img src="assets/support/support_qr_2.jpg" alt="Support QR code 2" width="220">
</p>

## Disclaimer

This project is for personal research, information collection, indicator calculation, paper trading review, and AI-assisted explanation only. It does not provide investment advice, trading instructions, or profit guarantees. Markets are risky; invest carefully.
