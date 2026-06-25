from __future__ import annotations

from sqlalchemy import select

from database.db import session_scope
from database.models import StockFundamental
from services.stock_data_service import StockDataService
from utils.math_utils import clamp
from utils.stock_utils import normalize_stock_code


class FundamentalService:
    def analyze(self, stock_code: str) -> dict:
        code = normalize_stock_code(stock_code)
        StockDataService().update_fundamentals(code)
        with session_scope() as session:
            item = session.scalar(
                select(StockFundamental)
                .where(StockFundamental.stock_code == code)
                .order_by(StockFundamental.report_date.desc())
            )
        if not item:
            return self._empty()

        fundamental_score = 50
        valuation_score = 50
        if item.roe is not None:
            fundamental_score += item.roe * 0.5
        if item.revenue_growth is not None:
            fundamental_score += item.revenue_growth * 0.2
        if item.profit_growth is not None:
            fundamental_score += item.profit_growth * 0.2
        if item.debt_ratio is not None and item.debt_ratio > 70:
            fundamental_score -= 15
        if item.pe is not None:
            valuation_score += 15 if 0 < item.pe < 30 else -10 if item.pe > 80 else 0
        if item.pb is not None:
            valuation_score += 10 if 0 < item.pb < 4 else -10 if item.pb > 8 else 0

        summary = f"PE={item.pe or '-'}，PB={item.pb or '-'}；第一版基本面以可得数据为准，财报细项接口已预留。"
        return {
            "fundamental_score": clamp(fundamental_score),
            "valuation_score": clamp(valuation_score),
            "fundamental_summary": summary,
            "pe": item.pe,
            "pb": item.pb,
            "roe": item.roe,
        }

    def _empty(self) -> dict:
        return {
            "fundamental_score": 50,
            "valuation_score": 50,
            "fundamental_summary": "基本面数据暂不足，维持中性评分。",
            "pe": None,
            "pb": None,
            "roe": None,
        }
