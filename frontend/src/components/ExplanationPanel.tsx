import type { Explanation } from '../types/api';

interface ExplanationPanelProps {
  explanation: Explanation | null;
}

export function ExplanationPanel({ explanation }: ExplanationPanelProps) {
  if (!explanation) {
    return (
      <div
        className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-4"
        role="status"
        aria-live="polite"
      >
        <div className="flex items-start gap-3 bg-gray-50 border border-gray-200 rounded-lg px-4 py-3 text-sm text-gray-600">
          <svg
            className="w-5 h-5 flex-shrink-0 mt-0.5 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>
            Explanation unavailable. Scoring and salary estimate are shown above.
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-4">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Analysis</h2>

      {/* Summary */}
      <p className="text-gray-700 leading-relaxed mb-6">{explanation.summary}</p>

      {/* Strengths */}
      <section aria-label="Strengths" className="mb-5">
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Strengths
        </h3>
        <ul className="space-y-2.5">
          {explanation.strengths.map((item, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span
                className="mt-0.5 flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-full bg-green-100 text-green-600 text-xs font-bold"
                aria-hidden="true"
              >
                ✓
              </span>
              <span className="text-sm text-gray-700 leading-snug">{item}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* Weaknesses / Gaps */}
      <section aria-label="Gaps and weaknesses" className="mb-5">
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Gaps &amp; Weaknesses
        </h3>
        <ul className="space-y-2.5">
          {explanation.weaknesses.map((item, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span
                className="mt-0.5 flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-full bg-amber-100 text-amber-600 text-xs font-bold"
                aria-hidden="true"
              >
                !
              </span>
              <span className="text-sm text-gray-700 leading-snug">{item}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* Recommendations */}
      <section aria-label="Recommendations" className="bg-blue-50 border border-blue-100 rounded-lg p-4 mb-5">
        <h3 className="text-sm font-semibold text-blue-800 uppercase tracking-wide mb-3">
          Recommendations
        </h3>
        <ol className="space-y-3 list-none">
          {explanation.recommendations.map((item, i) => (
            <li key={i} className="flex items-start gap-3">
              <span
                className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-full bg-blue-600 text-white text-xs font-bold"
                aria-hidden="true"
              >
                {i + 1}
              </span>
              <span className="text-sm text-blue-800 leading-snug">{item}</span>
            </li>
          ))}
        </ol>
      </section>

      {/* +30% Salary Growth Target */}
      {explanation.salary_growth_target && (
        <section aria-label="Salary growth target" className="bg-green-50 border border-green-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-green-800 uppercase tracking-wide mb-3">
            +30% Salary Growth Target
          </h3>
          <div className="flex items-center gap-3 mb-3">
            <div className="text-center">
              <p className="text-xs text-gray-500 uppercase">Current</p>
              <p className="text-sm font-semibold text-gray-700">
                {explanation.salary_growth_target.current_min.toLocaleString()}&ndash;{explanation.salary_growth_target.current_max.toLocaleString()} CZK
              </p>
            </div>
            <span className="text-green-600 font-bold text-lg">&rarr;</span>
            <div className="text-center">
              <p className="text-xs text-green-600 uppercase font-semibold">Target (+30%)</p>
              <p className="text-sm font-bold text-green-700">
                {explanation.salary_growth_target.target_min.toLocaleString()}&ndash;{explanation.salary_growth_target.target_max.toLocaleString()} CZK
              </p>
            </div>
          </div>
          <p className="text-xs font-semibold text-green-700 uppercase tracking-wide mb-2">Key actions to get there</p>
          <ol className="space-y-2 list-none">
            {explanation.salary_growth_target.key_actions.map((action, i) => (
              <li key={i} className="flex items-start gap-2.5">
                <span
                  className="flex-shrink-0 w-4 h-4 flex items-center justify-center rounded-full bg-green-600 text-white text-xs font-bold mt-0.5"
                  aria-hidden="true"
                >
                  {i + 1}
                </span>
                <span className="text-sm text-green-800 leading-snug">{action}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
