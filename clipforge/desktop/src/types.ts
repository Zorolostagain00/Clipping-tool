export interface Diagnostics {
  ffmpeg: { available: boolean; path?: string };
  ffprobe: { available: boolean; path?: string };
  faster_whisper: { available: boolean };
  openai_whisper: { available: boolean };
  yt_dlp: { available: boolean; path?: string };
  storage: { output_dir: string; free_gb: number; used_gb: number };
}

export interface Candidate {
  id: string;
  job_id: string;
  start_time: number;
  end_time: number;
  duration: number;
  score: number;
  score_breakdown: Record<string, number>;
  warnings: string[];
  transcript_text: string;
  export_path?: string;
  validated?: number;
  selected?: number;
  rank: number;
}

export interface JobRecord {
  id: string;
  state: string;
  progress: number;
  stage: string;
  message: string;
  source_path?: string;
  source_url?: string;
  source_type: string;
  config: Record<string, any>;
  error?: string;
  output_dir?: string;
  created_at: string;
  updated_at: string;
}
