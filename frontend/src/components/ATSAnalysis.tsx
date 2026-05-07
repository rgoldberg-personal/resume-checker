import { RadialBarChart, RadialBar, PolarAngleAxis } from 'recharts';
import type {
  ATSAnalysis as ATSAnalysisData,
  ATSKeyword,
  ATSKeywordImportance,
  ATSCandidateMatch,
  ATSRequirementMatch,
  ATSPriorityGap,
} from '../types/api';

interface ATSAnalysisProps {
  atsAnalysis: ATSAnalysisData | null;
  jobDescriptionProvided: boolean;
}

// ---------------------------------------------------------------------------
// Color helpers
// ---------------------------------------------------------------------------

function getATSScoreColor(score: number): { fill: string; text: string } {
  if (score <= 40) return { fill: '#ef4444', text: 'text-red-600' };
  if (score <= 70) return { fill: '#f59e0b', text: 'text-amber-600' };
  return { fill: '#22c55e', text: 'text-green-600' };
}

function getATSScoreLabel(score: number): string {
  if (score <= 40) return 'Low ATS Match';
  if (score <= 70) return 'Moderate ATS Match';
  return 'Strong ATS Match';
}

// ---------------------------------------------------------------------------
// Keyword sorting
// ---------------------------------------------------------------------------

const IMPORTANCE_ORDER: Record<ATSKeywordImportance, number> = {
  critical: 0,
  important: 1,
  nice_to_have: 2,
};

function sortKeywords(keywords: ATSKeyword[]): ATSKeyword[] {
  return [...keywords].sort((a, b) => {
    // Found keywords go last
    if (a.found_in_cv !== b.found_in_cv) {
      return a.found_in_cv ? 1 : -1;
    }
    // Among not-found: sort by importance (critical first)
    if (!a.found_in_cv) {
      return IMPORTANCE_ORDER[a.importance] - IMPORTANCE_ORDER[b.importance];
    }
    return 0;
  });
}

// ---------------------------------------------------------------------------
// Badge configs
// ---------------------------------------------------------------------------

const IMPORTANCE_BADGE_CLASS: Record<ATSKeywordImportance, string> = {
  critical: 'bg-red-100 text-red-700',
  important: 'bg-amber-100 text-amber-700',
  nice_to_have: 'bg-gray-100 text-gray-600',
};

const IMPORTANCE_LABEL: Record<ATSKeywordImportance, string> = {
  critical: 'Critical',
  important: 'Important',
  nice_to_have: 'Nice to have',
};

const MATCH_BADGE_CLASS: Record<ATSCandidateMatch, string> = {
  full: 'bg-green-100 text-green-700',
  partial: 'bg-amber-100 text-amber-700',
  none: 'bg-red-100 text-red-700',
};

