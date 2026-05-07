import type { AnalysisStatus } from '../types/api';

interface ProgressTrackerProps {
  status: AnalysisStatus;
  progressStep: string;
  errorMessage: string | null;
  warnings: string[];
}

type PipelineStep = {
  status: AnalysisStatus;
  label: string;
};

const PIPELINE_STEPS: PipelineStep[] = [
  { status: 'RECEIVED', label: 'Received' },
  { status: 'EXTRACTING', label: 'Extracting text' },
  { status: 'STRUCTURING', label: 'Parsing CV' },
  { status: 'SCORING', label: 'Computing score' },
  { status: 'ATS_SCORING', label: 'ATS scoring' },
  { status: 'ESTIMATING', label: 'Looking up salary' },
  { status: 'EXPLAINING', label: 'Generating explanation' },
  { status: 'ANALYZING_CONTENT', label: 'Analyzing content' },
  { status: 'VALIDATING', label: 'Finalizing results' },
];

const STEP_ORDER: AnalysisStatus[] = [
  'RECEIVED',
  'EXTRACTING',
  'STRUCTURING',
  'SCORING',
  'ATS_SCORING',
  'ESTIMATING',
  'EXPLAINING',
  'ANALYZING_CONTENT',
  'VALIDATING',
  'COMPLETED',
  'PARTIAL',
  'FAILED',
];

function getStepIndex(status: AnalysisStatus): number {
  return STEP_ORDER.indexOf(status);
}

export function ProgressTracker({
  status,
  progressStep,
  errorMessage,
  warnings,
}: ProgressTrackerProps) {
  const currentIndex = getStepIndex(status);
  const isFailed = status === 'FAILED';
  const isPartial = status === 'PARTIAL';

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
      {/* Header with spinner */}
      <div className="flex items-center gap-3 mb-5">
        {!isFailed ? (
          <span
            className="inline-block w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"
            aria-hidden="true"
          />
        ) : (
          <span className="inline-block w-5 h-5 text-red-500" aria-hidden="true">
            ✕
          </span>
        )}
        <span className="text-sm font-medium text-gray-700">{progressStep}</span>
      </div>

      {/* Step list */}
      <ol className="space-y-2" aria-label="Pipeline steps">
        {PIPELINE_STEPS.map((step) => {
          const stepIdx = getStepIndex(step.status);
          const isDone = currentIndex > stepIdx;
          const isCurrent =
            step.status === status ||
            (status === 'COMPLETED' && step.status === 'VALIDATING') ||
            (status === 'PARTIAL' && step.status === 'VALIDATING') ||
            (status === 'FAILED' && step.status === status);
          const isUpcoming = currentIndex < stepIdx;

          let dotClass = 'w-3 h-3 rounded-full flex-shrink-0 mt-0.5 ';
          let textClass = 'text-sm ';

          if (isDone) {
            dotClass += 'bg-green-500';
            textClass += 'text-gray-500';
          } else if (isCurrent && isFailed) {
            dotClass += 'bg-red-500';
            textClass += 'font-semibold text-red-700';
          } else if (isCurrent) {
            dotClass += 'bg-blue-500 animate-pulse';
            textClass += 'font-semibold text-blue-700';
          } else if (isUpcoming) {
            dotClass += 'bg-gray-200';
            textClass += 'text-gray-400';
          }

          return (
            <li key={step.status} className="flex items-start gap-2.5">
              <span className={dotClass} aria-hidden="true" />
              <span className={textClass}>{step.label}</span>
            </li>
          );
        })}
      </ol>

      {/* FAILED error */}
      {isFailed && errorMessage && (
        <div
          className="mt-4 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700"
          role="alert"
          aria-live="polite"
        >
          <p className="font-medium mb-1">Analysis failed</p>
          <p>{errorMessage}</p>
        </div>
      )}

      {/* PARTIAL warning */}
      {isPartial && (
        <div
          className="mt-4 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-700"
          role="status"
          aria-live="polite"
        >
          <p className="font-medium">Partial results available</p>
          <p className="text-amber-600">Explanation is unavailable — score and salary estimate are complete.</p>
        </div>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <ul className="mt-3 space-y-1" aria-label="Warnings">
          {warnings.map((w, i) => (
            <li key={i} className="text-xs text-amber-600 bg-amber-50 rounded px-3 py-1">
              {w}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
