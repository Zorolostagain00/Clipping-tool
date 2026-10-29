import React from 'react';
import { Candidate } from '../types';
import { Sparkles, Download, Check, AlertTriangle, Clock } from 'lucide-react';

interface CandidateCardProps {
  candidate: Candidate;
  onExport: (candidate: Candidate) => void;
  isExporting: boolean;
}

export const CandidateCard: React.FC<CandidateCardProps> = ({
  candidate,
  onExport,
  isExporting,
}) => {
  const scorePercent = Math.round(candidate.score * 100);

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="bg-white rounded-2xl border border-neutral-200 overflow-hidden shadow-sm hover:border-emerald-300 transition-all flex flex-col justify-between">
      <div className="p-5">
        <div className="flex items-start justify-between gap-4 mb-3">
          <div className="flex items-center space-x-2">
            <span className="w-6 h-6 rounded-lg bg-neutral-100 text-neutral-700 font-bold text-xs flex items-center justify-center">
              #{candidate.rank}
            </span>
            <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200">
              <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
              <span className="text-xs font-semibold text-emerald-800">
                Score: {scorePercent}%
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-1 text-xs text-neutral-500 font-mono">
            <Clock className="w-3.5 h-3.5 text-neutral-400" />
            <span>
              {formatTime(candidate.start_time)} - {formatTime(candidate.end_time)} ({candidate.duration.toFixed(0)}s)
            </span>
          </div>
        </div>

        <p className="text-sm text-neutral-700 line-clamp-3 leading-relaxed mb-4">
          "{candidate.transcript_text}"
        </p>

        {/* Signals Breakdown */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          {Object.entries(candidate.score_breakdown || {}).map(([key, val]) => (
            <span
              key={key}
              className="text-[11px] px-2 py-0.5 rounded bg-neutral-100 text-neutral-600 font-medium"
            >
              {key}: {Math.round(val * 100)}%
            </span>
          ))}
        </div>

        {candidate.warnings && candidate.warnings.length > 0 && (
          <div className="flex items-center space-x-1 text-[11px] text-amber-700 bg-amber-50 px-2 py-1 rounded-md border border-amber-200 mb-2">
            <AlertTriangle className="w-3 h-3 text-amber-600 shrink-0" />
            <span className="truncate">{candidate.warnings.join(', ')}</span>
          </div>
        )}
      </div>

      <div className="px-5 py-3.5 bg-neutral-50 border-t border-neutral-100 flex items-center justify-between">
        {candidate.validated ? (
          <span className="text-xs text-emerald-700 font-medium flex items-center gap-1">
            <Check className="w-3.5 h-3.5" /> Exported
          </span>
        ) : (
          <span className="text-xs text-neutral-400">Ready to render</span>
        )}

        <button
          onClick={() => onExport(candidate)}
          disabled={isExporting}
          className="flex items-center space-x-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-medium shadow-sm transition-colors disabled:opacity-50"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Export Clip</span>
        </button>
      </div>
    </div>
  );
};
