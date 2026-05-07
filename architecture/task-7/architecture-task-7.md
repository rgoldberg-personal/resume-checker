# Architecture Document: Rich Score Breakdown Schema

**Task ID:** task-7
**Date:** 2026-05-05
**Status:** Approved
**Author:** agent-architect

---

## 1. Overview

### Problem Statement

The current `ScoreBreakdown.justifications` field is typed as `dict[str, str]` — a flat map from category name to a single prose sentence. This is insufficient for the planned UI feature that needs to render per-category:

- How the score was calculated (formula transparency)
- What the candidate is missing to reach the maximum
- Concrete improvement actions
- A short learning path (quick wins, weeks to 1–2 months)
- A long learning path (strategic improvements, 3–6 months)

### Scope and Boundaries

This task is **documentation-only**. No implementation code is written or modified. The deliverables are:

1. Updated `architecture/api-interfaces.md` — new `CategoryBreakdown` sub-model, updated `ScoreBreakdown`, updated COMPLETED example
2. Updated `architecture/architecture.md` — `ScoreBreakdown` data model section and JSON example
3. This architecture document and the accompanying implementation plan

**Out of scope:** Backend implementation of `CategoryBreakdown` population, frontend UI rendering, LLM prompt updates.

### Key Stakeholders

| Stakeholder | Interest |
|-------------|----------|
| agent-backend | Implements `CategoryBreakdown` population in `compute_score.py` and LLM prompt in `generate_explanation.py` |
| agent-frontend | Renders `CategoryBreakdown` fields in the score breakdown UI component |
| agent-qa | Writes unit tests for the new schema shape |

---

## 2. Requirements Summary

### Functional Requirements

1. `ScoreBreakdown.justifications` must change type from `dict[str, str]` to `dict[str, CategoryBreakdown]`.
2. `CategoryBreakdown` must carry exactly five fields: `reasoning`, `gap_analysis`, `improvements`, `short_learning_path`, `long_learning_path`.
3. Both the Pydantic (backend) and TypeScript (frontend) contracts must reflect the new shape.
4. The COMPLETED response example in `api-interfaces.md §4` must show at least one category with all five fields populated.

### Non-Functional Requirements

- **Backward compatibility:** The four integer sub-score fields (`experience`, `skills`, `education`, `role_seniority`) and `job_fit_adjusted` are unchanged. Only `justifications` shape changes.
- **Single-purpose fields:** Every field in `CategoryBreakdown` stores exactly one type of value (see §5 Data Model).
- **Completeness:** All four categories must be present in `justifications`; no partial maps.

### Constraints and Assumptions

- **Breaking change on `justifications`:** Any client consuming the old `dict[str, str]` shape will break. This is acceptable because the frontend is built alongside the backend from the same contracts and no external consumers exist.
- **Assumption:** `short_learning_path` and `long_learning_path` are populated by the LLM `generate_explanation` task, not the rule-based `compute_score` task. The `compute_score` task populates `reasoning` and `gap_analysis` deterministically; `improvements`, `short_learning_path`, and `long_learning_path` are LLM-generated.
- **Assumption:** All five fields are required (non-optional). Empty lists are allowed for `improvements`, `short_learning_path`, and `long_learning_path` if the LLM produces nothing, but the fields must be present.

---

## 3. Architecture Decision Records (ADRs)

### ADR-007-1: Structured Sub-model vs. Flat String vs. Expanded Flat Map

**Context:**
`justifications` needs to carry structured data for each scoring category. Three shapes were considered.

**Options Considered:**

| Option | Shape | Pros | Cons |
|--------|-------|------|------|
| A — Keep flat string | `dict[str, str]` | No change | Cannot represent multiple typed fields; frontend must parse prose |
| B — Expanded flat map | `dict[str, dict[str, Any]]` | Simple serialization | No type safety; no field-level validation; opaque to mypy/Pydantic |
| C — Typed sub-model (selected) | `dict[str, CategoryBreakdown]` | Full type safety; Pydantic validation; self-documenting; TypeScript mirrors exactly | Slightly more verbose serialization |

**Decision:** Option C — `dict[str, CategoryBreakdown]`.

**Rationale:** Type safety in both Python (mypy + Pydantic v2) and TypeScript is non-negotiable for a contract that crosses the API boundary. Sub-models are the idiomatic Pydantic pattern and produce clean, validated JSON automatically.

**Consequences:** The `compute_score.py` task must construct a `CategoryBreakdown` object for each category. The LLM prompt for `generate_explanation.py` (or a new sub-task) must produce the five fields per category. The TypeScript frontend must destructure `CategoryBreakdown` objects instead of strings.

