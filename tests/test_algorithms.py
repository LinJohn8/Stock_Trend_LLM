from __future__ import annotations

from services.algorithm_service import AlgorithmService


def test_algorithm_registry() -> None:
    service = AlgorithmService()
    algorithms = service.list_algorithms()
    ids = {algo.id for algo in algorithms}
    assert "trend_following" in ids
    assert "learning_memory" in ids
    assert all(algo.weight > 0 for algo in algorithms)


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
