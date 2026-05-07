"""Task: compute weighted seniority score."""
from __future__ import annotations

import math
import time
from pathlib import Path

import yaml
from celery import shared_task

from app.job_store import set_job_error, update_job_status
from app.schemas import CategoryBreakdown, ScoreBreakdown

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "scoring_weights.yaml"

# Seniority keyword matching sets
_SENIOR_KEYWORDS = {"senior", "lead", "principal", "staff", "architect", "head", "director"}
_MID_KEYWORDS = {"mid", "middle", "medior", "experienced"}
_JUNIOR_KEYWORDS = {"junior", "associate", "graduate", "trainee", "intern"}


def _load_weights() -> dict[str, float]:
    with _CONFIG_PATH.open() as f:
        data = yaml.safe_load(f)
    weights: dict[str, float] = data.get("weights", {})
    total = sum(weights.values())
    if total == 0:
        return {"experience": 25.0, "skills": 25.0, "education": 15.0, "role_seniority": 15.0, "soft_skills": 20.0}
    # Normalise so weights always sum to 100
    factor = 100.0 / total
    return {k: v * factor for k, v in weights.items()}


def _compute_experience_score(
    experience_years: float,
    max_pts: float,
) -> tuple[int, CategoryBreakdown]:
    raw = min(max_pts, experience_years * (max_pts / 12.0))
    score = round(raw)
    target_years = 12.0  # max_pts / (max_pts / 12.0) = 12.0 always
    gap = target_years - experience_years

    reasoning = (
        f"{experience_years:.1f} years detected across CV roles. "
        f"Formula: min({int(max_pts)}, {experience_years:.1f} x {max_pts / 12.0:.2f}) "
        f"= {raw:.2f} -> {score}"
    )

    if score < int(max_pts):
        gap_analysis = (
            f"Need {target_years:.1f} total years for maximum {int(max_pts)} pts. "
            f"Current gap: {gap:.1f} years."
        )
    else:
        gap_analysis = "Maximum score achieved."

    improvements = [
        "List all freelance, contract, and part-time roles with explicit start/end dates.",
        "Include internships and relevant side projects with quantified outcomes.",
    ]
    short_learning_path = [
        "Audit CV for any missing date ranges on existing roles and add them — "
        "this can recover hidden years of experience immediately."
    ]
    long_learning_path = [
        (
            f"Accumulate {gap:.1f} more years of progressive hands-on experience"
            " to reach the maximum score."
        )
        if gap > 0
        else "No long-term experience gap — maintain current trajectory."
    ]

    return score, CategoryBreakdown(
        reasoning=reasoning,
        gap_analysis=gap_analysis,
        improvements=improvements,
        short_learning_path=short_learning_path,
        long_learning_path=long_learning_path,
    )


