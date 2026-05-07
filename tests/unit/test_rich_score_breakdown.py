"""Unit tests for the rich score breakdown feature (tasks 8–11).

Covers:
  - CategoryBreakdown / ScoreBreakdown schema validation  (app/schemas.py)
  - _compute_experience_score                              (app/tasks/compute_score.py)
  - _compute_skills_score                                  (app/tasks/compute_score.py)
  - _compute_education_score                               (app/tasks/compute_score.py)
  - _compute_role_seniority_score                          (app/tasks/compute_score.py)
  - build_explanation_user_prompt                          (app/llm/prompts.py)
"""
from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.schemas import CategoryBreakdown, ScoreBreakdown
from app.tasks.compute_score import (
    _compute_education_score,
    _compute_experience_score,
    _compute_role_seniority_score,
    _compute_skills_score,
)
from app.llm.prompts import build_explanation_user_prompt

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAX_EXP = 30.0
MAX_SKILLS = 30.0
MAX_EDU = 20.0
MAX_ROLE = 20.0


def _make_category_breakdown(**overrides) -> dict:
    """Return a minimal valid CategoryBreakdown dict."""
    defaults = {
        "reasoning": "test reasoning",
        "gap_analysis": "test gap",
        "improvements": ["improve A"],
        "short_learning_path": ["quick win"],
        "long_learning_path": ["strategic move"],
    }
    return {**defaults, **overrides}


def _make_score_breakdown(**overrides) -> dict:
    """Return a minimal valid ScoreBreakdown dict."""
    cat = _make_category_breakdown()
    defaults = {
        "experience": 20,
        "skills": 20,
        "education": 13,
        "role_seniority": 17,
        "total": 70,
        "justifications": {
            "experience": cat,
            "skills": cat,
            "education": cat,
            "role_seniority": cat,
        },
        "job_fit_adjusted": False,
    }
    return {**defaults, **overrides}


# ===========================================================================
# 1. Schema validation — CategoryBreakdown
# ===========================================================================


class TestCategoryBreakdownSchema:
    def test_valid_data_is_accepted(self):
        cat = CategoryBreakdown(
            reasoning="Score formula applied",
            gap_analysis="Need 2 more years",
            improvements=["Add dates", "Add projects"],
            short_learning_path=["Quick cert"],
            long_learning_path=["Master's degree"],
        )
        assert cat.reasoning == "Score formula applied"
        assert len(cat.improvements) == 2

    def test_missing_reasoning_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            CategoryBreakdown(
                gap_analysis="test",
                # reasoning omitted
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("reasoning",) for e in errors)

    def test_missing_gap_analysis_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            CategoryBreakdown(
                reasoning="test",
                # gap_analysis omitted
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("gap_analysis",) for e in errors)

    def test_empty_reasoning_raises_validation_error(self):
        """min_length=1 must be enforced on reasoning."""
        with pytest.raises(ValidationError):
            CategoryBreakdown(reasoning="", gap_analysis="test")

    def test_empty_gap_analysis_raises_validation_error(self):
        """min_length=1 must be enforced on gap_analysis."""
        with pytest.raises(ValidationError):
            CategoryBreakdown(reasoning="test", gap_analysis="")

    def test_list_fields_default_to_empty_list(self):
        cat = CategoryBreakdown(reasoning="r", gap_analysis="g")
        assert cat.improvements == []
        assert cat.short_learning_path == []
        assert cat.long_learning_path == []

    def test_all_five_fields_present(self):
        cat = CategoryBreakdown(
            reasoning="r", gap_analysis="g",
            improvements=["a"], short_learning_path=["b"], long_learning_path=["c"],
        )
        assert cat.reasoning == "r"
        assert cat.gap_analysis == "g"
        assert cat.improvements == ["a"]
        assert cat.short_learning_path == ["b"]
        assert cat.long_learning_path == ["c"]


# ===========================================================================
# 2. Schema validation — ScoreBreakdown
# ===========================================================================


