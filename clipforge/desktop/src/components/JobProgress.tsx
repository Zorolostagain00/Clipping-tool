import React from 'react';
import { JobRecord } from '../types';
import { Loader2, AlertCircle, CheckCircle, StopCircle } from 'lucide-react';

interface JobProgressProps {
  job: JobRecord;
  onCancel: () => void;
}

export const JobProgress: React.FC<JobProgressProps> = ({ job, onCancel }) => {
  const percent = Math.round(job.progress * 100);
  const isTerminal = ['COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED'].includes(job.state);

  return (
    <div className="bg-white rounded-2xl border border-neutral-200 p-6 shadow-sm mb-8">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-3">
          {!isTerminal ? (
            <Loader2 className="w-5 h-5 text-emerald-600 animate-spin" />
          ) : job.state === 'COMPLETED' ? (
            <CheckCircle className="w-5 h-5 text-emerald-600" />
          ) : (
            <AlertCircle className="w-5 h-5 text-rose-600" />
          )}
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="font-semibold text-neutral-900 text-sm">
                Stage: {job.stage || job.state}
              </h3>
              <span className="text-xs px-2 py-0.5 rounded bg-neutral-100 text-neutral-600 font-mono">
                {percent}%
              </span>
            </div>
            <p className="text-xs text-neutral-500 mt-0.5">{job.message || 'Processing video...'}</p>
          </div>
        </div>

        {!isTerminal && (
          <button
            onClick={onCancel}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-neutral-200 text-neutral-700 hover:bg-neutral-50 text-xs font-medium transition-colors"
          >
            <StopCircle className="w-3.5 h-3.5 text-neutral-500" />
            <span>Cancel Job</span>
          </button>
        )}
      </div>

      <div className="w-full bg-neutral-100 h-2 rounded-full overflow-hidden">
        <div
          className={`h-full transition-all duration-300 rounded-full ${
            job.state === 'FAILED'
              ? 'bg-rose-500'
              : job.state === 'CANCELLED'
              ? 'bg-amber-500'
              : 'bg-emerald-600'
          }`}
          style={{ width: `${Math.max(percent, 4)}%` }}
        />
      </div>

      {job.error && (
        <div className="mt-4 p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start space-x-2">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-medium">Job Encountered an Error</p>
            <p className="text-rose-700 mt-0.5">{job.error}</p>
          </div>
        </div>
      )}
    </div>
  );
};