---

### ADR-007-2: Learning Path Split — Two Lists vs. One Tagged List

**Context:**
Learning path items need to signal effort horizon (short-term quick wins vs. long-term strategic). Two structural approaches exist.

**Options Considered:**

| Option | Shape | Pros | Cons |
|--------|-------|------|------|
| A — Two typed lists (selected) | `short_learning_path: list[str]` + `long_learning_path: list[str]` | Separate fields; frontend can render two distinct sections without any parsing | Two fields instead of one |
| B — Single tagged list | `list[{"horizon": "short"|"long", "item": str}]` | One field | Requires a nested object or tuple; adds indirection; frontend must filter |

**Decision:** Option A — two separate lists.

**Rationale:** Separate lists enforce the invariant that single-purpose fields store exactly one kind of value. The horizon is structural, not content. TypeScript destructuring is cleaner with two typed arrays.

**Consequences:** The LLM prompt must return two distinct JSON arrays per category. Prompt engineering must specify expected item count (1–2 items each).

---

### ADR-007-3: Responsibility Split — compute_score vs. generate_explanation

**Context:**
Five fields need to be populated. Some are deterministic (derivable from scoring logic); others require LLM judgment.

**Decision:**

| Field | Owner Task | Rationale |
|-------|-----------|-----------|
| `reasoning` | `compute_score.py` | Pure formula output; no LLM needed |
| `gap_analysis` | `compute_score.py` | Max points minus current points; deterministic |
| `improvements` | `generate_explanation.py` | Requires domain knowledge; LLM-generated |
| `short_learning_path` | `generate_explanation.py` | Requires LLM judgment on effort horizon |
| `long_learning_path` | `generate_explanation.py` | Requires LLM judgment on effort horizon |

**Consequence:** `compute_score.py` produces a partial `CategoryBreakdown` with `reasoning` and `gap_analysis` populated, and `improvements`/`short_learning_path`/`long_learning_path` as empty lists (`[]`). `generate_explanation.py` receives the partial breakdown, calls the LLM, and fills in the three list fields. The assembled result must have all five fields non-null before being stored.

> **Note for implementers:** If `generate_explanation.py` times out or fails, the PARTIAL terminal status applies. In PARTIAL mode, the list fields (`improvements`, `short_learning_path`, `long_learning_path`) should remain empty lists. The schema allows this. The frontend must handle empty lists gracefully (hide the section or show a "Not available" message).

---

## 4. System Architecture

This task does not introduce new services or components. It modifies the data contract of the existing `ScoreBreakdown` model, which flows through the pipeline as follows:

```
compute_score task
        │
        ▼
CategoryBreakdown (reasoning + gap_analysis populated; lists empty)
        │
        ▼
generate_explanation task
        │
        ▼
CategoryBreakdown (all five fields populated)
        │
        ▼
assemble_output task → AnalysisResult → Redis → JobStatusResponse API
        │
        ▼
Frontend: ScoreBreakdown.justifications[category] → CategoryBreakdown
```

**Architecture pattern applied:** Value Object (DDD) — `CategoryBreakdown` is an immutable structured value object with no identity; it is always nested inside `ScoreBreakdown.justifications`.

---

## 5. Data Model

### CategoryBreakdown

New sub-model. Each field stores **exactly one type of value**:

| Field | Type | Single-Purpose Rule | Description |
|-------|------|---------------------|-------------|
| `reasoning` | `str` | Scoring formula trace only — never improvement advice | HOW the score was calculated: formula applied + input values |
| `gap_analysis` | `str` | Gap statement only — never a recommendation | What is numerically or structurally missing to reach the maximum points |
| `improvements` | `list[str]` | Actionable items only — never learning paths | 1–3 specific actions the candidate can take (CV rewrite, project, cert) |
| `short_learning_path` | `list[str]` | Short-horizon items only (weeks to 1–2 months) — never strategic | Quick wins: 1–2 items. NOT mixed with long-horizon content |
| `long_learning_path` | `list[str]` | Long-horizon items only (3–6+ months) — never quick wins | Strategic improvements: 1–2 items. NOT mixed with short-horizon content |

**Dual-purpose field prohibition:** `short_learning_path` must NEVER contain long-horizon items and vice versa. The LLM prompt must enforce this by definition, and the QA test suite must validate it with example outputs.

### Updated ScoreBreakdown