def _compute_skills_score(
    skills: list[str],
    job_description: str | None,
    max_pts: float,
) -> tuple[int, CategoryBreakdown, bool]:
    base = min(max_pts, len(skills) * (max_pts / 20.0))
    jd_boost = 0.0
    job_fit_adjusted = False
    matched = 0
    jd_words: set[str] = set()

    if job_description:
        jd_words = set(job_description.lower().split())
        matched = sum(1 for s in skills if s.lower() in jd_words)
        total_jd_skills = max(len(jd_words), 1)
        raw_boost = (matched / total_jd_skills) * 10.0
        # Cap so total skills score does not exceed max_pts
        jd_boost = min(raw_boost, max_pts - base)
        job_fit_adjusted = True

    score = round(min(max_pts, base + jd_boost))

    if job_description:
        reasoning = (
            f"{len(skills)} skills detected. "
            f"Base: min({int(max_pts)}, {len(skills)} x {max_pts / 20.0:.2f}) = {round(base)}. "
            f"JD match: {matched}/{len(jd_words)} words -> boost +{jd_boost:.1f}. "
            f"Total: {score}/{int(max_pts)}."
        )
    else:
        reasoning = (
            f"{len(skills)} skills detected. "
            f"Formula: min({int(max_pts)}, {len(skills)} x {max_pts / 20.0:.2f}) "
            f"= {score}/{int(max_pts)}."
        )

    if score < int(max_pts):
        needed_skills = math.ceil((max_pts - base) / (max_pts / 20.0))
        gap_analysis = (
            f"Need {needed_skills} additional in-demand skills to approach maximum. "
            f"Current: {len(skills)} skills."
        )
    else:
        gap_analysis = "Maximum base score achieved."

    improvements = [
        "Add specific versions and proficiency levels to skills (e.g. 'Python 3.12 — 5 years').",
        "Include tools and frameworks mentioned in target job descriptions "
        "to improve JD match score.",
        "Remove generic skills (e.g. 'Microsoft Office') and replace with "
        "technical differentiators.",
    ]
    short_learning_path = [
        "Identify the top 3 skills from the target job description that you have but "
        "haven't listed — add them immediately.",
        "Complete one online certification in a high-demand skill to add a credentialed "
        "entry to the skills list.",
    ]
    long_learning_path = [
        "Build one end-to-end project using 2-3 currently missing in-demand skills and "
        "publish it publicly (GitHub, blog post).",
        "Pursue a cloud or architecture certification (e.g. AWS Solutions Architect, CKA) "
        "over a 3-6 month study plan.",
    ]

    return score, CategoryBreakdown(
        reasoning=reasoning,
        gap_analysis=gap_analysis,
        improvements=improvements,
        short_learning_path=short_learning_path,
        long_learning_path=long_learning_path,
    ), job_fit_adjusted


def _compute_education_score(
    education_level: str,
    max_pts: float,
) -> tuple[int, CategoryBreakdown]:
    level = education_level.lower()
    mapping = {
        "phd": max_pts,
        "master": max_pts * 0.85,
        "bachelor": max_pts * 0.65,
        "other": max_pts * 0.40,
    }
    raw = mapping.get(level, max_pts * 0.40)
    score = round(raw)

    reasoning = (
        f"{education_level.title()} degree detected. "
        f"Tier mapping: phd={int(max_pts)}, master={round(max_pts * 0.85)}, "
        f"bachelor={round(max_pts * 0.65)}, other={round(max_pts * 0.40)}. "
        f"Score: {score}/{int(max_pts)}."
    )

    if level == "phd":
        gap_analysis = "Maximum education score achieved."
        improvements = ["Education score is maxed — no action needed."]
        short_learning_path = ["No short-term education action required."]
        long_learning_path = [
            "Education ceiling reached — invest long-term effort in publications, "
            "conference talks, or open-source leadership instead."
        ]
    elif level == "master":
        gap_analysis = (
            f"A PhD would add {int(max_pts) - score} pts. "
            "Master's is already a strong signal."
        )
        improvements = [
            "Highlight thesis or capstone project topics directly relevant to target roles.",
            "List relevant online courses, bootcamps, or MOOCs under education "
            "to supplement formal degree.",
        ]
        short_learning_path = [
            "Add any relevant professional development courses or certifications "
            "under the education section."
        ]
        long_learning_path = [
            "Education ceiling reached — invest long-term effort in publications, "
            "conference talks, or open-source leadership instead."
        ]
    elif level == "bachelor":
        gap_analysis = (
            f"A master's degree would add {round(max_pts * 0.85) - score} pts "
            f"({round(max_pts * 0.85)}/{int(max_pts)})."
        )
        improvements = [
            "Highlight thesis or capstone project topics directly relevant to target roles.",
            "List relevant online courses, bootcamps, or MOOCs under education "
            "to supplement formal degree.",
        ]
        short_learning_path = [
            "Add any relevant professional development courses or certifications "
            "under the education section."
        ]
        long_learning_path = [
            "Consider a part-time or online master's programme (1.5-2 years)"
            " to reach the next tier."
        ]
    else:
        gap_analysis = (
            f"A bachelor's degree would add {round(max_pts * 0.65) - score} pts "
            f"({round(max_pts * 0.65)}/{int(max_pts)})."
        )
        improvements = [
            "List any completed online courses or bootcamps under education.",
            "Consider enrolling in a part-time bachelor's programme if long-term "
            "career growth is a priority.",
        ]
        short_learning_path = [
            "Add any relevant professional development courses or certifications "
            "under the education section."
        ]
        long_learning_path = [
            "Pursue a bachelor's or equivalent accredited qualification if career trajectory "
            "requires formal credentials."
        ]

    return score, CategoryBreakdown(
        reasoning=reasoning,
        gap_analysis=gap_analysis,
        improvements=improvements,
        short_learning_path=short_learning_path,
        long_learning_path=long_learning_path,
    )


