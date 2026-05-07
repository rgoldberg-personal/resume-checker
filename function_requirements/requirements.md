# Functional Requirements: Job Fit & Salary Estimator

## 1. Overview

### Problem Statement

Hiring managers and candidates lack a quick, objective way to assess seniority level and expected market salary based on a CV. Candidates want actionable feedback on how to increase their earning potential. This system provides automated CV analysis with scoring, salary estimation, and LLM-powered explanations.

### Business Goals

- Demonstrate end-to-end AI/ML pipeline competency (portfolio project)
- Show ability to integrate LLM reasoning with structured data processing
- Produce a working, repeatable system that can be demoed or extended

### Scope (In)

- CV ingestion (PDF, DOCX)
- Text extraction and structuring
- Seniority scoring (0-100)
- Salary range estimation (CZK/month)
- LLM-generated explanation with strengths, weaknesses, and recommendations
- Optional: job description matching (AST scoring)
- Optional: simple UI (Streamlit)

### Scope (Out)

- Multi-language CV support beyond Czech and English
- Real-time job board integration
- User accounts / authentication
- Production deployment infrastructure
- ATS (Applicant Tracking System) integration

---

## 2. Actors & Roles

| Actor | Description | Capabilities |
|-------|-------------|--------------|
| User | Person submitting a CV for analysis | Upload CV, optionally provide job description, view results |
| System | The processing pipeline | Extract text, compute scores, call LLM, return results |
| LLM Service | External AI model (e.g., OpenAI API) | Generate explanations, assess qualitative factors |

---

## 3. User Flows

### Flow: Primary Analysis (Happy Path)

**Trigger:** User submits a CV file for analysis
**Preconditions:** System is running; LLM API key is configured
**Actor:** User

**Steps:**
1. User provides CV file (PDF or DOCX) and optionally a job description text -> System acknowledges input
2. System extracts text from the CV -> Structured text content is available
3. System parses extracted text into structured sections (experience, skills, education, etc.) -> Parsed CV data object
4. System calculates seniority score (0-100) based on parsed data -> Score with component breakdown
5. System estimates salary range based on score, role, and market data -> Salary range (min-max CZK/month)
6. System sends structured data + score + salary to LLM for explanation -> LLM returns analysis text
7. System assembles final output and presents to user -> User sees score, salary, and explanation

**Success Result:** User receives seniority score, salary range, and detailed LLM explanation including strengths, weaknesses, and +30% salary recommendations.

**Alternative Flows:**
- [1a] User provides job description alongside CV -> System includes job-fit (AST) scoring in step 4 and passes job context to LLM in step 6
- [1b] User provides only CV (no job description) -> System performs general analysis without role-specific matching

**Error Flows:**
- [E1] CV file is corrupted or unreadable -> System returns error: "Unable to extract text from the provided file. Please ensure the file is a valid PDF or DOCX."
- [E2] CV contains no extractable text (scanned image without OCR) -> System returns error: "No text content found. The file may be a scanned image. Please provide a text-based PDF or DOCX."
- [E3] LLM API call fails (timeout, rate limit, auth error) -> System returns partial result (score + salary) with message: "Explanation unavailable. Scoring completed successfully."
- [E4] Parsed CV has insufficient data (e.g., only a name, no experience) -> System returns warning: "Insufficient data for reliable analysis" and provides best-effort score with low confidence indicator.

---

### Flow: Analysis via UI (Streamlit - NICE TO HAVE)

**Trigger:** User opens web interface
**Preconditions:** Streamlit app is running
**Actor:** User

**Steps:**
1. User opens Streamlit page -> File upload widget and optional job description text area displayed
2. User uploads CV file -> File is validated (type check: .pdf or .docx)
3. User optionally pastes job description -> Text stored in session
4. User clicks "Analyze" button -> Loading spinner shown; pipeline executes
5. Pipeline completes -> Results displayed: score gauge, salary range, formatted explanation

**Error Flows:**
- [2a] User uploads unsupported file type (.txt, .jpg, etc.) -> UI shows inline error: "Please upload a PDF or DOCX file"
- [4a] Processing takes longer than 60 seconds -> UI shows timeout message with option to retry

---

### Flow: Analysis via API Endpoint (NICE TO HAVE)

**Trigger:** Client sends POST request to `/analyze` endpoint
**Preconditions:** API server is running
**Actor:** External client (e.g., Postman, curl, frontend app)