class TestScoreBreakdownSchema:
    def test_justifications_stores_category_breakdown_objects(self):
        """justifications dict must contain CategoryBreakdown instances, not strings."""
        sb = ScoreBreakdown(**_make_score_breakdown())
        for key in ("experience", "skills", "education", "role_seniority"):
            assert isinstance(sb.justifications[key], CategoryBreakdown), (
                f"justifications[{key!r}] should be CategoryBreakdown, got {type(sb.justifications[key])}"
            )

    def test_model_validator_passes_with_correct_sum(self):
        sb = ScoreBreakdown(**_make_score_breakdown(
            experience=20, skills=20, education=13, role_seniority=17, total=70
        ))
        assert sb.total == 70

    def test_model_validator_fails_when_total_mismatches_sum(self):
        """Total must equal sum of sub-scores within ±1 tolerance."""
        with pytest.raises(ValidationError):
            ScoreBreakdown(**_make_score_breakdown(
                experience=20, skills=20, education=13, role_seniority=17, total=99
            ))

    def test_model_validator_passes_with_tolerance_of_1(self):
        """model_validator allows ±1 rounding tolerance."""
        sb = ScoreBreakdown(**_make_score_breakdown(
            experience=20, skills=20, education=13, role_seniority=17, total=71  # off by 1
        ))
        assert sb.total == 71

    def test_missing_justification_key_raises_validation_error(self):
        """ScoreBreakdown must have all four required justification keys."""
        data = _make_score_breakdown()
        # Remove one key
        del data["justifications"]["skills"]
        with pytest.raises(ValidationError) as exc_info:
            ScoreBreakdown(**data)
        assert "skills" in str(exc_info.value)

    def test_model_dump_justifications_are_dicts_not_strings(self):
        """After model_dump(), justifications should be dict[str, dict], not dict[str, str]."""
        sb = ScoreBreakdown(**_make_score_breakdown())
        dumped = sb.model_dump()
        for key, val in dumped["justifications"].items():
            assert isinstance(val, dict), (
                f"After model_dump(), justifications[{key!r}] should be dict, got {type(val)}"
            )
            assert "reasoning" in val


# ===========================================================================
# 3. Scoring logic — _compute_experience_score
# ===========================================================================


class TestComputeExperienceScore:
    def test_0_years_gives_0_score(self):
        score, bd = _compute_experience_score(0.0, MAX_EXP)
        assert score == 0
        assert isinstance(bd, CategoryBreakdown)

    def test_0_years_gap_analysis_mentions_target(self):
        _, bd = _compute_experience_score(0.0, MAX_EXP)
        assert "12.0" in bd.gap_analysis or "12" in bd.gap_analysis

    def test_6_years_score_is_correct(self):
        score, _ = _compute_experience_score(6.0, MAX_EXP)
        expected = round(min(MAX_EXP, 6.0 * (MAX_EXP / 12.0)))
        assert score == expected  # should be 15

    def test_9_5_years_score_is_correct(self):
        score, _ = _compute_experience_score(9.5, MAX_EXP)
        expected = round(min(MAX_EXP, 9.5 * (MAX_EXP / 12.0)))
        assert score == expected  # should be 24

    def test_12_years_gives_max_score(self):
        score, bd = _compute_experience_score(12.0, MAX_EXP)
        assert score == int(MAX_EXP)
        assert bd.gap_analysis == "Maximum score achieved."

    def test_over_12_years_is_capped_at_max(self):
        score, bd = _compute_experience_score(15.0, MAX_EXP)
        assert score == int(MAX_EXP)
        assert bd.gap_analysis == "Maximum score achieved."

    def test_all_five_category_breakdown_fields_non_empty(self):
        _, bd = _compute_experience_score(5.0, MAX_EXP)
        assert bd.reasoning
        assert bd.gap_analysis
        assert bd.improvements  # non-empty list
        assert bd.short_learning_path  # non-empty list
        assert bd.long_learning_path  # non-empty list

    def test_gap_case_long_learning_path_mentions_gap(self):
        _, bd = _compute_experience_score(3.0, MAX_EXP)
        long_text = " ".join(bd.long_learning_path)
        # Should mention remaining years needed
        assert "9.0" in long_text or "years" in long_text.lower()

    def test_max_score_long_learning_path_positive_message(self):
        _, bd = _compute_experience_score(12.0, MAX_EXP)
        long_text = " ".join(bd.long_learning_path)
        assert "No long-term experience gap" in long_text

    def test_reasoning_contains_formula_components(self):
        _, bd = _compute_experience_score(6.0, MAX_EXP)
        assert "6.0" in bd.reasoning
        assert "years" in bd.reasoning.lower()