def _compute_role_seniority_score(
    role_titles: list[str],
    has_management_indicators: bool,
    max_pts: float,
) -> tuple[int, CategoryBreakdown]:
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

    management_bonus = max_pts * 0.15 if has_management_indicators else 0.0
    score = round(min(max_pts, base + management_bonus))

    reasoning = (
        f"Titles: {role_titles}. Detected tier: {tier} -> base {round(base)}/{int(max_pts)}. "
        f"Management indicators: {'yes' if has_management_indicators else 'no'} "
        f"(+{round(management_bonus)} pts). Total: {score}/{int(max_pts)}."
    )

    if score == int(max_pts):
        gap_analysis = "Maximum role seniority score achieved."
    elif has_management_indicators:
        gap_analysis = (
            f"Score is {score}/{int(max_pts)}. Moving to a principal, VP, or C-level title "
            "would add further points."
        )
    else:
        gap_analysis = (
            f"Score is {score}/{int(max_pts)}. Adding a senior/lead title and demonstrating "
            f"management experience would add up to {int(max_pts) - score} pts."
        )

    improvements = [
        "Use explicit seniority keywords in job titles"
        " (Senior, Lead, Principal, Staff, Architect) where accurate.",
        "Quantify team leadership: 'Led a team of 5 engineers' is a strong management indicator.",
        "List promotions explicitly as separate roles to show career progression.",
    ]
    short_learning_path = [
        "Rewrite current title line to include seniority level if the role warrants it "
        "(check with employer if needed).",
        "Add a one-line summary under each role that mentions team size, scope, or "
        "cross-functional influence.",
    ]
    long_learning_path = [
        "Target a lead or principal-level role at the next job change — even informally "
        "leading a workstream creates legitimate title advancement.",
        "Volunteer to mentor junior engineers or lead a project to build a management "
        "track record over 6-12 months.",
    ]

    return score, CategoryBreakdown(
        reasoning=reasoning,
        gap_analysis=gap_analysis,
        improvements=improvements,
        short_learning_path=short_learning_path,
        long_learning_path=long_learning_path,
    )


_VALUED_SOFT_SKILLS = {
    "leadership", "communication", "problem-solving", "mentoring",
    "stakeholder management", "cross-functional collaboration",
    "strategic thinking", "adaptability", "conflict resolution",
    "team management", "negotiation", "presentation", "coaching",
    "decision-making", "project management", "critical thinking",
    "time management", "emotional intelligence", "creativity",
    "analytical thinking", "collaboration", "delegation",
}