**Steps:**
1. Client sends POST with CV file (multipart/form-data) and optional `job_description` field -> Server validates request
2. Server processes through pipeline -> Returns JSON response

**Success Result:**
```json
{
  "seniority_score": 72,
  "score_breakdown": {"experience": 25, "skills": 22, "education": 15, "role_seniority": 10},
  "salary_estimate": {"min": 80000, "max": 120000, "currency": "CZK", "period": "month"},
  "explanation": { "summary": "...", "strengths": [...], "weaknesses": [...], "recommendations": [...] }
}
```

**Error Flows:**
- [1a] No file attached -> 400 Bad Request: `{"error": "No CV file provided"}`
- [1b] Invalid file type -> 400 Bad Request: `{"error": "Unsupported file format. Use PDF or DOCX"}`
- [2a] Internal processing error -> 500 Internal Server Error: `{"error": "Processing failed", "details": "..."}`

---

## 4. Functional Requirements

### 4.1 CV Ingestion

**FR-ING-001:** System (Who) shall accept CV files in PDF format (What) when user submits a file for analysis (When). System extracts text using a PDF parsing library (Result).

**FR-ING-002:** System (Who) shall accept CV files in DOCX format (What) when user submits a file for analysis (When). System extracts text using a DOCX parsing library (Result).

**FR-ING-003:** System (Who) shall reject files that are not PDF or DOCX (What) when user submits an unsupported format (When). System returns a clear error message specifying accepted formats (Result).

**FR-ING-004:** System (Who) shall enforce a maximum file size of 10 MB (What) when user submits a file (When). Files exceeding the limit are rejected with an appropriate error message (Result).

**FR-ING-005:** System (Who) shall detect and report empty or unreadable files (What) when text extraction yields zero content (When). Error message distinguishes between corrupted file and image-only PDF (Result).

### 4.2 Text Extraction & Structuring

**FR-EXT-001:** System (Who) shall extract raw text from the uploaded CV (What) immediately after ingestion validation passes (When). Extracted text preserves section ordering from the original document (Result).

**FR-EXT-002:** System (Who) shall parse extracted text into structured sections (What) after raw text extraction completes (When). Sections include: personal info, work experience, skills, education, certifications, languages (Result). If a section cannot be identified, it is marked as missing/empty.

**FR-EXT-003:** System (Who) shall extract years of experience from work history entries (What) during structuring (When). Total years calculated as sum of individual role durations; overlapping periods counted once (Result).

**FR-EXT-004:** System (Who) shall identify and list technical skills, soft skills, and tools/technologies (What) during structuring (When). Skills are normalized to lowercase and deduplicated (Result).

### 4.3 Seniority Scoring

**FR-SCO-001:** System (Who) shall calculate a seniority score between 0 and 100 (What) after CV structuring is complete (When). Score is composed of weighted sub-scores (Result):
- Experience (0-30 points): based on total years and role progression
- Skills (0-30 points): based on breadth, depth, and relevance of technical skills
- Education (0-20 points): based on degree level and field relevance
- Role Seniority (0-20 points): based on highest role title and management indicators

**FR-SCO-002:** System (Who) shall return a breakdown of sub-scores alongside the total score (What) for every analysis (When). Each sub-score includes a brief justification string (Result).

**FR-SCO-003:** System (Who) shall apply job-description matching to adjust skill relevance scoring (What) when user provides a job description (When). Skills matching the JD receive higher weight; score breakdown indicates "job-fit adjusted" (Condition).

**FR-SCO-004:** System (Who) shall clamp final score to 0-100 range (What) regardless of sub-score calculation results (When). If any sub-score exceeds its maximum, it is capped at maximum (Result).

### 4.4 Salary Estimation

**FR-SAL-001:** System (Who) shall estimate a salary range in CZK per month (What) after seniority score is calculated (When). Range is expressed as min-max (e.g., 80,000 - 120,000 CZK/month) (Result).

**FR-SAL-002:** System (Who) shall base salary estimation on seniority score, identified role category, and market reference data (What) for every analysis (When). If no role category can be determined, system uses a general "IT professional" baseline (Condition).

**FR-SAL-003:** System (Who) shall use one of the following salary data sources (What) during estimation (When):
- Option A: Hardcoded salary bands per seniority tier and role (simplest)
- Option B: Reference data from public salary surveys (e.g., Czechitas, Hays, Grafton reports)
- Option C: Synthetic dataset derived from scraped job postings

