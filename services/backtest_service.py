from __future__ import annotations

from sqlalchemy import select

from database.db import session_scope
from database.models import AISignal, SignalTracking, StockDailyData
from services.memory_service import MemoryService


class BacktestService:
    """Track forward returns for saved AI signals."""

    def update_tracking(self) -> int:
        updated = 0
        with session_scope() as session:
            tracks = list(session.scalars(select(SignalTracking)).all())
            for track in tracks:
                prices = list(
                    session.scalars(
                        select(StockDailyData)
                        .where(
                            StockDailyData.stock_code == track.stock_code,
                            StockDailyData.date >= track.signal_date,
                        )
                        .order_by(StockDailyData.date)
                    )
                )
                if not prices or not track.price_at_signal:
                    continue
                closes = [p.close for p in prices]
                for days, price_attr, ret_attr in [
                    (1, "price_after_1d", "return_1d"),
                    (5, "price_after_5d", "return_5d"),
                    (20, "price_after_20d", "return_20d"),
                    (60, "price_after_60d", "return_60d"),
                ]:
                    if len(closes) > days:
                        price = closes[days]
                        setattr(track, price_attr, price)
                        setattr(track, ret_attr, (price - track.price_at_signal) / track.price_at_signal)
                peak = closes[0]
                max_dd = 0
                for price in closes:
                    peak = max(peak, price)
                    max_dd = min(max_dd, price / peak - 1)
                track.max_drawdown_after_signal = max_dd
                signal = session.get(AISignal, track.signal_id)
                ret20 = track.return_20d if track.return_20d is not None else track.return_5d
                if signal and ret20 is not None:
                    if signal.action in ["buy_candidate", "hold", "watch"]:
                        track.is_success = ret20 > 0
                    elif signal.action in ["reduce", "sell", "avoid"]:
                        track.is_success = ret20 <= 0
                updated += 1
        return updated

    def update_tracking_and_memory(self, include_success: bool = False) -> dict:
        tracked = self.update_tracking()
        memories = MemoryService().generate_learning_memories(include_success=include_success)
        return {"tracked": tracked, "memories": memories}

    def stats(self) -> dict:
        with session_scope() as session:
            signals = list(session.scalars(select(AISignal)).all())
            tracks = list(session.scalars(select(SignalTracking)).all())
        action_counts: dict[str, int] = {}
        success_counts: dict[str, int] = {}
        signal_by_id = {s.id: s for s in signals}
        returns = []
        for track in tracks:
            signal = signal_by_id.get(track.signal_id)
            if not signal:
                continue
            action_counts[signal.action] = action_counts.get(signal.action, 0) + 1
            if track.is_success:
                success_counts[signal.action] = success_counts.get(signal.action, 0) + 1
            if track.return_20d is not None:
                returns.append(track.return_20d)
        return {
            "total_signals": len(signals),
            "action_counts": action_counts,
            "success_counts": success_counts,
            "avg_return_20d": sum(returns) / len(returns) if returns else None,
            "tracked_count": len(tracks),
        }
