# Quick Start

<p>
  <img src="https://count.getloli.com/@stock_trend_llm_quickstart?theme=minecraft&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto" alt="Quickstart counter">
</p>

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

## 3. Generic Python Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -c "from database.db import init_db; init_db()"
streamlit run dashboard/streamlit_app.py --server.address=127.0.0.1 --server.port=9696
```

Open:

- Dashboard: http://localhost:9696

## 4. macOS Command Start

Only macOS uses the command launchers:

```bash
chmod +x local.command LAN.command
```

- `local.command`: local-only startup.
- `LAN.command`: LAN-accessible startup.

You can double-click either file in Finder.

## 5. Manual Dashboard Only

```bash
streamlit run dashboard/streamlit_app.py
```

## 6. Add Stocks

Open http://localhost:9696:

- Add watchlist stocks in `自选股管理`.
- Add positions in `持仓管理`.
- Run `手动触发每日分析` from the dashboard home page.

## 7. Scheduled Email

Default sample schedule:

```env
EMAIL_SEND_TIMES=08:50,12:50
```

The scheduler runs in the dashboard process.

## 8. Manual Commands

```bash
python -m tasks.daily_job
python -m tasks.send_daily_email
python -m tasks.update_market_data 600519
python -m tasks.update_news 600519 --name 贵州茅台
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

## 10. LLM Skill Review

Open `LLM Skill 查看` in the dashboard:

- Choose a stock.
- Choose `不使用 Skill` to inspect computed context.
- Or choose one of the built-in skills to ask the LLM for a focused review.

The review is saved and can be inspected later with its original input snapshot.

## 11. Algorithm Selection

Open `算法分析` in the dashboard:

- Enter a stock code.
- Enable `运行前拉取/更新数据`.
- Select one or more algorithms.
- Run analysis.

Results are saved in `algorithm_runs` and can be reviewed later.

## Reminder

This project is for information collection, indicator calculation, simulated review, and AI-assisted explanation. It is not an auto-trading system and does not provide investment advice or profit guarantees.

## Support

The dashboard has a top-right `支持项目` button. The same support QR codes are also available here:

<p>
  <img src="assets/support/support_qr_1.jpg" alt="Support QR code 1" width="180">
  <img src="assets/support/support_qr_2.jpg" alt="Support QR code 2" width="180">
</p>