The chosen approach must be documented in system configuration (Condition).

**FR-SAL-004:** System (Who) shall perform a sanity check on the estimated salary (What) before returning results (When). If salary falls outside plausible bounds (below 25,000 or above 500,000 CZK/month for Czech market), system flags the estimate as low-confidence (Result).

### 4.5 LLM Explanation

**FR-LLM-001:** System (Who) shall generate a natural-language explanation of the scoring and salary estimate (What) after both are computed (When). Explanation is generated by an LLM (e.g., GPT-4, Claude) using a structured prompt (Result).

**FR-LLM-002:** System (Who) shall include the following sections in the LLM explanation (What) for every successful analysis (When):
1. Summary: why this score and salary were assigned
2. Strengths: 3-5 specific strengths identified from the CV
3. Weaknesses/Gaps: 2-4 areas where the candidate is lacking
4. Recommendations: specific, actionable steps to increase salary by ~30%

**FR-LLM-003:** System (Who) shall pass structured CV data, score breakdown, salary estimate, and optional job description to the LLM prompt (What) when generating the explanation (When). Raw CV text is included for context but structured data is primary (Condition).

**FR-LLM-004:** System (Who) shall validate LLM response structure (What) after receiving LLM output (When). If the response does not contain all required sections, system retries once with a more explicit prompt. If retry fails, system returns partial explanation with a note (Result).

**FR-LLM-005:** System (Who) shall enforce a maximum response time of 30 seconds for LLM calls (What) per call (When). On timeout, system returns score and salary without explanation and logs the timeout event (Result).

### 4.6 Pipeline Orchestration

**FR-PIP-001:** System (Who) shall execute analysis as a sequential pipeline with distinct steps (What) for every analysis request (When). Steps: Ingest -> Extract -> Structure -> Score -> Estimate Salary -> Generate Explanation -> Assemble Output (Result).

**FR-PIP-002:** System (Who) shall allow the pipeline to return partial results if a non-critical step fails (What) when errors occur in explanation generation (When). Score and salary are critical (pipeline halts on failure); explanation is non-critical (Result).

**FR-PIP-003:** System (Who) shall log execution time for each pipeline step (What) on every run (When). Logs include step name, duration, success/failure status (Result). [NICE TO HAVE]

**FR-PIP-004:** System (Who) shall cache LLM responses keyed by a hash of the input data (What) when the same CV is analyzed multiple times (When). Cache TTL is configurable; default 24 hours (Result). [NICE TO HAVE]

### 4.7 Output Validation

**FR-VAL-001:** System (Who) shall validate the final output before returning to user (What) after pipeline completion (When). Validation checks:
- Seniority score is integer 0-100
- Salary min < salary max
- Salary min > 0
- Explanation is non-empty string (if generated)
- All required fields are present

**FR-VAL-002:** System (Who) shall return a confidence indicator (low/medium/high) (What) alongside results (When). Confidence is reduced when: CV data is sparse, parsing quality is low, salary falls near bounds (Conditions).

---

## 5. State Diagram

### Analysis Request Lifecycle

| State | Description |
|-------|-------------|
| RECEIVED | File uploaded, awaiting processing |
| EXTRACTING | Text extraction in progress |
| STRUCTURING | Parsing text into structured sections |
| SCORING | Computing seniority score |
| ESTIMATING | Calculating salary range |
| EXPLAINING | LLM generating explanation |
| VALIDATING | Output sanity checks |
| COMPLETED | All results available |
| PARTIAL | Score/salary available but explanation failed |
| FAILED | Critical step failed; no results |

### Transitions

| From | To | Trigger | Conditions |
|------|----|---------|------------|
| RECEIVED | EXTRACTING | Processing starts | File passes format/size validation |
| RECEIVED | FAILED | Validation error | Invalid file type or size |
| EXTRACTING | STRUCTURING | Text extracted | Non-empty text obtained |
| EXTRACTING | FAILED | Extraction error | No text content / corrupted file |
| STRUCTURING | SCORING | Sections parsed | At least experience OR skills section found |
| STRUCTURING | FAILED | Parse failure | No meaningful sections identified |
| SCORING | ESTIMATING | Score computed | Score in valid range |
| ESTIMATING | EXPLAINING | Salary computed | Range passes sanity check |
| EXPLAINING | VALIDATING | Explanation received | LLM responded |
| EXPLAINING | VALIDATING | Explanation timeout/error | Skip explanation, proceed with partial |
| VALIDATING | COMPLETED | All checks pass | All required fields valid |
| VALIDATING | PARTIAL | Explanation missing | Score + salary valid but no explanation |
| VALIDATING | FAILED | Critical validation fail | Score or salary invalid |

