from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from database.db import session_scope
from database.models import SimulationAlgorithmPreset


class SimulationPresetService:
    """Persist reusable historical-simulation algorithm groups."""

    def list_presets(self, include_defaults: bool = True) -> list[SimulationAlgorithmPreset]:
        with session_scope() as session:
            stmt = select(SimulationAlgorithmPreset).order_by(SimulationAlgorithmPreset.is_default.desc(), SimulationAlgorithmPreset.updated_at.desc())
            rows = list(session.scalars(stmt).all())
            if include_defaults and not rows:
                return self.ensure_default_presets()
            return rows

    def ensure_default_presets(self) -> list[SimulationAlgorithmPreset]:
        from services.algorithm_service import AlgorithmService

        service = AlgorithmService()
        default_ids = service.default_algorithm_ids()
        fallback = [
            {
                "name": "默认强核心组",
                "description": "趋势、动量、量价、估值、新闻、风控、学习记忆的平衡组合。",
                "selected_algorithms": default_ids,
                "strategy_mode": "consensus",
                "benchmark_code": "sh000300",
                "fee_rate": 0.0003,
                "max_position": 0.85,
                "is_default": True,
            },
            {
                "name": "保守风控组",
                "description": "更重视风控和确认，只在高共识时提高仓位。",
                "selected_algorithms": [algo_id for algo_id in default_ids if algo_id != "momentum_ret20_8"],
                "strategy_mode": "conservative",
                "benchmark_code": "sh000300",
                "fee_rate": 0.0003,
                "max_position": 0.55,
                "is_default": True,
            },
        ]
        for item in fallback:
            self.save_preset(**item)
        with session_scope() as session:
            return list(session.scalars(select(SimulationAlgorithmPreset).order_by(SimulationAlgorithmPreset.id)).all())

    def save_preset(
        self,
        name: str,
        selected_algorithms: list[str],
        description: str = "",
        strategy_mode: str = "consensus",
        benchmark_code: str = "sh000300",
        fee_rate: float = 0.0003,
        max_position: float = 0.85,
        is_default: bool = False,
    ) -> SimulationAlgorithmPreset:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("算法组名称不能为空。")
        if not selected_algorithms:
            raise ValueError("算法组至少需要包含一个算法。")
        with session_scope() as session:
            item = session.scalar(select(SimulationAlgorithmPreset).where(SimulationAlgorithmPreset.name == clean_name))
            values: dict[str, Any] = {
                "description": description.strip(),
                "selected_algorithms": json.dumps(list(dict.fromkeys(selected_algorithms)), ensure_ascii=False),
                "strategy_mode": strategy_mode,
                "benchmark_code": benchmark_code,
                "fee_rate": float(fee_rate),
                "max_position": float(max_position),
                "is_default": is_default,
            }
            if item:
                for key, value in values.items():
                    setattr(item, key, value)
            else:
                item = SimulationAlgorithmPreset(name=clean_name, **values)
                session.add(item)
            session.flush()
            session.refresh(item)
            return item

    def delete_preset(self, preset_id: int) -> bool:
        with session_scope() as session:
            item = session.get(SimulationAlgorithmPreset, preset_id)
            if not item or item.is_default:
                return False
            session.delete(item)
            return True

    @staticmethod
    def algorithm_ids(item: SimulationAlgorithmPreset) -> list[str]:
        try:
            values = json.loads(item.selected_algorithms or "[]")
            return [str(value) for value in values]
        except Exception:
            return []