# ===========================================================================
# 4. Scoring logic — _compute_skills_score
# ===========================================================================


class TestComputeSkillsScore:
    def test_0_skills_no_jd_gives_0_score(self):
        score, bd, job_fit = _compute_skills_score([], None, MAX_SKILLS)
        assert score == 0
        assert job_fit is False

    def test_0_skills_no_jd_gap_analysis_mentions_needed_skills(self):
        _, bd, _ = _compute_skills_score([], None, MAX_SKILLS)
        assert "skills" in bd.gap_analysis.lower()

    def test_10_skills_no_jd_score_is_correct(self):
        skills = [f"skill_{i}" for i in range(10)]
        score, _, job_fit = _compute_skills_score(skills, None, MAX_SKILLS)
        expected = round(min(MAX_SKILLS, 10 * (MAX_SKILLS / 20.0)))
        assert score == expected  # should be 15
        assert job_fit is False

    def test_10_skills_no_jd_reasoning_has_no_jd_boost_mention(self):
        skills = [f"skill_{i}" for i in range(10)]
        _, bd, _ = _compute_skills_score(skills, None, MAX_SKILLS)
        assert "JD match" not in bd.reasoning

    def test_10_skills_with_jd_matching_3_score_includes_boost(self):
        skills = ["python", "django", "postgres", "react", "docker",
                  "git", "linux", "bash", "redis", "celery"]
        # JD contains python, django, postgres and other unrelated words
        jd = "We need python django postgres expert developer"
        score, bd, job_fit = _compute_skills_score(skills, jd, MAX_SKILLS)
        # Base = round(min(30, 10 * 1.5)) = 15
        # JD has 5 words, matched = 3, raw_boost = (3/5)*10 = 6
        # Capped at min(6, 30-15=15) = 6 -> score = round(15+6) = 21
        assert score > 15  # boost must have been applied
        assert job_fit is True
        assert "JD match" in bd.reasoning

    def test_20_plus_skills_max_score(self):
        skills = [f"skill_{i}" for i in range(25)]
        score, bd, _ = _compute_skills_score(skills, None, MAX_SKILLS)
        assert score == int(MAX_SKILLS)
        assert bd.gap_analysis == "Maximum base score achieved."

    def test_jd_boost_present_in_reasoning_when_jd_provided(self):
        skills = ["python", "django"]
        jd = "Looking for python developer"
        _, bd, _ = _compute_skills_score(skills, jd, MAX_SKILLS)
        assert "JD match" in bd.reasoning
        assert "boost" in bd.reasoning.lower()

    def test_jd_boost_absent_in_reasoning_when_no_jd(self):
        skills = ["python", "django"]
        _, bd, _ = _compute_skills_score(skills, None, MAX_SKILLS)
        assert "JD match" not in bd.reasoning
        assert "boost" not in bd.reasoning.lower()

    def test_all_five_fields_non_empty(self):
        skills = [f"skill_{i}" for i in range(10)]
        _, bd, _ = _compute_skills_score(skills, None, MAX_SKILLS)
        assert bd.reasoning
        assert bd.gap_analysis
        assert bd.improvements
        assert bd.short_learning_path
        assert bd.long_learning_path


# ===========================================================================
# 5. Scoring logic — _compute_education_score
# ===========================================================================


