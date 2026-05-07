import { useState } from 'react';
import { RadialBarChart, RadialBar, PolarAngleAxis } from 'recharts';
import type { ScoreBreakdown } from '../types/api';

interface ScoreGaugeProps {
  score: number;
  breakdown: ScoreBreakdown;
}

type ScoreColor = 'red' | 'amber' | 'green';

function getScoreColor(score: number): ScoreColor {
  if (score <= 33) return 'red';
  if (score <= 66) return 'amber';
  return 'green';
}

function getScoreColorValues(color: ScoreColor): { fill: string; text: string; bg: string; label: string } {
  switch (color) {
    case 'red':
      return { fill: '#ef4444', text: 'text-red-600', bg: 'bg-red-50', label: 'Low' };
    case 'amber':
      return { fill: '#f59e0b', text: 'text-amber-600', bg: 'bg-amber-50', label: 'Medium' };
    case 'green':
      return { fill: '#22c55e', text: 'text-green-600', bg: 'bg-green-50', label: 'High' };
  }
}

function getSeniorityLabel(score: number): string {
  if (score <= 34) return 'Junior';
  if (score <= 59) return 'Mid-level';
  if (score <= 79) return 'Senior';
  return 'Lead / Principal';
}

type BreakdownRow = {
  key: 'experience' | 'skills' | 'education' | 'role_seniority' | 'soft_skills';
  label: string;
  max: number;
};

const BREAKDOWN_ROWS: BreakdownRow[] = [
  { key: 'experience', label: 'Experience', max: 25 },
  { key: 'skills', label: 'Skills', max: 25 },
  { key: 'soft_skills', label: 'Soft Skills & Personality', max: 20 },
  { key: 'education', label: 'Education', max: 15 },
  { key: 'role_seniority', label: 'Role Seniority', max: 15 },
];

export function ScoreGauge({ score, breakdown }: ScoreGaugeProps) {
  const color = getScoreColor(score);
  const colorValues = getScoreColorValues(color);
  const seniorityLabel = getSeniorityLabel(score);

  const chartData = [{ value: score, fill: colorValues.fill }];

  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const toggleRow = (key: string) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-4">
      <div className="flex items-start justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">Seniority Score</h2>
        {breakdown.job_fit_adjusted && (
          <span className="inline-flex items-center gap-1 text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 px-2.5 py-1 rounded-full">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            Job-fit adjusted
          </span>
        )}
      </div>

      {/* Score gauge + number */}
      <div className="flex flex-col items-center mb-6">
        <div className="relative" style={{ width: 180, height: 120 }}>
          <RadialBarChart
            width={180}
            height={120}
            cx={90}
            cy={110}
            innerRadius={70}
            outerRadius={100}
            startAngle={180}
            endAngle={0}
            data={chartData}
            barSize={16}
          >
            <PolarAngleAxis
              type="number"
              domain={[0, 100]}
              angleAxisId={0}
              tick={false}
            />
            <RadialBar
              dataKey="value"
              cornerRadius={8}
              background={{ fill: '#f3f4f6' }}
            />
          </RadialBarChart>

          {/* Score number overlay */}
          <div className="absolute inset-0 flex flex-col items-center justify-end pb-1 pointer-events-none">
            <span className={`text-4xl font-bold ${colorValues.text}`}>{score}</span>
          </div>
        </div>

        {/* Score band label */}
        <span
          className={`inline-block mt-2 text-xs font-semibold uppercase tracking-wide px-2.5 py-1 rounded-full ${colorValues.bg} ${colorValues.text}`}
          aria-label={`Score level: ${colorValues.label}`}
        >
          {colorValues.label} ({score}/100)
        </span>

        {/* Seniority label */}
        <p className="mt-1 text-base font-medium text-gray-700">{seniorityLabel}</p>
      </div>

      {/* Sub-score breakdown table */}
      <div>
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">
          Score Breakdown
        </h3>
        <div className="divide-y divide-gray-100">
          {BREAKDOWN_ROWS.map(({ key, label, max }) => {
            const cat = breakdown.justifications[key];
            const isExpanded = expandedRows.has(key);
            return (
              <div key={key} className="py-3">
                {/* Header row: label, score, chevron toggle */}
                <button
                  onClick={() => toggleRow(key)}
                  className="w-full flex items-center justify-between group"
                  aria-expanded={isExpanded}
                  aria-controls={`breakdown-${key}`}
                >
                  <span className="text-sm font-medium text-gray-700">{label}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-gray-900 tabular-nums">
                      {breakdown[key]}{' '}
                      <span className="text-gray-400 font-normal">/ {max}</span>
                    </span>
                    {/* Chevron icon — rotates when expanded */}
                    <svg
                      className={`w-4 h-4 text-gray-400 transition-transform ${
                        isExpanded ? 'rotate-180' : ''
                      }`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                      aria-hidden="true"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </button>

                {/* Progress bar */}
                <div className="mt-1.5 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all"
                    style={{ width: `${(breakdown[key] / max) * 100}%` }}
                    aria-label={`${label}: ${breakdown[key]} of ${max}`}
                  />
                </div>

                {/* Expandable panel */}
                {isExpanded && cat && (
                  <div id={`breakdown-${key}`} className="mt-3 space-y-3 pl-1">

                    {/* Reasoning */}
                    {cat.reasoning && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-0.5">How scored</p>
                        <p className="text-xs text-gray-600 leading-snug">{cat.reasoning}</p>
                      </div>
                    )}

                    {/* Gap analysis */}
                    {cat.gap_analysis && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-0.5">Gap</p>
                        <p className="text-xs text-gray-600 leading-snug">{cat.gap_analysis}</p>
                      </div>
                    )}

                    {/* Improvements */}
                    {cat.improvements && cat.improvements.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Improvements</p>
                        <ul className="space-y-1">
                          {cat.improvements.map((item, i) => (
                            <li key={i} className="flex items-start gap-1.5">
                              <span className="mt-0.5 flex-shrink-0 w-1 h-1 rounded-full bg-blue-400" aria-hidden="true" />
                              <span className="text-xs text-gray-600 leading-snug">{item}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Short learning path */}
                    {cat.short_learning_path && cat.short_learning_path.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-amber-600 uppercase tracking-wide mb-1">Quick wins — weeks to 2 months</p>
                        <ul className="space-y-1">
                          {cat.short_learning_path.map((item, i) => (
                            <li key={i} className="flex items-start gap-1.5">
                              <span className="mt-0.5 flex-shrink-0 w-1 h-1 rounded-full bg-amber-400" aria-hidden="true" />
                              <span className="text-xs text-gray-600 leading-snug">{item}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Long learning path */}
                    {cat.long_learning_path && cat.long_learning_path.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-green-700 uppercase tracking-wide mb-1">Strategic path — 3-6 months</p>
                        <ul className="space-y-1">
                          {cat.long_learning_path.map((item, i) => (
                            <li key={i} className="flex items-start gap-1.5">
                              <span className="mt-0.5 flex-shrink-0 w-1 h-1 rounded-full bg-green-500" aria-hidden="true" />
                              <span className="text-xs text-gray-600 leading-snug">{item}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
