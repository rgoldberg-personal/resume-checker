# API Interfaces: Job Fit & Salary Estimator

**Version:** 1.1
**Date:** 2026-05-05
**Status:** Implementation-Ready
**Source document:** `./architecture/architecture.md`
**Last updated:** task-7 — `CategoryBreakdown` sub-model introduced; `ScoreBreakdown.justifications` changed from `dict[str, str]` to `dict[str, CategoryBreakdown]`

---

## Table of Contents

1. [Base URL & Versioning](#1-base-url--versioning)
2. [Authentication](#2-authentication)
3. [Error Response Format](#3-error-response-format)
4. [Endpoints](#4-endpoints)
   - [POST /api/v1/analyze](#post-apiv1analyze)
   - [GET /api/v1/jobs/{job_id}/status](#get-apiv1jobsjob_idstatus)
   - [GET /api/v1/health](#get-apiv1health)
5. [Polling Contract](#5-polling-contract)
6. [Pydantic Models (Backend)](#6-pydantic-models-backend)
7. [TypeScript Types (Frontend)](#7-typescript-types-frontend)
8. [Typed API Client (Frontend)](#8-typed-api-client-frontend)
9. [All Error Codes Reference](#9-all-error-codes-reference)
10. [curl Examples](#10-curl-examples)

---

## 1. Base URL & Versioning

```
http://localhost:8000/api/v1
```

**Versioning strategy:** URL-path prefix (`/api/v1`). Breaking changes require a new prefix (`/api/v2`). The frontend always includes the explicit version prefix. Non-breaking additions (new optional fields in responses) do not require a version bump.

**CORS:** The FastAPI backend must allow requests from `http://localhost:5173` (Vite dev server). Configured via `fastapi.middleware.cors.CORSMiddleware`.

---

## 2. Authentication

**MVP:** No authentication. All endpoints are unauthenticated and accept any request. This is acceptable for a local portfolio demo.

**Future:** Add a Bearer-token middleware on all routes before any production exposure.

---

## 3. Error Response Format

Every error from the API — regardless of HTTP status code — returns the same JSON envelope:

```json
{
  "error": {
    "code": "SNAKE_CASE_ERROR_CODE",
    "message": "Human-readable message safe to show to users.",
    "details": null
  }
}
```

- `code`: uppercase snake_case string constant. Used by the frontend to branch on error type.
- `message`: user-displayable string in English.
- `details`: `null` for MVP. Can be a string or object for additional context (e.g., field-level validation errors).

FastAPI exception handler (register in `app/main.py`):

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred. Please try again.", "details": None}},
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.detail["code"], "message": exc.detail["message"], "details": exc.detail.get("details")}},
    )
```

---

## 4. Endpoints

### POST /api/v1/analyze

Submit a CV for analysis. Returns immediately with a `job_id`; processing happens asynchronously via Celery.

**Method:** `POST`
**Path:** `/api/v1/analyze`
**Content-Type:** `multipart/form-data`

#### Request Fields

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `cv_file` | file | Yes | PDF or DOCX, max 10 MB | The CV to analyze |
| `job_description` | string | No | max 10,000 chars | Plain-text job description for job-fit scoring |

#### Successful Response — 202 Accepted

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "RECEIVED",
  "message": "Analysis queued. Poll /api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/status for results."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string (UUID v4) | Unique identifier for this analysis job |
| `status` | `"RECEIVED"` | Always `RECEIVED` on success |
| `message` | string | Human-readable next-step instruction |

#### Error Responses

| HTTP Status | `error.code` | `error.message` | When |
|-------------|--------------|-----------------|------|
| 400 | `MISSING_FILE` | "No CV file provided." | `cv_file` field absent from request |
| 400 | `INVALID_FILE_TYPE` | "Unsupported file format. Please upload a PDF or DOCX file." | File extension or MIME type is not PDF/DOCX |
| 400 | `FILE_TOO_LARGE` | "File exceeds the 10 MB size limit." | File size > 10,485,760 bytes |
| 422 | `VALIDATION_ERROR` | "Request validation failed." | FastAPI Pydantic form validation failure |
| 429 | `TOO_MANY_REQUESTS` | "Service busy. Please retry in a moment." | Concurrent job limit exceeded (configurable via `MAX_CONCURRENT_JOBS`) |
| 500 | `INTERNAL_ERROR` | "An unexpected error occurred. Please try again." | Unhandled exception in route handler |

#### FastAPI Route Signature

```python
from fastapi import APIRouter, UploadFile, File, Form
from app.schemas import AnalyzeResponse

router = APIRouter(prefix="/api/v1")

@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
async def analyze_cv(
    cv_file: UploadFile = File(..., description="PDF or DOCX CV file, max 10 MB"),
    job_description: str | None = Form(default=None, max_length=10_000),
) -> AnalyzeResponse:
    ...
```

---

### GET /api/v1/jobs/{job_id}/status

Poll for job status and results. Returns the current state of the analysis. Call every 2 seconds until `status` is `COMPLETED`, `PARTIAL`, or `FAILED`.

**Method:** `GET`
**Path:** `/api/v1/jobs/{job_id}/status`
**Path parameter:** `job_id` — UUID string

#### Response Schema (all cases) — 200 OK

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "<AnalysisStatus>",
  "progress_step": "<human-readable step label>",
  "created_at": "2026-05-05T10:00:00Z",
  "result": null,
  "error_message": null,
  "warnings": []
}
```

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | UUID of this job |
| `status` | `AnalysisStatus` | Current pipeline state (see Status Enum below) |
| `progress_step` | string | Human-readable label for the current step |
| `created_at` | string (ISO 8601 UTC) | When the job was created |
| `result` | `AnalysisResult` or `null` | `null` until terminal status; populated on `COMPLETED` or `PARTIAL` |
| `error_message` | string or `null` | User-facing error on `FAILED`; `null` otherwise |
| `warnings` | `string[]` | Non-fatal warnings accumulated during processing |

#### Status Enum

| Status | Terminal | Description |
|--------|----------|-------------|
| `RECEIVED` | No | Job created; queued for processing |
| `EXTRACTING` | No | Text extraction from PDF/DOCX in progress |
| `STRUCTURING` | No | LLM parsing CV into structured sections |
| `SCORING` | No | Computing weighted seniority score |
| `ESTIMATING` | No | Looking up salary via Platy MCP |
| `EXPLAINING` | No | Generating LLM explanation |
| `VALIDATING` | No | Running output validation checks |
| `COMPLETED` | Yes | All results available; `result` is populated |
| `PARTIAL` | Yes | Score and salary available; explanation failed or timed out |
| `FAILED` | Yes | Critical step failed; `result` is `null`; `error_message` set |

The frontend must stop polling when `status` is `COMPLETED`, `PARTIAL`, or `FAILED`.

#### Response Example — In Progress

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "SCORING",
  "progress_step": "Computing seniority score...",
  "created_at": "2026-05-05T10:00:00Z",
  "result": null,
  "error_message": null,
  "warnings": []
}
```

#### Response Example — COMPLETED

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "COMPLETED",
  "progress_step": "Analysis complete.",
  "created_at": "2026-05-05T10:00:00Z",
  "result": {
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "seniority_score": 72,
    "score_breakdown": {
      "experience": 25,
      "skills": 22,
      "education": 15,
      "role_seniority": 10,
      "total": 72,
      "justifications": {
        "experience": {
          "reasoning": "8 years of non-overlapping work experience across 3 roles. Scoring formula: 10 pts per 3-year block; 2 full blocks + 2 partial years = 25/30.",
          "gap_analysis": "4 more years of progressive experience needed to reach the 30-point ceiling.",
          "improvements": [
            "List each role's duration and 2–3 measurable outcomes to make seniority self-evident.",
            "Quantify impact with metrics: team size, system scale, SLA targets, cost savings."
          ],
          "short_learning_path": [
            "Add metrics and outcomes to every role entry in the CV (1–2 hours of editing)."
          ],
          "long_learning_path": [
            "Target a Staff Engineer or Architect title to demonstrate breadth of technical scope over 12–24 months."
          ]
        },
        "skills": {
          "reasoning": "14 technical skills matched; 3 JD-required skills found (Python, AWS, Kubernetes) adding 2 bonus points. Score: 22/30.",
          "gap_analysis": "Missing JD-required skills: Terraform, Prometheus, Helm.",
          "improvements": [
            "Add Terraform IaC experience; obtain HashiCorp Terraform Associate certification."
          ],
          "short_learning_path": [
            "Complete Terraform Associate study path (3–4 weeks)."
          ],
          "long_learning_path": [
            "Lead an infrastructure-as-code initiative at current employer over 6 months."
          ]
        },
        "education": {
          "reasoning": "Bachelor's degree in Computer Science = 15 pts. No Master's degree detected.",
          "gap_analysis": "A Master's degree would add 5 points to reach the 20-point maximum.",
          "improvements": [
            "Highlight any professional certifications as partial substitutes for postgraduate education."
          ],
          "short_learning_path": [
            "Obtain AWS Solutions Architect Associate certification (4–6 weeks)."
          ],
          "long_learning_path": [
            "Evaluate a part-time Master's programme if strategically aligned with career goals."
          ]
        },
        "role_seniority": {
          "reasoning": "Highest title detected: Senior Software Engineer = 10 pts. No management indicators found in role descriptions.",
          "gap_analysis": "A Staff Engineer title or evidence of team leadership would add up to 10 additional points.",
          "improvements": [
            "Explicitly mention team leadership scope, mentoring, or on-call rotation ownership in role descriptions."
          ],
          "short_learning_path": [
            "Reframe current role description to surface technical leadership responsibilities."
          ],
          "long_learning_path": [
            "Pursue a Staff Engineer role or lead a cross-team technical initiative over 12+ months."
          ]
        }
      },
      "job_fit_adjusted": true
    },
    "salary_estimate": {
      "min_czk": 85000,
      "max_czk": 120000,
      "currency": "CZK",
      "period": "month",
      "data_source": "platy_mcp",
      "confidence": "high",
      "is_low_confidence_flag": false
    },
    "explanation": {
      "summary": "This candidate presents as a strong mid-to-senior software engineer with 8 years of experience and a solid mix of backend and cloud skills.",
      "strengths": [
        "Deep Python expertise demonstrated across multiple roles and projects.",
        "Hands-on Kubernetes and AWS experience directly relevant to the target role.",
        "Consistent career progression from junior to senior level over 8 years."
      ],
      "weaknesses": [
        "No formal cloud certification (AWS Solutions Architect or equivalent).",
        "Limited evidence of system design ownership or architectural decision-making in the CV."
      ],
      "recommendations": [
        "Obtain the AWS Solutions Architect Associate certification — this credential directly maps to a 10–15% salary increase for cloud-adjacent roles in the Czech market.",
        "Contribute to or lead an open-source project to demonstrate architectural decision-making ability and increase visibility to hiring managers."
      ],
      "raw_llm_response": "{...}"
    },
    "confidence": "high",
    "created_at": "2026-05-05T10:00:35Z"
  },
  "error_message": null,
  "warnings": []
}
```

#### Response Example — PARTIAL (explanation failed)

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "PARTIAL",
  "progress_step": "Analysis complete (partial results).",
  "created_at": "2026-05-05T10:00:00Z",
  "result": {
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "seniority_score": 72,
    "score_breakdown": {
      "experience": 25,
      "skills": 22,
      "education": 15,
      "role_seniority": 10,
      "total": 72,
      "justifications": {
        "experience": {
          "reasoning": "8 years of work experience across 3 roles. Score: 25/30.",
          "gap_analysis": "4 more years needed to reach the 30-point maximum.",
          "improvements": [],
          "short_learning_path": [],
          "long_learning_path": []
        },
        "skills": {
          "reasoning": "14 technical skills identified. Score: 22/30.",
          "gap_analysis": "Missing 3 JD-required skills.",
          "improvements": [],
          "short_learning_path": [],
          "long_learning_path": []
        },
        "education": {
          "reasoning": "Bachelor's degree detected. Score: 15/20.",
          "gap_analysis": "No Master's degree detected.",
          "improvements": [],
          "short_learning_path": [],
          "long_learning_path": []
        },
        "role_seniority": {
          "reasoning": "Senior Software Engineer title detected. Score: 10/20.",
          "gap_analysis": "No management indicators detected.",
          "improvements": [],
          "short_learning_path": [],
          "long_learning_path": []
        }
      },
      "job_fit_adjusted": false
    },
    "salary_estimate": {
      "min_czk": 85000,
      "max_czk": 120000,
      "currency": "CZK",
      "period": "month",
      "data_source": "platy_mcp",
      "confidence": "medium",
      "is_low_confidence_flag": false
    },
    "explanation": null,
    "confidence": "medium",
    "created_at": "2026-05-05T10:00:35Z"
  },
  "error_message": null,
  "warnings": [
    "LLM explanation generation timed out after 30 seconds. Seniority score and salary estimate are complete."
  ]
}
```

#### Response Example — FAILED

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "FAILED",
  "progress_step": "Analysis failed.",
  "created_at": "2026-05-05T10:00:00Z",
  "result": null,
  "error_message": "No text found in the PDF. Please provide a text-based (not scanned) PDF.",
  "warnings": []
}
```

#### Error Responses

| HTTP Status | `error.code` | `error.message` | When |
|-------------|--------------|-----------------|------|
| 404 | `JOB_NOT_FOUND` | "No job found with this ID." | `job_id` does not exist in Redis |
| 500 | `INTERNAL_ERROR` | "An unexpected error occurred. Please try again." | Redis connection failure or unhandled exception |

#### FastAPI Route Signature

```python
from fastapi import APIRouter
from app.schemas import JobStatusResponse

@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    ...
```

---

### GET /api/v1/health

Health check endpoint. Used by Docker health checks and for manual verification that all required services are reachable.

**Method:** `GET`
**Path:** `/api/v1/health`

#### Response — 200 OK (healthy)

```json
{
  "status": "ok",
  "version": "1.0.0",
  "services": {
    "redis": "connected",
    "mcp_server": "connected",
    "openrouter": "configured"
  }
}
```

#### Response — 200 OK (degraded — MCP unreachable but fallback available)

```json
{
  "status": "degraded",
  "version": "1.0.0",
  "services": {
    "redis": "connected",
    "mcp_server": "unavailable",
    "openrouter": "configured"
  }
}
```

#### Response — 503 Service Unavailable (Redis down — cannot process jobs)

```json
{
  "status": "error",
  "version": "1.0.0",
  "services": {
    "redis": "unavailable",
    "mcp_server": "unknown",
    "openrouter": "configured"
  }
}
```

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `status` | string | `"ok"`, `"degraded"`, `"error"` | Overall health |
| `version` | string | semver | Application version |
| `services.redis` | string | `"connected"`, `"unavailable"` | Redis broker/result-backend status |
| `services.mcp_server` | string | `"connected"`, `"unavailable"`, `"unknown"` | Platy MCP subprocess status |
| `services.openrouter` | string | `"configured"`, `"unconfigured"` | Whether `OPENROUTER_API_KEY` is set (not validated via live call) |

---

## 5. Polling Contract

The client polls `GET /api/v1/jobs/{job_id}/status` until a terminal status is returned.

### Polling Rules

| Rule | Value |
|------|-------|
| Poll interval | 2 seconds |
| Terminal statuses (stop polling) | `COMPLETED`, `PARTIAL`, `FAILED` |
| Maximum poll duration | 90 seconds (client-side timeout guard) |
| On 404 during poll | Stop polling; show "Job not found. The link may have expired." |
| On network error during poll | Continue polling (transient failure); show inline reconnecting indicator |

### Progress Step Labels

The `progress_step` field is set by each Celery task. The frontend must display this verbatim.

Canonical values (backend sets these):

| Status | `progress_step` |
|--------|----------------|
| `RECEIVED` | `"Uploading CV..."` |
| `EXTRACTING` | `"Extracting text from document..."` |
| `STRUCTURING` | `"Parsing CV structure with AI..."` |
| `SCORING` | `"Computing seniority score..."` |
| `ESTIMATING` | `"Looking up salary data..."` |
| `EXPLAINING` | `"Generating explanation..."` |
| `VALIDATING` | `"Finalizing results..."` |
| `COMPLETED` | `"Analysis complete."` |
| `PARTIAL` | `"Analysis complete (partial results)."` |
| `FAILED` | `"Analysis failed."` |

### Frontend Polling Implementation (React Query)

```typescript
// hooks/useAnalysis.ts
import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { apiClient } from '../api/client';
import type { AnalyzeResponse, JobStatusResponse } from '../types/api';

const TERMINAL_STATUSES = ['COMPLETED', 'PARTIAL', 'FAILED'] as const;
const POLL_INTERVAL_MS = 2000;
const MAX_POLL_DURATION_MS = 90_000;

export function useAnalysis() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [pollStartedAt] = useState<number | null>(null);

  const submitMutation = useMutation<AnalyzeResponse, Error, FormData>({
    mutationFn: (formData) => apiClient.submitAnalysis(formData),
    onSuccess: (data) => setJobId(data.job_id),
  });

  const statusQuery = useQuery<JobStatusResponse, Error>({
    queryKey: ['job-status', jobId],
    queryFn: () => apiClient.getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status) return POLL_INTERVAL_MS;
      if (TERMINAL_STATUSES.includes(status as typeof TERMINAL_STATUSES[number])) return false;
      const elapsed = pollStartedAt ? Date.now() - pollStartedAt : 0;
      if (elapsed > MAX_POLL_DURATION_MS) return false;
      return POLL_INTERVAL_MS;
    },
  });

  return { submitMutation, statusQuery, jobId };
}
```

---

## 6. Pydantic Models (Backend)

All models live in `app/schemas.py`. Import and use these throughout the codebase — never construct raw dicts for responses.

```python
# app/schemas.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AnalysisStatus(str, Enum):
    RECEIVED    = "RECEIVED"
    EXTRACTING  = "EXTRACTING"
    STRUCTURING = "STRUCTURING"
    SCORING     = "SCORING"
    ESTIMATING  = "ESTIMATING"
    EXPLAINING  = "EXPLAINING"
    VALIDATING  = "VALIDATING"
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
    reasoning:           str       = Field(..., min_length=1, description="HOW the score was calculated: formula applied + input values. Populated by compute_score task.")
    gap_analysis:        str       = Field(..., min_length=1, description="What is numerically or structurally missing to reach maximum points. Populated by compute_score task.")
    improvements:        list[str] = Field(default_factory=list, description="1–3 specific actionable items (CV rewrite, project, cert). Populated by generate_explanation task; empty list on PARTIAL.")
    short_learning_path: list[str] = Field(default_factory=list, description="Quick wins achievable in weeks to 1–2 months (1–2 items). Populated by generate_explanation task; empty list on PARTIAL.")
    long_learning_path:  list[str] = Field(default_factory=list, description="Strategic improvements requiring 3–6+ months (1–2 items). Populated by generate_explanation task; empty list on PARTIAL.")


class ScoreBreakdown(BaseModel):
    experience:      int = Field(..., ge=0, le=30, description="Experience sub-score (max 30)")
    skills:          int = Field(..., ge=0, le=30, description="Skills sub-score (max 30)")
    education:       int = Field(..., ge=0, le=20, description="Education sub-score (max 20)")
    role_seniority:  int = Field(..., ge=0, le=20, description="Role seniority sub-score (max 20)")
    total:           int = Field(..., ge=0, le=100, description="Clamped total score")
    justifications:  dict[str, CategoryBreakdown] = Field(..., description="Per-category structured breakdown. Keys: experience, skills, education, role_seniority")
    job_fit_adjusted: bool = Field(..., description="True if job description was used for scoring")

    @model_validator(mode="after")
    def validate_total_matches_sum(self) -> "ScoreBreakdown":
        computed = self.experience + self.skills + self.education + self.role_seniority
        if abs(computed - self.total) > 1:
            raise ValueError(
                f"Score total {self.total} does not match sub-score sum {computed} (tolerance ±1)"
            )
        return self

    @model_validator(mode="after")
    def validate_justification_keys(self) -> "ScoreBreakdown":
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
    def validate_min_less_than_max(self) -> "SalaryEstimate":
        if self.min_czk >= self.max_czk:
            raise ValueError(f"min_czk ({self.min_czk}) must be less than max_czk ({self.max_czk})")
        return self


class Explanation(BaseModel):
    summary:          str       = Field(..., min_length=1)
    strengths:        list[str] = Field(..., min_length=2, description="3–5 specific strengths")
    weaknesses:       list[str] = Field(..., min_length=1, description="2–4 identified gaps")
    recommendations:  list[str] = Field(..., min_length=2, description="Actionable steps to increase salary by ~30%")
    raw_llm_response: str       = Field(..., description="Stored for debugging; never shown to users")


class AnalysisResult(BaseModel):
    request_id:       str
    seniority_score:  int            = Field(..., ge=0, le=100)
    score_breakdown:  ScoreBreakdown
    salary_estimate:  SalaryEstimate
    explanation:      Optional[Explanation] = None  # None on PARTIAL result
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
    result:        Optional[AnalysisResult] = None
    error_message: Optional[str] = None
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
    details: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
```

---

## 7. TypeScript Types (Frontend)

All types live in `frontend/src/types/api.ts`. They mirror the Pydantic models exactly. Update both files together when adding fields.

```typescript
// frontend/src/types/api.ts

// ---------------------------------------------------------------------------
// Enums / unions
// ---------------------------------------------------------------------------

export type AnalysisStatus =
  | "RECEIVED"
  | "EXTRACTING"
  | "STRUCTURING"
  | "SCORING"
  | "ESTIMATING"
  | "EXPLAINING"
  | "VALIDATING"
  | "COMPLETED"
  | "PARTIAL"
  | "FAILED";

export const TERMINAL_STATUSES: ReadonlyArray<AnalysisStatus> = [
  "COMPLETED",
  "PARTIAL",
  "FAILED",
];

export type ConfidenceLevel = "low" | "medium" | "high";

export type DataSource = "platy_mcp" | "fallback_bands";

// ---------------------------------------------------------------------------
// Sub-types (pipeline outputs)
// ---------------------------------------------------------------------------

export interface CategoryBreakdown {
  /** HOW the score was calculated: formula applied + input values. Populated by compute_score task. */
  reasoning: string;
  /** What is numerically or structurally missing to reach maximum points. Populated by compute_score task. */
  gap_analysis: string;
  /** 1–3 specific actionable items (CV rewrite, project, cert). Empty array on PARTIAL result. */
  improvements: string[];
  /** Quick wins achievable in weeks to 1–2 months (1–2 items). Empty array on PARTIAL result. */
  short_learning_path: string[];
  /** Strategic improvements requiring 3–6+ months (1–2 items). Empty array on PARTIAL result. */
  long_learning_path: string[];
}

export interface ScoreBreakdown {
  experience: number;       // 0–30
  skills: number;           // 0–30
  education: number;        // 0–20
  role_seniority: number;   // 0–20
  total: number;            // 0–100
  justifications: Record<"experience" | "skills" | "education" | "role_seniority", CategoryBreakdown>;
  job_fit_adjusted: boolean;
}

export interface SalaryEstimate {
  min_czk: number;                  // integer CZK/month
  max_czk: number;                  // integer CZK/month
  currency: "CZK";
  period: "month";
  data_source: DataSource;
  confidence: ConfidenceLevel;
  is_low_confidence_flag: boolean;
}

export interface Explanation {
  summary: string;
  strengths: string[];        // 3–5 items
  weaknesses: string[];       // 2–4 items
  recommendations: string[];  // 2+ actionable items
  raw_llm_response: string;   // for debugging, not displayed in UI
}

export interface AnalysisResult {
  request_id: string;
  seniority_score: number;          // 0–100
  score_breakdown: ScoreBreakdown;
  salary_estimate: SalaryEstimate;
  explanation: Explanation | null;  // null on PARTIAL
  confidence: ConfidenceLevel;
  created_at: string;               // ISO 8601 UTC
}

// ---------------------------------------------------------------------------
// API response types
// ---------------------------------------------------------------------------

export interface AnalyzeResponse {
  job_id: string;
  status: "RECEIVED";
  message: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: AnalysisStatus;
  progress_step: string;
  created_at: string;             // ISO 8601 UTC
  result: AnalysisResult | null;
  error_message: string | null;
  warnings: string[];
}

export interface HealthServices {
  redis: "connected" | "unavailable";
  mcp_server: "connected" | "unavailable" | "unknown";
  openrouter: "configured" | "unconfigured";
}

export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  version: string;
  services: HealthServices;
}

// ---------------------------------------------------------------------------
// Error types
// ---------------------------------------------------------------------------

export interface ApiErrorDetail {
  code: string;
  message: string;
  details: string | null;
}

export interface ApiErrorResponse {
  error: ApiErrorDetail;
}

/** Type guard: narrows a fetch response body to ApiErrorResponse */
export function isApiError(body: unknown): body is ApiErrorResponse {
  return (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    typeof (body as ApiErrorResponse).error === "object"
  );
}
```

---

## 8. Typed API Client (Frontend)

Centralised fetch wrapper lives in `frontend/src/api/client.ts`. All network calls go through this module — never call `fetch` directly in components or hooks.

```typescript
// frontend/src/api/client.ts
import type { AnalyzeResponse, ApiErrorResponse, JobStatusResponse, HealthResponse } from '../types/api';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';

class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorBody: ApiErrorResponse | null = null;
    try {
      errorBody = await response.json();
    } catch {
      // response body is not JSON
    }

    const code = errorBody?.error?.code ?? 'UNKNOWN_ERROR';
    const message = errorBody?.error?.message ?? `HTTP ${response.status}`;
    throw new ApiError(code, message, response.status);
  }
  return response.json() as Promise<T>;
}

export const apiClient = {
  /**
   * POST /api/v1/analyze
   * Submit a CV file and optional job description for analysis.
   * Returns a job_id to poll with.
   */
  async submitAnalysis(formData: FormData): Promise<AnalyzeResponse> {
    const response = await fetch(`${BASE_URL}/analyze`, {
      method: 'POST',
      body: formData,
      // Do NOT set Content-Type — browser sets multipart boundary automatically
    });
    return handleResponse<AnalyzeResponse>(response);
  },

  /**
   * GET /api/v1/jobs/{job_id}/status
   * Poll for job status and results.
   */
  async getJobStatus(jobId: string): Promise<JobStatusResponse> {
    const response = await fetch(`${BASE_URL}/jobs/${encodeURIComponent(jobId)}/status`);
    return handleResponse<JobStatusResponse>(response);
  },

  /**
   * GET /api/v1/health
   * Check backend health status.
   */
  async getHealth(): Promise<HealthResponse> {
    const response = await fetch(`${BASE_URL}/health`);
    return handleResponse<HealthResponse>(response);
  },
};

export { ApiError };
```

**Environment variable:** Set `VITE_API_BASE_URL` in `frontend/.env.local` for production:

```bash
# frontend/.env.local
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

---

## 9. All Error Codes Reference

Complete list of all `error.code` values the frontend may receive. Every code must be handled — either with a specific user message or a fallback to the `error.message` value.

| Code | HTTP Status | Source | User-Facing Action |
|------|-------------|--------|-------------------|
| `MISSING_FILE` | 400 | POST /analyze route | Show inline form error: "Please select a CV file." |
| `INVALID_FILE_TYPE` | 400 | POST /analyze route | Show inline form error: use the `error.message` verbatim |
| `FILE_TOO_LARGE` | 400 | POST /analyze route | Show inline form error: use `error.message` verbatim |
| `VALIDATION_ERROR` | 422 | FastAPI form validation | Show generic: "Request could not be processed. Please try again." |
| `TOO_MANY_REQUESTS` | 429 | POST /analyze route | Show banner: "Service is busy. Please try again in a moment." |
| `JOB_NOT_FOUND` | 404 | GET /jobs/{id}/status | Stop polling; show: "Job not found. Please start a new analysis." |
| `INTERNAL_ERROR` | 500 | Any route | Show banner: "An unexpected error occurred. Please try again." |

---

## 10. curl Examples

### Submit a PDF CV (no job description)

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -F "cv_file=@/path/to/my-cv.pdf"
```

Expected response (202):
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "RECEIVED",
  "message": "Analysis queued. Poll /api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/status for results."
}
```

### Submit a DOCX CV with a job description

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -F "cv_file=@/path/to/my-cv.docx" \
  -F "job_description=We are looking for a Senior Python Engineer with experience in Kubernetes, AWS, and distributed systems..."
```

### Poll for job status

```bash
curl http://localhost:8000/api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/status
```

### Poll until done (bash loop)

```bash
JOB_ID="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
while true; do
  RESPONSE=$(curl -s "http://localhost:8000/api/v1/jobs/${JOB_ID}/status")
  STATUS=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])")
  echo "Status: $STATUS"
  if [[ "$STATUS" == "COMPLETED" || "$STATUS" == "PARTIAL" || "$STATUS" == "FAILED" ]]; then
    echo "$RESPONSE" | python3 -m json.tool
    break
  fi
  sleep 2
done
```

### Health check

```bash
curl http://localhost:8000/api/v1/health
```

### Submit a file that is too large (expect 400)

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -F "cv_file=@/path/to/large-file.pdf"
# Response: {"error": {"code": "FILE_TOO_LARGE", "message": "File exceeds the 10 MB size limit.", "details": null}}
```

### Submit an invalid file type (expect 400)

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -F "cv_file=@/path/to/resume.txt"
# Response: {"error": {"code": "INVALID_FILE_TYPE", "message": "Unsupported file format. Please upload a PDF or DOCX file.", "details": null}}
```