| Field | Type | Change | Notes |
|-------|------|--------|-------|
| `experience` | `int` | Unchanged | 0–30 |
| `skills` | `int` | Unchanged | 0–30 |
| `education` | `int` | Unchanged | 0–20 |
| `role_seniority` | `int` | Unchanged | 0–20 |
| `total` | `int` | Unchanged | 0–100 |
| `justifications` | `dict[str, CategoryBreakdown]` | **Changed** (was `dict[str, str]`) | Keys: `"experience"`, `"skills"`, `"education"`, `"role_seniority"` |
| `job_fit_adjusted` | `bool` | Unchanged | |

### Data Flow

```
compute_score.py:
  for each category:
    breakdown = CategoryBreakdown(
        reasoning=<formula string>,
        gap_analysis=<gap string>,
        improvements=[],
        short_learning_path=[],
        long_learning_path=[],
    )
  score_breakdown = ScoreBreakdown(
      experience=..., skills=..., education=..., role_seniority=..., total=...,
      justifications={"experience": breakdown, ...},
      job_fit_adjusted=...,
  )

generate_explanation.py:
  for each category in score_breakdown.justifications:
    llm_result = call_llm(category, reasoning, gap_analysis, cv_text, job_description)
    breakdown.improvements = llm_result["improvements"]
    breakdown.short_learning_path = llm_result["short_learning_path"]
    breakdown.long_learning_path = llm_result["long_learning_path"]
```

---

## 6. API Contracts

### Changed Model: `CategoryBreakdown` (new)

See `api-interfaces.md §6` for the canonical Pydantic definition and `§7` for the TypeScript mirror.

### Changed Field: `ScoreBreakdown.justifications`

**Before:** `dict[str, str]`
**After:** `dict[str, CategoryBreakdown]`

This is a **breaking change** on the `justifications` field shape. All other fields of `ScoreBreakdown` are unchanged.

**Versioning impact:** No URL version bump needed. The `api-interfaces.md` versioning strategy states that URL bumps are required only for breaking changes on stable external consumers. Since this API has no external consumers (it is a local portfolio demo), the change is applied in-place without incrementing `/api/v2`.

---

## 7. Integration Points

No new integration points are introduced. The change propagates through the existing Celery task chain:

- `compute_score.py` → constructs `ScoreBreakdown` with partial `CategoryBreakdown` objects
- `generate_explanation.py` → enriches `CategoryBreakdown` list fields via LLM
- `assemble_output.py` → validates and stores the final `ScoreBreakdown` in Redis
- `GET /api/v1/jobs/{job_id}/status` → serializes `AnalysisResult` including the enriched `ScoreBreakdown`

---

## 8. Cross-Cutting Concerns

### Authentication & Authorization
**What:** No auth in MVP. **Where:** N/A. **How:** N/A. **Gaps:** Same as existing system; no new exposure introduced by this schema change.

### Data Isolation / Tenant Scoping
Not applicable — single-tenant, no user accounts.

### Logging & Observability
**What:** Each `compute_score` task should log the constructed `ScoreBreakdown` (including `CategoryBreakdown` objects) at DEBUG level using structlog, keyed by `job_id`.
**Where:** `compute_score.py`, `generate_explanation.py`
**How:** `log.debug("score_breakdown_computed", job_id=job_id, breakdown=score_breakdown.model_dump())`
**Gaps:** No change from existing logging pattern.

### Error Handling
**What:** If LLM fails to produce valid `CategoryBreakdown` list fields, the job transitions to PARTIAL status. The `improvements`, `short_learning_path`, and `long_learning_path` fields remain empty lists `[]`.
**Where:** `generate_explanation.py` exception handler
**How:** Existing PARTIAL status flow; no new error codes needed.

### Configuration Management
No new config fields. The existing `LLM_TIMEOUT_SECONDS` applies to the enrichment LLM call.

### Security
No PII risk from the new fields — they are LLM-generated text about the CV, not raw PII from the CV. The existing PII stripping before LLM calls covers this.

---

## 8.5. System Invariants & Enforcement

### Invariant: All four category keys must be present in `justifications`

**Rule:** `ScoreBreakdown.justifications` must always contain exactly the four keys: `"experience"`, `"skills"`, `"education"`, `"role_seniority"`.

**Canonical path:** Pydantic model validation in `app/schemas.py`. A `model_validator` should check that the four expected keys are present.

**Bypass audit:**
- `compute_score.py` — constructs the dict directly; must include all four keys. Implementation task required.
- `generate_explanation.py` — reads the dict and writes to it; must not remove keys. Low risk.
- `assemble_output.py` — validates the `AnalysisResult`; Pydantic `model_validate` will catch missing keys.
- Redis serialization — stored as JSON string; deserialization via `model_validate` enforces schema.
- Tests — must assert all four keys present after `compute_score` task runs.

