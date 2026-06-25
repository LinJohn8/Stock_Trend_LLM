from __future__ import annotations

from services.llm_skill_service import LLMReviewSkillService


def test_llm_skill_registry() -> None:
    service = LLMReviewSkillService()
    skills = service.list_skills()
    assert len(skills) >= 4
    assert service.get_skill("conservative_decision_review").prompt_file.endswith(".md")


def test_llm_skill_unknown() -> None:
    service = LLMReviewSkillService()
    try:
        service.get_skill("missing")
    except ValueError as exc:
        assert "未知 LLM Skill" in str(exc)
    else:
        raise AssertionError("missing skill should raise ValueError")
