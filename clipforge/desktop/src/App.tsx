import React, { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { JobProgress } from './components/JobProgress';
import { CandidateCard } from './components/CandidateCard';
import { ExportModal } from './components/ExportModal';
import { Diagnostics, JobRecord, Candidate } from './types';
import { Play, Sparkles, Youtube, FileVideo, RefreshCw, FolderCheck } from 'lucide-react';

export const App: React.FC = () => {
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [activeTab, setActiveTab] = useState<'url' | 'local'>('url');
  const [urlInput, setUrlInput] = useState<string>('');
  const [localPathInput, setLocalPathInput] = useState<string>('');
  const [model, setModel] = useState<string>('base');
  const [currentJob, setCurrentJob] = useState<JobRecord | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [isExporting, setIsExporting] = useState<boolean>(false);
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [message, setMessage] = useState<string>('');

  // Fetch diagnostics
  const fetchDiagnostics = async () => {
    try {
      const res = await fetch('/api/system/diagnostics');
      if (res.ok) {
        const data = await res.json();
        setDiagnostics(data);
      }
    } catch (e) {
      console.warn('Could not reach ClipForge engine:', e);
    }
  };

  useEffect(() => {
    fetchDiagnostics();
  }, []);

  // Poll job status and listen to progress
  useEffect(() => {
    if (!currentJob || ['COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED'].includes(currentJob.state)) {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${currentJob.id}`);
        if (res.ok) {
          const data: JobRecord = await res.json();
          setCurrentJob(data);

          if (data.state === 'COMPLETED') {
            // Fetch candidates
            const cRes = await fetch(`/api/jobs/${data.id}/candidates`);
            if (cRes.ok) {
              const cData = await cRes.json();
              setCandidates(cData.candidates);
            }
          }
        }
      } catch (e) {
        console.error('Error polling job status:', e);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [currentJob]);

  // Start Job
  const handleStartJob = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage('');
    setIsStarting(true);

    try {
      const payload: Record<string, any> = {
        whisper_model: model,
        min_duration: 20,
        max_duration: 120,
        min_score: 0.0,
      };

      if (activeTab === 'url') {
        if (!urlInput.trim()) {
          setMessage('Please enter a YouTube URL.');
          setIsStarting(false);
          return;
        }
        payload.source_url = urlInput.trim();
      } else {
        if (!localPathInput.trim()) {
          setMessage('Please enter an absolute video file path.');
          setIsStarting(false);
          return;
        }
        payload.source_path = localPathInput.trim();
      }

      const res = await fetch('/api/jobs/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to create job');
      }

      const data = await res.json();
      setCurrentJob({
        id: data.job_id,
        state: 'QUEUED',
        progress: 0.0,
        stage: 'Queued',
        message: 'Initializing job...',
        source_type: activeTab === 'url' ? 'youtube' : 'local',
        config: payload,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
      setCandidates([]);
    } catch (err: any) {
      setMessage(`Error: ${err.message}`);
    } finally {
      setIsStarting(false);
    }
  };

  // Cancel Job
  const handleCancelJob = async () => {
    if (!currentJob) return;
    try {
      await fetch(`/api/jobs/${currentJob.id}/cancel`, { method: 'POST' });
    } catch (e) {
      console.error('Failed to cancel job:', e);
    }
  };

  // Export Confirmation
  const handleConfirmExport = async (config: { aspect: string | null; crf: number; preferFast: boolean }) => {
    if (!currentJob || !selectedCandidate) return;
    setIsExporting(true);
    setSelectedCandidate(null);

    try {
      const res = await fetch(`/api/jobs/${currentJob.id}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidate_ids: [selectedCandidate.id],
          prefer_fast: config.preferFast,
          target_aspect: config.aspect,
          crf: config.crf,
        }),
      });

      if (res.ok) {
        // Refresh candidates
        const cRes = await fetch(`/api/jobs/${currentJob.id}/candidates`);
        if (cRes.ok) {
          const cData = await cRes.json();
          setCandidates(cData.candidates);
        }
      }
    } catch (e) {
      console.error('Export failed:', e);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-neutral-50 text-neutral-900">
      <Header diagnostics={diagnostics} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8">
        {/* Source Ingestion Panel */}
        <div className="bg-white rounded-2xl border border-neutral-200 p-6 shadow-sm mb-8">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-semibold text-neutral-900">New Video Project</h2>
              <p className="text-xs text-neutral-500">Provide an authorized YouTube video or select a local media file</p>
            </div>

            {/* Model Selector */}
            <div className="flex items-center space-x-2">
              <label className="text-xs font-medium text-neutral-600">Model:</label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="text-xs bg-neutral-100 border border-neutral-200 rounded-lg px-2.5 py-1.5 font-medium text-neutral-800 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              >
                <option value="tiny">tiny (Ultra Fast)</option>
                <option value="base">base (Balanced - Recommended)</option>
                <option value="small">small (High Quality)</option>
                <option value="medium">medium (Professional)</option>
              </select>
            </div>
          </div>

          {/* Mode Switch Tabs */}
          <div className="flex space-x-2 mb-4 border-b border-neutral-100 pb-3">
            <button
              type="button"
              onClick={() => setActiveTab('url')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'url'
                  ? 'bg-emerald-50 text-emerald-800 border border-emerald-200 shadow-sm'
                  : 'text-neutral-500 hover:text-neutral-900 hover:bg-neutral-100'
              }`}
            >
              <Youtube className="w-4 h-4 text-emerald-600" />
              <span>YouTube URL</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('local')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeTab === 'local'
                  ? 'bg-emerald-50 text-emerald-800 border border-emerald-200 shadow-sm'
                  : 'text-neutral-500 hover:text-neutral-900 hover:bg-neutral-100'
              }`}
            >
              <FileVideo className="w-4 h-4 text-emerald-600" />
              <span>Local Video File</span>
            </button>
          </div>

          <form onSubmit={handleStartJob} className="space-y-4">
            {activeTab === 'url' ? (
              <div>
                <input
                  type="text"
                  placeholder="https://www.youtube.com/watch?v=..."
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-4 py-2.5 text-neutral-900 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all font-mono"
                />
              </div>
            ) : (
              <div>
                <input
                  type="text"
                  placeholder="C:\Videos\my_recording.mp4"
                  value={localPathInput}
                  onChange={(e) => setLocalPathInput(e.target.value)}
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-4 py-2.5 text-neutral-900 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all font-mono"
                />
              </div>
            )}

            {message && <p className="text-xs text-rose-600 font-medium">{message}</p>}

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={isStarting || (currentJob !== null && !['COMPLETED', 'FAILED', 'CANCELLED'].includes(currentJob.state))}
                className="flex items-center space-x-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-medium shadow-sm transition-all disabled:opacity-50"
              >
                <Sparkles className="w-4 h-4" />
                <span>{isStarting ? 'Starting Pipeline...' : 'Discover Viral Moments'}</span>
              </button>
            </div>
          </form>
        </div>

        {/* Live Job Progress Tracker */}
        {currentJob && <JobProgress job={currentJob} onCancel={handleCancelJob} />}

        {/* Ranked Candidate Highlights */}
        {candidates.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-semibold text-neutral-900">
                  Extracted Highlight Candidates ({candidates.length})
                </h3>
                <p className="text-xs text-neutral-500">
                  Ranked by speech engagement signals, keyword density, and structural variety
                </p>
              </div>

              <div className="flex items-center space-x-2 text-xs text-neutral-500">
                <FolderCheck className="w-4 h-4 text-emerald-600" />
                <span>Output: output/clips</span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {candidates.map((cand) => (
                <CandidateCard
                  key={cand.id}
                  candidate={cand}
                  onExport={(c) => setSelectedCandidate(c)}
                  isExporting={isExporting}
                />
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Export Options Modal */}
      <ExportModal
        candidate={selectedCandidate}
        onClose={() => setSelectedCandidate(null)}
        onConfirm={handleConfirmExport}
      />
    </div>
  );
};