class TestComputeEducationScore:
    def test_phd_gives_max_score(self):
        score, bd = _compute_education_score("phd", MAX_EDU)
        assert score == int(MAX_EDU)
        assert bd.gap_analysis == "Maximum education score achieved."

    def test_master_gives_85_percent_score(self):
        score, _ = _compute_education_score("master", MAX_EDU)
        assert score == round(MAX_EDU * 0.85)

    def test_bachelor_gives_65_percent_score(self):
        score, _ = _compute_education_score("bachelor", MAX_EDU)
        assert score == round(MAX_EDU * 0.65)

    def test_other_gives_40_percent_score(self):
        score, _ = _compute_education_score("other", MAX_EDU)
        assert score == round(MAX_EDU * 0.40)

    def test_phd_gap_analysis_says_maximum(self):
        _, bd = _compute_education_score("phd", MAX_EDU)
        assert "Maximum" in bd.gap_analysis

    def test_master_gap_analysis_mentions_phd(self):
        _, bd = _compute_education_score("master", MAX_EDU)
        assert "PhD" in bd.gap_analysis or "phd" in bd.gap_analysis.lower()

    def test_bachelor_gap_analysis_mentions_master(self):
        _, bd = _compute_education_score("bachelor", MAX_EDU)
        assert "master" in bd.gap_analysis.lower()

    def test_other_gap_analysis_mentions_bachelor(self):
        _, bd = _compute_education_score("other", MAX_EDU)
        assert "bachelor" in bd.gap_analysis.lower()

    def test_all_five_fields_non_empty_for_all_levels(self):
        for level in ("phd", "master", "bachelor", "other"):
            _, bd = _compute_education_score(level, MAX_EDU)
            assert bd.reasoning, f"reasoning empty for {level}"
            assert bd.gap_analysis, f"gap_analysis empty for {level}"
            assert bd.improvements, f"improvements empty for {level}"
            assert bd.short_learning_path, f"short_learning_path empty for {level}"
            assert bd.long_learning_path, f"long_learning_path empty for {level}"

    def test_reasoning_contains_tier_mapping(self):
        _, bd = _compute_education_score("bachelor", MAX_EDU)
        assert "phd=" in bd.reasoning
        assert "master=" in bd.reasoning
        assert "bachelor=" in bd.reasoning


# ===========================================================================
# 6. Scoring logic — _compute_role_seniority_score
# ===========================================================================