def _compute_soft_skills_score(
    soft_skills: list[str],
    has_management_indicators: bool,
    max_pts: float,
) -> tuple[int, CategoryBreakdown]:
    """Score soft skills / personality traits detected from the CV."""
    # Count recognized soft skills (normalize to lowercase)
    matched = [s for s in soft_skills if s.lower() in _VALUED_SOFT_SKILLS]
    unrecognized = [s for s in soft_skills if s.lower() not in _VALUED_SOFT_SKILLS]

    # Base: each matched skill contributes proportionally, cap at ~8 skills for max
    base = min(max_pts * 0.8, len(matched) * (max_pts * 0.8 / 8.0))
    # Management bonus
    mgmt_bonus = max_pts * 0.2 if has_management_indicators else 0.0
    score = round(min(max_pts, base + mgmt_bonus))

    reasoning = (
        f"{len(soft_skills)} soft skills detected ({len(matched)} recognized). "
        f"Matched: {', '.join(matched[:5])}{'...' if len(matched) > 5 else ''}. "
        f"Base: {round(base)}/{int(max_pts * 0.8)}. "
        f"Management bonus: {'yes' if has_management_indicators else 'no'} "
        f"(+{round(mgmt_bonus)}). Total: {score}/{int(max_pts)}."
    )

    if score < int(max_pts):
        missing_count = max(0, 8 - len(matched))
        gap_analysis = (
            f"Need {missing_count} more recognized soft skills for maximum base score. "
            f"Valued traits not yet listed: "
            f"{', '.join(list(_VALUED_SOFT_SKILLS - {s.lower() for s in soft_skills})[:4])}."
        )
    else:
        gap_analysis = "Maximum soft skills score achieved."

    improvements = [
        "Explicitly mention soft skills demonstrated in role descriptions "
        "(e.g. 'led cross-functional team' evidences leadership and collaboration).",
        "Add a dedicated 'Leadership & Soft Skills' section if the CV lacks one.",
    ]
    short_learning_path = [
        "Review each role description and add 1-2 soft skill keywords that are already "
        "evidenced by the described responsibilities.",
    ]
    long_learning_path = [
        "Pursue a leadership or management certification (e.g. PMP, Scrum Master) "
        "to formalize soft skills and add credentialed entries.",
    ]

    return score, CategoryBreakdown(
        reasoning=reasoning,
        gap_analysis=gap_analysis,
        improvements=improvements,
        short_learning_path=short_learning_path,
        long_learning_path=long_learning_path,
    )


@shared_task(bind=True, max_retries=0, time_limit=10)
def compute_score(self, context: dict) -> dict:  # type: ignore[override]
    """
    Compute the weighted seniority score from parsed CV data.

    No LLM call. Uses scoring weights from config/scoring_weights.yaml.
    Stores ScoreBreakdown in context.
    """
    job_id = context["job_id"]
    update_job_status(job_id, "SCORING", "Computing seniority score...")
    start = time.time()

    try:
        weights = _load_weights()
        parsed_cv: dict = context["parsed_cv"]
        job_description: str | None = context.get("job_description")

        exp_score, exp_breakdown = _compute_experience_score(
            parsed_cv.get("experience_years", 0.0),
            weights["experience"],
        )
        skills_score, skills_breakdown, job_fit_adjusted = _compute_skills_score(
            parsed_cv.get("skills", []),
            job_description,
            weights["skills"],
        )
        edu_score, edu_breakdown = _compute_education_score(
            parsed_cv.get("education_level", "other"),
            weights["education"],
        )
        role_score, role_breakdown = _compute_role_seniority_score(
            parsed_cv.get("role_titles", []),
            parsed_cv.get("has_management_indicators", False),
            weights["role_seniority"],
        )
        soft_score, soft_breakdown = _compute_soft_skills_score(
            parsed_cv.get("soft_skills", []),
            parsed_cv.get("has_management_indicators", False),
            weights["soft_skills"],
        )

        raw_total = exp_score + skills_score + edu_score + role_score + soft_score
        total = max(0, min(100, raw_total))

        breakdown = ScoreBreakdown(
            experience=exp_score,
            skills=skills_score,
            education=edu_score,
            role_seniority=role_score,
            soft_skills=soft_score,
            total=total,
            justifications={
                "experience": exp_breakdown,
                "skills": skills_breakdown,
                "education": edu_breakdown,
                "role_seniority": role_breakdown,
                "soft_skills": soft_breakdown,
            },
            job_fit_adjusted=job_fit_adjusted,
        )
        context["score_breakdown"] = breakdown.model_dump()

    except Exception:
        set_job_error(job_id, "Scoring failed. Please try again.")
        raise

    context["step_timings"]["compute_score"] = time.time() - start
    return context
