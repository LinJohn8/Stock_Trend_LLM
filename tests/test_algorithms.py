from __future__ import annotations

from services.algorithm_service import AlgorithmService


def test_algorithm_registry() -> None:
    service = AlgorithmService()
    algorithms = service.list_algorithms()
    ids = {algo.id for algo in algorithms}
    assert "trend_following" in ids
    assert "learning_memory" in ids
    assert all(algo.weight > 0 for algo in algorithms)
    assert len(algorithms) >= 200
    assert "trend_ma20_breakout_3" in ids
    assert "risk_guard_drawdown_15" in ids


def test_default_algorithm_ids_are_subset() -> None:
    service = AlgorithmService()
    ids = {algo.id for algo in service.list_algorithms()}
    default_ids = service.default_algorithm_ids()
    assert 5 <= len(default_ids) < len(ids)
    assert set(default_ids).issubset(ids)


def test_generated_algorithm_template_runs() -> None:
    service = AlgorithmService()
    algo = next(item for item in service.list_algorithms() if item.id == "trend_ma20_breakout_3")
    result = algo.runner(
        {
            "technical": {"current_price": 105, "ma20": 100, "trend_score": 65},
            "fundamental": {},
            "sentiment": {},
            "news_evidence": [],
            "holding": None,
            "memories": [],
        }
    )
    normalized = service._normalize_result(result, algo)
    assert normalized["score"] > 50
    assert normalized["direction"] in {"bullish", "neutral", "bearish"}


def test_algorithm_action() -> None:
    service = AlgorithmService()
    assert service._action(75, [{"risks": []}]) == "buy_candidate"
    assert service._action(35, [{"risks": []}]) == "avoid"
    assert service._action(70, [{"risks": ["放量下跌"]}]) == "reduce"


def test_algorithm_weighted_score() -> None:
    service = AlgorithmService()
    score = service._weighted_score([
        {"score": 80, "weight": 0.5},
        {"score": 40, "weight": 0.5},
    ])
    assert score == 60


def test_algorithm_combination_hard_risk_blocks_buy() -> None:
    service = AlgorithmService()
    decision = service.combine_results(
        [
            {"score": 80, "weight": 0.5, "direction": "bullish", "position_bias": 0.3, "risks": []},
            {"score": 76, "weight": 0.5, "direction": "bullish", "position_bias": 0.25, "risks": ["放量下跌"]},
        ],
        {"risk": {"risk_level": "high"}, "memories": [], "holding": None},
    )
    assert decision["action"] == "avoid"
    assert decision["position"] == "0%"