class TestComputeRoleSeniorityScore:
    def test_senior_keyword_tier(self):
        score, bd = _compute_role_seniority_score(["Senior Software Engineer"], False, MAX_ROLE)
        expected = round(min(MAX_ROLE, MAX_ROLE * 0.85))
        assert score == expected
        assert "senior/lead" in bd.reasoning

    def test_lead_keyword_maps_to_senior_tier(self):
        score, _ = _compute_role_seniority_score(["Lead Developer"], False, MAX_ROLE)
        expected = round(min(MAX_ROLE, MAX_ROLE * 0.85))
        assert score == expected

    def test_mid_keyword_tier(self):
        score, bd = _compute_role_seniority_score(["Mid Software Engineer"], False, MAX_ROLE)
        expected = round(min(MAX_ROLE, MAX_ROLE * 0.60))
        assert score == expected
        assert "mid-level" in bd.reasoning

    def test_medior_keyword_maps_to_mid_tier(self):
        score, _ = _compute_role_seniority_score(["Medior Developer"], False, MAX_ROLE)
        expected = round(min(MAX_ROLE, MAX_ROLE * 0.60))
        assert score == expected

    def test_junior_keyword_tier(self):
        score, bd = _compute_role_seniority_score(["Junior Developer"], False, MAX_ROLE)
        expected = round(min(MAX_ROLE, MAX_ROLE * 0.30))
        assert score == expected
        assert "junior" in bd.reasoning

    def test_unclassified_tier_when_no_keywords_match(self):
        score, bd = _compute_role_seniority_score(["Software Engineer"], False, MAX_ROLE)
        expected = round(min(MAX_ROLE, MAX_ROLE * 0.50))
        assert score == expected
        assert "unclassified" in bd.reasoning

    def test_management_bonus_increases_score(self):
        score_no_mgmt, _ = _compute_role_seniority_score(["Software Engineer"], False, MAX_ROLE)
        score_with_mgmt, bd = _compute_role_seniority_score(["Software Engineer"], True, MAX_ROLE)
        assert score_with_mgmt > score_no_mgmt
        assert "yes" in bd.reasoning

    def test_management_bonus_capped_at_max(self):
        """Senior + management should not exceed max_pts."""
        score, _ = _compute_role_seniority_score(["Senior Engineer"], True, MAX_ROLE)
        assert score <= int(MAX_ROLE)

    def test_senior_with_management_reaches_max(self):
        """0.85 + 0.15 = 1.0 so senior + management = max points."""
        score, bd = _compute_role_seniority_score(["Senior Engineer"], True, MAX_ROLE)
        assert score == int(MAX_ROLE)
        assert bd.gap_analysis == "Maximum role seniority score achieved."

    def test_reasoning_contains_titles_tier_and_management(self):
        _, bd = _compute_role_seniority_score(["Senior Developer"], False, MAX_ROLE)
        assert "Senior Developer" in bd.reasoning
        assert "senior/lead" in bd.reasoning
        assert "no" in bd.reasoning.lower()

    def test_all_five_fields_non_empty(self):
        _, bd = _compute_role_seniority_score(["Software Engineer"], False, MAX_ROLE)
        assert bd.reasoning
        assert bd.gap_analysis
        assert bd.improvements
        assert bd.short_learning_path
        assert bd.long_learning_path

    def test_empty_titles_list_maps_to_unclassified(self):
        score, bd = _compute_role_seniority_score([], False, MAX_ROLE)
        expected = round(min(MAX_ROLE, MAX_ROLE * 0.50))
        assert score == expected
        assert "unclassified" in bd.reasoning


# ===========================================================================
# 7. Prompt formatting — build_explanation_user_prompt
# ===========================================================================


class TestBuildExplanationUserPrompt:
    def _make_populated_score_breakdown(self) -> dict:
        cat = {
            "reasoning": "6.0 years detected. Formula: min(30, 6.0 x 2.50) = 15.00 -> 15",
            "gap_analysis": "Need 12.0 total years for maximum 30 pts. Current gap: 6.0 years.",
            "improvements": ["List freelance roles", "Add side projects"],
            "short_learning_path": ["Audit CV for missing date ranges"],
            "long_learning_path": ["Accumulate 6.0 more years of hands-on experience"],
        }
        return {
            "experience": 15,
            "skills": 15,
            "education": 13,
            "role_seniority": 10,
            "total": 53,
            "justifications": {
                "experience": cat,
                "skills": cat,
                "education": cat,
                "role_seniority": cat,
            },
            "job_fit_adjusted": False,
        }

    def test_prompt_contains_how_scored_label(self):
        prompt = build_explanation_user_prompt(
            seniority_score=53,
            score_breakdown=self._make_populated_score_breakdown(),
            salary_estimate={"min_czk": 50000, "max_czk": 70000, "confidence": "medium"},
            parsed_cv_summary={},
        )
        assert "Reasoning:" in prompt

    def test_prompt_contains_gap_label(self):
        prompt = build_explanation_user_prompt(
            seniority_score=53,
            score_breakdown=self._make_populated_score_breakdown(),
            salary_estimate={"min_czk": 50000, "max_czk": 70000, "confidence": "medium"},
            parsed_cv_summary={},
        )
        assert "Gap:" in prompt

    def test_prompt_contains_short_path_label(self):
        prompt = build_explanation_user_prompt(
            seniority_score=53,
            score_breakdown=self._make_populated_score_breakdown(),
            salary_estimate={"min_czk": 50000, "max_czk": 70000, "confidence": "medium"},
            parsed_cv_summary={},
        )
        assert "Short path" in prompt

    def test_prompt_contains_long_path_label(self):
        prompt = build_explanation_user_prompt(
            seniority_score=53,
            score_breakdown=self._make_populated_score_breakdown(),
            salary_estimate={"min_czk": 50000, "max_czk": 70000, "confidence": "medium"},
            parsed_cv_summary={},
        )
        assert "Long path" in prompt

    def test_prompt_does_not_contain_raw_python_dict_repr_for_justifications(self):
        """The justifications must NOT appear as raw Python dict repr like {'reasoning': ..."""
        prompt = build_explanation_user_prompt(
            seniority_score=53,
            score_breakdown=self._make_populated_score_breakdown(),
            salary_estimate={"min_czk": 50000, "max_czk": 70000, "confidence": "medium"},
            parsed_cv_summary={},
        )
        assert "{'reasoning':" not in prompt
        assert "\"reasoning\":" not in prompt

    def test_prompt_with_empty_justifications_does_not_crash(self):
        """If justifications is missing or empty, prompt should still generate without raising."""
        minimal = {
            "experience": 0, "skills": 0, "education": 0, "role_seniority": 0,
            "total": 0, "justifications": {}, "job_fit_adjusted": False,
        }
        prompt = build_explanation_user_prompt(
            seniority_score=0,
            score_breakdown=minimal,
            salary_estimate={"min_czk": 25000, "max_czk": 40000, "confidence": "low"},
            parsed_cv_summary={},
        )
        assert "Seniority Score: 0/100" in prompt

    def test_prompt_includes_score_and_salary(self):
        prompt = build_explanation_user_prompt(
            seniority_score=75,
            score_breakdown=self._make_populated_score_breakdown(),
            salary_estimate={"min_czk": 80000, "max_czk": 120000, "confidence": "high"},
            parsed_cv_summary={"experience_years": 6},
        )
        assert "75/100" in prompt
        assert "80,000" in prompt
        assert "120,000" in prompt


