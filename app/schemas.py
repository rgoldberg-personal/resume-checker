from __future__ import annotations

from datetime import datetime
from enum import Enum, StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Internal pipeline models (not exposed as API responses)
# ---------------------------------------------------------------------------

class CVSections(BaseModel):
    experience:     str = ""
    skills:         str = ""
    education:      str = ""
    certifications: str = ""
    languages:      str = ""


class ParsedCV(BaseModel):
    """Structured output from the LLM CV extraction step."""
    sections:                 CVSections
    skills:                   list[str]
    soft_skills:              list[str]  # e.g. ["leadership", "communication", "problem-solving"]
    experience_years:         float
    education_level:          Literal["bachelor", "master", "phd", "other"]
    role_titles:              list[str]
    has_management_indicators: bool
    role_category:            str  # LLM-classified canonical role category


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AnalysisStatus(str, Enum):
    RECEIVED    = "RECEIVED"
    EXTRACTING  = "EXTRACTING"
    STRUCTURING = "STRUCTURING"
    SCORING     = "SCORING"
    ATS_SCORING       = "ATS_SCORING"
    ESTIMATING  = "ESTIMATING"
    EXPLAINING        = "EXPLAINING"
    ANALYZING_CONTENT = "ANALYZING_CONTENT"
    VALIDATING        = "VALIDATING"
    COMPLETED   = "COMPLETED"
    PARTIAL     = "PARTIAL"
    FAILED      = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in {self.COMPLETED, self.PARTIAL, self.FAILED}


