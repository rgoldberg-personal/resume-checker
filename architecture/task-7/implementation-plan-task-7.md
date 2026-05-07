# Implementation Plan: Rich Score Breakdown Schema

**Task ID:** task-7
**Date:** 2026-05-05
**Architecture Reference:** `./architecture/task-7/architecture-task-7.md`

---

## 1. Overview

This task is **documentation-only**. It updates the global architecture contracts to reflect the new `CategoryBreakdown` sub-model replacing the flat `dict[str, str]` justifications field in `ScoreBreakdown`. No application source code is written.

Three files are updated:
1. `architecture/api-interfaces.md` — Pydantic models (§6), TypeScript types (§7), COMPLETED endpoint example (§4)
2. `architecture/architecture.md` — `ScoreBreakdown` model definition (§5 Data Model) and JSON example

---

## 2. Prerequisites

- Read access to `architecture/api-interfaces.md` and `architecture/architecture.md`
- Understanding of Pydantic v2 `BaseModel` and TypeScript `interface` patterns
- No tooling dependencies (documentation only)

---

## 3. Implementation Phases

### Phase 1 — Update `api-interfaces.md`

**Objective:** Reflect the new `CategoryBreakdown` sub-model in all three relevant sections.

**Tasks:**

| Task ID | Description | Section | File |
|---------|-------------|---------|------|
| T7-1 | Add `CategoryBreakdown` Pydantic model; update `ScoreBreakdown.justifications` type | §6 Pydantic Models | `api-interfaces.md` |
| T7-2 | Add `CategoryBreakdown` TypeScript interface; update `ScoreBreakdown.justifications` type | §7 TypeScript Types | `api-interfaces.md` |
| T7-3 | Update COMPLETED response example to show new nested structure | §4 Endpoints | `api-interfaces.md` |
| T7-4 | Update PARTIAL response example to use new nested structure (for consistency) | §4 Endpoints | `api-interfaces.md` |

**Acceptance Criteria:**
- `CategoryBreakdown` appears as a named model before `ScoreBreakdown` in §6
- `ScoreBreakdown.justifications` type is `dict[str, CategoryBreakdown]` in §6
- `CategoryBreakdown` TypeScript interface appears before `ScoreBreakdown` in §7
- `ScoreBreakdown.justifications` TypeScript type is `Record<'experience' | 'skills' | 'education' | 'role_seniority', CategoryBreakdown>` in §7
- The COMPLETED example in §4 shows at least one category with all five fields (`reasoning`, `gap_analysis`, `improvements`, `short_learning_path`, `long_learning_path`)

---

### Phase 2 — Update `architecture.md`

**Objective:** Bring the scoring section data model definition into sync with the new contract.

**Tasks:**

| Task ID | Description | File |
|---------|-------------|------|
| T7-5 | Add `CategoryBreakdown` class before `ScoreBreakdown` in the data model section | `architecture.md` |
| T7-6 | Update `ScoreBreakdown.justifications` type annotation in `architecture.md` | `architecture.md` |
| T7-7 | Update the JSON example in `architecture.md` to use new nested structure | `architecture.md` |

**Acceptance Criteria:**
- `CategoryBreakdown` class definition appears in `architecture.md` scoring/data-model section
- `ScoreBreakdown.justifications` annotation is `dict[str, CategoryBreakdown]`
- JSON example shows new nested structure

---

## 4. Detailed Task Breakdown

### T7-1: Add `CategoryBreakdown` Pydantic model + update `ScoreBreakdown`

**File:** `architecture/api-interfaces.md`
**Section:** §6 Pydantic Models (`# app/schemas.py` code block)

**Changes:**
1. Insert the following model **immediately before** the existing `ScoreBreakdown` class:

```python
class CategoryBreakdown(BaseModel):
    reasoning:           str       = Field(..., min_length=1, description="HOW the score was calculated: formula applied + input values")
    gap_analysis:        str       = Field(..., min_length=1, description="What is numerically or structurally missing to reach maximum points")
    improvements:        list[str] = Field(default_factory=list, description="1–3 specific actionable items (CV rewrite, project, cert)")
    short_learning_path: list[str] = Field(default_factory=list, description="Quick wins achievable in weeks to 1–2 months (1–2 items)")
    long_learning_path:  list[str] = Field(default_factory=list, description="Strategic improvements requiring 3–6+ months (1–2 items)")
```

2. Replace the `justifications` field in `ScoreBreakdown`:
   - **Before:** `justifications:  dict[str, str] = Field(..., description="Per-sub-score reason strings")`
   - **After:** `justifications:  dict[str, CategoryBreakdown] = Field(..., description="Per-category structured breakdown. Keys: experience, skills, education, role_seniority")`

