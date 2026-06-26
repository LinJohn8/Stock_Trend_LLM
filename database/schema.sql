CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY,
    stock_code VARCHAR(16) NOT NULL UNIQUE,
    stock_name VARCHAR(64),
    market VARCHAR(16),
    industry VARCHAR(64),
    added_at DATETIME,
    note TEXT,
    tags VARCHAR(255),
    is_active BOOLEAN
);

CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY,
    stock_code VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64),
    buy_date DATE NOT NULL,
    buy_time TIME,
    buy_price FLOAT NOT NULL,
    quantity INTEGER NOT NULL,
    total_cost FLOAT NOT NULL,
    fee FLOAT,
    current_quantity INTEGER NOT NULL,
    buy_reason TEXT,
    source_info TEXT,
    is_real_position BOOLEAN,
    note TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    status VARCHAR(32)
);

CREATE TABLE IF NOT EXISTS holding_snapshots (
    id INTEGER PRIMARY KEY,
    holding_id INTEGER NOT NULL,
    stock_code VARCHAR(16) NOT NULL,
    date DATE NOT NULL,
    current_price FLOAT NOT NULL,
    market_value FLOAT NOT NULL,
    profit_amount FLOAT NOT NULL,
    profit_rate FLOAT NOT NULL,
    max_profit_rate FLOAT,
    max_drawdown FLOAT,
    holding_days INTEGER,
    benchmark_return FLOAT,
    industry_return FLOAT,
    risk_level VARCHAR(16),
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS stock_daily_data (
    id INTEGER PRIMARY KEY,
    stock_code VARCHAR(16) NOT NULL,
    date DATE NOT NULL,
    open FLOAT NOT NULL,
    high FLOAT NOT NULL,
    low FLOAT NOT NULL,
    close FLOAT NOT NULL,
    volume FLOAT,
    amount FLOAT,
    turnover_rate FLOAT,
    pct_change FLOAT,
    created_at DATETIME,
    UNIQUE(stock_code, date)
);

CREATE TABLE IF NOT EXISTS stock_indicators (
    id INTEGER PRIMARY KEY,
    stock_code VARCHAR(16) NOT NULL,
    date DATE NOT NULL,
    ma5 FLOAT,
    ma10 FLOAT,
    ma20 FLOAT,
    ma60 FLOAT,
    rsi FLOAT,
    macd FLOAT,
    atr FLOAT,
    volatility FLOAT,
    volume_ratio FLOAT,
    trend_score FLOAT,
    momentum_score FLOAT,
    risk_score FLOAT,
    created_at DATETIME,
    UNIQUE(stock_code, date)
);

CREATE TABLE IF NOT EXISTS stock_fundamentals (
    id INTEGER PRIMARY KEY,
    stock_code VARCHAR(16) NOT NULL,
    report_date DATE NOT NULL,
    pe FLOAT,
    pb FLOAT,
    roe FLOAT,
    revenue_growth FLOAT,
    profit_growth FLOAT,
    gross_margin FLOAT,
    debt_ratio FLOAT,
    cash_flow FLOAT,
    created_at DATETIME,
    UNIQUE(stock_code, report_date)
);

CREATE TABLE IF NOT EXISTS news_articles (
    id INTEGER PRIMARY KEY,
    source VARCHAR(64) NOT NULL,
    title VARCHAR(512),
    url VARCHAR(1024),
    published_at DATETIME,
    content TEXT,
    summary TEXT,
    raw_json TEXT,
    content_hash VARCHAR(64) NOT NULL UNIQUE,
    source_credibility FLOAT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS stock_news_evidence (
    id INTEGER PRIMARY KEY,
    stock_code VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64),
    article_id INTEGER NOT NULL,
    relevance_score FLOAT,
    keyword_score FLOAT,
    semantic_score FLOAT,
    reliability_score FLOAT,
    sentiment_score FLOAT,
    matched_keywords TEXT,
    risk_keywords TEXT,
    positive_keywords TEXT,
    event_types TEXT,
    extracted_entities TEXT,
    evidence_reason TEXT,
    created_at DATETIME,
    UNIQUE(stock_code, article_id)
);

CREATE TABLE IF NOT EXISTS ai_signals (
    id INTEGER PRIMARY KEY,
    stock_code VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64),
    signal_date DATE NOT NULL,
    current_price FLOAT,
    action VARCHAR(32),
    confidence FLOAT,
    overall_score FLOAT,
    trend_score FLOAT,
    fundamental_score FLOAT,
    valuation_score FLOAT,
    capital_score FLOAT,
    news_score FLOAT,
    risk_score FLOAT,
    reason TEXT,
    risk_points TEXT,
    invalidation_conditions TEXT,
    suggested_position VARCHAR(32),
    stop_loss_price FLOAT,
    take_profit_price FLOAT,
    ai_model VARCHAR(64),
    raw_ai_response TEXT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS signal_tracking (
    id INTEGER PRIMARY KEY,
    signal_id INTEGER NOT NULL,
    stock_code VARCHAR(16) NOT NULL,
    signal_date DATE NOT NULL,
    price_at_signal FLOAT,
    price_after_1d FLOAT,
    return_1d FLOAT,
    price_after_5d FLOAT,
    return_5d FLOAT,
    price_after_20d FLOAT,
    return_20d FLOAT,
    price_after_60d FLOAT,
    return_60d FLOAT,
    max_drawdown_after_signal FLOAT,
    benchmark_return FLOAT,
    is_success BOOLEAN,
    updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS learning_memories (
    id INTEGER PRIMARY KEY,
    signal_id INTEGER NOT NULL,
    stock_code VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64),
    review_date DATE NOT NULL,
    signal_date DATE NOT NULL,
    horizon_days INTEGER,
    original_action VARCHAR(32),
    confidence FLOAT,
    price_at_signal FLOAT,
    actual_return FLOAT,
    max_drawdown FLOAT,
    benchmark_return FLOAT,
    outcome VARCHAR(32),
    error_type VARCHAR(64),
    possible_causes TEXT,
    evidence_snapshot TEXT,
    lesson TEXT,
    proposed_changes TEXT,
    status VARCHAR(32),
    created_at DATETIME,
    updated_at DATETIME,
    UNIQUE(signal_id, horizon_days)
);

CREATE TABLE IF NOT EXISTS stock_skill_reviews (
    id INTEGER PRIMARY KEY,
    stock_code VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64),
    skill_id VARCHAR(64) NOT NULL,
    skill_name VARCHAR(128),
    review_date DATE NOT NULL,
    input_snapshot TEXT,
    result_text TEXT,
    ai_provider VARCHAR(64),
    ai_model VARCHAR(64),
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS algorithm_runs (
    id INTEGER PRIMARY KEY,
    stock_code VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64),
    run_date DATE NOT NULL,
    selected_algorithms TEXT,
    result_json TEXT,
    overall_score FLOAT,
    action VARCHAR(32),
    confidence FLOAT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS historical_simulations (
    id INTEGER PRIMARY KEY,
    stock_code VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_cash FLOAT,
    strategy_mode VARCHAR(32),
    selected_algorithms TEXT,
    benchmark_code VARCHAR(32),
    fee_rate FLOAT,
    max_position FLOAT,
    summary_json TEXT,
    equity_curve_json TEXT,
    trades_json TEXT,
    diagnostics_json TEXT,
    ai_review TEXT,
    final_return FLOAT,
    benchmark_return FLOAT,
    max_drawdown FLOAT,
    win_rate FLOAT,
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS email_logs (
    id INTEGER PRIMARY KEY,
    send_time DATETIME,
    recipient VARCHAR(255),
    subject VARCHAR(255),
    status VARCHAR(32),
    error_message TEXT,
    html_path VARCHAR(512),
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS system_settings (
    id INTEGER PRIMARY KEY,
    key VARCHAR(128) NOT NULL UNIQUE,
    value TEXT,
    updated_at DATETIME
);
