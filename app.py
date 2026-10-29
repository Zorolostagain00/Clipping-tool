import os
import sys
import time
import subprocess
import re
import json
import shutil
from pathlib import Path
import streamlit as st

# Set page configuration
st.set_page_config(
    page_title="AI Viral Clipping Studio",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Base directories
BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
CLIPS_DIR = OUTPUT_DIR / "clips"
LOGS_DIR = OUTPUT_DIR / "logs"

# Ensure directories exist
for p in [INPUT_DIR, CLIPS_DIR, LOGS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1f1c2c 0%, #928DAB 100%);
        padding: 24px;
        border-radius: 12px;
        color: white;
        margin-bottom: 24px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .metric-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        padding: 16px;
        text-align: center;
    }
    .status-badge-ok {
        background-color: #10B981;
        color: white;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 600;
    }
    .status-badge-warn {
        background-color: #F59E0B;
        color: white;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 600;
    }
    .status-badge-err {
        background-color: #EF4444;
        color: white;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Ensure WinGet/FFmpeg paths are in PATH if available
winget_links = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links"
if winget_links.exists() and str(winget_links) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{winget_links};{os.environ.get('PATH', '')}"

def check_dependencies():
    """Check required system dependencies and packages."""
    status = {}
    
    # FFmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    status["ffmpeg"] = bool(ffmpeg_path)
    
    # Python Packages
    packages = ["torch", "whisper", "yt_dlp", "tqdm", "ffmpeg"]
    for pkg in packages:
        try:
            __import__(pkg)
            status[pkg] = True
        except ImportError:
            status[pkg] = False
            
    return status

deps = check_dependencies()

# Sidebar
with st.sidebar:
    st.markdown("### 🎬 **Viral Clip AI Studio**")
    st.markdown("Analyze full videos. Discover high-engagement viral moments with Whisper AI & smart pattern scoring.")
    st.markdown("---")
    
    st.markdown("#### ⚡ System Status")
    col_a, col_b = st.columns(2)
    with col_a:
        st.write("FFmpeg:")
        st.write("Whisper:")
        st.write("PyTorch:")
        st.write("yt-dlp:")
    with col_b:
        st.markdown('<span class="status-badge-ok">Installed</span>' if deps.get("ffmpeg") else '<span class="status-badge-warn">Missing</span>', unsafe_allow_html=True)
        st.markdown('<span class="status-badge-ok">Installed</span>' if deps.get("whisper") else '<span class="status-badge-warn">Missing</span>', unsafe_allow_html=True)
        st.markdown('<span class="status-badge-ok">Installed</span>' if deps.get("torch") else '<span class="status-badge-warn">Missing</span>', unsafe_allow_html=True)
        st.markdown('<span class="status-badge-ok">Installed</span>' if deps.get("yt_dlp") else '<span class="status-badge-warn">Missing</span>', unsafe_allow_html=True)

    st.markdown("---")
    
    total_clips = len(list(CLIPS_DIR.glob("*.mp4")))
    total_inputs = len([f for f in INPUT_DIR.glob("*.*") if f.suffix.lower() in [".mp4", ".mkv", ".avi", ".mov", ".webm"]])
    st.metric("Total Clips Exported", total_clips)
    st.metric("Input Videos Ready", total_inputs)

    st.markdown("---")
    st.caption("100% Local • Private • Unlimited Processing")

# Main Header
st.markdown("""
<div class="main-header">
    <h1 style="margin:0; font-size: 2.2rem;">🎬 AI Viral Clipping Studio</h1>
    <p style="margin: 6px 0 0 0; opacity: 0.9;">Automatically transcribe, detect funny & viral moments, and extract ready-to-share clips.</p>
</div>
""", unsafe_allow_html=True)

# Tabs Navigation
tab_clip, tab_library, tab_batch, tab_system = st.tabs([
    "🚀 Create Clips",
    "🎞️ Clip Library & Player",
    "📦 Batch Processor",
    "⚙️ System Diagnostics"
])

# -------------------------------------------------------------
# TAB 1: CREATE CLIPS
# -------------------------------------------------------------
with tab_clip:
    st.subheader("Extract Clips from Video")
    
    source_type = st.radio(
        "Select Video Source:",
        ["📺 YouTube URL", "📁 Local Video File"],
        horizontal=True
    )
    
    col1, col2 = st.columns([1.2, 0.8])
    
    with col1:
        if "YouTube" in source_type:
            yt_url = st.text_input("Enter YouTube Video URL:", placeholder="https://www.youtube.com/watch?v=...")
            
            if yt_url:
                with st.expander("🔍 Video Preview & Info", expanded=True):
                    try:
                        from youtube_downloader import validate_youtube_url, fetch_metadata
                        valid = validate_youtube_url(yt_url)
                        if valid.get("valid"):
                            st.success(f"Valid YouTube URL (ID: {valid.get('video_id')})")
                            if st.button("Fetch Details"):
                                with st.spinner("Fetching metadata..."):
                                    meta = fetch_metadata(yt_url)
                                    if meta:
                                        st.write(f"**Title:** {meta.title}")
                                        st.write(f"**Channel:** {meta.author}")
                                        st.write(f"**Duration:** {meta.duration_formatted}")
                                        if meta.thumbnail_url:
                                            st.image(meta.thumbnail_url, width=320)
                        else:
                            st.warning("Please enter a valid YouTube URL.")
                    except Exception as e:
                        st.info(f"URL entered: {yt_url}")
        else:
            existing_files = [
                f.name for f in INPUT_DIR.glob("*.*") 
                if f.suffix.lower() in [".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"]
                and not re.search(r'\.f\d+\.', f.name) and "Frag" not in f.name
            ]
            
            selected_file = None
            if existing_files:
                selected_file = st.selectbox("Choose a video from input folder:", existing_files)
            else:
                st.info("No video files found in the `input/` folder.")
                
            uploaded_file = st.file_uploader("Or upload a new video file:", type=["mp4", "mkv", "avi", "mov", "webm"])
            if uploaded_file is not None:
                save_path = INPUT_DIR / uploaded_file.name
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                st.success(f"Saved: {uploaded_file.name} to `input/`")
                selected_file = uploaded_file.name

    with col2:
        st.markdown("#### ⚙️ Clipping Settings")
        whisper_model = st.selectbox(
            "Whisper Model:",
            ["base", "tiny", "small", "medium", "large"],
            index=0,
            help="Tiny/Base are fast. Small/Medium offer higher transcription accuracy."
        )
        
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            min_duration = st.number_input("Min Duration (s):", min_value=10, max_value=300, value=30, step=5)
        with col_s2:
            max_duration = st.number_input("Max Duration (s):", min_value=20, max_value=600, value=90, step=5)
            
        min_score = st.slider("Engagement Min Score:", min_value=1, max_value=20, value=5, help="Higher values only keep the highest-density viral moments.")
        
        burn_subtitles = st.checkbox("Burn Subtitles directly into clips", value=False)
        dry_run = st.checkbox("Dry Run (analyze & score without exporting video files)", value=False)

    st.markdown("---")
    
    # Run Action
    if st.button("🔥 Start AI Clipping Process", type="primary", use_container_width=True):
        cmd = []
        if "YouTube" in source_type:
            if not yt_url:
                st.error("Please enter a YouTube URL.")
            else:
                cmd = [
                    sys.executable,
                    str(BASE_DIR / "yt_to_clips.py"),
                    yt_url,
                    "--model", whisper_model,
                    "--min-duration", str(min_duration),
                    "--max-duration", str(max_duration),
                    "--min-score", str(min_score)
                ]
                if dry_run:
                    cmd.append("--dry-run")
        else:
            if not selected_file:
                st.error("Please select or upload a video file.")
            else:
                target_video_path = INPUT_DIR / selected_file
                cmd = [
                    sys.executable,
                    str(BASE_DIR / "clipper.py"),
                    str(target_video_path),
                    "--model", whisper_model,
                    "--min-duration", str(min_duration),
                    "--max-duration", str(max_duration),
                    "--min-score", str(min_score)
                ]
                if dry_run:
                    cmd.append("--dry-run")

        if cmd:
            st.info(f"🚀 **Started Pipeline:** `{' '.join(cmd[1:])}`")
            
            # Visual Stage Tracker
            status_placeholder = st.empty()
            progress_bar = st.progress(0.05, text="🎬 Initializing AI Viral Clipper...")
            
            # Live Output Expander
            log_expander = st.expander("📄 View Live Console Output", expanded=True)
            with log_expander:
                log_box = st.empty()
            
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                cwd=str(BASE_DIR)
            )
            
            output_lines = []
            current_progress = 0.05
            current_stage = "Starting..."
            total_clips_to_export = 10
            exported_clips_count = 0
            
            # Helper to update stage status card
            def render_stage_card(active_step: int, message: str):
                steps = [
                    ("1. Ingestion / Download", "📥"),
                    ("2. Whisper Transcription", "🎙️"),
                    ("3. Viral Pattern Scoring", "🧠"),
                    ("4. FFmpeg Clip Cutting", "✂️"),
                    ("5. Complete", "🎉")
                ]
                html = '<div style="display: flex; gap: 8px; margin: 12px 0; flex-wrap: wrap;">'
                for i, (title, icon) in enumerate(steps, 1):
                    if i < active_step:
                        bg = "#065F46"; border = "#10B981"; opacity = "0.9" # Done
                    elif i == active_step:
                        bg = "#1E3A8A"; border = "#3B82F6"; opacity = "1.0" # Active
                    else:
                        bg = "rgba(255,255,255,0.05)"; border = "rgba(255,255,255,0.1)"; opacity = "0.6" # Upcoming
                    
                    html += f'<div style="flex: 1; min-width: 130px; background: {bg}; border: 1px solid {border}; border-radius: 8px; padding: 10px; opacity: {opacity}; text-align: center;">'
                    html += f'<div style="font-size: 1.1rem;">{icon}</div>'
                    html += f'<div style="font-size: 0.8rem; font-weight: 600; margin-top: 4px;">{title}</div>'
                    html += '</div>'
                html += '</div>'
                html += f'<div style="font-weight: 600; color: #60A5FA; margin-bottom: 8px;">Status: {message}</div>'
                status_placeholder.markdown(html, unsafe_allow_html=True)

            render_stage_card(1, "Preparing video source...")

            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    clean_line = line.strip()
                    if not clean_line:
                        continue
                    
                    # Filter out repetitive progress bar redraw noise from raw log
                    if not clean_line.startswith("[█") and "WRITING" not in clean_line:
                        output_lines.append(clean_line)
                        with log_expander:
                            log_box.code("\n".join(output_lines[-12:]), language="text")
                    
                    # Stage 1: Download detection
                    dl_match = re.search(r'\[download\]\s+([\d\.]+)%\s+of\s+~?\s*([\d\.\w]+)\s+at\s+([\d\.\w/]+)\s+ETA\s+([\d:]+)', clean_line)
                    if dl_match:
                        pct, size, speed, eta = dl_match.groups()
                        pct_f = float(pct)
                        current_progress = 0.05 + (pct_f / 100.0) * 0.30
                        msg = f"Downloading video: {pct_f:.1f}% ({speed}, ETA {eta})"
                        progress_bar.progress(min(current_progress, 0.35), text=msg)
                        render_stage_card(1, msg)
                    elif "MERGING" in clean_line or "[Merger]" in clean_line or "[ffmpeg]" in clean_line:
                        current_progress = 0.38
                        msg = "Merging audio and video tracks with FFmpeg..."
                        progress_bar.progress(current_progress, text=msg)
                        render_stage_card(1, msg)
                    
                    # Stage 2: Whisper Transcription
                    elif "Step 2: Transcribing speech" in clean_line or "Transcribing speech" in clean_line or "stage_transcribe" in clean_line:
                        current_progress = 0.45
                        msg = f"Transcribing full speech with Whisper AI ({whisper_model} model)..."
                        progress_bar.progress(current_progress, text=msg)
                        render_stage_card(2, msg)
                    elif "Transcript ready" in clean_line or "segments" in clean_line:
                        current_progress = 0.65
                        msg = "Transcript complete! Analyzing dialogue..."
                        progress_bar.progress(current_progress, text=msg)
                        render_stage_card(2, msg)
                    
                    # Stage 3: Viral Analysis & Pattern Scoring
                    elif "Step 3: Finding" in clean_line or "Finding ALL worthwhile moments" in clean_line or "stage_find_clips" in clean_line:
                        current_progress = 0.70
                        msg = "Scanning transcript for viral hooks, comedy, & high engagement moments..."
                        progress_bar.progress(current_progress, text=msg)
                        render_stage_card(3, msg)
                    elif "Score filter" in clean_line:
                        current_progress = 0.75
                        msg = f"Filtering moments by engagement score (threshold >= {min_score})..."
                        progress_bar.progress(current_progress, text=msg)
                        render_stage_card(3, msg)
                    
                    # Stage 4: FFmpeg Clip Cutting
                    elif "Exporting" in clean_line and "clip" in clean_line:
                        exp_match = re.search(r'Exporting\s+(\d+)\s+clip', clean_line)
                        if exp_match:
                            total_clips_to_export = max(int(exp_match.group(1)), 1)
                        current_progress = 0.80
                        msg = f"Cutting {total_clips_to_export} clips using FFmpeg (lossless stream copy)..."
                        progress_bar.progress(current_progress, text=msg)
                        render_stage_card(4, msg)
                    elif clean_line.startswith("#") and "->" in clean_line and "score:" in clean_line:
                        exported_clips_count += 1
                        clip_pct = min(exported_clips_count / total_clips_to_export, 1.0)
                        current_progress = 0.80 + (clip_pct * 0.16)
                        msg = f"Cutting clip #{exported_clips_count} of {total_clips_to_export}..."
                        progress_bar.progress(min(current_progress, 0.96), text=msg)
                        render_stage_card(4, msg)
                    
                    # Stage 5: Finalizing
                    elif "RESULTS DASHBOARD" in clean_line or "Export complete" in clean_line:
                        current_progress = 0.98
                        msg = "Building report and finalizing clip exports..."
                        progress_bar.progress(current_progress, text=msg)
                        render_stage_card(5, msg)
                        
            rc = process.poll()
            if rc == 0:
                progress_bar.progress(1.0, text="✅ 100% Complete! All clips ready!")
                render_stage_card(5, "Completed successfully! Enjoy your viral clips.")
                st.balloons()
                st.success("🎉 Processing complete! You can preview and download your clips below or in the 'Clip Library & Player' tab.")
                
                # Show immediate preview of newly created clips
                recent_clips = sorted(list(CLIPS_DIR.glob("*.mp4")), key=os.path.getmtime, reverse=True)[:3]
                if recent_clips:
                    st.markdown("### 🎬 Newly Created Clips Preview")
                    prev_cols = st.columns(len(recent_clips))
                    for idx, cpath in enumerate(recent_clips):
                        with prev_cols[idx]:
                            st.write(f"**{cpath.name}**")
                            st.video(str(cpath))
            else:
                st.error(f"Process ended with error code {rc}. Check output above.")


# -------------------------------------------------------------
# TAB 2: CLIP LIBRARY & PLAYER
# -------------------------------------------------------------
with tab_library:
    st.subheader("Generated Clips & Reports")
    
    clips = sorted(list(CLIPS_DIR.glob("*.mp4")), key=os.path.getmtime, reverse=True)
    logs = sorted(list(LOGS_DIR.glob("*.md")), key=os.path.getmtime, reverse=True)
    
    col_l1, col_l2 = st.columns([1.4, 0.6])
    
    with col_l1:
        if not clips:
            st.info("No clips found yet in `output/clips/`. Run the clipper in the first tab to generate clips!")
        else:
            st.write(f"Found **{len(clips)}** exported clips:")
            
            # Pagination or selection
            selected_clip_path = st.selectbox(
                "Select a clip to preview:",
                clips,
                format_func=lambda x: f"🎬 {x.name} ({round(x.stat().st_size / (1024*1024), 2)} MB)"
            )
            
            if selected_clip_path:
                st.markdown(f"#### Playing: `{selected_clip_path.name}`")
                st.video(str(selected_clip_path))
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    with open(selected_clip_path, "rb") as video_file:
                        st.download_button(
                            label="⬇️ Download Clip MP4",
                            data=video_file,
                            file_name=selected_clip_path.name,
                            mime="video/mp4",
                            use_container_width=True
                        )
                with col_btn2:
                    if st.button("🗑️ Delete Clip", use_container_width=True):
                        selected_clip_path.unlink()
                        st.warning(f"Deleted {selected_clip_path.name}")
                        st.rerun()

    with col_l2:
        st.markdown("#### 📄 Analysis Reports")
        if logs:
            selected_log = st.selectbox("Select Report:", logs, format_func=lambda x: x.name)
            if selected_log:
                with st.expander("View Full Markdown Report", expanded=True):
                    with open(selected_log, "r", encoding="utf-8", errors="replace") as f:
                        report_content = f.read()
                    st.markdown(report_content)
        else:
            st.caption("No reports generated yet.")


# -------------------------------------------------------------
# TAB 3: BATCH PROCESSOR
# -------------------------------------------------------------
with tab_batch:
    st.subheader("Batch Process Videos")
    st.write("Automatically process all video files placed in the `input/` folder in sequence.")
    
    batch_files = [
        f for f in INPUT_DIR.glob("*.*") 
        if f.suffix.lower() in [".mp4", ".mkv", ".avi", ".mov", ".webm"]
        and not re.search(r'\.f\d+\.', f.name) and "Frag" not in f.name
    ]
    
    if batch_files:
        st.write(f"Videos queued in `input/` ({len(batch_files)}):")
        for f in batch_files:
            st.write(f"- `{f.name}` ({round(f.stat().st_size / (1024*1024), 2)} MB)")
            
        b_model = st.selectbox("Whisper Model for Batch:", ["base", "tiny", "small", "medium"], key="batch_model")
        b_score = st.slider("Min Engagement Score:", min_value=1, max_value=15, value=5, key="batch_score")
        
        if st.button("🚀 Run Batch Processing", type="primary"):
            cmd = [
                sys.executable,
                str(BASE_DIR / "batch_processor.py"),
                "--model", b_model,
                "--min-score", str(b_score)
            ]
            st.info(f"Running: {' '.join(cmd)}")
            log_area = st.empty()
            
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            
            p = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                cwd=str(BASE_DIR)
            )
            
            lines = []
            while True:
                line = p.stdout.readline()
                if not line and p.poll() is not None:
                    break
                if line:
                    lines.append(line.rstrip())
                    log_area.code("\n".join(lines[-15:]), language="text")
            st.success("Batch processing completed!")
    else:
        st.info("No videos found in `input/`. Please drop video files into the input folder or upload them in Tab 1.")


# -------------------------------------------------------------
# TAB 4: SYSTEM & DIAGNOSTICS
# -------------------------------------------------------------
with tab_system:
    st.subheader("System Diagnostics & Environment Setup")
    
    st.markdown("""
    The AI Viral Clipper requires **FFmpeg**, **PyTorch**, and **OpenAI Whisper** to transcribe audio and cut clips.
    """)
    
    diag_col1, diag_col2 = st.columns(2)
    with diag_col1:
        st.markdown("#### Installed Tools & Packages")
        for item, ok in deps.items():
            icon = "✅" if ok else "❌"
            label = "Ready" if ok else "Not Found"
            st.write(f"{icon} **{item.upper()}**: {label}")
            
    with diag_col2:
        st.markdown("#### Quick Fixes")
        if not deps.get("ffmpeg"):
            st.warning("FFmpeg is missing. Install via terminal with `winget install Gyan.FFmpeg` or download from ffmpeg.org and add to PATH.")
        if not deps.get("torch") or not deps.get("whisper"):
            st.info("Run in terminal:\n```bash\npip install torch --index-url https://download.pytorch.org/whl/cpu\npip install openai-whisper\n```")

    if st.button("🔄 Refresh Diagnostics"):
        st.rerun()

