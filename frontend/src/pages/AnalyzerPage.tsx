import { ApiError } from '../api/client';
import { ATSAnalysis } from '../components/ATSAnalysis';
import { ContentAnalysis } from '../components/ContentAnalysis';
import { ErrorBanner } from '../components/ErrorBanner';
import { ExplanationPanel } from '../components/ExplanationPanel';
import { ProgressTracker } from '../components/ProgressTracker';
import { SalaryRange } from '../components/SalaryRange';
import { ScoreGauge } from '../components/ScoreGauge';
import { UploadForm } from '../components/UploadForm';
import { useAnalysis } from '../hooks/useAnalysis';
import type { AnalysisStatus } from '../types/api';

const TERMINAL_STATUSES: ReadonlyArray<AnalysisStatus> = ['COMPLETED', 'PARTIAL', 'FAILED'];

type PageState = 'idle' | 'loading' | 'results' | 'failed' | 'submitError';

function derivePageState(
  isPending: boolean,
  isSubmitError: boolean,
  status: AnalysisStatus | undefined,
): PageState {
  if (isSubmitError) return 'submitError';
  if (isPending) return 'loading';
  if (!status) return 'idle';
  if (status === 'FAILED') return 'failed';
  if (status === 'COMPLETED' || status === 'PARTIAL') return 'results';
  if (!TERMINAL_STATUSES.includes(status)) return 'loading';
  return 'idle';
}

export function AnalyzerPage() {
  const { submitMutation, statusQuery, reset } = useAnalysis();

  const status = statusQuery.data?.status;
  const pageState = derivePageState(
    submitMutation.isPending,
    submitMutation.isError,
    status,
  );

  const submitError = submitMutation.isError
    ? (submitMutation.error instanceof ApiError ? submitMutation.error : null)
    : null;

  const handleStartOver = () => {
    submitMutation.reset();
    reset();
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Page header */}
      <header className="bg-white border-b border-gray-200 px-4 py-5">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">CV Analyzer</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Upload your CV to get a seniority score, salary estimate, and personalised feedback.
            </p>
          </div>
          {(pageState === 'results' || pageState === 'failed' || pageState === 'submitError') && (
            <button
              type="button"
              onClick={handleStartOver}
              className="text-sm font-medium text-blue-600 hover:text-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded px-2 py-1"
              aria-label="Start over"
            >
              ← Start over
            </button>
          )}
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8">
        {/* Submit error banner */}
        {pageState === 'submitError' && submitError && (
          <ErrorBanner message={submitError.message} onDismiss={handleStartOver} />
        )}

        {/* Upload form — shown when idle OR when there's a submit error (so user can retry) */}
        {(pageState === 'idle' || pageState === 'submitError') && (
          <UploadForm
            onSubmit={(formData) => submitMutation.mutate(formData)}
            isLoading={false}
            error={submitError}
          />
        )}

        {/* Progress tracker — shown while loading (submitting or polling non-terminal) */}
        {pageState === 'loading' && (
          <ProgressTracker
            status={status ?? 'RECEIVED'}
            progressStep={statusQuery.data?.progress_step ?? 'Uploading CV…'}
            errorMessage={null}
            warnings={statusQuery.data?.warnings ?? []}
          />
        )}

        {/* Failed state */}
        {pageState === 'failed' && statusQuery.data && (
          <>
            <ProgressTracker
              status="FAILED"
              progressStep={statusQuery.data.progress_step}
              errorMessage={statusQuery.data.error_message}
              warnings={statusQuery.data.warnings}
            />
            <div className="mt-4">
              <button
                type="button"
                onClick={handleStartOver}
                className="w-full sm:w-auto bg-blue-600 text-white font-medium px-6 py-2.5 rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
              >
                Try again
              </button>
            </div>
          </>
        )}

        {/* Results — COMPLETED or PARTIAL */}
        {pageState === 'results' && statusQuery.data?.result && (
          <div aria-live="polite">
            {/* PARTIAL warning banner */}
            {status === 'PARTIAL' && (
              <div
                className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 mb-5 text-sm text-amber-700 flex items-start gap-2"
                role="status"
              >
                <svg
                  className="w-5 h-5 flex-shrink-0 mt-0.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
                <span>
                  <strong>Partial results:</strong> Explanation generation timed out. Score and salary estimate are complete.
                </span>
              </div>
            )}

            <ScoreGauge
              score={statusQuery.data.result.seniority_score}
              breakdown={statusQuery.data.result.score_breakdown}
            />
            <SalaryRange salary={statusQuery.data.result.salary_estimate} />
            <ExplanationPanel explanation={statusQuery.data.result.explanation} />
            <ContentAnalysis contentAnalysis={statusQuery.data.result.content_analysis} />
            <ATSAnalysis
              atsAnalysis={statusQuery.data.result.ats_analysis}
              jobDescriptionProvided={statusQuery.data.result.score_breakdown.job_fit_adjusted}
            />
          </div>
        )}
      </main>
    </div>
  );
}
