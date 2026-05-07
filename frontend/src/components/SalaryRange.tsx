import type { ConfidenceLevel, SalaryEstimate } from '../types/api';

interface SalaryRangeProps {
  salary: SalaryEstimate;
}

type ConfidenceMeta = {
  dot: string;
  label: string;
  textClass: string;
  bgClass: string;
  borderClass: string;
};

const CONFIDENCE_META: Record<ConfidenceLevel, ConfidenceMeta> = {
  high: {
    dot: '🟢',
    label: 'High',
    textClass: 'text-green-700',
    bgClass: 'bg-green-50',
    borderClass: 'border-green-200',
  },
  medium: {
    dot: '🟡',
    label: 'Medium',
    textClass: 'text-amber-700',
    bgClass: 'bg-amber-50',
    borderClass: 'border-amber-200',
  },
  low: {
    dot: '🔴',
    label: 'Low',
    textClass: 'text-red-700',
    bgClass: 'bg-red-50',
    borderClass: 'border-red-200',
  },
};

function formatCzk(value: number): string {
  return value.toLocaleString('en-US');
}

function formatDataSource(source: string): string {
  if (source === 'platy_mcp' || source === 'platy_cz_live') return 'Platy.cz';
  if (source === 'fallback_bands') return 'Reference data';
  return 'Reference data';
}

export function SalaryRange({ salary }: SalaryRangeProps) {
  const meta = CONFIDENCE_META[salary.confidence];

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-4">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Salary Estimate</h2>

      {/* Main range */}
      <div className="text-2xl font-bold text-gray-900 mb-1">
        CZK {formatCzk(salary.min_czk)}{' '}
        <span className="text-gray-400 font-normal">–</span>{' '}
        {formatCzk(salary.max_czk)}{' '}
        <span className="text-base font-medium text-gray-500">/ month</span>
      </div>

      {/* Confidence badge */}
      <div className="flex items-center gap-3 mt-3 flex-wrap">
        <span
          className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full border ${meta.bgClass} ${meta.textClass} ${meta.borderClass}`}
          aria-label={`Confidence: ${meta.label}`}
        >
          <span aria-hidden="true">{meta.dot}</span>
          {meta.label} confidence
        </span>

        {/* Data source */}
        <span className="text-xs text-gray-400">
          Source: {formatDataSource(salary.data_source)}
        </span>
      </div>

      {/* Low confidence warning */}
      {salary.is_low_confidence_flag && (
        <div
          className="mt-4 flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-700"
          role="alert"
        >
          <svg
            className="w-4 h-4 flex-shrink-0 mt-0.5"
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
          <span>Estimate outside typical bounds — treat with caution.</span>
        </div>
      )}
    </div>
  );
}