class ConfidenceLevel(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


# ---------------------------------------------------------------------------
# Sub-models (pipeline outputs)
# ---------------------------------------------------------------------------

class CategoryBreakdown(BaseModel):
    reasoning:           str       = Field(
        ..., min_length=1,
        description=(
            "HOW the score was calculated: formula applied + input values."
            " Populated by compute_score task."
        ),
    )
    gap_analysis:        str       = Field(
        ..., min_length=1,
        description=(
            "What is numerically or structurally missing to reach maximum points."
            " Populated by compute_score task."
        ),
    )
    improvements:        list[str] = Field(
        default_factory=list,
        description=(
            "1–3 specific actionable items (CV rewrite, project, cert)."
            " Populated by compute_score task."
        ),
    )
    short_learning_path: list[str] = Field(
        default_factory=list,
        description=(
            "Quick wins achievable in weeks to 1–2 months (1–2 items)."
            " Populated by compute_score task."
        ),
    )
    long_learning_path:  list[str] = Field(
        default_factory=list,
        description=(
            "Strategic improvements requiring 3–6+ months (1–2 items)."
            " Populated by compute_score task."
        ),
    )


class ScoreBreakdown(BaseModel):
    experience:      int = Field(..., ge=0, description="Experience sub-score")
    skills:          int = Field(..., ge=0, description="Skills sub-score")
    education:       int = Field(..., ge=0, description="Education sub-score")
    role_seniority:  int = Field(..., ge=0, description="Role seniority sub-score")
    soft_skills:     int = Field(default=0, ge=0, description="Soft skills / personality traits sub-score")
    total:           int = Field(..., ge=0, le=100, description="Clamped total score")
    justifications:  dict[str, CategoryBreakdown] = Field(
        ...,
        description=(
            "Per-category structured breakdown."
            " Keys: experience, skills, education, role_seniority, soft_skills"
        ),
    )
    job_fit_adjusted: bool = Field(..., description="True if job description was used for scoring")

    @model_validator(mode="after")
    def validate_total_matches_sum(self) -> ScoreBreakdown:
        computed = self.experience + self.skills + self.education + self.role_seniority + self.soft_skills
        if abs(computed - self.total) > 1:
            raise ValueError(
                f"Score total {self.total} does not match sub-score sum {computed} (tolerance ±1)"
            )
        return self

    @model_validator(mode="after")
    def validate_justification_keys(self) -> ScoreBreakdown:
        expected = {"experience", "skills", "education", "role_seniority"}
        missing = expected - set(self.justifications.keys())
        if missing:
            raise ValueError(f"justifications is missing required category keys: {missing}")
        return self


class SalaryEstimate(BaseModel):
    min_czk:              int = Field(..., gt=0, description="Minimum salary in CZK/month")
    max_czk:              int = Field(..., gt=0, description="Maximum salary in CZK/month")
    currency:             Literal["CZK"] = "CZK"
    period:               Literal["month"] = "month"
    data_source:          str = Field(..., description="'platy_mcp' or 'fallback_bands'")
    confidence:           ConfidenceLevel
    is_low_confidence_flag: bool = Field(
        ..., description="True if salary falls outside 25k–500k plausible bounds"
    )

    @model_validator(mode="after")
    def validate_min_less_than_max(self) -> SalaryEstimate:
        if self.min_czk >= self.max_czk:
            raise ValueError(f"min_czk ({self.min_czk}) must be less than max_czk ({self.max_czk})")
        return self


class SalaryGrowthTarget(BaseModel):
    current_min: int = Field(..., description="Current salary estimate min CZK")
    current_max: int = Field(..., description="Current salary estimate max CZK")
    target_min:  int = Field(..., description="Target salary min after +30%")
    target_max:  int = Field(..., description="Target salary max after +30%")
    key_actions: list[str] = Field(..., min_length=1, description="Specific actions to reach +30%")


class Explanation(BaseModel):
    summary:              str       = Field(..., min_length=1)
    strengths:            list[str] = Field(..., min_length=2, description="3–5 specific strengths")
    weaknesses:           list[str] = Field(..., min_length=1, description="2–4 identified gaps")
    recommendations:      list[str] = Field(
        ..., min_length=2, description="Actionable steps to increase salary by ~30%",
    )
    salary_growth_target: SalaryGrowthTarget | None = Field(
        default=None, description="+30% salary growth target with actions",
    )
    raw_llm_response:     str       = Field(
        ..., description="Stored for debugging; never shown to users",
    )


class ContentIssueType(StrEnum):
    MISSING_INFO    = "missing_info"
    REPETITION      = "repetition"
    TYPO            = "typo"
    GRAMMAR         = "grammar"
    MISSING_SECTION = "missing_section"


class ContentIssue(BaseModel):
    issue_type: ContentIssueType
    original:   str = Field(
        ..., min_length=1, description="Offending sentence or phrase from the CV",
    )
    fixed:      str = Field(..., min_length=1, description="Corrected/suggested version")


class CVContentAnalysis(BaseModel):
    issues: list[ContentIssue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ATS scoring models
# ---------------------------------------------------------------------------

class ATSKeywordImportance(StrEnum):
    CRITICAL     = "critical"
    IMPORTANT    = "important"
    NICE_TO_HAVE = "nice_to_have"


class ATSKeyword(BaseModel):
    keyword:     str = Field(..., min_length=1)
    found_in_cv: bool
    importance:  ATSKeywordImportance


class ATSCandidateMatch(StrEnum):
    FULL    = "full"
    PARTIAL = "partial"
    NONE    = "none"


class ATSRequirementMatch(BaseModel):
    requirement:     str = Field(..., min_length=1)
    candidate_match: ATSCandidateMatch
    evidence:        str = Field(
        default="",
        description="Text from CV that supports this match; empty string if none.",
    )
    gap:             str = Field(
        default="",
        description="What is missing to achieve a full match; empty string if fully met.",
    )


class ATSPriorityGap(BaseModel):
    priority:    int = Field(
        ..., ge=1, le=3,
        description="1=critical deal-breaker, 2=important, 3=nice-to-have",
    )
    description: str = Field(..., min_length=1)


class ATSAnalysis(BaseModel):
    ats_score:            int = Field(..., ge=0, le=100, description="ATS match score 0-100")
    keyword_matches:      list[ATSKeyword] = Field(default_factory=list)
    requirement_matches:  list[ATSRequirementMatch] = Field(default_factory=list)
    priority_gaps:        list[ATSPriorityGap] = Field(default_factory=list)
    tailoring_suggestions: list[str] = Field(
        default_factory=list,
        description="Truth-preserving suggestions to improve ATS match",
    )


class AnalysisResult(BaseModel):
    request_id:       str
    seniority_score:  int            = Field(..., ge=0, le=100)
    score_breakdown:  ScoreBreakdown
    salary_estimate:  SalaryEstimate
    explanation:      Explanation | None = None  # None on PARTIAL result
    content_analysis: CVContentAnalysis | None = None  # None if analysis step failed
    ats_analysis:     ATSAnalysis | None = None  # None when no JD provided or task failed
    confidence:       ConfidenceLevel
    created_at:       datetime


# ---------------------------------------------------------------------------
# API Response models
# ---------------------------------------------------------------------------

class AnalyzeResponse(BaseModel):
    """Response from POST /api/v1/analyze"""
    job_id:  str
    status:  Literal["RECEIVED"] = "RECEIVED"
    message: str


class JobStatusResponse(BaseModel):
    """Response from GET /api/v1/jobs/{job_id}/status"""
    job_id:        str
    status:        AnalysisStatus
    progress_step: str
    created_at:    datetime
    result:        AnalysisResult | None = None
    error_message: str | None = None
    warnings:      list[str] = Field(default_factory=list)


class HealthService(BaseModel):
    redis:       Literal["connected", "unavailable"]
    mcp_server:  Literal["connected", "unavailable", "unknown"]
    openrouter:  Literal["configured", "unconfigured"]


class HealthResponse(BaseModel):
    """Response from GET /api/v1/health"""
    status:   Literal["ok", "degraded", "error"]
    version:  str
    services: HealthService


# ---------------------------------------------------------------------------
# Error model
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    code:    str
    message: str
    details: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