const MATCH_LABEL: Record<ATSCandidateMatch, string> = {
  full: 'Full',
  partial: 'Partial',
  none: 'None',
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function CheckIcon() {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-green-600 stroke-current"
      aria-hidden="true"
    >
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-red-500 stroke-current"
      aria-hidden="true"
    >
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// ATSScoreGauge (smaller variant of the main gauge)
// ---------------------------------------------------------------------------

function ATSScoreGauge({ score }: { score: number }) {
  const { fill, text } = getATSScoreColor(score);
  const label = getATSScoreLabel(score);
  const chartData = [{ value: score, fill }];

  return (
    <div className="flex flex-col items-center mb-6">
      <RadialBarChart
        width={140}
        height={90}
        cx={70}
        cy={83}
        innerRadius={55}
        outerRadius={78}
        startAngle={180}
        endAngle={0}
        data={chartData}
        barSize={13}
      >
        <PolarAngleAxis
          type="number"
          domain={[0, 100]}
          angleAxisId={0}
          tick={false}
        />
        <RadialBar
          dataKey="value"
          cornerRadius={6}
          background={{ fill: '#f3f4f6' }}
        />
      </RadialBarChart>

      <span className={`text-3xl font-bold ${text} -mt-1`} aria-label={`ATS score: ${score} out of 100`}>
        {score}
      </span>
      <span className={`mt-1 text-sm font-medium ${text}`}>{label}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// KeywordCoverageTable
// ---------------------------------------------------------------------------

function KeywordCoverageTable({ keywords }: { keywords: ATSKeyword[] }) {
  if (keywords.length === 0) return null;

  const sorted = sortKeywords(keywords);

  return (
    <section className="mb-6" aria-label="Keyword coverage">
      <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
        Keyword Coverage
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-label="Keyword matches table">
          <thead>
            <tr className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wide border-b border-gray-100">
              <th className="pb-2 pr-4 font-semibold">Keyword</th>
              <th className="pb-2 pr-4 font-semibold">Importance</th>
              <th className="pb-2 font-semibold">Found</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {sorted.map((kw, i) => (
              <tr key={i} className="align-middle">
                <td className="py-2 pr-4 text-gray-800 font-medium">{kw.keyword}</td>
                <td className="py-2 pr-4">
                  <span
                    className={`inline-block text-xs font-semibold px-2 py-0.5 rounded-full ${IMPORTANCE_BADGE_CLASS[kw.importance]}`}
                  >
                    {IMPORTANCE_LABEL[kw.importance]}
                  </span>
                </td>
                <td className="py-2">
                  <span
                    className="flex items-center"
                    aria-label={kw.found_in_cv ? 'Found in CV' : 'Not found in CV'}
                  >
                    {kw.found_in_cv ? <CheckIcon /> : <XIcon />}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// RequirementsMapping
// ---------------------------------------------------------------------------

function RequirementsMapping({ requirements }: { requirements: ATSRequirementMatch[] }) {
  if (requirements.length === 0) return null;

  return (
    <section className="mb-6" aria-label="Requirements mapping">
      <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
        Requirements Mapping
      </h3>
      <div className="divide-y divide-gray-100">
        {requirements.map((req, i) => (
          <div key={i} className="py-3 first:pt-0 last:pb-0">
            <div className="flex items-start gap-2 mb-2">
              <span
                className={`flex-shrink-0 mt-0.5 inline-block text-xs font-semibold px-2 py-0.5 rounded-full ${MATCH_BADGE_CLASS[req.candidate_match]}`}
              >
                {MATCH_LABEL[req.candidate_match]}
              </span>
              <span className="text-sm font-medium text-gray-800 leading-snug">{req.requirement}</span>
            </div>

            {req.evidence.length > 0 && (
              <div className="mb-1.5 ml-1">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Evidence</p>
                <div className="bg-green-50 rounded-md px-3 py-2 text-xs text-gray-700 leading-snug">
                  {req.evidence}
                </div>
              </div>
            )}

            {req.gap.length > 0 && (
              <div className="ml-1">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Gap</p>
                <div className="bg-red-50 rounded-md px-3 py-2 text-xs text-gray-700 leading-snug">
                  {req.gap}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// PriorityGapsList
// ---------------------------------------------------------------------------

const PRIORITY_CONFIG: Record<
  1 | 2 | 3,
  { heading: string; headingClass: string; dotClass: string }
> = {
  1: {
    heading: 'Critical — Deal-breakers',
    headingClass: 'text-red-600',
    dotClass: 'bg-red-400',
  },
  2: {
    heading: 'Important — Qualifications Missing',
    headingClass: 'text-amber-600',
    dotClass: 'bg-amber-400',
  },
  3: {
    heading: 'Nice-to-have Gaps',
    headingClass: 'text-gray-500',
    dotClass: 'bg-gray-400',
  },
};

function PriorityGapsList({ gaps }: { gaps: ATSPriorityGap[] }) {
  if (gaps.length === 0) return null;

  const byPriority: Record<1 | 2 | 3, ATSPriorityGap[]> = { 1: [], 2: [], 3: [] };
  for (const gap of gaps) {
    byPriority[gap.priority].push(gap);
  }

  const priorities: (1 | 2 | 3)[] = [1, 2, 3];

  return (
    <section className="mb-6" aria-label="Priority gaps">
      <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
        Priority Gaps
      </h3>
      <div className="space-y-4">
        {priorities.map((priority) => {
          const items = byPriority[priority];
          if (items.length === 0) return null;
          const { heading, headingClass, dotClass } = PRIORITY_CONFIG[priority];
          return (
            <div key={priority}>
              <p className={`text-xs font-semibold ${headingClass} uppercase tracking-wide mb-2`}>
                {heading}
              </p>
              <ul className="space-y-1">
                {items.map((gap, i) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <span
                      className={`mt-1.5 flex-shrink-0 w-1 h-1 rounded-full ${dotClass}`}
                      aria-hidden="true"
                    />
                    <span className="text-sm text-gray-700 leading-snug">{gap.description}</span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// TailoringSuggestions
// ---------------------------------------------------------------------------

function TailoringSuggestions({ suggestions }: { suggestions: string[] }) {
  if (suggestions.length === 0) return null;

  return (
    <section aria-label="Tailoring suggestions">
      <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
        Tailoring Suggestions
      </h3>
      <ol className="space-y-2" aria-label="Numbered list of tailoring suggestions">
        {suggestions.map((suggestion, i) => (
          <li key={i} className="flex items-start gap-2.5">
            <span className="flex-shrink-0 text-xs font-bold text-blue-600 mt-0.5 w-5 text-right">
              {i + 1}.
            </span>
            <div className="flex-1 bg-blue-50 rounded-md px-3 py-2 text-sm text-gray-700 leading-snug">
              {suggestion}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ATSAnalysis({ atsAnalysis, jobDescriptionProvided }: ATSAnalysisProps) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-4">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">ATS Match Score</h2>

      {/* Empty state — no job description provided */}
      {!jobDescriptionProvided && atsAnalysis === null && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg px-4 py-3 text-sm text-gray-500">
          Provide a job description to get ATS scoring.
        </div>
      )}

      {/* Degraded state — JD was provided but ATS task failed */}
      {jobDescriptionProvided && atsAnalysis === null && (
        <div
          className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-700"
          role="status"
        >
          ATS scoring unavailable for this result.
        </div>
      )}

      {/* Populated state */}
      {atsAnalysis !== null && (
        <>
          <ATSScoreGauge score={atsAnalysis.ats_score} />
          <KeywordCoverageTable keywords={atsAnalysis.keyword_matches} />
          <RequirementsMapping requirements={atsAnalysis.requirement_matches} />
          <PriorityGapsList gaps={atsAnalysis.priority_gaps} />
          <TailoringSuggestions suggestions={atsAnalysis.tailoring_suggestions} />
        </>
      )}
    </div>
  );
}