---

## 6. Edge Cases & Error Scenarios

### 6.1 Input Edge Cases

| Scenario | System Behavior | User Sees |
|----------|----------------|-----------|
| CV is a scanned image PDF (no text layer) | Extraction returns empty string; pipeline halts | Error: "No extractable text. Please provide a text-based document." |
| CV is password-protected | PDF library raises access error | Error: "File is password-protected. Please remove protection and retry." |
| CV is extremely short (< 50 words) | Structuring finds minimal data | Warning: "Limited data available. Results may be unreliable." + low confidence flag |
| CV is extremely long (> 20 pages) | System processes first 10 pages | Warning: "Only first 10 pages analyzed." |
| CV is in non-supported language | Structuring may partially fail | Best-effort analysis with reduced confidence |
| Job description is empty string | Treated as "no job description provided" | General analysis without job-fit scoring |

### 6.2 Processing Edge Cases

| Scenario | System Behavior | User Sees |
|----------|----------------|-----------|
| LLM API key is invalid or expired | LLM step fails; partial result returned | Score + salary shown; message: "Explanation unavailable due to service configuration error." |
| LLM returns malformed/off-topic response | Retry once with stricter prompt; if still bad, skip | Score + salary shown; generic note about explanation unavailability |
| Score calculation produces all-zero sub-scores | Final score is 0; salary defaults to entry-level range | Results with very low score and minimum salary band + high uncertainty note |
| Two skills are semantically identical but written differently (e.g., "JS" vs "JavaScript") | Normalization step maps common aliases | Deduplicated skill list in output |

### 6.3 System Edge Cases

| Scenario | System Behavior | User Sees |
|----------|----------------|-----------|
| Disk full during file upload (API mode) | Request rejected at ingestion | Error: "Unable to process upload. Please try again later." |
| Concurrent requests exceed capacity | Queue or reject with 429 | Error: "Service busy. Please retry in a moment." (API mode) |
| LLM rate limit hit | Exponential backoff (1 retry); if still failing, return partial | Partial result or delay |

---

## 7. Acceptance Criteria

### AC-001: Basic End-to-End

```
Given a valid PDF CV with at least 2 years of work experience listed
When the user submits it for analysis
Then the system returns a seniority score (integer 0-100), a salary range (two positive integers where min < max), and a non-empty explanation text
```

### AC-002: DOCX Support

```
Given a valid DOCX CV
When the user submits it for analysis
Then the system produces the same output structure as for a PDF input
```

### AC-003: Score Breakdown

```
Given any successful analysis
When results are returned
Then the score breakdown contains sub-scores for experience, skills, education, and role_seniority that sum to the total score (within rounding tolerance of +/-1)
```

### AC-004: Salary Sanity

```
Given a CV indicating a senior software engineer with 10+ years experience
When the system estimates salary
Then the range falls within 100,000 - 250,000 CZK/month (Czech market plausible bounds for this role)
```

### AC-005: LLM Explanation Structure

```
Given a successful LLM explanation
When the explanation is parsed
Then it contains identifiable sections for: summary, strengths (at least 2 items), weaknesses (at least 1 item), and recommendations (at least 2 items)
```

### AC-006: Error Handling - Invalid File

```
Given a file that is not PDF or DOCX (e.g., a .txt file)
When the user submits it
Then the system returns an error message within 2 seconds without crashing
```

### AC-007: Partial Result on LLM Failure

```
Given the LLM API is unreachable
When the user submits a valid CV
Then the system returns score and salary estimate with a message indicating explanation is unavailable
```

### AC-008: Job Description Matching

```
Given a CV and a job description emphasizing "Kubernetes" and "AWS"
When the candidate's CV lists these skills
Then the skills sub-score is higher than if the same CV were analyzed without the job description
```

---

## 8. Data Requirements

### Key Entities

