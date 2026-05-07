# Architecture Document: Job Fit & Salary Estimator

**Version:** 1.0
**Date:** 2026-05-05
**Status:** Final Draft

---

## Table of Contents

1. [Overview](#1-overview)
2. [Requirements Summary](#2-requirements-summary)
3. [Architecture Decision Records (ADRs)](#3-architecture-decision-records-adrs)
4. [System Architecture](#4-system-architecture)
5. [Multi-Agent Graph Design](#5-multi-agent-graph-design)
6. [MCP Server Design](#6-mcp-server-design)
7. [Data Model](#7-data-model)
8. [API Contracts](#8-api-contracts)
9. [Frontend Architecture](#9-frontend-architecture)
10. [Configuration Management](#10-configuration-management)
11. [Integration Points](#11-integration-points)
12. [Cross-Cutting Concerns](#12-cross-cutting-concerns)
13. [System Invariants & Enforcement](#13-system-invariants--enforcement)
14. [Failure Mode Analysis](#14-failure-mode-analysis)
15. [Technology Stack](#15-technology-stack)
16. [Risks & Mitigations](#16-risks--mitigations)
17. [Open Questions for Stakeholder Input](#17-open-questions-for-stakeholder-input)

---

## 1. Overview

### Problem Statement

Hiring managers and candidates lack a quick, objective way to assess seniority level and expected market salary based on a CV. This system provides automated CV analysis with seniority scoring, CZK salary estimation drawn from real Platy.cz market data, and LLM-generated actionable feedback — all orchestrated through a Celery task pipeline with MCP server integration.

### Scope (In)

- CV ingestion: PDF and DOCX, English-only, max 10 MB
- LLM-based CV text structuring (experience, skills, education, role titles)
- Seniority scoring 0–100 with configurable weights (YAML/JSON)
- Salary range estimation in CZK/month using Platy.cz data via MCP server
- LLM-generated explanation: summary, strengths, weaknesses, +30% salary recommendations
- Optional: job description matching (adjusts skill sub-score)
- React web frontend
- FastAPI backend
- Pipeline orchestration via Celery task queue with Redis
- GPT-4 access via OpenRouter

### Scope (Out)

- Multi-language CV support
- User accounts / authentication
- Real-time job board integration
- Production deployment infrastructure
- ATS integration
- Non-Czech market salary data

### Key Stakeholders

| Stakeholder | Interest |
|-------------|---------|
| Portfolio reviewer | Sees a coherent, working AI pipeline demo |
| End user (candidate) | Gets accurate scoring, salary estimate, actionable feedback |
| Developer | Clean, maintainable, extensible codebase |

---

## 2. Requirements Summary

### Functional Requirements (condensed)

| ID | Requirement |
|----|------------|
| FR-ING-001/002 | Accept PDF and DOCX CV files |
| FR-ING-003/004 | Reject invalid types and files > 10 MB |
| FR-ING-005 | Detect empty/image-only files |
| FR-EXT-001/002 | Extract raw text; parse into sections (experience, skills, education, certifications, languages) |
| FR-EXT-003/004 | Compute total years of experience; normalize and deduplicate skills |
| FR-SCO-001–004 | Score 0–100 with weighted sub-scores (Experience 30, Skills 30, Education 20, Role Seniority 20); configurable weights; clamp to valid range |
| FR-SAL-001–004 | Salary range in CZK/month from Platy.cz MCP; sanity check bounds 25k–500k |
| FR-LLM-001–005 | GPT-4 via OpenRouter: structured explanation with summary/strengths/weaknesses/recommendations; 30s timeout; one retry on bad response |
| FR-PIP-001–004 | Sequential pipeline with partial-result support; step timing logs; optional LLM response cache |
| FR-VAL-001/002 | Output validation; confidence indicator (low/medium/high) |

### Non-Functional Requirements

| Concern | Target |
|---------|--------|
| End-to-end latency | < 45 seconds (LLM is bottleneck) |
| Text extraction | < 5 seconds |
| Scoring + salary | < 2 seconds |
| UI responsiveness | Loading indicator within 500ms |
| Score determinism | < 5 point variance for identical input (LLM temperature = 0) |
| Salary accuracy | Within ±20% of expert assessment |
| Throughput | Single-user demo; no horizontal scaling required |

### Constraints & Assumptions

- CVs are English-only; no language detection required
- Market is Czech-only; all salary output in CZK/month
- LLM: GPT-4 via OpenRouter API (not direct OpenAI)
- Salary data source: Platy.cz, accessed via a custom MCP server
- Scoring weights configurable via YAML/JSON file
- No user authentication or session management
- CV files are NOT persisted after processing unless explicitly configured
- Personal contact data (name, email, phone) is stripped before LLM prompt construction

---

## 3. Architecture Decision Records (ADRs)

### ADR-001: Pipeline Orchestration with Celery

**Context:** The pipeline has several distinct processing steps that benefit from specialization: CV extraction, scoring, salary lookup, and explanation. We need a way to orchestrate these with proper state management, retry logic, and async processing.

**Options Considered:**

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A: Single LLM chain | One monolithic LLM prompt does everything | Simple | No separation, hard to debug, no retry per step |
| B: LangGraph multi-agent | Multiple specialized agents as graph nodes with typed state | LLM-native tool use, extensible | Over-engineered for a linear pipeline, adds complexity without real branching needs |
| C: Celery task pipeline | Async task queue with discrete workers chained together | Battle-tested, proper async, independent retry/timeout per step, scalable, monitorable (Flower) | Requires message broker (Redis) |

**Decision:** Option C — Celery task pipeline with Redis as broker. Each pipeline step is an independent Celery task chained together.

**Rationale:** The pipeline is fundamentally sequential with no complex decision-making between steps. Celery provides: independent retry logic per task, proper timeout handling, task status tracking (maps directly to our polling API), built-in monitoring via Flower, and proven production reliability. LLM calls and MCP tool calls are made within tasks as regular function calls — no need for an agent framework to invoke them.

**Consequences:** Requires Redis as message broker. Each task is independently deployable and testable. Pipeline state flows through Celery's chain mechanism. Task results stored in Redis for polling.

---

### ADR-002: CV Structuring via LLM (not rule-based parsing)

**Context:** CV text must be decomposed into structured sections. Two viable approaches exist: regex/heuristic parsing or LLM-based extraction.

**Options Considered:**

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A: Rule-based (regex) | Keyword/header matching | Fast, zero API cost, deterministic | Brittle, breaks on non-standard CVs |
| B: LLM extraction | Structured JSON prompt to GPT-4 | Handles format variability, minimal code | Adds LLM call cost, non-deterministic |
| C: Hybrid (rules + LLM fallback) | Rules first, LLM if low confidence | Cost-efficient for standard CVs | Two code paths to maintain |

**Decision:** Option B — LLM-based extraction using a structured JSON output prompt. This is handled by the `extract_cv_structure` Celery task.

**Rationale:** As documented in the requirements analysis (Section 13), LLM extraction demonstrates sophisticated LLM use, handles diverse CV formats robustly, and requires minimal maintenance. For a portfolio project where demo reliability matters more than API cost, this is correct.

**Consequences:** Each analysis incurs two LLM calls (extraction + explanation). At temperature=0, output is highly deterministic. Response is validated with Pydantic before proceeding.

---

### ADR-003: Salary Data via Platy.cz MCP Server

**Context:** Salary estimation requires real market data. The requirements specify Platy.cz as the source, accessed via a custom MCP server.

**Options Considered:**

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A: Hardcoded salary bands | Static YAML/JSON config | Simple, zero dependencies | Stale data, coarse |
| B: Platy.cz MCP server | Custom MCP server wrapping Platy.cz data | Real data, LLM-callable tool, portfolio value | Build effort, web scraping/data maintenance |
| C: CSV data file | Parsed salary survey CSV | Structured, updatable without code | No tool integration, manual data maintenance |

**Decision:** Option B — build a custom MCP server (`platy-mcp`) that exposes Platy.cz salary data as structured tools callable by the `SalaryEstimatorAgent`. Hardcoded salary bands are retained as a fallback in case MCP lookup fails.

**Rationale:** The constraint explicitly requires "Platy.cz data accessed via a custom MCP server." This also demonstrates MCP protocol integration, a key portfolio signal.

**Consequences:** Platy.cz data must be scraped or obtained beforehand and stored locally (to avoid live scraping on every request). The MCP server is a separate Python process communicating over stdio or SSE.

---

### ADR-004: FastAPI Backend with Async Endpoints

**Context:** The backend needs to expose HTTP endpoints for the React frontend and orchestrate the Celery pipeline.

**Options Considered:**

| Option | Description |
|--------|-------------|
| Flask | Synchronous, simpler | Lacks native async; poor fit for async LLM calls |
| FastAPI | Async-native, Pydantic models, auto-docs | Slight learning curve |
| Django | Full-featured | Overkill for this scope |

**Decision:** FastAPI with async endpoints and Pydantic v2 for request/response validation.

**Rationale:** FastAPI's async support works well alongside Celery's async task execution. Pydantic models serve double duty as API schema and internal data models. Built-in OpenAPI docs are useful for the portfolio.

---

### ADR-005: React Frontend (Vite + TypeScript)

**Context:** The frontend must be a React web application.

**Decision:** React 18 + TypeScript + Vite + Tailwind CSS + React Query (TanStack Query) for API state management.

**Rationale:** Vite provides fast dev server. TypeScript adds type safety for the multi-field response objects. React Query handles loading/error states and polling for job status elegantly. Tailwind avoids CSS boilerplate for a portfolio project.

---

### ADR-006: Async Job Processing via Background Tasks

**Context:** Analysis takes up to 45 seconds. A synchronous HTTP endpoint would hold the connection open, creating timeout and UX problems.

**Options Considered:**

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A: Synchronous endpoint | Block until done, return result | Simple | 45s HTTP timeout risk, poor UX |
| B: Background task + polling | POST returns job ID; client polls GET /jobs/{id}/status | Clean UX, standard REST pattern | Extra polling logic on client |
| C: WebSocket streaming | Stream partial results as they arrive | Best UX | Complex to implement, overkill for MVP |

**Decision:** Option B — POST /analyze returns a `job_id`; client polls `GET /jobs/{job_id}/status` every 2 seconds. Celery executes the pipeline as a chained task sequence. Redis stores both task state and job results.

**Rationale:** Provides clean UX (progress display per pipeline step), avoids timeout issues. Celery's built-in task state tracking (`PENDING`, `STARTED`, `SUCCESS`, `FAILURE`) maps naturally to our job status model. Redis serves double duty as Celery broker and result backend.

---

## 4. System Architecture

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User's Browser                               │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    React Frontend (Vite)                      │   │
│  │  - CV file upload + optional job description textarea         │   │
│  │  - Progress display (per-agent step status)                   │   │
│  │  - Results: score gauge, salary range, LLM explanation        │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
└─────────────────────────────│───────────────────────────────────────┘
                              │ HTTP (REST JSON)
                              │ POST /api/v1/analyze
                              │ GET  /api/v1/jobs/{id}/status
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (Python 3.12)                    │
│                                                                      │
│  ┌─────────────────┐   ┌──────────────────┐   ┌─────────────────┐  │
│  │  API Layer      │   │  Redis           │   │  Config Loader  │  │
│  │  (routes.py)    │   │  (broker+results)│   │  (YAML/JSON)    │  │
│  └────────┬────────┘   └──────────────────┘   └─────────────────┘  │
│           │                                                          │
│           │ enqueues Celery chain                                    │
│           ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              Celery Task Pipeline (chained tasks)            │    │
│  │                                                              │    │
│  │  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐ │    │
│  │  │ingest_cv     │→ │extract_cv     │→ │compute_score     │ │    │
│  │  │              │  │_structure(LLM)│  │                  │ │    │
│  │  │ - pdf_extract│  │ - GPT-4 call  │  │ - weighted calc  │ │    │
│  │  │ - docx_extract│ │ - pii_strip   │  │ - apply_weights  │ │    │
│  │  │ - validate   │  │ - validate    │  │ - jd_boost       │ │    │
│  │  └──────────────┘  └───────────────┘  └────────┬─────────┘ │    │
│  │                                                 │            │    │
│  │  ┌──────────────────────────────────────────────▼─────────┐ │    │
│  │  │              estimate_salary                            │ │    │
│  │  │  - lookup_salary_mcp (calls Platy MCP Server)          │ │    │
│  │  │  - fallback_salary_bands (if MCP fails)                │ │    │
│  │  │  - validate_salary_range                               │ │    │
│  │  └──────────────────────────┬──────────────────────────────┘ │    │
│  │                             │                                  │    │
│  │  ┌──────────────────────────▼──────────────────────────────┐ │    │
│  │  │              generate_explanation (LLM)                 │ │    │
│  │  │  - GPT-4 call via OpenRouter                           │ │    │
│  │  │  - validate structure                                  │ │    │
│  │  │  - retry once on malformed response                    │ │    │
│  │  └──────────────────────────┬──────────────────────────────┘ │    │
│  │                             │                                  │    │
│  │  ┌──────────────────────────▼──────────────────────────────┐ │    │
│  │  │              assemble_output                            │ │    │
│  │  │  - validate all fields                                 │ │    │
│  │  │  - compute confidence                                  │ │    │
│  │  │  - store final result in Redis                         │ │    │
│  │  └─────────────────────────────────────────────────────────┘ │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────┬──────────────────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────┐
              │                            │                         │
              ▼                            ▼                         ▼
┌─────────────────────┐     ┌──────────────────────┐   ┌──────────────────┐
│  Platy MCP Server   │     │  OpenRouter API       │   │  Local File      │
│  (Python stdio MCP) │     │  (GPT-4)              │   │  System          │
│                     │     │                        │   │  (temp uploads)  │
│  tools:             │     │  Used by:              │   │                  │
│  - get_salary_range │     │  - CVExtractorAgent    │   │  /tmp/uploads/   │
│  - list_roles       │     │  - ExplanationAgent    │   │  (auto-deleted)  │
│  - get_market_stats │     │                        │   │                  │
│                     │     │  model: gpt-4o         │   │                  │
│  data: salary_data/ │     │  temp: 0.0             │   │                  │
│  (JSON/CSV)         │     │  timeout: 30s          │   │                  │
└─────────────────────┘     └──────────────────────┘   └──────────────────┘
```

### Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| React Frontend | File upload, job description input, progress polling, results rendering |
| FastAPI API Layer | HTTP routing, file validation, enqueues Celery chain, serves job status |
| Redis | Celery message broker + result backend + job state store |
| Celery Worker | Executes pipeline tasks sequentially via chain |
| `ingest_cv` task | File format validation, text extraction (PDF/DOCX), PII stripping |
| `extract_cv_structure` task | LLM-based structured extraction of CV sections into typed Pydantic model |
| `compute_score` task | Weighted scoring algorithm, job-fit adjustment when JD provided |
| `estimate_salary` task | Salary lookup via Platy MCP, fallback to hardcoded bands, sanity check |
| `generate_explanation` task | LLM-generated explanation with retry on malformed response |
| `assemble_output` task | Validates final output, computes confidence, stores AnalysisResult in Redis |
| Platy MCP Server | Exposes Platy.cz salary data as structured tool calls via MCP protocol |
| Config Loader | Reads scoring weights and salary bands from YAML/JSON at startup |

---

## 5. Celery Pipeline Design

### Overview

The pipeline is modeled as a Celery chain — a sequence of tasks where each task's return value is passed as the first argument to the next task. All tasks share a common `PipelineContext` dict that accumulates results as it flows through the chain.

#### 5.1 Pipeline Data Models

```python
from typing import Optional, Literal
from pydantic import BaseModel

class ParsedCV(BaseModel):
    raw_text: str                        # full extracted text
    sections: dict[str, str]             # {"experience": "...", "skills": "..."}
    skills: list[str]                    # normalized, deduplicated
    experience_years: float              # total non-overlapping years
    education_level: str                 # "bachelor" | "master" | "phd" | "other"
    role_titles: list[str]               # e.g. ["Senior Software Engineer", "Tech Lead"]
    has_management_indicators: bool      # true if "managed", "led team of", etc.

class CategoryBreakdown(BaseModel):
    reasoning:           str       # HOW the score was calculated (formula + inputs); populated by compute_score task
    gap_analysis:        str       # What is missing to reach maximum points; populated by compute_score task
    improvements:        list[str] # Specific actionable items (1–3 bullets); LLM-populated; empty list on PARTIAL
    short_learning_path: list[str] # Quick wins, weeks–2 months (1–2 items); LLM-populated; empty list on PARTIAL
    long_learning_path:  list[str] # Strategic, 3–6+ months (1–2 items); LLM-populated; empty list on PARTIAL

class ScoreBreakdown(BaseModel):
    experience: int                      # 0–30
    skills: int                          # 0–30
    education: int                       # 0–20
    role_seniority: int                  # 0–20
    total: int                           # 0–100; sum of sub-scores, clamped
    justifications: dict[str, CategoryBreakdown]  # keys: experience, skills, education, role_seniority
    job_fit_adjusted: bool               # true if JD was used in scoring

class SalaryEstimate(BaseModel):
    min_czk: int                         # minimum CZK/month
    max_czk: int                         # maximum CZK/month
    currency: Literal["CZK"] = "CZK"
    period: Literal["month"] = "month"
    data_source: str                     # "platy_mcp" | "fallback_bands"
    confidence: Literal["low", "medium", "high"]
    is_low_confidence_flag: bool         # true if outside 25k–500k bounds

class Explanation(BaseModel):
    summary: str
    strengths: list[str]                 # 3–5 items
    weaknesses: list[str]                # 2–4 items
    recommendations: list[str]           # specific, actionable, 2+ items
    raw_llm_response: str                # stored for debugging
```

#### 5.2 Pipeline Context (flows through chain)

```python
# Each task receives and returns this dict
PipelineContext = {
    # Inputs (set at chain start)
    "job_id": str,
    "file_path": str,                    # temp file path on disk
    "file_type": "pdf" | "docx",
    "job_description": Optional[str],

    # Accumulated results (added by each task)
    "parsed_cv": Optional[dict],         # ParsedCV.model_dump()
    "score_breakdown": Optional[dict],   # ScoreBreakdown.model_dump()
    "salary_estimate": Optional[dict],   # SalaryEstimate.model_dump()
    "explanation": Optional[dict],       # Explanation.model_dump()

    # Metadata
    "warnings": list[str],
    "step_timings": dict[str, float],    # {task_name: duration_seconds}
}
```

#### 5.3 Chain Definition

```python
from celery import chain
from app.tasks import (
    ingest_cv,
    extract_cv_structure,
    compute_score,
    estimate_salary,
    generate_explanation,
    assemble_output,
)

def run_analysis_pipeline(job_id: str, file_path: str, file_type: str, job_description: str | None):
    """Enqueue the full analysis pipeline as a Celery chain."""
    context = {
        "job_id": job_id,
        "file_path": file_path,
        "file_type": file_type,
        "job_description": job_description,
        "warnings": [],
        "step_timings": {},
    }

    pipeline = chain(
        ingest_cv.s(context),
        extract_cv_structure.s(),
        compute_score.s(),
        estimate_salary.s(),
        generate_explanation.s(),
        assemble_output.s(),
    )

    pipeline.apply_async(task_id=job_id)
```

#### 5.4 Task Status Updates

Each task updates job status in Redis before and after execution:

```python
import redis
import time
from celery import shared_task

redis_client = redis.Redis()

def update_job_status(job_id: str, status: str, progress_step: str):
    redis_client.hset(f"job:{job_id}", mapping={
        "status": status,
        "progress_step": progress_step,
    })

@shared_task(bind=True, max_retries=0, time_limit=30)
def ingest_cv(self, context: dict) -> dict:
    job_id = context["job_id"]
    update_job_status(job_id, "EXTRACTING", "Extracting text from document...")
    start = time.time()

    # ... extraction logic ...

    context["step_timings"]["ingest_cv"] = time.time() - start
    return context
```

#### 5.5 Error Handling Strategy

| Task | On Failure | Behavior |
|------|-----------|----------|
| `ingest_cv` | Critical | Chain aborts; job status → FAILED |
| `extract_cv_structure` | Critical | Chain aborts; job status → FAILED |
| `compute_score` | Critical | Chain aborts; job status → FAILED |
| `estimate_salary` | Degraded | Falls back to hardcoded bands; adds warning; chain continues |
| `generate_explanation` | Non-critical | Sets explanation=None; adds warning; chain continues with PARTIAL |
| `assemble_output` | Critical | Chain aborts; job status → FAILED |

```python
@shared_task(bind=True, max_retries=1, time_limit=35)
def generate_explanation(self, context: dict) -> dict:
    """Non-critical task: on failure, pipeline continues with partial results."""
    job_id = context["job_id"]
    update_job_status(job_id, "EXPLAINING", "Generating explanation...")

    try:
        # ... LLM call logic ...
        context["explanation"] = explanation.model_dump()
    except Exception as e:
        context["explanation"] = None
        context["warnings"].append(f"LLM explanation unavailable: {str(e)}")

    return context
```

#### 5.6 Task Definitions

##### Task: `ingest_cv`

**Role:** Validate file, extract raw text, strip PII from raw text.

**Functions used:**
```python
def extract_pdf_text(file_path: str) -> dict:
    """Extract text from a PDF file. Returns {text: str, page_count: int, is_image_only: bool}"""

def extract_docx_text(file_path: str) -> dict:
    """Extract text from a DOCX file. Returns {text: str, paragraph_count: int}"""

def strip_pii_from_text(text: str) -> str:
    """Remove email addresses, phone numbers from text before LLM processing."""
```

**Logic (pure Python, no LLM call):**
1. Validate file_type and file size (raise if > 10 MB)
2. Dispatch to `extract_pdf_text` or `extract_docx_text`
3. If text is empty or < 50 words → raise exception (chain aborts, job → FAILED)
4. If page count > 10 → truncate and add warning
5. Run `strip_pii_from_text`
6. Add `raw_text` to context

**Does NOT make LLM calls.** Deterministic, fast (< 5s target). `time_limit=15`.

---

##### Task: `extract_cv_structure`

**Role:** Use GPT-4 via OpenRouter to extract structured CV data from raw text.

```python
@shared_task(bind=True, max_retries=1, time_limit=35)
def extract_cv_structure(self, context: dict) -> dict:
    """
    Sends raw CV text to GPT-4 with a structured extraction prompt.
    Validates response with ParsedCV Pydantic model.
    Retries once if response is not valid JSON matching schema.
    """
```

**System Prompt (extraction):**
```
You are a CV parser. Extract structured information from the following CV text.
Return ONLY valid JSON matching this exact schema:
{
  "sections": {
    "experience": "<work experience text>",
    "skills": "<skills text>",
    "education": "<education text>",
    "certifications": "<certifications or empty string>",
    "languages": "<languages or empty string>"
  },
  "skills": ["list", "of", "normalized", "lowercase", "skills"],
  "experience_years": <float total years>,
  "education_level": "<bachelor|master|phd|other>",
  "role_titles": ["list", "of", "job", "titles"],
  "has_management_indicators": <true|false>
}
Do not include any explanation outside the JSON object.
```

**Validation:** Response parsed with `ParsedCV.model_validate_json()`. On `ValidationError`, retry once with stricter prompt. On second failure, raise exception (chain aborts).

**LLM Config:** `model=gpt-4o` via OpenRouter, `temperature=0.0`, `timeout=30s`, `response_format={"type": "json_object"}`

---

##### Task: `compute_score`

**Role:** Compute the weighted seniority score. No LLM call.

**Scoring Logic:**

| Sub-score | Max | Calculation |
|-----------|-----|-------------|
| experience | 30 | `min(30, years * 2.5)` (12 years → capped at 30) |
| skills | 30 | `base_skill_score + jd_boost`; base = `min(30, len(skills) * 1.5)`; jd_boost = matched_skills / total_jd_skills * 10, capped so total ≤ 30 |
| education | 20 | phd=20, master=17, bachelor=13, other=8 |
| role_seniority | 20 | calculated from highest role title string matching: principal/vp=20, lead/staff=17, senior=13, mid=8, junior=3; +2 if has_management_indicators |

Weights are loaded from `config/scoring_weights.yaml` at startup. If weights sum ≠ 100, system normalizes and logs a warning.

**No LLM calls. Deterministic.** `time_limit=10`.

---

##### Task: `estimate_salary`

**Role:** Look up salary range from Platy.cz data via MCP, apply sanity check.

**Functions used:**
```python
def lookup_salary_mcp(role_category: str, seniority_tier: str) -> dict:
    """Calls Platy MCP Server tool get_salary_range. Returns {min_czk, max_czk, source, year}."""

def classify_role_category(role_titles: list[str], skills: list[str]) -> str:
    """Maps role titles + skills to Platy.cz role category. Rule-based (no LLM)."""

def score_to_seniority_tier(total_score: int) -> str:
    """Maps 0-100 score to: 'junior' (0-34), 'mid' (35-59), 'senior' (60-79), 'lead' (80-100)."""

def fallback_salary_bands(role_category: str, seniority_tier: str) -> dict:
    """Hardcoded salary bands as fallback when MCP lookup fails."""

def validate_salary_range(min_czk: int, max_czk: int) -> dict:
    """Checks min < max, both > 0, within 25k-500k plausible bounds."""
```

**Logic:**
1. `classify_role_category` → role_category string
2. `score_to_seniority_tier` → seniority_tier
3. Try `lookup_salary_mcp`; on failure → `fallback_salary_bands`
4. `validate_salary_range` → set `is_low_confidence_flag` if outside plausible bounds
5. Populate `SalaryEstimate`

**No LLM calls.**

---

##### Task: `generate_explanation`

**Role:** Generate natural-language explanation via GPT-4. Non-critical: pipeline continues on failure (PARTIAL result).

**System Prompt (explanation):**
```
You are a senior career coach specializing in the Czech IT job market.
Given a candidate's CV analysis results, provide a structured evaluation.

Return ONLY valid JSON:
{
  "summary": "<2-3 sentence summary of why this score and salary were assigned>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "weaknesses": ["<gap 1>", "<gap 2>"],
  "recommendations": [
    "<specific actionable step to increase salary by ~30%, naming actual skills/certs>",
    "<specific actionable step 2>"
  ]
}
```

**Timeout:** 30 seconds (`time_limit=35`). On timeout → set `explanation = None`, add warning.
**Retry:** `max_retries=1`. On failed validation, retry once with stricter prompt. On second failure → explanation=None, chain continues.

---

##### Task: `assemble_output`

**Role:** Validate all fields, compute confidence, assemble final `AnalysisResult`, store in Redis. No LLM calls.

**Confidence calculation:**
- **low:** CV < 50 words OR score == 0 OR salary.is_low_confidence_flag
- **medium:** CV 50-200 words OR explanation is None
- **high:** all sections found, explanation present, salary in bounds

**Final status:**
- All fields present → COMPLETED
- explanation is None → PARTIAL
- Critical validation fails → FAILED

---

## 6. MCP Server Design

### 6.1 Overview

The Platy MCP Server is a standalone Python process implementing the Model Context Protocol (MCP). It exposes Platy.cz salary data as structured tools that the `estimate_salary` Celery task can call. Communication is via **stdio** transport (simple, reliable for local deployment; upgrade to SSE for remote).

### 6.2 Data Source Strategy

Platy.cz does not provide a public API. The MCP server uses **pre-scraped / manually curated data** stored as local JSON files:

```
platy_mcp/
├── server.py               # MCP server entry point
├── data/
│   ├── salary_data.json    # curated from Platy.cz salary survey pages
│   └── roles.json          # canonical role category list
└── tools.py                # tool implementations
```

**`salary_data.json` schema:**
```json
[
  {
    "role_category": "software-engineer",
    "seniority_tier": "junior",
    "min_czk": 35000,
    "max_czk": 55000,
    "source": "platy.cz",
    "year": 2025,
    "sample_size": 1240
  },
  {
    "role_category": "software-engineer",
    "seniority_tier": "mid",
    "min_czk": 55000,
    "max_czk": 90000,
    "source": "platy.cz",
    "year": 2025,
    "sample_size": 3100
  }
]
```

### 6.3 MCP Tool Definitions

```python
# platy_mcp/tools.py

@mcp.tool()
def get_salary_range(role_category: str, seniority_tier: str) -> dict:
    """
    Returns salary range for a given role and seniority tier from Platy.cz data.

    Args:
        role_category: One of the canonical role categories (see list_roles tool).
                       Use 'software-engineer' as default for unknown IT roles.
        seniority_tier: One of 'junior', 'mid', 'senior', 'lead', 'principal'

    Returns:
        {
            "role_category": str,
            "seniority_tier": str,
            "min_czk": int,
            "max_czk": int,
            "source": "platy.cz",
            "year": int,
            "sample_size": int,
            "found": bool  # false if no exact match, returns closest
        }
    """

@mcp.tool()
def list_roles() -> list[str]:
    """
    Returns all canonical role category strings supported by the salary database.
    Use this to find the correct role_category string before calling get_salary_range.
    """

@mcp.tool()
def get_market_stats(role_category: str) -> dict:
    """
    Returns market statistics across all seniority tiers for a role.

    Returns:
        {
            "role_category": str,
            "tiers": [
                {
                    "tier": str,
                    "median_czk": int,
                    "min_czk": int,
                    "max_czk": int
                }
            ],
            "year": int
        }
    """
```

### 6.4 MCP Server Entry Point

```python
# platy_mcp/server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("platy-salary-mcp")
# tools registered via @mcp.tool() decorators in tools.py

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### 6.5 MCP Client Integration in Celery Worker

The `estimate_salary` task communicates with the MCP server via the `mcp` Python client SDK. The MCP client session is initialized once per worker process (not per request):

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Initialized in Celery worker_init signal
_mcp_session: ClientSession | None = None

async def create_platy_mcp_client() -> ClientSession:
    server_params = StdioServerParameters(
        command="python",
        args=["platy_mcp/server.py"],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return session

# Called in estimate_salary task
async def lookup_salary_via_mcp(role_category: str, seniority_tier: str) -> dict:
    result = await _mcp_session.call_tool(
        "get_salary_range",
        arguments={"role_category": role_category, "seniority_tier": seniority_tier}
    )
    return result
```

The MCP server subprocess is managed by the Celery worker lifecycle — started on `worker_init`, terminated on `worker_shutdown`.

### 6.6 Role Category Mapping

A rule-based mapping (no LLM) maps CV role titles + skills to canonical role categories:

```yaml
# config/role_mappings.yaml
software-engineer:
  title_keywords: ["software engineer", "software developer", "backend developer", "frontend developer", "fullstack"]
  skill_signals: ["python", "java", "javascript", "typescript", "golang", "rust"]

data-scientist:
  title_keywords: ["data scientist", "ml engineer", "machine learning"]
  skill_signals: ["pytorch", "tensorflow", "scikit-learn", "pandas", "numpy"]

devops-engineer:
  title_keywords: ["devops", "sre", "platform engineer", "infrastructure"]
  skill_signals: ["kubernetes", "terraform", "ansible", "ci/cd", "docker"]

data-engineer:
  title_keywords: ["data engineer", "etl developer"]
  skill_signals: ["spark", "airflow", "dbt", "kafka"]

product-manager:
  title_keywords: ["product manager", "product owner"]
  skill_signals: []

default: "software-engineer"
```

---

## 7. Data Model

### 7.1 Core Entities

These entities are stored in Redis (no database for MVP). They flow through the Celery pipeline context.

#### AnalysisRequest (persisted in Redis)

```python
class AnalysisRequest(BaseModel):
    id: str                              # UUID, generated on submission
    file_type: Literal["pdf", "docx"]   # file format (not file path — see below)
    temp_file_path: str                  # absolute path to temp file on disk
    job_description_provided: bool       # whether JD text was submitted
    created_at: datetime
    status: AnalysisStatus               # enum: RECEIVED | EXTRACTING | ... | COMPLETED | PARTIAL | FAILED
    error_message: Optional[str]
    warnings: list[str]
    step_timings: dict[str, float]
    result: Optional[AnalysisResult]     # None until COMPLETED/PARTIAL
```

**Single-purpose field note:**
- `temp_file_path`: stores ONLY the local filesystem path. Never stores a URL, S3 key, or remote reference.
- `file_type`: stores ONLY the file format string ("pdf" or "docx"). Never used for routing logic other than dispatch to correct extractor.

#### AnalysisResult (assembled at end of pipeline)

```python
class AnalysisResult(BaseModel):
    request_id: str
    seniority_score: int                 # 0–100
    score_breakdown: ScoreBreakdown
    salary_estimate: SalaryEstimate
    explanation: Optional[Explanation]   # None on PARTIAL result
    confidence: Literal["low", "medium", "high"]
    created_at: datetime
```

### 7.2 Status Enum

```python
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
```

### 7.3 Configuration Data Structures

```python
class ScoringWeights(BaseModel):
    experience: int = 30     # max points for experience sub-score
    skills: int = 30
    education: int = 20
    role_seniority: int = 20
    # invariant: sum must equal 100

class SalaryBand(BaseModel):
    role_category: str
    seniority_tier: str      # junior | mid | senior | lead | principal
    min_czk: int
    max_czk: int
    source: str
    year: int
```

### 7.4 Data Flow

```
File Upload (multipart/form-data)
    │
    ▼
[API Layer] → validates type/size → saves to /tmp/uploads/{job_id}.{ext}
    │
    ▼
[ingest_cv] reads temp_file_path → extracts text → strips PII
    │
    ▼ (context + raw_text)
[extract_cv_structure] → GPT-4 extraction → ParsedCV
    │
    ▼ (context + ParsedCV)
[compute_score] → ScoreBreakdown
    │
    ▼ (context + score)
[estimate_salary] → MCP tool call → SalaryEstimate
    │
    ▼ (context + salary)
[generate_explanation] → GPT-4 explanation → Explanation (or None)
    │
    ▼ (complete context)
[assemble_output] → AnalysisResult
    │
    ▼
[Redis] stores AnalysisResult
    │
    ▼
[API] client polls GET /jobs/{id}/status → returns AnalysisResult
    │
    ▼
[Cleanup] delete /tmp/uploads/{job_id}.{ext} after result is stored
```

**Privacy constraint enforcement:**
- `temp_file_path` is deleted immediately after `OutputAssemblerAgent` completes (success or failure)
- Logs never include the raw_text or any name/email/phone extracted from CV
- LLM prompts receive PII-stripped text only

---

## 8. API Contracts

### 8.1 Base URL

```
http://localhost:8000/api/v1
```

### 8.2 Endpoints

#### POST /api/v1/analyze

Submit a CV for analysis.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| cv_file | file | Yes | PDF or DOCX, max 10 MB |
| job_description | string | No | Plain text job description |

**Response 202 Accepted:**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "RECEIVED",
  "message": "Analysis queued. Poll /api/v1/jobs/{job_id}/status for results."
}
```

**Error Responses:**

| Status | Error Code | Message |
|--------|-----------|---------|
| 400 | `MISSING_FILE` | "No CV file provided" |
| 400 | `INVALID_FILE_TYPE` | "Unsupported file format. Use PDF or DOCX." |
| 400 | `FILE_TOO_LARGE` | "File exceeds 10 MB limit." |
| 429 | `TOO_MANY_REQUESTS` | "Service busy. Please retry in a moment." |
| 500 | `INTERNAL_ERROR` | "Processing failed. Please try again." |

---

#### GET /api/v1/jobs/{job_id}/status

Poll for job status and results.

**Response 200:**
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

**Response 200 (COMPLETED):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "COMPLETED",
  "progress_step": "Analysis complete",
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
          "reasoning": "8 years across 3 roles. Formula: 10 pts/3-year block; 2 full blocks + 2 partial years = 25/30.",
          "gap_analysis": "4 more years needed to reach the 30-point ceiling.",
          "improvements": ["Add metrics and outcomes to each role entry.", "Quantify impact with team size, scale, SLA data."],
          "short_learning_path": ["Add metrics to CV entries (1–2 hours of editing)."],
          "long_learning_path": ["Target a Staff Engineer or Architect title over 12–24 months."]
        },
        "skills": {
          "reasoning": "14 skills matched; 3 JD-required (Python, AWS, Kubernetes) add 2 bonus pts. Score: 22/30.",
          "gap_analysis": "Missing JD-required skills: Terraform, Prometheus, Helm.",
          "improvements": ["Obtain HashiCorp Terraform Associate certification."],
          "short_learning_path": ["Complete Terraform Associate study path (3–4 weeks)."],
          "long_learning_path": ["Lead infrastructure-as-code adoption at current employer."]
        },
        "education": {
          "reasoning": "Bachelor's degree in Computer Science = 15 pts. No Master's detected.",
          "gap_analysis": "Master's degree would add 5 pts to reach 20/20.",
          "improvements": ["Highlight professional certifications as partial substitutes."],
          "short_learning_path": ["Obtain AWS Solutions Architect Associate (4–6 weeks)."],
          "long_learning_path": ["Evaluate part-time Master's programme."]
        },
        "role_seniority": {
          "reasoning": "Highest title: Senior Software Engineer = 10 pts. No management indicators.",
          "gap_analysis": "Staff Engineer title or team leadership evidence adds up to 10 pts.",
          "improvements": ["Mention team leadership scope or mentoring in role descriptions."],
          "short_learning_path": ["Reframe CV to surface existing technical leadership."],
          "long_learning_path": ["Pursue Staff Engineer role or cross-team technical initiative."]
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
        "Deep Python expertise demonstrated across multiple roles",
        "Hands-on Kubernetes and AWS experience relevant to the target role",
        "Consistent career progression from junior to senior level"
      ],
      "weaknesses": [
        "No formal cloud certification (AWS/GCP)",
        "Limited evidence of system design or architecture ownership"
      ],
      "recommendations": [
        "Obtain AWS Solutions Architect Associate certification (directly maps to 10-15% salary increase for cloud roles in Czech market)",
        "Lead or contribute to an open-source project to demonstrate architectural decision-making"
      ],
      "raw_llm_response": "..."
    },
    "confidence": "high",
    "created_at": "2026-05-05T10:00:35Z"
  },
  "error_message": null,
  "warnings": []
}
```

**Response 200 (PARTIAL — explanation unavailable):**
```json
{
  "job_id": "...",
  "status": "PARTIAL",
  "result": {
    "explanation": null,
    "seniority_score": 72,
    "salary_estimate": {...},
    "score_breakdown": {...},
    "confidence": "medium"
  },
  "warnings": ["LLM explanation unavailable due to timeout. Score and salary are complete."]
}
```

**Response 200 (FAILED):**
```json
{
  "job_id": "...",
  "status": "FAILED",
  "result": null,
  "error_message": "No extractable text found. The file may be a scanned image.",
  "warnings": []
}
```

**Error Responses:**

| Status | Error Code | Message |
|--------|-----------|---------|
| 404 | `JOB_NOT_FOUND` | "No job found with this ID." |

---

#### GET /api/v1/health

Health check endpoint.

**Response 200:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "mcp_server": "connected",
  "openrouter": "configured"
}
```

---

### 8.3 Error Response Schema (all errors)

```json
{
  "error": {
    "code": "INVALID_FILE_TYPE",
    "message": "Unsupported file format. Use PDF or DOCX.",
    "details": null
  }
}
```

### 8.4 Versioning Strategy

API is versioned via URL path prefix (`/api/v1`). No breaking changes without incrementing the version. The frontend always targets the explicit version prefix.

---

## 9. Frontend Architecture

### 9.1 Directory Structure

```
frontend/
├── src/
│   ├── api/
│   │   └── client.ts           # typed API client (fetch wrappers)
│   ├── components/
│   │   ├── UploadForm.tsx       # file dropzone + job description textarea
│   │   ├── ProgressTracker.tsx  # step-by-step progress display
│   │   ├── ScoreGauge.tsx       # circular score visualization
│   │   ├── SalaryRange.tsx      # min-max salary display with confidence badge
│   │   ├── ExplanationPanel.tsx # collapsible strengths/weaknesses/recommendations
│   │   └── ErrorBanner.tsx      # error and warning display
│   ├── hooks/
│   │   └── useAnalysis.ts       # React Query hook for polling job status
│   ├── types/
│   │   └── api.ts               # TypeScript types mirroring backend Pydantic models
│   ├── pages/
│   │   └── AnalyzerPage.tsx     # main page composing all components
│   └── main.tsx
├── public/
├── index.html
├── vite.config.ts
├── tailwind.config.ts
└── package.json
```

### 9.2 State Management

React Query (`@tanstack/react-query`) handles:
- `POST /api/v1/analyze` mutation on form submit
- `GET /api/v1/jobs/{job_id}/status` polling query (every 2 seconds)
- Polling stops when status is `COMPLETED`, `PARTIAL`, or `FAILED`
- Loading/error states managed by React Query's built-in state

```typescript
// hooks/useAnalysis.ts
export function useAnalysis() {
  const [jobId, setJobId] = useState<string | null>(null);

  const submitMutation = useMutation({
    mutationFn: (formData: FormData) => api.submitAnalysis(formData),
    onSuccess: (data) => setJobId(data.job_id),
  });

  const statusQuery = useQuery({
    queryKey: ['job-status', jobId],
    queryFn: () => api.getJobStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (data) => {
      const terminal = ['COMPLETED', 'PARTIAL', 'FAILED'];
      return terminal.includes(data?.status ?? '') ? false : 2000;
    },
  });

  return { submitMutation, statusQuery };
}
```

### 9.3 Progress Step Display

Map `pipeline_status` → human-readable step label:

```typescript
const PROGRESS_LABELS: Record<string, string> = {
  RECEIVED:    "Uploading CV...",
  EXTRACTING:  "Extracting text from document...",
  STRUCTURING: "Parsing CV structure with AI...",
  SCORING:     "Computing seniority score...",
  ESTIMATING:  "Looking up salary data...",
  EXPLAINING:  "Generating explanation...",
  VALIDATING:  "Finalizing results...",
  COMPLETED:   "Analysis complete.",
  PARTIAL:     "Analysis complete (partial results).",
  FAILED:      "Analysis failed.",
};
```

### 9.4 File Upload Constraints (client-side)

- Accept: `.pdf,.docx`
- Max size check: 10 MB before submission (client-side pre-check)
- File type validation by MIME type and extension

---

## 10. Configuration Management

### 10.1 Scoring Weights

```yaml
# config/scoring_weights.yaml
# Weights define max points per sub-score. Must sum to 100.
scoring_weights:
  experience: 30      # based on total years and role progression
  skills: 30          # breadth, depth, relevance; boosted if JD provided
  education: 20       # degree level and field relevance
  role_seniority: 20  # job title seniority and management indicators
```

Loaded at application startup. Validated: must sum to 100. Changes take effect on restart (no hot reload for MVP).

### 10.2 Salary Fallback Bands

```yaml
# config/salary_bands.yaml
# Used when Platy MCP server is unavailable.
# Values in CZK/month.
salary_bands:
  software-engineer:
    junior:    { min: 35000, max: 55000 }
    mid:       { min: 55000, max: 90000 }
    senior:    { min: 90000, max: 140000 }
    lead:      { min: 120000, max: 180000 }
    principal: { min: 160000, max: 250000 }
  data-scientist:
    junior:    { min: 40000, max: 60000 }
    mid:       { min: 60000, max: 95000 }
    senior:    { min: 95000, max: 145000 }
    lead:      { min: 130000, max: 190000 }
  default:
    junior:    { min: 30000, max: 50000 }
    mid:       { min: 50000, max: 80000 }
    senior:    { min: 80000, max: 120000 }
    lead:      { min: 110000, max: 160000 }
```

### 10.3 Environment Variables

```bash
# .env (never committed to source control)
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openai/gpt-4o
LLM_TEMPERATURE=0.0
LLM_TIMEOUT_SECONDS=30

BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_URL=http://localhost:5173

# Optional
LLM_CACHE_ENABLED=false
LLM_CACHE_TTL_SECONDS=86400
MAX_CONCURRENT_JOBS=5
UPLOAD_DIR=/tmp/uploads
```

All secrets loaded via `python-dotenv`. Never logged. `OPENROUTER_API_KEY` validated at startup (HEAD request to OpenRouter); startup fails fast if key is invalid.

### 10.4 LLM Response Cache (optional, FR-PIP-004)

When `LLM_CACHE_ENABLED=true`, a SHA-256 hash of the PII-stripped raw CV text is used as the cache key. Cache is in-memory (dict) for MVP; configurable TTL. Disabled by default.

---

## 11. Integration Points

### 11.1 OpenRouter API

**Protocol:** HTTPS REST (OpenAI-compatible API format)
**Auth:** Bearer token (`OPENROUTER_API_KEY`)
**Endpoint:** `POST https://openrouter.ai/api/v1/chat/completions`
**Model:** `openai/gpt-4o`
**Used by:** `extract_cv_structure` task, `generate_explanation` task
**Retry policy:** 1 retry on 429 (rate limit) with 5s backoff; no retry on 401/400
**Timeout:** 30 seconds per call

### 11.2 Platy MCP Server

**Protocol:** MCP over stdio
**Transport:** `StdioServerParameters` (subprocess)
**Used by:** `estimate_salary` task
**Initialization:** Once per Celery worker process; session reused
**Failure handling:** On MCP call failure → fallback to `salary_bands.yaml`
**Retry policy:** 1 retry with 1s backoff; then fallback

### 11.3 Local Filesystem

**Used for:** Temporary CV file storage during processing
**Path:** `UPLOAD_DIR` env var (default: `/tmp/uploads/`)
**File naming:** `{job_id}.{ext}` — no original filename preserved (security)
**Cleanup:** Deleted immediately after `assemble_output` task completes
**No URL or remote path ever stored in `temp_file_path` field**

---

## 12. Cross-Cutting Concerns

### 12.1 Authentication & Authorization

**What:** No user authentication required (single-user portfolio demo). API endpoints are unauthenticated.
**Where:** All FastAPI routes are public.
**How:** N/A for MVP. If multi-user is added later, all job records must be scoped to a user session or API key.
**Gaps:** No auth is acceptable for a local demo. For production, add Bearer token or API key middleware at the route level before any other change.

### 12.2 File Security

**What:** Uploaded files are validated for type and size before any processing. Files are stored only in the configured `UPLOAD_DIR`. No path traversal is possible because filenames are replaced with `{job_id}.{ext}`.
**Where:** `POST /api/v1/analyze` route handler; `ingest_cv` task functions.
**How:** Python `magic` library (libmagic) validates MIME type independent of file extension. File size checked before writing to disk.
**Gaps:** Large file streaming not implemented for MVP; 10 MB limit mitigates risk.

### 12.3 PII Handling

**What:** Email addresses, phone numbers are stripped from CV text before it is sent to any LLM prompt. Names are NOT stripped (needed for context) but are not logged.
**Where:** `strip_pii_from_text` function in `ingest_cv` task; applied before `extract_cv_structure`.
**How:** Regex patterns for email (`[\w\.-]+@[\w\.-]+\.\w+`) and phone numbers.
**Gaps:** Stripping is best-effort regex. Unusual formats may not be caught. This is acceptable for MVP (no production data).

### 12.4 Logging & Observability

**What:**
- Structured JSON logs via Python `structlog`
- Each log entry includes: `job_id`, `step`, `duration_ms`, `status`
- Logs NEVER include: raw CV text, PII fields, LLM API keys
- Step timings collected in `PipelineState.step_timings` and included in final log entry

**Where:** Every Celery task logs entry/exit with timing. API routes log request receipt and response status.
**How:** `structlog` configured with `JSONRenderer`. Log level via `LOG_LEVEL` env var (default: `INFO`).
**Gaps:** No distributed tracing (overkill for single-process MVP).

### 12.5 Error Handling

**What:** All errors produce structured JSON error responses. Internal Python exceptions are caught at the API boundary and never exposed raw.
**Where:** FastAPI exception handlers catch `ValueError`, `HTTPException`, and generic `Exception`. Celery tasks catch and translate errors into job status updates in Redis.
**How:** Global `@app.exception_handler(Exception)` returns `{"error": {"code": ..., "message": ...}}`.
**Gaps:** None; all error paths documented in §14.

### 12.6 Configuration Management

**What:** All configurable values (scoring weights, salary bands, LLM settings, file limits) are externalized. No magic numbers in business logic code.
**Where:** `config/scoring_weights.yaml`, `config/salary_bands.yaml`, `config/role_mappings.yaml`, `.env`
**How:** `pydantic-settings` loads env vars with type validation at startup. YAML configs loaded with `pyyaml`. Invalid config (e.g., weights not summing to 100) causes startup failure with clear error message.
**Gaps:** No hot-reload of config; restart required for config changes.

---

## 13. System Invariants & Enforcement

### Invariant 1: File paths are always local filesystem paths

**Rule:** `temp_file_path` in `AnalysisRequest` and `file_path` in pipeline context store ONLY absolute local filesystem paths. Never a URL, S3 key, or relative path.
**Canonical path:** Set once in the API route handler after `aiofiles.open()` write; never reassigned.
**Bypass audit:**
- API route handler: sets `temp_file_path` correctly — COMPLIANT
- `ingest_cv` task: reads `file_path` for extraction — COMPLIANT (reads only)
- `assemble_output` task: deletes `temp_file_path` — COMPLIANT
- No other code path reads or writes this field
**Enforcement:** Pydantic validator on `AnalysisRequest.temp_file_path` asserts `path.startswith('/')` and `path.exists()` at assignment time.

### Invariant 2: Salary fields min_czk and max_czk store only integer CZK values

**Rule:** `SalaryEstimate.min_czk` stores the minimum salary in CZK as an integer. `SalaryEstimate.max_czk` stores the maximum salary in CZK as an integer. Neither field stores currency symbols, formatted strings, or non-CZK values.
**Canonical path:** `SalaryEstimatorAgent` populates these fields from MCP response or fallback bands.
**Enforcement:** Pydantic `int` type annotation + `@validator` asserting `min_czk > 0` and `max_czk > min_czk`.

### Invariant 3: Score sub-scores sum to total within rounding tolerance

**Rule:** `score_breakdown.experience + score_breakdown.skills + score_breakdown.education + score_breakdown.role_seniority == score_breakdown.total` (within ±1 for rounding).
**Canonical path:** `ScoringAgent.compute_score` tool.
**Bypass audit:** `OutputAssemblerAgent` validates this invariant before final assembly. If violated, pipeline status → FAILED.
**Enforcement:** Pydantic `@model_validator` on `ScoreBreakdown`.

### Invariant 4: PII-stripped text is the only text sent to LLM

**Rule:** LLM prompts in CVExtractorAgent and ExplanationAgent always use the PII-stripped version of raw_text, never the original file bytes or the pre-strip text.
**Canonical path:** `strip_pii_from_text` runs in IngestionAgent before any LLM call. Result stored in `parsed_cv.raw_text`.
**Bypass audit:**
- CVExtractorAgent: uses `state["parsed_cv"].raw_text` — COMPLIANT (PII already stripped)
- ExplanationAgent: uses `parsed_cv.sections` (derived from stripped text) — COMPLIANT
- No agent accesses `file_path` for LLM prompt content
**Enforcement:** Code review rule: no LLM `messages` construction may reference `file_path` or `state["file_path"]`.

---

## 14. Failure Mode Analysis

### 14.1 Race Conditions

**Concurrent submissions (same user, rapid double-submit):**
- Risk: Two jobs created for same CV file with same temp filename.
- Guard: Job IDs are UUIDs; temp filenames use `{job_id}.{ext}` pattern. Each submission gets a unique job ID and unique file path. No conflict possible.
- Frontend guard: "Analyze" button is disabled after first submit and re-enabled only after COMPLETED/PARTIAL/FAILED.

**Concurrent pipeline execution:**
- FastAPI `BackgroundTasks` runs pipelines concurrently. Each pipeline operates on its own `PipelineState` (a separate Python dict). No shared mutable state between pipeline runs.
- Job store is an in-memory dict; writes are keyed by `job_id`. Python GIL prevents true concurrent dict corruption for simple key assignments.
- Risk at scale: dict is not thread-safe for complex updates. Mitigation: use `asyncio.Lock` per job_id for status updates, or upgrade to Redis for multi-user.

**MCP server concurrency:**
- The Platy MCP server runs as a subprocess. If multiple pipeline runs call `lookup_salary_mcp` concurrently, stdio transport serializes calls. No corruption risk; slight latency.

### 14.2 Partial Failures (Step-by-step)

**Pipeline steps:** (1) Ingest → (2) Extract → (3) Score → (4) Salary → (5) Explain → (6) Assemble

| If step N fails | After steps | Result |
|-----------------|------------|--------|
| Step 1 (Ingest) fails | Nothing committed | → FAILED immediately; temp file deleted if it was written; user sees file error |
| Step 2 (Extract) fails | File written to disk | → FAILED; temp file deleted in `finally` block of pipeline runner |
| Step 3 (Score) fails | ParsedCV in memory | → FAILED; temp file deleted; no disk state persists |
| Step 4 (Salary) fails (MCP down) | Score available | → try fallback bands; if fallback also fails → FAILED |
| Step 5 (Explain) fails/timeout | Score + salary available | → PARTIAL; explanation = None; user sees warning; temp file deleted |
| Step 6 (Assemble) fails | All data in memory | → FAILED; this should not happen in practice (all validation is pydantic-level) |

**Cleanup guarantee:** The pipeline runner wraps the entire execution in a `try/finally` block. `finally` always deletes `temp_file_path`. This ensures no orphaned files even on unexpected exceptions.

### 14.3 Offline & Degraded Operation

| Feature | Offline Behavior | UI Signal |
|---------|-----------------|-----------|
| CV text extraction (PDF/DOCX) | Fully offline — pure Python libs | None |
| CV structuring (LLM) | Unavailable | Analysis fails at step 2; error displayed |
| Scoring | Fully offline — pure algorithm | None |
| Salary lookup (MCP) | MCP is local subprocess — fully offline | None (fallback bands used if data files present) |
| Explanation (LLM) | Unavailable | PARTIAL result; banner: "Explanation unavailable — network required" |

**Online → offline transition mid-request:** If network drops after LLM extraction completes but before explanation LLM call, system returns PARTIAL result with score and salary. User sees: "Explanation unavailable. Score and salary estimate are complete."

**Note:** The Platy MCP server is a local process reading local data files. It is "offline-capable" in the sense that it does not require internet access. The `salary_data.json` must be pre-populated.

### 14.4 Retry & Recovery

| Operation | Retries | Backoff | Idempotency | Terminal Failure |
|-----------|---------|---------|-------------|-----------------|
| LLM extraction (`extract_cv_structure` task) | 1 retry | Immediate | Safe (same input, same prompt) | FAILED status; user sees extraction error |
| LLM explanation (`generate_explanation` task) | 1 retry on bad structure | Immediate | Safe | PARTIAL status; warning displayed |
| LLM rate limit (429 from OpenRouter) | 1 retry | 5s fixed | Safe | PARTIAL or FAILED depending on which step |
| MCP salary lookup | 1 retry | 1s fixed | Safe | Fallback to hardcoded bands |
| File write to `/tmp/uploads/` | 0 retries (fail fast) | N/A | N/A | FAILED; "Unable to process upload" |

### 14.5 Error-to-UI Mapping

Every error in the system maps to exactly one user-facing outcome:

| Error Scenario | Status | User-Facing Message |
|---------------|--------|---------------------|
| File type not PDF/DOCX | 400 response | "Unsupported file format. Please upload a PDF or DOCX file." |
| File > 10 MB | 400 response | "File exceeds the 10 MB size limit." |
| PDF is password-protected | FAILED | "The PDF is password-protected. Please remove the password and try again." |
| PDF is image-only (no text layer) | FAILED | "No text found in the PDF. Please provide a text-based (not scanned) PDF." |
| CV text < 50 words | PARTIAL/warning | "Limited content detected. Results may be unreliable." (low confidence) |
| LLM extraction fails (both attempts) | FAILED | "Unable to parse CV content. The document format may be unusual. Try a cleaner PDF or DOCX." |
| LLM explanation timeout (30s) | PARTIAL | "Explanation generation timed out. Seniority score and salary estimate are complete." |
| LLM explanation bad structure (both attempts) | PARTIAL | "Explanation could not be generated in the required format. Seniority score and salary estimate are complete." |
| LLM API key invalid | PARTIAL/FAILED | "Explanation unavailable due to a service configuration error." (logged: invalid API key) |
| LLM rate limit exhausted | PARTIAL | "Explanation service is busy. Seniority score and salary estimate are complete." |
| MCP server crashes (not just call failure) | Graceful degradation | No user message; fallback bands used silently; logged as `mcp_server_unavailable` |
| MCP + fallback both fail | FAILED | "Unable to estimate salary. Please try again later." |
| Disk full on upload | 500 response | "Unable to process the upload. Please try again." |
| Job ID not found | 404 response | "Job not found. The link may have expired." |
| Unknown internal error | 500 response | "An unexpected error occurred. Please try again." (full exception logged, never exposed) |

**Logging-only errors (not shown to user, logged at ERROR level):**
- MCP server connection failure (handled by fallback; user sees normal salary result)
- LLM response validation failure on first attempt (retry is transparent to user)

---

## 15. Technology Stack

### Backend

| Technology | Version | Purpose | Rationale |
|-----------|---------|---------|-----------|
| Python | 3.12 | Runtime | As per project constraints |
| FastAPI | 0.111+ | API framework | Async-native, Pydantic integration, auto-docs |
| Celery | 5.4+ | Task queue / pipeline orchestration | Battle-tested async pipeline with per-task retry, timeout, monitoring |
| Redis | 7.x | Message broker + result backend | Celery broker, job state store, result cache |
| Pydantic | 2.x | Data validation | FastAPI default; strict type enforcement |
| pdfplumber | 0.10+ | PDF text extraction | Better than PyPDF2 for complex layouts |
| python-docx | 1.1+ | DOCX text extraction | Standard library for DOCX |
| python-magic | 0.4+ | MIME type validation | File type validation independent of extension |
| structlog | 24+ | Structured logging | JSON logs with context binding |
| pydantic-settings | 2.x | Config/env management | Type-safe env var loading |
| pyyaml | 6.x | YAML config parsing | Scoring weights and salary bands |
| python-dotenv | 1.x | .env file loading | Development environment secrets |
| httpx | 0.27+ | Async HTTP client | OpenRouter API calls |
| mcp | 1.x | MCP client/server SDK | Platy MCP server implementation |
| aiofiles | 23+ | Async file I/O | Non-blocking file write for uploads |
| uvicorn | 0.29+ | ASGI server | FastAPI runtime |
| flower | 2.x | Celery monitoring (optional) | Task inspection and debugging |

### Frontend

| Technology | Version | Purpose |
|-----------|---------|---------|
| React | 18 | UI framework |
| TypeScript | 5.x | Type safety |
| Vite | 5.x | Build tool / dev server |
| Tailwind CSS | 3.x | Utility CSS |
| @tanstack/react-query | 5.x | API state, polling |
| react-dropzone | 14.x | File upload UX |
| recharts | 2.x | Score gauge visualization |

### MCP Server (Platy)

| Technology | Purpose |
|-----------|---------|
| Python 3.12 | Runtime |
| mcp[server] | MCP server SDK |
| FastMCP | High-level MCP server abstraction |

### Development

| Technology | Purpose |
|-----------|---------|
| pytest + pytest-asyncio | Backend testing |
| pytest-httpx | Mock OpenRouter calls in tests |
| Docker Compose | Run backend + frontend + MCP server together |

---

## 16. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Platy.cz changes site structure, breaking data scrape | Medium | Medium | Store salary data as static JSON; update manually. MCP server reads files, not live web. |
| OpenRouter outage or model unavailability | Low | High | Retry with 5s backoff; return PARTIAL result if explanation fails. Score and salary are always available offline. |
| LLM extraction produces inconsistent JSON despite temperature=0 | Low | Medium | Pydantic validation + 1 retry with stricter prompt. On failure, pipeline halts at EXTRACTING with clear error. |
| CV files with unusual encoding (e.g., DOCX with embedded images as text) | Medium | Low | pdfplumber handles most cases; image-only detection catches fully unreadable files. |
| In-memory job store lost on server restart | High (expected) | Low | Acceptable for portfolio demo. Job IDs become invalid after restart; user retries. Document this limitation clearly in README. |
| LLM explanation leaks PII despite stripping | Low | Medium | Regex PII stripping before prompt. LLM is instructed not to reproduce personal contact info. |
| Scoring weights YAML misconfigured (not summing to 100) | Low | High | Startup validation fails fast with clear error message. |
| Python `magic` library not installed (libmagic missing) | Medium | Low | Fallback to extension-only validation with warning. Document libmagic installation in README. |
| MCP stdio transport blocking on long salary data file | Low | Low | Salary data file is small (< 1000 rows). File is read into memory at startup. |
| Concurrent requests contending on job store dict | Low (single user) | Low | Python GIL + simple key-value writes. For multi-user, replace with asyncio.Lock or Redis. |

---

## 17. Open Questions for Stakeholder Input

These questions require a decision before implementation can proceed on the affected components. All other aspects of the architecture can proceed without these answers.

---

**Q1: Platy.cz data acquisition strategy**

The MCP server requires a pre-populated `salary_data.json`. Platy.cz does not have a public API. What is the intended approach?

- **Option A:** Manual data entry — developer manually transcribes salary ranges from Platy.cz survey pages into `salary_data.json` before demo.
- **Option B:** One-time web scrape — write a scraper (Python + BeautifulSoup) to extract salary data from Platy.cz public pages, run it once, commit the JSON. Risk: Platy.cz ToS / rate limits.
- **Option C:** Use Platy.cz's publicly available PDF salary reports — parse the PDFs into JSON.

**Impact:** If Option A, the MCP server can be built immediately. If Option B or C, scraping/parsing work is required first and may block MCP server testing.

---

**Q2: Role category granularity**

How many distinct role categories should the Platy MCP server support?

- **Minimal (5 categories):** software-engineer, data-scientist, devops-engineer, product-manager, other-IT — simpler mapping, less data needed.
- **Expanded (15+ categories):** mobile-developer, QA-engineer, data-engineer, security-engineer, UX-designer, etc. — more precise salary estimates, more data to curate.

**Impact:** Affects `roles.json` size, mapping complexity in `classify_role_category`, and data curation effort.

---

**Q3: LLM response language**

Should the LLM-generated explanation be in English or Czech?

The requirements state CVs are English-only and the market is Czech. Should the explanation (strengths, weaknesses, recommendations) be delivered in:
- **English** (consistent with CV language)
- **Czech** (consistent with market/audience)
- **Configurable** (prompt parameter)

**Impact:** Affects the system prompt in ExplanationAgent. Czech output may reduce explanation quality slightly (GPT-4 performs better in English).

---

**Q4: LLM response cache scope**

FR-PIP-004 specifies an optional LLM response cache keyed by CV content hash. Should this cache also cover the CV Extraction LLM call (step 2), or only the Explanation call (step 5)?

- Caching extraction means identical CVs skip the structuring LLM call on re-submission.
- Risk: if the extraction prompt changes (e.g., new fields added), cached responses become stale.

**Impact:** Cache invalidation strategy differs significantly between the two choices.

---

**Q5: Result persistence**

Should analysis results survive a backend restart?

Currently: results are in-memory (lost on restart). Options:
- **MVP (no persistence):** Acceptable for demo; document limitation.
- **SQLite persistence:** Results stored to a local SQLite file. Minimal effort. Results survive restarts.
- **No persistence needed:** The demo is always run fresh; results are consumed immediately.

**Impact:** If SQLite is desired, the Job Store component needs a data access layer, and alembic/schema migrations need to be designed.

---

**Q6: Frontend deployment method**

Should the React frontend be:
- **Served by FastAPI** as static files (single port, simpler demo) — Vite builds to `frontend/dist/`, FastAPI mounts it at `/`
- **Run separately** (Vite dev server on port 5173, FastAPI on 8000) — standard dev setup, requires CORS configuration
- **Docker Compose** with separate containers for backend, frontend, and MCP server

**Impact:** Affects CORS configuration, build pipeline, and Docker Compose design.