3. Add a `model_validator` to `ScoreBreakdown` that asserts all four expected keys are present:

```python
    @model_validator(mode="after")
    def validate_justification_keys(self) -> "ScoreBreakdown":
        expected = {"experience", "skills", "education", "role_seniority"}
        missing = expected - set(self.justifications.keys())
        if missing:
            raise ValueError(f"justifications is missing required category keys: {missing}")
        return self
```

**Definition of Done:**
- Pydantic block compiles (valid Python syntax)
- `CategoryBreakdown` appears before `ScoreBreakdown`
- All five `CategoryBreakdown` fields are documented with descriptions and constraints
- Both `model_validator` methods exist in `ScoreBreakdown` (total and keys)

---

### T7-2: Add `CategoryBreakdown` TypeScript interface + update `ScoreBreakdown`

**File:** `architecture/api-interfaces.md`
**Section:** §7 TypeScript Types (`// frontend/src/types/api.ts` code block)

**Changes:**
1. Insert the following interface **immediately before** the existing `ScoreBreakdown` interface:

```typescript
export interface CategoryBreakdown {
  /** HOW the score was calculated: formula applied + input values */
  reasoning: string;
  /** What is numerically or structurally missing to reach maximum points */
  gap_analysis: string;
  /** 1–3 specific actionable items (CV rewrite, project, cert) */
  improvements: string[];
  /** Quick wins achievable in weeks to 1–2 months (1–2 items) */
  short_learning_path: string[];
  /** Strategic improvements requiring 3–6+ months (1–2 items) */
  long_learning_path: string[];
}
```

2. Replace the `justifications` line in `ScoreBreakdown`:
   - **Before:** `justifications: Record<"experience" | "skills" | "education" | "role_seniority", string>;`
   - **After:** `justifications: Record<"experience" | "skills" | "education" | "role_seniority", CategoryBreakdown>;`

**Definition of Done:**
- TypeScript block is valid syntax
- `CategoryBreakdown` interface appears before `ScoreBreakdown`
- JSDoc comments document field semantics

---

### T7-3: Update COMPLETED response example

**File:** `architecture/api-interfaces.md`
**Section:** §4 Endpoints → `GET /api/v1/jobs/{job_id}/status` → Response Example — COMPLETED

**Changes:**
Replace the flat `justifications` object with the new nested structure. Show one full example category (`experience`) and three abbreviated categories:

```json
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
    "improvements": ["Add Terraform IaC experience; obtain HashiCorp Terraform Associate certification."],
    "short_learning_path": ["Complete Terraform Associate study path (3–4 weeks)."],
    "long_learning_path": ["Lead an infrastructure-as-code initiative at current employer over 6 months."]
  },
  "education": {
    "reasoning": "Bachelor's degree in Computer Science = 15 pts. No Master's degree detected.",
    "gap_analysis": "A Master's degree would add 5 points to reach the 20-point maximum.",
    "improvements": ["Highlight any professional certifications as partial substitutes for postgraduate education."],
    "short_learning_path": ["Obtain AWS Solutions Architect Associate certification (4–6 weeks)."],
    "long_learning_path": ["Evaluate a part-time Master's programme if strategically aligned with career goals."]
  },
  "role_seniority": {
    "reasoning": "Highest title detected: Senior Software Engineer = 10 pts. No management indicators found in role descriptions.",
    "gap_analysis": "A Staff Engineer title or evidence of team leadership would add up to 10 additional points.",
    "improvements": ["Explicitly mention team leadership scope, mentoring, or on-call rotation ownership in role descriptions."],
    "short_learning_path": ["Reframe current role description to surface technical leadership responsibilities."],
    "long_learning_path": ["Pursue a Staff Engineer role or lead a cross-team technical initiative over 12+ months."]
  }
}
```

**Definition of Done:**
- JSON is valid
- All four categories present
- `experience` shows all five fields with realistic content
- All other categories also show all five fields (abbreviated but complete)

---

### T7-4: Update PARTIAL response example

**File:** `architecture/api-interfaces.md`
**Section:** §4 Endpoints → Response Example — PARTIAL

**Changes:**
Replace the flat `justifications` in the PARTIAL example with the new nested structure. Use empty lists for `improvements`, `short_learning_path`, `long_learning_path` to accurately reflect the PARTIAL scenario where LLM enrichment failed:

```json
"justifications": {
  "experience": {
    "reasoning": "8 years of work experience across 3 roles. Score: 25/30.",
    "gap_analysis": "4 more years needed to reach 30-point maximum.",
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
    "reasoning": "Senior Software Engineer title. Score: 10/20.",
    "gap_analysis": "No management indicators detected.",
    "improvements": [],
    "short_learning_path": [],
    "long_learning_path": []
  }
}
```

