import type { CVContentAnalysis, ContentIssueType } from '../types/api';

interface ContentAnalysisProps {
  contentAnalysis: CVContentAnalysis | null;
}

const ISSUE_TYPE_LABELS: Record<ContentIssueType, string> = {
  missing_info: 'Missing Info',
  missing_section: 'Missing Section',
  repetition: 'Repetition',
  typo: 'Typo',
  grammar: 'Grammar',
};

const ISSUE_TYPE_BADGE_CLASS: Record<ContentIssueType, string> = {
  missing_info: 'bg-amber-100 text-amber-700',
  missing_section: 'bg-amber-100 text-amber-700',
  repetition: 'bg-purple-100 text-purple-700',
  typo: 'bg-red-100 text-red-700',
  grammar: 'bg-red-100 text-red-700',
};

export function ContentAnalysis({ contentAnalysis }: ContentAnalysisProps) {
  if (!contentAnalysis) {
    return null;
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-4">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">CV Content Issues</h2>

      {contentAnalysis.issues.length === 0 ? (
        <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-700">
          No content issues found. Your CV looks clean.
        </div>
      ) : (
        <ul aria-label="CV content issues list" className="divide-y divide-gray-100">
          {contentAnalysis.issues.map((issue, i) => (
            <li key={i} className="py-4 first:pt-0 last:pb-0">
              {/* Badge */}
              <span
                className={`inline-block text-xs font-semibold px-2.5 py-1 rounded-full mb-3 ${ISSUE_TYPE_BADGE_CLASS[issue.issue_type]}`}
              >
                {ISSUE_TYPE_LABELS[issue.issue_type]}
              </span>

              {/* Original */}
              <div className="mb-2">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                  Original
                </p>
                <div className="bg-red-50 rounded-md px-3 py-2 text-sm text-gray-800 leading-snug">
                  {issue.original}
                </div>
              </div>

              {/* Suggested fix */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                  Suggested fix
                </p>
                <div className="bg-green-50 rounded-md px-3 py-2 text-sm text-gray-800 leading-snug">
                  {issue.fixed}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
