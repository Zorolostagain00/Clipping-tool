import React, { useState } from 'react';
import { Candidate } from '../types';
import { X, Sliders, Check } from 'lucide-react';

interface ExportModalProps {
  candidate: Candidate | null;
  onClose: () => void;
  onConfirm: (config: { aspect: string | null; crf: number; preferFast: boolean }) => void;
}

export const ExportModal: React.FC<ExportModalProps> = ({
  candidate,
  onClose,
  onConfirm,
}) => {
  const [aspect, setAspect] = useState<string | null>(null);
  const [crf, setCrf] = useState<number>(23);
  const [preferFast, setPreferFast] = useState<boolean>(true);

  if (!candidate) return null;

  return (
    <div className="fixed inset-0 z-50 bg-neutral-900/40 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-neutral-200">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <Sliders className="w-5 h-5 text-emerald-600" />
            <h3 className="font-semibold text-neutral-900">Export Clip #{candidate.rank}</h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-neutral-400 hover:text-neutral-600 hover:bg-neutral-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-4 mb-6">
          {/* Aspect Ratio */}
          <div>
            <label className="block text-xs font-medium text-neutral-700 mb-1.5">
              Aspect Ratio (Framing)
            </label>
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: 'Original', value: null },
                { label: '9:16 (Shorts/Reels)', value: '9:16' },
                { label: '1:1 (Square)', value: '1:1' },
              ].map((item) => (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => setAspect(item.value)}
                  className={`py-2 px-3 text-xs rounded-xl font-medium border text-center transition-all ${
                    aspect === item.value
                      ? 'bg-emerald-50 border-emerald-600 text-emerald-800'
                      : 'border-neutral-200 text-neutral-600 hover:bg-neutral-50'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          {/* Quality Mode */}
          <div>
            <label className="block text-xs font-medium text-neutral-700 mb-1.5">
              Rendering Mode
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setPreferFast(true)}
                disabled={aspect !== null}
                className={`p-3 rounded-xl border text-left transition-all ${
                  preferFast && aspect === null
                    ? 'bg-emerald-50 border-emerald-600 text-emerald-800'
                    : 'border-neutral-200 text-neutral-600 opacity-60'
                }`}
              >
                <div className="text-xs font-semibold">Fast (Stream Copy)</div>
                <div className="text-[11px] text-neutral-500 mt-0.5">Near-instant, no re-encode</div>
              </button>

              <button
                type="button"
                onClick={() => setPreferFast(false)}
                className={`p-3 rounded-xl border text-left transition-all ${
                  !preferFast || aspect !== null
                    ? 'bg-emerald-50 border-emerald-600 text-emerald-800'
                    : 'border-neutral-200 text-neutral-600'
                }`}
              >
                <div className="text-xs font-semibold">Precise (Re-encode)</div>
                <div className="text-[11px] text-neutral-500 mt-0.5">Applies crops and filters</div>
              </button>
            </div>
          </div>

          {/* Quality Slider (CRF) */}
          {(!preferFast || aspect !== null) && (
            <div>
              <div className="flex justify-between text-xs text-neutral-700 mb-1 font-medium">
                <span>Quality (CRF): {crf}</span>
                <span className="text-neutral-400">{crf <= 18 ? 'Visually Lossless' : crf <= 24 ? 'High Quality' : 'Standard'}</span>
              </div>
              <input
                type="range"
                min="16"
                max="32"
                value={crf}
                onChange={(e) => setCrf(Number(e.target.value))}
                className="w-full accent-emerald-600"
              />
            </div>
          )}
        </div>

        <div className="flex space-x-2">
          <button
            onClick={onClose}
            className="flex-1 py-2 rounded-xl border border-neutral-200 text-neutral-700 text-xs font-medium hover:bg-neutral-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm({ aspect, crf, preferFast: preferFast && aspect === null })}
            className="flex-1 py-2 rounded-xl bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-700 transition-colors shadow-sm flex items-center justify-center space-x-1.5"
          >
            <Check className="w-3.5 h-3.5" />
            <span>Start Render</span>
          </button>
        </div>
      </div>
    </div>
  );
};
