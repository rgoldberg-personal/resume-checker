"""Task: compute weighted seniority score + LLM-generated qualitative analysis."""
from __future__ import annotations

import asyncio
import json
import math
import time
from pathlib import Path

import yaml
from celery import shared_task

from app.job_store import set_job_error, update_job_status
from app.llm.client import call_llm
from app.llm.prompts import SCORE_ANALYSIS_SYSTEM_PROMPT, build_score_analysis_user_prompt
from app.schemas import CategoryBreakdown, ScoreBreakdown

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "scoring_weights.yaml"

# Seniority keyword matching sets
_SENIOR_KEYWORDS = {"senior", "lead", "principal", "staff", "architect", "head", "director"}
_MID_KEYWORDS = {"mid", "middle", "medior", "experienced"}
_JUNIOR_KEYWORDS = {"junior", "associate", "graduate", "trainee", "intern"}

_VALUED_SOFT_SKILLS = {
    "leadership", "communication", "problem-solving", "mentoring",
    "stakeholder management", "cross-functional collaboration",
    "strategic thinking", "adaptability", "conflict resolution",
    "team management", "negotiation", "presentation", "coaching",
    "decision-making", "project management", "critical thinking",
    "time management", "emotional intelligence", "creativity",
    "analytical thinking", "collaboration", "delegation",
}


def _load_weights() -> dict[str, float]:
    with _CONFIG_PATH.open() as f:
        data = yaml.safe_load(f)
    weights: dict[str, float] = data.get("weights", {})
    total = sum(weights.values())
    if total == 0:
        return {"experience": 25.0, "skills": 25.0, "education": 15.0, "role_seniority": 15.0, "soft_skills": 20.0}
    factor = 100.0 / total
    return {k: v * factor for k, v in weights.items()}


def _compute_experience_score(experience_years: float, max_pts: float) -> tuple[int, str]:
    raw = min(max_pts, experience_years * (max_pts / 12.0))
    score = round(raw)
    reasoning = (
        f"{experience_years:.1f} years detected. "
        f"Formula: min({int(max_pts)}, {experience_years:.1f} x {max_pts / 12.0:.2f}) = {score}/{int(max_pts)}."
    )
    return score, reasoning


def _compute_skills_score(
    skills: list[str], job_description: str | None, max_pts: float,
) -> tuple[int, str, bool]:
    base = min(max_pts, len(skills) * (max_pts / 20.0))
    jd_boost = 0.0
    job_fit_adjusted = False
    matched = 0

    if job_description:
        jd_words = set(job_description.lower().split())
        matched = sum(1 for s in skills if s.lower() in jd_words)
        raw_boost = (matched / max(len(jd_words), 1)) * 10.0
        jd_boost = min(raw_boost, max_pts - base)
        job_fit_adjusted = True

    score = round(min(max_pts, base + jd_boost))

    if job_description:
        reasoning = (
            f"{len(skills)} skills detected. Base: {round(base)}. "
            f"JD match: {matched} words -> boost +{jd_boost:.1f}. Total: {score}/{int(max_pts)}."
        )
    else:
        reasoning = f"{len(skills)} skills detected. Score: {score}/{int(max_pts)}."

    return score, reasoning, job_fit_adjusted


def _compute_education_score(education_level: str, max_pts: float) -> tuple[int, str]:
    level = education_level.lower()
    mapping = {"phd": max_pts, "master": max_pts * 0.85, "bachelor": max_pts * 0.65, "other": max_pts * 0.40}
    score = round(mapping.get(level, max_pts * 0.40))
    reasoning = f"{education_level.title()} degree detected. Score: {score}/{int(max_pts)}."
    return score, reasoning


def _compute_role_seniority_score(
    role_titles: list[str], has_management_indicators: bool, max_pts: float,
) -> tuple[int, str]:
    titles_lower = " ".join(role_titles).lower()

    if any(kw in titles_lower for kw in _SENIOR_KEYWORDS):
        base = max_pts * 0.85
        tier = "senior/lead"
    elif any(kw in titles_lower for kw in _MID_KEYWORDS):
        base = max_pts * 0.60
        tier = "mid-level"
    elif any(kw in titles_lower for kw in _JUNIOR_KEYWORDS):
        base = max_pts * 0.30
        tier = "junior"
    else:
        base = max_pts * 0.50
        tier = "unclassified"

    mgmt_bonus = max_pts * 0.15 if has_management_indicators else 0.0
    score = round(min(max_pts, base + mgmt_bonus))
    reasoning = (
        f"Titles: {role_titles}. Tier: {tier} -> base {round(base)}. "
        f"Management: {'yes' if has_management_indicators else 'no'} (+{round(mgmt_bonus)}). "
        f"Total: {score}/{int(max_pts)}."
    )
    return score, reasoning


