"""
ClipForge Studio — Command Line Interface.
Runs clipping pipelines, checks system status, and exports clips directly from the terminal.
"""

import argparse
import json
import logging
import pathlib
import sys
import time

# Ensure clipforge/ is in sys.path
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import engine.config as _cfg
from engine.config import OUTPUT_DIR, DEFAULT_WHISPER_MODEL
from engine.job_manager import JobManager
from engine.workspace_manager import WorkspaceManager
from engine.cleanup_manager import CleanupManager
from engine.pipeline import PipelineConfig, run_pipeline
from engine.clip_exporter import ExportConfig, export_candidate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("clipforge.cli")


def cmd_diagnostics(args):
    """Run diagnostics and print system status."""
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    print("\nClipForge Studio — System Diagnostics")
    print("=" * 45)
    print(f"FFmpeg:         {'Installed (' + ffmpeg + ')' if ffmpeg else 'MISSING'}")
    print(f"FFprobe:        {'Installed (' + ffprobe + ')' if ffprobe else 'MISSING'}")

    try:
        import faster_whisper
        print("faster-whisper: Installed (Primary Transcriber)")
    except ImportError:
        print("faster-whisper: MISSING")

    try:
        import whisper
        print("openai-whisper: Installed (Fallback Transcriber)")
    except ImportError:
        print("openai-whisper: MISSING")

    try:
        import yt_dlp
        print("yt-dlp:         Installed")
    except ImportError:
        print("yt-dlp:         MISSING")

    total, used, free = shutil.disk_usage(str(OUTPUT_DIR))
    print(f"Storage:        {round(free / 1e9, 2)} GB free / {round(total / 1e9, 2)} GB total")
    print(f"Output Dir:     {OUTPUT_DIR}\n")


def cmd_process(args):
    """Process a local video or YouTube URL."""
    jm = JobManager()
    wm = WorkspaceManager()
    cm = CleanupManager()

    source = args.source.strip()
    is_url = source.startswith("http://") or source.startswith("https://") or "youtu" in source

    source_path = None if is_url else pathlib.Path(source).resolve()
    source_url = source if is_url else None

    if not is_url and (not source_path or not source_path.exists()):
        print(f"Error: Local video file not found: {source}")
        sys.exit(1)

    config = PipelineConfig(
        whisper_model=args.model,
        language=args.language,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        min_score=args.min_score,
        max_candidates=args.max_candidates,
    )

    job_id = jm.create_job(
        source_path=str(source_path) if source_path else None,
        source_url=source_url,
        source_type="youtube" if is_url else "local",
        config=config.__dict__,
    )

    print(f"\nProcessing Job Started: {job_id}")
    print(f"Source: {source} (Type: {'YouTube' if is_url else 'Local'})")
    print(f"Model: {args.model}")
    print("-" * 50)

    result = run_pipeline(
        job_id=job_id,
        source_path=source_path,
        config=config,
        job_manager=jm,
        workspace_manager=wm,
        source_url=source_url,
    )

    if not result.ok:
        print(f"\nPipeline FAILED: {result.error}")
        sys.exit(1)

    print(f"\nPipeline COMPLETE! Found {len(result.candidates)} ranked candidates:\n")
    for cand in result.candidates:
        score_val = cand.score.total
        print(f"  #{cand.rank:2d} | Score: {score_val:.2f} | Time: {cand.start:.1f}s - {cand.end:.1f}s ({cand.duration:.1f}s)")
        print(f"       Text: \"{cand.transcript_text[:90]}...\"")
        if cand.warnings:
            print(f"       Warnings: {', '.join(cand.warnings)}")
        print()

    if args.auto_export:
        print("\nAuto-exporting candidates...")
        export_config = ExportConfig(
            output_dir=OUTPUT_DIR,
            filename_prefix=args.prefix or "clip",
            target_aspect=args.aspect,
        )
        session = wm.get_session_by_job(job_id)
        renders_dir = session.renders_dir if session else OUTPUT_DIR / "renders"

        for cand in result.candidates[:args.export_count]:
            print(f"  Exporting candidate #{cand.rank} ({cand.start:.1f}s - {cand.end:.1f}s)...")
            res = export_candidate(
                source_path=pathlib.Path(jm.get_job(job_id).source_path),
                start=cand.start,
                end=cand.end,
                renders_dir=renders_dir,
                final_output_dir=OUTPUT_DIR,
                config=export_config,
                candidate_id=cand.id,
                prefer_fast=(args.aspect is None),
            )
            if res.ok:
                print(f"    Exported: {res.output_path.name} (mode={res.mode})")
            else:
                print(f"    Export FAILED: {res.error}")

    # Auto-clean if YouTube
    if is_url and result.session_id:
        sess = wm.get_session(result.session_id)
        if sess:
            print("\nCleaning up temporary download...")
            clean_res = cm.cleanup_session(sess, youtube_only=True)
            print(f"Cleaned {len(clean_res['removed'])} temp files.")

    print(f"\nFinished. Clips located in: {OUTPUT_DIR}\n")


def cmd_list_jobs(args):
    """List recent jobs."""
    jm = JobManager()
    jobs = jm.list_jobs(limit=args.limit)
    print(f"\nRecent Jobs ({len(jobs)}):")
    print("=" * 65)
    for j in jobs:
        print(f"[{j.state:11s}] {j.id[:12]} | {j.source_type:7s} | {j.created_at[:19]} | {j.message or ''}")
    print()


def main():
    parser = argparse.ArgumentParser(description="ClipForge Studio CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # diagnostics
    subparsers.add_parser("diagnostics", help="Run system diagnostics")

    # process
    proc_p = subparsers.add_parser("process", help="Process video into clips")
    proc_p.add_argument("source", help="Path to video or YouTube URL")
    proc_p.add_argument("--model", default="base", help="Whisper model (tiny, base, small, medium, large-v3)")
    proc_p.add_argument("--language", default=None, help="Language code (e.g. en, hi)")
    proc_p.add_argument("--min-duration", type=float, default=20.0, help="Min clip length in seconds")
    proc_p.add_argument("--max-duration", type=float, default=120.0, help="Max clip length in seconds")
    proc_p.add_argument("--min-score", type=float, default=0.0, help="Min highlight score threshold")
    proc_p.add_argument("--max-candidates", type=int, default=10, help="Max candidate clips to generate")
    proc_p.add_argument("--auto-export", action="store_true", help="Automatically export top clips")
    proc_p.add_argument("--export-count", type=int, default=3, help="Number of top clips to auto-export")
    proc_p.add_argument("--aspect", default=None, help="Crop aspect ratio, e.g. 9:16 or 1:1")
    proc_p.add_argument("--prefix", default="clip", help="Export filename prefix")

    # list-jobs
    list_p = subparsers.add_parser("list-jobs", help="List recent processing jobs")
    list_p.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "diagnostics":
        cmd_diagnostics(args)
    elif args.command == "process":
        cmd_process(args)
    elif args.command == "list-jobs":
        cmd_list_jobs(args)


if __name__ == "__main__":
    main()
