import type { AnalyzeResponse, ApiErrorResponse, HealthResponse, JobStatusResponse } from '../types/api';

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
