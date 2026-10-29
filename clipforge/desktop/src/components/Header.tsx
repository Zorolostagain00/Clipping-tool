import React from 'react';
import { Diagnostics } from '../types';
import { Film, CheckCircle2, AlertCircle, HardDrive, Cpu } from 'lucide-react';

interface HeaderProps {
  diagnostics: Diagnostics | null;
}

export const Header: React.FC<HeaderProps> = ({ diagnostics }) => {
  return (
    <header className="bg-white border-b border-neutral-200 sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center text-white shadow-sm">
            <Film className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="font-semibold text-neutral-900 tracking-tight text-lg">ClipForge Studio</h1>
              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                100% Local AI
              </span>
            </div>
            <p className="text-xs text-neutral-500">Autonomous Video Highlight Extraction</p>
          </div>
        </div>

        {diagnostics && (
          <div className="flex items-center space-x-4 text-xs">
            <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-neutral-100 border border-neutral-200">
              <Cpu className="w-3.5 h-3.5 text-neutral-500" />
              <span className="text-neutral-600 font-medium">Whisper:</span>
              {diagnostics.faster_whisper.available ? (
                <span className="text-emerald-700 font-medium flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3 text-emerald-600" /> faster-whisper
                </span>
              ) : diagnostics.openai_whisper.available ? (
                <span className="text-emerald-700 font-medium">openai-whisper</span>
              ) : (
                <span className="text-amber-600 font-medium flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" /> Missing
                </span>
              )}
            </div>

            <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-neutral-100 border border-neutral-200">
              <span className="text-neutral-600 font-medium">FFmpeg:</span>
              {diagnostics.ffmpeg.available ? (
                <span className="text-emerald-700 font-medium flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Ready
                </span>
              ) : (
                <span className="text-rose-600 font-medium">Not detected</span>
              )}
            </div>

            <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-neutral-100 border border-neutral-200">
              <HardDrive className="w-3.5 h-3.5 text-neutral-500" />
              <span className="text-neutral-600 font-medium">Free:</span>
              <span className="text-neutral-800 font-medium">{diagnostics.storage.free_gb} GB</span>
            </div>
          </div>
        )}
      </div>
    </header>
  );
};
