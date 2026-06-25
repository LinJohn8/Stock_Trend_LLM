# Stock Trend LLM / 股票 AI 辅助决策系统

这是一个本地优先的中国 A 股信息收集、指标分析、持仓复盘和 AI 辅助解释系统。项目目标不是自动量化交易，也不是荐股软件，而是帮助不太懂股票的人把每天需要看的信息整理清楚：行情、指标、风险、新闻/公告、持仓盈亏、模拟建议表现和邮件日报。

公开仓库：

```bash
git clone https://github.com/LinJohn8/Stock_Trend_LLM.git
```

快速启动见：[QUICKSTART.md](QUICKSTART.md)

## 重要边界

- 不承诺盈利。
- 不自动实盘下单。
- 不接券商交易接口。
- 不输出“稳赚”“必涨”“确定买入”。
- AI 只是辅助解释，最终决策由用户自己判断。
- 高风险股票不会输出强买入建议。
- 每个建议都应包含数据依据、风险点、反向条件、建议动作和置信度。

## 主要功能

- 自选股管理：添加、暂停、删除、备注、标签、手动分析。
- 持仓管理：记录买入日期、时间、价格、数量、手续费、买入理由、参考信息、真实/模拟持仓。
- 数据获取：第一版使用 AKShare 获取 A 股日线、实时行情、指数和可得基本面字段。
- 指标计算：MA5/10/20/60、RSI、MACD、ATR、近 5/20/60 日涨跌幅、量比、波动率、最大回撤。
- 风险控制：ST、跌破 MA20、跌破 MA60、放量下跌、短期涨幅过大、成交量不足、负面关键词、止损/止盈阈值。
- 综合评分：技术面、基本面、估值、资金面、消息面、风险控制。
- AI 分析：支持 DeepSeek/OpenAI/GLM 风格 Provider，默认可关闭，规则引擎仍可运行。
- 邮件日报：支持多个发送时间，当前配置为早上 `08:50` 和下午 `14:20`。
- 模拟复盘：保存每条建议，追踪未来 1/5/20/60 日收益和最大回撤。
- 学习记忆：把模拟建议的错误或不确定结果记录成可审计的复盘条目，包括可能原因、证据快照和后续规则修改建议。
- LLM Skill 查看：在指标、风险、持仓、历史记忆等计算完成后，选择不同 Skill 让 LLM 从保守决策、技术信号、新闻风险、历史错误记忆等角度解释。
- 算法分析：仪表盘可输入股票代码拉取数据，并勾选趋势、动量、均值回归、估值、资金量价、新闻风险、持仓复核、历史记忆等算法组合运行。
- Streamlit 仪表盘：首页、自选股、持仓、每日分析、股票详情、模拟复盘、邮件设置、系统设置。
- Docker 长期运行：仪表盘和 FastAPI/定时器分成两个服务。

## 安装与启动

Docker 首次构建或依赖变更后：

```bash
cp .env.sample .env
./docker-build.command
```

日常启动，不重新 build：

```bash
./start.command
```

macOS 双击启动：

```bash
chmod +x start.command start_api.command docker-build.command start_local.command
open start.command
```

如果 Docker Hub 访问超时，可以先用本地 Python 方式启动：

```bash
./start_local.command
```

本地 Python：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
python -c "from database.db import init_db; init_db()"
streamlit run dashboard/streamlit_app.py
```

打开：

- 仪表盘：http://localhost:8501
- API 健康检查：http://localhost:8000/health

## 配置邮箱和 DeepSeek

真实密钥只写入 `.env`，不要提交到 GitHub。`.gitignore` 已忽略 `.env`。

公开样例在 `.env.sample`：

```env
EMAIL_ENABLED=true
EMAIL_SEND_TIMES=08:50,14:20
EMAIL_TIMEZONE=Asia/Shanghai
EMAIL_HOST=smtp.qq.com
EMAIL_PORT=465
EMAIL_USE_SSL=true
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

