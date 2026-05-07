// ---------------------------------------------------------------------------
// Enums / unions
// ---------------------------------------------------------------------------

export type AnalysisStatus =
  | "RECEIVED"
  | "EXTRACTING"
  | "STRUCTURING"
  | "SCORING"
  | "ATS_SCORING"
  | "ESTIMATING"
  | "EXPLAINING"
  | "ANALYZING_CONTENT"
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

export interface SalaryGrowthTarget {
  current_min: number;
  current_max: number;
  target_min: number;
  target_max: number;
  key_actions: string[];
}

export interface ScoreBreakdown {
  experience: number;       // 0–25
  skills: number;           // 0–25
  education: number;        // 0–15
  role_seniority: number;   // 0–15
  soft_skills: number;      // 0–20
  total: number;            // 0–100
  justifications: Record<"experience" | "skills" | "education" | "role_seniority" | "soft_skills", CategoryBreakdown>;
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
  salary_growth_target: SalaryGrowthTarget | null;
  raw_llm_response: string;   // for debugging, not displayed in UI
}

export type ContentIssueType =
  | "missing_info"
  | "repetition"
  | "typo"
  | "grammar"
  | "missing_section";

export interface ContentIssue {
  issue_type: ContentIssueType;
  /** Offending sentence or phrase from the CV */
  original: string;
  /** Corrected/suggested version */
  fixed: string;
}

export interface CVContentAnalysis {
  issues: ContentIssue[];
}

export type ATSKeywordImportance = "critical" | "important" | "nice_to_have";

export interface ATSKeyword {
  keyword: string;
  found_in_cv: boolean;
  importance: ATSKeywordImportance;
}

export type ATSCandidateMatch = "full" | "partial" | "none";

export interface ATSRequirementMatch {
  requirement: string;
  candidate_match: ATSCandidateMatch;
  /** Text from CV that supports this match; empty string if none */
  evidence: string;
  /** What is missing to achieve a full match; empty string if fully met */
  gap: string;
}

export interface ATSPriorityGap {
  /** 1 = critical deal-breaker, 2 = important, 3 = nice-to-have */
  priority: 1 | 2 | 3;
  description: string;
}

export interface ATSAnalysis {
  ats_score: number;                        // 0–100
  keyword_matches: ATSKeyword[];
  requirement_matches: ATSRequirementMatch[];
  priority_gaps: ATSPriorityGap[];
  tailoring_suggestions: string[];
}

export interface AnalysisResult {
  request_id: string;
  seniority_score: number;          // 0–100
  score_breakdown: ScoreBreakdown;
  salary_estimate: SalaryEstimate;
  explanation: Explanation | null;  // null on PARTIAL
  content_analysis: CVContentAnalysis | null;  // null when task failed or skipped
  ats_analysis: ATSAnalysis | null;            // null when no JD provided or task failed
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