| Entity | Attributes | Lifecycle |
|--------|-----------|-----------|
| AnalysisRequest | id, file_path, file_type, job_description (optional), created_at, status | Created on submission; terminal state: COMPLETED/PARTIAL/FAILED |
| ParsedCV | raw_text, sections (dict), skills (list), experience_years, education_level, role_titles | Created during structuring; immutable once created |
| SeniorityScore | total (int), experience (int), skills (int), education (int), role_seniority (int), justifications (dict) | Created during scoring; immutable |
| SalaryEstimate | min (int), max (int), currency (str), confidence (str), data_source (str) | Created during estimation; immutable |
| Explanation | summary (str), strengths (list), weaknesses (list), recommendations (list), raw_llm_response (str) | Created during explanation; immutable |
| AnalysisResult | request_id, score, salary, explanation, confidence, created_at | Assembled at end; returned to user |

### Salary Reference Data

- Source: hardcoded bands (MVP) or external CSV/JSON with role-salary mappings
- Structure: `{role_category, seniority_tier (junior/mid/senior/lead/principal), min_salary, max_salary, source, year}`
- Must be updatable without code changes (configuration file or data file)

### Privacy Constraints

- CV files should not be persisted beyond processing unless explicitly configured
- No personal data (names, emails, phone numbers) stored in logs
- LLM prompts should not include raw personal contact information (strip before sending)

---

## 9. Non-Functional Requirements

### Performance

- End-to-end processing time: < 45 seconds for a typical 2-page CV (LLM call is the bottleneck)
- Text extraction: < 5 seconds
- Scoring + salary estimation: < 2 seconds
- UI responsiveness: loading indicator shown within 500ms of submission

### Security

- LLM API keys stored in environment variables, never in source code
- Uploaded files validated for type and size before processing
- No arbitrary file path access (file handling sandboxed to upload directory)

### Offline Behavior

- System requires network access for LLM calls
- Text extraction and scoring can function offline if LLM step is skipped (partial mode)

### Accessibility (UI - if implemented)

- Streamlit default accessibility (semantic HTML)
- Results text is selectable and copyable
- Color is not the sole indicator of score quality (include text labels)

---

## 10. Dependencies

| Dependency | Purpose | Criticality |
|-----------|---------|-------------|
| Python 3.10+ | Runtime | Required |
| PDF parsing library (e.g., PyPDF2, pdfplumber) | Text extraction from PDF | Required |
| DOCX parsing library (e.g., python-docx) | Text extraction from DOCX | Required |
| LLM API (GPT-4 via OpenRouter) | Explanation generation + CV structuring | Required for full pipeline; partial results possible without |
| Streamlit | Web UI | Optional (NICE TO HAVE) |
| FastAPI / Flask | API endpoint | Optional (NICE TO HAVE) |
| Platy.cz MCP Server | Market salary lookup | Required — custom MCP server wrapping Platy.cz data |
| OpenRouter API | LLM gateway | Required — routes requests to GPT-4 |

---

## 11. Success Metrics

### Quantitative

- Pipeline completes successfully for 90%+ of well-formatted CVs (PDF/DOCX with text)
- Average processing time under 45 seconds
- Score variance for the same CV across multiple runs: < 5 points (determinism, assuming temperature=0 for LLM)
- Salary estimate within +/-20% of manual expert assessment for test cases

### Qualitative

- LLM explanation reads as coherent and specific (not generic boilerplate)
- Recommendations are actionable (specific skills/certifications named, not "get more experience")
- Portfolio reviewers understand the system's purpose within 30 seconds of seeing the output

---

## 12. Resolved Decisions

| # | Question | Decision |
|---|----------|----------|
| OQ-1 | Which LLM provider to use? | **GPT-4 via OpenRouter API.** Allows provider flexibility through OpenRouter's unified interface. |
| OQ-2 | What salary data source to use? | **Public data from Platy.cz via MCP server.** Build an MCP (Model Context Protocol) server that wraps Platy.cz salary data for structured lookups. |
| OQ-3 | Should the system support non-Czech markets? | **Czech only (CZK).** No multi-market support for now. Code structured so locale could be added later. |
| OQ-4 | How to handle CV languages? | **English only.** All CVs assumed to be in English. No language detection or multilingual support needed. |
| OQ-5 | Should scoring weights be configurable? | **Yes — configurable via YAML/JSON** with sensible defaults (Experience 30, Skills 30, Education 20, Role Seniority 20). |
| OQ-6 | How to validate scoring accuracy? | **Manual review** during development. No automated golden set for now. |