也兼容这些变量名：

```env
SMTP_SERVER=smtp.qq.com
SMTP_PORT=465
SENDER_EMAIL=your_email@qq.com
SENDER_PASS=your_smtp_auth_code
RECEIVER_EMAIL=your_receive_email@qq.com
```

## 每日邮件逻辑

项目长期运行时，FastAPI 服务会启动 APScheduler。

当前默认每天两个时间点：

- 08:50
- 14:20

邮件只汇总当前项目里仍处于 active 状态的自选股和 active 持仓。已暂停跟踪的股票不会进入日报筛选。

## 常用命令

```bash
# 手动更新数据
python -m tasks.update_market_data 600519

# 手动运行每日任务
python -m tasks.daily_job

# 手动发送今日邮件
python -m tasks.send_daily_email

# 更新模拟复盘追踪
python -m backtest.runner

# 根据失败模拟建议生成学习记忆
python -m tasks.generate_learning_memory

# 成功样本也一起记录
python -m tasks.generate_learning_memory --include-success

# 测试
pytest
```

## 学习记忆机制

项目不会让 LLM 静默修改规则，而是把每次模拟建议和现实表现拆开记录：

- `ai_signals`：记录原始建议、评分、理由、风险点和失效条件。
- `signal_tracking`：记录未来 1/5/20/60 日收益、最大回撤、是否成功。
- `learning_memories`：记录失败或不确定样本，包括错误类型、可能原因、证据快照、经验总结和建议修改。

记忆状态包括：

- `open`：待复盘。
- `reviewed`：已人工看过。
- `applied`：已经用于规则或数据源更新。
- `ignored`：暂不处理。

后续你更新项目时，可以优先查看“学习记忆”页面，把重复出现的问题转化为新的指标、数据源、权重或风控规则。

## LLM Skill 查看

仪表盘新增“LLM Skill 查看”页面。它不是直接让 LLM 猜股票，而是先读取系统计算后的上下文：

- 最近行情数据
- 技术指标
- 基本面和估值
- 消息面关键词
- 风险规则结果
- 最新 AI/规则信号
- 当前持仓信息
- 历史学习记忆

然后你可以选择：

- 不使用 Skill，只查看计算结果快照。
- `1. 保守决策复核`
- `2. 技术信号解释`
- `3. 新闻风险核查`
- `4. 历史错误记忆复盘`

每次 Skill 查看都会保存到 `stock_skill_reviews` 表，后续可以在仪表盘里查看输入快照和 LLM 输出。

## 算法分析

仪表盘新增“算法分析”页面。流程是：

1. 输入股票代码。
2. 选择是否先拉取/更新日线数据。
3. 勾选要使用的算法。
4. 运行分析并保存到 `algorithm_runs` 表。

当前内置算法包括：

- 趋势跟踪
- 动量强弱
- 回撤修复
- 估值检查
- 资金量价
- 新闻风险
- 持仓复核
- 历史记忆

这些算法是确定性计算模块，适合先给出可解释的数值和理由；LLM Skill 可以在这些计算之后再做中文解释和复盘。

## 日志

- `logs/app.log`
- `logs/scheduler.log`
- `logs/email.log`
- `logs/data_fetch.log`
- `logs/ai_analysis.log`

## 后续扩展

- 接入更完整的公告、新闻、巨潮资讯、东方财富信息。
- 接入 Tushare Pro 财务、北向资金、龙虎榜、主力资金。
- 增加真实交易日历、停牌检测、ST 检测强化。
- 增加行业指数和沪深300对比。
- 把系统设置页改成可写配置。
- 后续可从 Streamlit 迁移为 FastAPI + Vue。

## 免责声明

本项目生成内容仅用于个人研究、信息整理、指标计算、模拟复盘和 AI 辅助解释，不构成投资建议、交易指令或收益承诺。市场有风险，投资需谨慎。