**Enforcement mechanism:** Pydantic `model_validator(mode="after")` in `ScoreBreakdown`; unit tests in `test_scoring.py`.

---

## 9. Failure Mode Analysis

### 9.1. Race Conditions

This schema change does not introduce new mutations or async operations. The existing race-condition analysis (compute_score + generate_explanation running sequentially in a Celery chain) is unchanged.

### 9.2. Partial Failures

**generate_explanation.py fails after compute_score.py succeeds:**
- `ScoreBreakdown.justifications` will have all four keys with empty lists for `improvements`, `short_learning_path`, `long_learning_path`.
- `reasoning` and `gap_analysis` are already populated (by `compute_score.py`).
- Terminal status: `PARTIAL`.
- User sees: seniority score + salary + partial breakdown (reasoning/gap_analysis visible; improvement lists empty or hidden).
- Recovery: None (no retry for explanation in MVP). User must re-submit if they want improvements.

### 9.3. Offline & Degraded Operation

`CategoryBreakdown` is populated during the pipeline run. If the LLM is unavailable, the PARTIAL flow applies (see §9.2). No new offline behavior introduced.

### 9.4. Retry & Recovery

The `generate_explanation.py` LLM call retry policy is inherited from the existing system (3 attempts, exponential backoff with jitter, 30-second timeout per attempt). No changes required for the `CategoryBreakdown` enrichment call since it uses the same LLM client.

### 9.5. Error-to-UI Mapping

| Error Scenario | User-Facing Result |
|----------------|-------------------|
| LLM times out before enriching `CategoryBreakdown` | PARTIAL status; improvements section shows "Improvement suggestions unavailable" |
| LLM returns malformed JSON for `CategoryBreakdown` | PARTIAL status; same message as above |
| `compute_score.py` fails (cannot construct `CategoryBreakdown`) | FAILED status; existing error handling; `error_message` set |

---

## 10. Technology Stack

No new technologies introduced. All existing stack components apply:
- **Pydantic v2** — `CategoryBreakdown` and updated `ScoreBreakdown` are standard `BaseModel` subclasses
- **TypeScript** — `CategoryBreakdown` interface added to `frontend/src/types/api.ts`
- **OpenRouter / GPT-4o** — LLM that must produce the five-field structured output per category

---

## 11. Tier Impact Analysis

### Free Tier ("Remember")

| Dimension | Analysis |
|-----------|----------|
| **Impact** | All Free-tier users receive the full `CategoryBreakdown` in the response. The richer schema benefits all tiers equally. |
| **Gating** | None. `CategoryBreakdown` is part of the core scoring output — no tier gating. |
| **Data model implications** | No change in storage. Redis stores the serialized JSON; richer content means slightly larger JSON payloads (~1–3 KB per result). Acceptable for MVP. |
| **Upgrade path** | N/A — feature is available to all tiers. |
| **Edge cases** | PARTIAL results (LLM timeout): Free-tier users see `reasoning` and `gap_analysis` but empty improvement lists. This is acceptable and documented in §9.2. |

*(Only Free tier is listed in this task's `tier` field. Plus and Premium tiers are unaffected by this schema-level change.)*

---

## 12. Risks & Mitigations

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| LLM produces inconsistent field count (e.g., only 3 of 5 fields) | Medium | Medium | Pydantic validation will reject the response; fallback to empty lists; PARTIAL status |
| `short_learning_path` and `long_learning_path` contain mixed-horizon items | Low | Medium | LLM prompt must define each bucket with explicit horizon language; QA must test with golden examples |
| Frontend renders empty `improvements` list as an error state | Low | Low | Frontend spec must handle `[]` gracefully — hide the section rather than show an error |
| Redis payload growth causes performance regression | Low | Very Low | Payload increase is ~1–3 KB; Redis is not the bottleneck at MVP scale |
| Confusion between `gap_analysis` (diagnosis) and `improvements` (prescription) | Low | Medium | Field documentation and LLM prompt must clearly distinguish diagnosis from action |

### Open Questions

| Q# | Question | Owner | Resolution Target |
|----|----------|-------|------------------|
| Q1 | Should `reasoning` be shown to end users or kept as debug info only? | agent-product-owner | Before frontend implementation task |
| Q2 | What is the maximum character count for each string field? (UI truncation concern) | agent-frontend | Before frontend rendering task |
| Q3 | Should the LLM be asked to populate all five fields in a single call or two separate calls? | agent-backend | Before backend implementation task |
