from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class Watchlist(Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("stock_code", name="uq_watchlist_stock_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    stock_name: Mapped[str] = mapped_column(String(64), default="")
    market: Mapped[str] = mapped_column(String(16), default="CN")
    industry: Mapped[str] = mapped_column(String(64), default="")
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    note: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    stock_name: Mapped[str] = mapped_column(String(64), default="")
    buy_date: Mapped[date] = mapped_column(Date)
    buy_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    buy_price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)
    total_cost: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float, default=0)
    current_quantity: Mapped[int] = mapped_column(Integer)
    buy_reason: Mapped[str] = mapped_column(Text, default="")
    source_info: Mapped[str] = mapped_column(Text, default="")
    is_real_position: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    status: Mapped[str] = mapped_column(String(32), default="holding")

    snapshots: Mapped[list["HoldingSnapshot"]] = relationship(
        back_populates="holding",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class HoldingSnapshot(Base):
    __tablename__ = "holding_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    holding_id: Mapped[int] = mapped_column(ForeignKey("holdings.id", ondelete="CASCADE"), index=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    current_price: Mapped[float] = mapped_column(Float)
    market_value: Mapped[float] = mapped_column(Float)
    profit_amount: Mapped[float] = mapped_column(Float)
    profit_rate: Mapped[float] = mapped_column(Float)
    max_profit_rate: Mapped[float] = mapped_column(Float, default=0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0)
    holding_days: Mapped[int] = mapped_column(Integer, default=0)
    benchmark_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    industry_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(16), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    holding: Mapped[Holding] = relationship(back_populates="snapshots")


class StockDailyData(Base):
    __tablename__ = "stock_daily_data"
    __table_args__ = (UniqueConstraint("stock_code", "date", name="uq_stock_daily_code_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0)
    amount: Mapped[float] = mapped_column(Float, default=0)
    turnover_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    pct_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StockIndicator(Base):
    __tablename__ = "stock_indicators"
    __table_args__ = (UniqueConstraint("stock_code", "date", name="uq_stock_indicator_code_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    ma5: Mapped[float | None] = mapped_column(Float, nullable=True)
    ma10: Mapped[float | None] = mapped_column(Float, nullable=True)
    ma20: Mapped[float | None] = mapped_column(Float, nullable=True)
    ma60: Mapped[float | None] = mapped_column(Float, nullable=True)
    rsi: Mapped[float | None] = mapped_column(Float, nullable=True)
    macd: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend_score: Mapped[float] = mapped_column(Float, default=50)
    momentum_score: Mapped[float] = mapped_column(Float, default=50)
    risk_score: Mapped[float] = mapped_column(Float, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StockFundamental(Base):
    __tablename__ = "stock_fundamentals"
    __table_args__ = (UniqueConstraint("stock_code", "report_date", name="uq_fundamental_code_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    pe: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb: Mapped[float | None] = mapped_column(Float, nullable=True)
    roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    debt_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (UniqueConstraint("content_hash", name="uq_news_article_content_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    url: Mapped[str] = mapped_column(String(1024), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_credibility: Mapped[float] = mapped_column(Float, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StockNewsEvidence(Base):
    __tablename__ = "stock_news_evidence"
    __table_args__ = (UniqueConstraint("stock_code", "article_id", name="uq_stock_news_article"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    stock_name: Mapped[str] = mapped_column(String(64), default="")
    article_id: Mapped[int] = mapped_column(ForeignKey("news_articles.id"), index=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    keyword_score: Mapped[float] = mapped_column(Float, default=0)
    semantic_score: Mapped[float] = mapped_column(Float, default=0)
    reliability_score: Mapped[float] = mapped_column(Float, default=0)
    sentiment_score: Mapped[float] = mapped_column(Float, default=50)
    matched_keywords: Mapped[str] = mapped_column(Text, default="[]")
    risk_keywords: Mapped[str] = mapped_column(Text, default="[]")
    positive_keywords: Mapped[str] = mapped_column(Text, default="[]")
    event_types: Mapped[str] = mapped_column(Text, default="[]")
    extracted_entities: Mapped[str] = mapped_column(Text, default="{}")
    evidence_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AISignal(Base):
    __tablename__ = "ai_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    stock_name: Mapped[str] = mapped_column(String(64), default="")
    signal_date: Mapped[date] = mapped_column(Date, index=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    action: Mapped[str] = mapped_column(String(32), default="uncertain")
    confidence: Mapped[float] = mapped_column(Float, default=50)
    overall_score: Mapped[float] = mapped_column(Float, default=50)
    trend_score: Mapped[float] = mapped_column(Float, default=50)
    fundamental_score: Mapped[float] = mapped_column(Float, default=50)
    valuation_score: Mapped[float] = mapped_column(Float, default=50)
    capital_score: Mapped[float] = mapped_column(Float, default=50)
    news_score: Mapped[float] = mapped_column(Float, default=50)
    risk_score: Mapped[float] = mapped_column(Float, default=50)
    reason: Mapped[str] = mapped_column(Text, default="")
    risk_points: Mapped[str] = mapped_column(Text, default="")
    invalidation_conditions: Mapped[str] = mapped_column(Text, default="")
    suggested_position: Mapped[str] = mapped_column(String(32), default="0%")
    stop_loss_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_model: Mapped[str] = mapped_column(String(64), default="rule_based")
    raw_ai_response: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SignalTracking(Base):
    __tablename__ = "signal_tracking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("ai_signals.id"), index=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    signal_date: Mapped[date] = mapped_column(Date, index=True)
    price_at_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_after_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_after_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_after_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_after_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_after_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class LearningMemory(Base):
    __tablename__ = "learning_memories"
    __table_args__ = (UniqueConstraint("signal_id", "horizon_days", name="uq_learning_memory_signal_horizon"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("ai_signals.id"), index=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    stock_name: Mapped[str] = mapped_column(String(64), default="")
    review_date: Mapped[date] = mapped_column(Date, index=True)
    signal_date: Mapped[date] = mapped_column(Date, index=True)
    horizon_days: Mapped[int] = mapped_column(Integer, default=20)
    original_action: Mapped[str] = mapped_column(String(32), default="uncertain")
    confidence: Mapped[float] = mapped_column(Float, default=50)
    price_at_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), default="unknown")
    error_type: Mapped[str] = mapped_column(String(64), default="")
    possible_causes: Mapped[str] = mapped_column(Text, default="[]")
    evidence_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    lesson: Mapped[str] = mapped_column(Text, default="")
    proposed_changes: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class StockSkillReview(Base):
    __tablename__ = "stock_skill_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    stock_name: Mapped[str] = mapped_column(String(64), default="")
    skill_id: Mapped[str] = mapped_column(String(64), index=True)
    skill_name: Mapped[str] = mapped_column(String(128), default="")
    review_date: Mapped[date] = mapped_column(Date, index=True)
    input_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    result_text: Mapped[str] = mapped_column(Text, default="")
    ai_provider: Mapped[str] = mapped_column(String(64), default="")
    ai_model: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AlgorithmRun(Base):
    __tablename__ = "algorithm_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    stock_name: Mapped[str] = mapped_column(String(64), default="")
    run_date: Mapped[date] = mapped_column(Date, index=True)
    selected_algorithms: Mapped[str] = mapped_column(Text, default="[]")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    overall_score: Mapped[float] = mapped_column(Float, default=50)
    action: Mapped[str] = mapped_column(String(32), default="uncertain")
    confidence: Mapped[float] = mapped_column(Float, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class HistoricalSimulation(Base):
    __tablename__ = "historical_simulations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    stock_name: Mapped[str] = mapped_column(String(64), default="")
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    initial_cash: Mapped[float] = mapped_column(Float, default=100000)
    strategy_mode: Mapped[str] = mapped_column(String(32), default="consensus")
    selected_algorithms: Mapped[str] = mapped_column(Text, default="[]")
    benchmark_code: Mapped[str] = mapped_column(String(32), default="sh000300")
    fee_rate: Mapped[float] = mapped_column(Float, default=0.0003)
    max_position: Mapped[float] = mapped_column(Float, default=0.85)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    equity_curve_json: Mapped[str] = mapped_column(Text, default="[]")
    trades_json: Mapped[str] = mapped_column(Text, default="[]")
    price_projection_json: Mapped[str] = mapped_column(Text, default="[]")
    diagnostics_json: Mapped[str] = mapped_column(Text, default="{}")
    ai_review: Mapped[str] = mapped_column(Text, default="")
    final_return: Mapped[float] = mapped_column(Float, default=0)
    benchmark_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FutureSimulationForecast(Base):
    __tablename__ = "future_simulation_forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    stock_name: Mapped[str] = mapped_column(String(64), default="")
    forecast_start_date: Mapped[date] = mapped_column(Date, index=True)
    forecast_end_date: Mapped[date] = mapped_column(Date, index=True)
    horizon_days: Mapped[int] = mapped_column(Integer, default=20)
    base_price: Mapped[float] = mapped_column(Float, default=0)
    selected_algorithms: Mapped[str] = mapped_column(Text, default="[]")
    strategy_mode: Mapped[str] = mapped_column(String(32), default="consensus")
    projection_json: Mapped[str] = mapped_column(Text, default="[]")
    comparison_json: Mapped[str] = mapped_column(Text, default="[]")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    diagnostics_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SimulationAlgorithmPreset(Base):
    __tablename__ = "simulation_algorithm_presets"
    __table_args__ = (UniqueConstraint("name", name="uq_simulation_algorithm_preset_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    selected_algorithms: Mapped[str] = mapped_column(Text, default="[]")
    strategy_mode: Mapped[str] = mapped_column(String(32), default="consensus")
    benchmark_code: Mapped[str] = mapped_column(String(32), default="sh000300")
    fee_rate: Mapped[float] = mapped_column(Float, default=0.0003)
    max_position: Mapped[float] = mapped_column(Float, default=0.85)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    send_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    recipient: Mapped[str] = mapped_column(String(255), default="")
    subject: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error_message: Mapped[str] = mapped_column(Text, default="")
    html_path: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    __table_args__ = (UniqueConstraint("key", name="uq_system_settings_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
