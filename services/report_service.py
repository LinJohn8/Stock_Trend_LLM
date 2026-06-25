from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config.settings import get_settings
from services.holding_service import HoldingService
from services.portfolio_service import PortfolioService
from services.signal_service import SignalService
from utils.time_utils import is_probable_cn_trading_day, now_tz


class ReportService:
    def __init__(self) -> None:
        self.settings = get_settings()
        template_dir = self.settings.root_dir / "reports" / "templates"
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def build_daily_context(self, signals: list[dict] | None = None) -> dict:
        if signals is None:
            signals = [_signal_to_dict(s) for s in SignalService().latest_signals(limit=100)]
        active_codes = self._active_report_codes()
        if active_codes:
            signals = [s for s in signals if s.get("stock_code") in active_codes]
        today_signals = [s for s in signals if str(s.get("signal_date")) == now_tz().date().isoformat()]
        if not today_signals:
            today_signals = signals[:20]
        today_signals = _latest_per_stock(today_signals)
        high_risk = [s for s in today_signals if s.get("risk_score", 50) < 35 or s.get("action") in ["reduce", "sell", "avoid"]]
        buy_candidates = [s for s in today_signals if s.get("action") == "buy_candidate"]
        holding_actions = [s for s in today_signals if s.get("action") in ["hold", "reduce", "sell"]]
        focus = sorted(today_signals, key=lambda x: (x.get("risk_score", 50), -x.get("overall_score", 50)))[:5]
        return {
            "today": now_tz().date(),
            "is_trading_day": is_probable_cn_trading_day(),
            "market_summary": "第一版市场环境使用交易日与股票池信号聚合，后续可接入指数和行业广度。",
            "signals": today_signals,
            "high_risk": high_risk,
            "buy_candidates": buy_candidates,
            "holding_actions": holding_actions,
            "focus": focus,
            "disclaimer": "本报告由程序和 AI 自动生成，仅用于个人研究和辅助决策，不构成投资建议。市场有风险，投资需谨慎。",
        }

    def _active_report_codes(self) -> set[str]:
        watchlist = PortfolioService().list_watchlist(active_only=True)
        holdings = HoldingService().list_holdings(active_only=True)
        return {item.stock_code for item in watchlist} | {item.stock_code for item in holdings}

    def render_daily_html(self, context: dict | None = None) -> tuple[str, Path]:
        context = context or self.build_daily_context()
        template = self.env.get_template("daily_email.html")
        html = template.render(**context)
        path = self.settings.report_dir / f"daily_report_{date.today().isoformat()}.html"
        path.write_text(html, encoding="utf-8")
        return html, path


def _signal_to_dict(signal) -> dict:
    return {
        "id": signal.id,
        "stock_code": signal.stock_code,
        "stock_name": signal.stock_name,
        "signal_date": signal.signal_date,
        "current_price": signal.current_price,
        "action": signal.action,
        "confidence": signal.confidence,
        "overall_score": signal.overall_score,
        "trend_score": signal.trend_score,
        "fundamental_score": signal.fundamental_score,
        "valuation_score": signal.valuation_score,
        "capital_score": signal.capital_score,
        "news_score": signal.news_score,
        "risk_score": signal.risk_score,
        "reason": signal.reason,
        "risk_points": signal.risk_points,
        "invalidation_conditions": signal.invalidation_conditions,
        "suggested_position": signal.suggested_position,
        "stop_loss_price": signal.stop_loss_price,
        "take_profit_price": signal.take_profit_price,
    }


def _latest_per_stock(signals: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for signal in sorted(signals, key=lambda x: x.get("id") or 0, reverse=True):
        code = signal.get("stock_code")
        if code and code not in latest:
            latest[code] = signal
    return list(latest.values())