# ===========================================================================
# 8. Regression: compute_score task context structure
# ===========================================================================


class TestComputeScoreContextStructure:
    """Verify that after compute_score runs, context['score_breakdown']['justifications']
    is a dict of dicts (Pydantic serialised), not a dict of CategoryBreakdown objects."""

    def test_compute_score_justifications_are_serialised_dicts(self):
        """Call the helper functions directly and simulate what compute_score does."""
        from app.tasks.compute_score import (
            _compute_education_score,
            _compute_experience_score,
            _compute_role_seniority_score,
            _compute_skills_score,
        )

        exp_score, exp_breakdown = _compute_experience_score(6.0, 30.0)
        skills_score, skills_breakdown, job_fit = _compute_skills_score(["python"], None, 30.0)
        edu_score, edu_breakdown = _compute_education_score("bachelor", 20.0)
        role_score, role_breakdown = _compute_role_seniority_score(["Engineer"], False, 20.0)

        raw_total = exp_score + skills_score + edu_score + role_score
        total = max(0, min(100, raw_total))

        breakdown = ScoreBreakdown(
            experience=exp_score,
            skills=skills_score,
            education=edu_score,
            role_seniority=role_score,
            total=total,
            justifications={
                "experience": exp_breakdown,
                "skills": skills_breakdown,
                "education": edu_breakdown,
                "role_seniority": role_breakdown,
            },
            job_fit_adjusted=job_fit,
        )

        # Simulate what compute_score does: model_dump() and store in context
        dumped = breakdown.model_dump()
        justifications = dumped["score_breakdown"]["justifications"] if "score_breakdown" in dumped else dumped["justifications"]

        for key, val in justifications.items():
            assert isinstance(val, dict), (
                f"After model_dump(), justifications[{key!r}] should be dict, got {type(val)}"
            )
            # Verify all five fields are present and non-empty
            assert "reasoning" in val and val["reasoning"]
            assert "gap_analysis" in val and val["gap_analysis"]
            assert "improvements" in val
            assert "short_learning_path" in val
            assert "long_learning_path" in val