---

## 13. Options Analysis

### Options for Salary Estimation Approach

#### Option A: Hardcoded Salary Bands

**Description:** Define salary ranges per role category and seniority tier directly in a configuration file (JSON/YAML). Score maps to a tier, tier maps to salary band.

**Pros:**
- Simplest to implement (hours, not days)
- Fully deterministic and explainable
- No external data dependencies

**Cons:**
- Static; becomes stale without manual updates
- Coarse granularity (e.g., all "senior developers" get same range)
- Less impressive as a portfolio piece

**Complexity:** Low
**User Impact:** Adequate for demo; less precise for real use
**Risks:** Salary bands may not reflect current market
**Example:** Many HR screening tools use tiered bands internally

#### Option B: Public Salary Survey Data

**Description:** Parse data from published Czech salary surveys (Hays, Grafton, Czechitas, Platy.cz reports) into a structured dataset. Use this as lookup table with interpolation.

**Pros:**
- Based on real market data
- More granular (role + seniority + region)
- Shows data engineering capability in portfolio

**Cons:**
- Data may be behind paywalls or in PDF format (scraping effort)
- Requires periodic manual updates
- Licensing/attribution concerns

**Complexity:** Medium
**User Impact:** More accurate estimates; builds confidence in output
**Risks:** Data availability; format changes breaking parser
**Example:** Levels.fyi (US equivalent approach)

#### Option C: Synthetic Dataset + Simple Model

**Description:** Generate synthetic salary data based on known distributions and train a simple regression model (e.g., linear regression, decision tree) that predicts salary from features.

**Pros:**
- Demonstrates ML skills (portfolio value)
- Model can capture non-linear relationships
- Easily expandable with real data later

**Cons:**
- Synthetic data may not reflect reality
- Adds model training/maintenance complexity
- Harder to explain to non-technical reviewers

**Complexity:** Medium-High
**User Impact:** Potentially more nuanced estimates
**Risks:** Overfitting to synthetic patterns; "garbage in, garbage out" if synthetic data is unrealistic
**Example:** Academic projects; Kaggle notebooks

#### Recommendation

Start with **Option A** (hardcoded bands) for MVP to get the pipeline working end-to-end quickly. Structure the data file so it can be replaced with Option B data later. If time permits and portfolio impact is important, add Option C as a "v2" enhancement.

---

### Options for CV Structuring Approach

#### Option A: Rule-Based Parsing (Regex + Heuristics)

**Description:** Use regex patterns and keyword matching to identify sections (e.g., "Experience", "Education", "Skills" headings) and extract structured data.

**Pros:**
- Fast execution, no API cost
- Deterministic output
- Easy to debug

**Cons:**
- Brittle; breaks on non-standard CV formats
- Requires maintenance as new formats encountered
- Poor handling of creative/non-traditional CVs

**Complexity:** Medium (many edge cases)
**User Impact:** Works well for standard CVs; fails silently on unusual ones

#### Option B: LLM-Based Extraction

**Description:** Send raw CV text to LLM with a structured extraction prompt (e.g., "Extract the following fields as JSON: ..."). LLM handles format variability.

**Pros:**
- Handles diverse formats robustly
- Minimal maintenance
- Can extract nuanced information (implied skills, role seniority)

**Cons:**
- Adds API cost per analysis
- Slower (additional LLM call)
- Non-deterministic; may vary between runs

**Complexity:** Low (implementation is simple; just a prompt)
**User Impact:** More reliable extraction across varied CV formats

#### Option C: Hybrid (Rules + LLM Fallback)

**Description:** Attempt rule-based extraction first. If confidence is low (few sections found), fall back to LLM extraction.

**Pros:**
- Fast for standard CVs (no API call needed)
- Robust for unusual CVs (LLM fallback)
- Cost-efficient (LLM only when needed)

**Cons:**
- More complex logic
- Need to define "low confidence" threshold
- Two code paths to maintain

**Complexity:** Medium-High

#### Recommendation

For a portfolio project, **Option B** (LLM-based extraction) is recommended. It demonstrates sophisticated use of LLMs beyond simple Q&A, handles edge cases gracefully, and requires minimal code. The added cost per analysis is negligible for a demo project. If cost becomes a concern, evolve to Option C.