**Definition of Done:**
- JSON is valid
- All four categories present with empty lists for the three LLM-populated fields
- Accurately represents the PARTIAL scenario

---

### T7-5 / T7-6 / T7-7: Update `architecture.md`

**File:** `architecture/architecture.md`

**T7-5 + T7-6 changes** (around line 339–346):
Insert `CategoryBreakdown` class before `ScoreBreakdown` and update `justifications` type:

```python
class CategoryBreakdown(BaseModel):
    reasoning:           str       # HOW the score was calculated (formula + inputs)
    gap_analysis:        str       # What is missing to reach maximum points
    improvements:        list[str] # Specific actionable items (1–3 bullets); LLM-populated
    short_learning_path: list[str] # Quick wins, weeks–2 months (1–2 items); LLM-populated
    long_learning_path:  list[str] # Strategic, 3–6+ months (1–2 items); LLM-populated

class ScoreBreakdown(BaseModel):
    experience: int                      # 0–30
    skills: int                          # 0–30
    education: int                       # 0–20
    role_seniority: int                  # 0–20
    total: int                           # 0–100; sum of sub-scores, clamped
    justifications: dict[str, CategoryBreakdown]  # keys: experience, skills, education, role_seniority
    job_fit_adjusted: bool               # true if JD was used in scoring
```

**T7-7 change** (around line 1013–1018):
Update the JSON example `justifications` block to use the new nested structure (abbreviated, one category shown in full).

**Definition of Done:**
- `architecture.md` scoring section shows `CategoryBreakdown` before `ScoreBreakdown`
- `justifications` type is `dict[str, CategoryBreakdown]`
- JSON example uses new nested shape

---

## 5. Testing Strategy

This task produces documentation, not code. The testing strategy applies to the **downstream implementation tasks** that will consume this schema:

| Test Type | Scope | Responsibility |
|-----------|-------|---------------|
| Unit — schema validation | `CategoryBreakdown` model validates correctly; missing required fields raise `ValidationError` | agent-backend (future task) |
| Unit — key invariant | `ScoreBreakdown.justifications` with missing category key raises `ValidationError` | agent-backend (future task) |
| Unit — empty list PARTIAL | PARTIAL result has empty `improvements`/path lists but valid `reasoning` and `gap_analysis` | agent-backend (future task) |
| Contract test — TypeScript | `CategoryBreakdown` interface matches response JSON shape in E2E test | agent-frontend (future task) |
| LLM output validation | Golden-file test: LLM response for a known CV produces non-empty `improvements` with 1–3 items | agent-qa (future task) |

---

## 6. Migration Strategy

### Backward Compatibility

The `justifications` field shape change is a **breaking change** on that specific field. Since this API has no versioned external consumers, no migration is required. The backend and frontend are updated together.

### Rollback

If the new schema is rejected:
- Revert `api-interfaces.md` and `architecture.md` to the previous `dict[str, str]` shape.
- No database or Redis migration is needed — Redis is ephemeral in MVP.

---

## 7. Deployment Considerations

Documentation-only task — no deployment required. The downstream backend and frontend implementation tasks will include deployment notes.

---

## 8. Monitoring & Validation

### Acceptance Criteria Checklist

- [ ] `architecture/api-interfaces.md §6`: `CategoryBreakdown` Pydantic model present with all 5 fields
- [ ] `architecture/api-interfaces.md §6`: `ScoreBreakdown.justifications` type is `dict[str, CategoryBreakdown]`
- [ ] `architecture/api-interfaces.md §6`: `ScoreBreakdown` has `model_validator` for required keys
- [ ] `architecture/api-interfaces.md §7`: `CategoryBreakdown` TypeScript interface present with all 5 fields
- [ ] `architecture/api-interfaces.md §7`: `ScoreBreakdown.justifications` TypeScript type uses `CategoryBreakdown`
- [ ] `architecture/api-interfaces.md §4`: COMPLETED example shows new nested `justifications` structure (all 4 categories, all 5 fields)
- [ ] `architecture/api-interfaces.md §4`: PARTIAL example shows new nested `justifications` with empty lists
- [ ] `architecture/architecture.md`: `CategoryBreakdown` class present in scoring data model section
- [ ] `architecture/architecture.md`: `ScoreBreakdown.justifications` updated to `dict[str, CategoryBreakdown]`
- [ ] `architecture/architecture.md`: JSON example updated to new nested shape
- [ ] Task JSON status set to `completed`