def _compute_soft_skills_score(
    soft_skills: list[str], has_management_indicators: bool, max_pts: float,
) -> tuple[int, str]:
    matched = [s for s in soft_skills if s.lower() in _VALUED_SOFT_SKILLS]
    base = min(max_pts * 0.8, len(matched) * (max_pts * 0.8 / 8.0))
    mgmt_bonus = max_pts * 0.2 if has_management_indicators else 0.0
    score = round(min(max_pts, base + mgmt_bonus))
    reasoning = (
        f"{len(soft_skills)} soft skills detected ({len(matched)} recognized: "
        f"{', '.join(matched[:5])}{'...' if len(matched) > 5 else ''}). "
        f"Management bonus: {'yes' if has_management_indicators else 'no'} (+{round(mgmt_bonus)}). "
        f"Total: {score}/{int(max_pts)}."
    )
    return score, reasoning


def _build_placeholder_breakdown(reasoning: str) -> CategoryBreakdown:
    """Create a placeholder breakdown with just reasoning (used if LLM fails)."""
    return CategoryBreakdown(
        reasoning=reasoning,
        gap_analysis="Analysis unavailable.",
        improvements=[],
        short_learning_path=[],
        long_learning_path=[],
    )


def _generate_llm_justifications(
    scores: dict[str, tuple[int, str]],
    parsed_cv: dict,
    job_description: str | None,
) -> dict[str, CategoryBreakdown]:
    """Call LLM to generate qualitative analysis for each scoring category."""
    user_message = build_score_analysis_user_prompt(scores, parsed_cv, job_description)

    try:
        raw = asyncio.run(
            call_llm(SCORE_ANALYSIS_SYSTEM_PROMPT, user_message, {"type": "json_object"})
        )
        data = json.loads(raw)
        categories = data.get("categories", {})

        result: dict[str, CategoryBreakdown] = {}
        for key, (_, reasoning) in scores.items():
            cat_data = categories.get(key, {})
            result[key] = CategoryBreakdown(
                reasoning=reasoning,
                gap_analysis=cat_data.get("gap_analysis", "Analysis unavailable."),
                improvements=cat_data.get("improvements", []),
                short_learning_path=cat_data.get("short_learning_path", []),
                long_learning_path=cat_data.get("long_learning_path", []),
            )
        return result

    except Exception:
        # Fallback: return placeholders with just the formula-based reasoning
        return {key: _build_placeholder_breakdown(reasoning) for key, (_, reasoning) in scores.items()}


@shared_task(bind=True, max_retries=0, time_limit=45)
def compute_score(self, context: dict) -> dict:  # type: ignore[override]
    """
    Compute weighted seniority score (deterministic) and generate
    LLM-based qualitative analysis (improvements, gaps, learning paths).
    """
    job_id = context["job_id"]
    update_job_status(job_id, "SCORING", "Computing seniority score...")
    start = time.time()

    try:
        weights = _load_weights()
        parsed_cv: dict = context["parsed_cv"]
        job_description: str | None = context.get("job_description")

        exp_score, exp_reasoning = _compute_experience_score(
            parsed_cv.get("experience_years", 0.0), weights["experience"],
        )
        skills_score, skills_reasoning, job_fit_adjusted = _compute_skills_score(
            parsed_cv.get("skills", []), job_description, weights["skills"],
        )
        edu_score, edu_reasoning = _compute_education_score(
            parsed_cv.get("education_level", "other"), weights["education"],
        )
        role_score, role_reasoning = _compute_role_seniority_score(
            parsed_cv.get("role_titles", []),
            parsed_cv.get("has_management_indicators", False),
            weights["role_seniority"],
        )
        soft_score, soft_reasoning = _compute_soft_skills_score(
            parsed_cv.get("soft_skills", []),
            parsed_cv.get("has_management_indicators", False),
            weights["soft_skills"],
        )

        scores = {
            "experience": (exp_score, exp_reasoning),
            "skills": (skills_score, skills_reasoning),
            "education": (edu_score, edu_reasoning),
            "role_seniority": (role_score, role_reasoning),
            "soft_skills": (soft_score, soft_reasoning),
        }

        raw_total = sum(s for s, _ in scores.values())
        total = max(0, min(100, raw_total))

        # LLM generates qualitative analysis based on actual CV content
        update_job_status(job_id, "SCORING", "Analyzing score breakdown...")
        justifications = _generate_llm_justifications(scores, parsed_cv, job_description)

        breakdown = ScoreBreakdown(
            experience=exp_score,
            skills=skills_score,
            education=edu_score,
            role_seniority=role_score,
            soft_skills=soft_score,
            total=total,
            justifications=justifications,
            job_fit_adjusted=job_fit_adjusted,
        )
        context["score_breakdown"] = breakdown.model_dump()

    except Exception:
        set_job_error(job_id, "Scoring failed. Please try again.")
        raise

    context["step_timings"]["compute_score"] = time.time() - start
    return context
