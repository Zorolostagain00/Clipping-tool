"""
Transcription adapters for ClipForge Studio.

Primary:  FasterWhisperTranscriber  (faster-whisper + CTranslate2, local)
Fallback: OpenAIWhisperTranscriber  (openai-whisper, local)

Both produce a unified TranscriptionResult with segment-level word timestamps.
Cache key = SHA256(source_path + file_size + mtime + model_id + language).
Cache is stored as JSON in TRANSCRIPT_CACHE_DIR.
"""

import hashlib
import json
import logging
import pathlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from engine.config import (
    TRANSCRIPT_CACHE_DIR,
    MODEL_CACHE_DIR,
    DEFAULT_WHISPER_MODEL,
    DEFAULT_LANGUAGE,
)

log = logging.getLogger(__name__)


# ── Data structures ─────────────────────────────────────────────────────────

@dataclass
class WordTimestamp:
    word: str
    start: float
    end: float
    probability: float = 1.0


@dataclass
class TranscriptSegment:
    id: int
    start: float
    end: float
    text: str
    words: list[WordTimestamp] = field(default_factory=list)
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0


@dataclass
class TranscriptionResult:
    segments: list[TranscriptSegment]
    language: str
    model_id: str
    duration: float
    cache_key: str
    cached: bool = False
    transcription_time: float = 0.0

    @property
    def full_text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments)

    def to_dict(self) -> dict:
        return {
            "segments": [
                {
                    "id": s.id,
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "avg_logprob": s.avg_logprob,
                    "no_speech_prob": s.no_speech_prob,
                    "words": [
                        {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                        for w in s.words
                    ],
                }
                for s in self.segments
            ],
            "language": self.language,
            "model_id": self.model_id,
            "duration": self.duration,
            "cache_key": self.cache_key,
        }


# ── Cache helpers ────────────────────────────────────────────────────────────

def _make_cache_key(path: pathlib.Path, model_id: str, language: Optional[str]) -> str:
    stat = path.stat()
    raw = f"{path}|{stat.st_size}|{stat.st_mtime}|{model_id}|{language or 'auto'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _cache_path(cache_key: str) -> pathlib.Path:
    return TRANSCRIPT_CACHE_DIR / f"{cache_key}.json"


def _load_cache(cache_key: str) -> Optional[TranscriptionResult]:
    cp = _cache_path(cache_key)
    if not cp.exists():
        return None
    try:
        data = json.loads(cp.read_text(encoding="utf-8"))
        segments = []
        for s in data.get("segments", []):
            words = [
                WordTimestamp(w["word"], w["start"], w["end"], w.get("probability", 1.0))
                for w in s.get("words", [])
            ]
            segments.append(TranscriptSegment(
                id=s.get("id", 0),
                start=s["start"],
                end=s["end"],
                text=s["text"],
                words=words,
                avg_logprob=s.get("avg_logprob", 0.0),
                no_speech_prob=s.get("no_speech_prob", 0.0),
            ))
        return TranscriptionResult(
            segments=segments,
            language=data.get("language", "unknown"),
            model_id=data.get("model_id", "unknown"),
            duration=data.get("duration", 0.0),
            cache_key=cache_key,
            cached=True,
        )
    except Exception as e:
        log.warning("Failed to load transcript cache %s: %s", cp, e)
        return None


def _save_cache(result: TranscriptionResult) -> None:
    cp = _cache_path(result.cache_key)
    try:
        cp.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("Transcript cached: %s", cp)
    except Exception as e:
        log.warning("Could not save transcript cache: %s", e)


# ── Abstract base ────────────────────────────────────────────────────────────

class TranscriptionAdapter(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio_path: pathlib.Path,
        model_id: str = DEFAULT_WHISPER_MODEL,
        language: Optional[str] = DEFAULT_LANGUAGE,
        use_cache: bool = True,
        progress_callback=None,
    ) -> TranscriptionResult:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


# ── FasterWhisper adapter ────────────────────────────────────────────────────

class FasterWhisperTranscriber(TranscriptionAdapter):
    """Primary transcriber using faster-whisper (CTranslate2 backend)."""

    @property
    def name(self) -> str:
        return "faster-whisper"

    def is_available(self) -> bool:
        try:
            import faster_whisper  # noqa
            return True
        except ImportError:
            return False

    def transcribe(
        self,
        audio_path: pathlib.Path,
        model_id: str = DEFAULT_WHISPER_MODEL,
        language: Optional[str] = DEFAULT_LANGUAGE,
        use_cache: bool = True,
        progress_callback=None,
    ) -> TranscriptionResult:
        from faster_whisper import WhisperModel

        audio_path = pathlib.Path(audio_path)
        cache_key = _make_cache_key(audio_path, f"fw-{model_id}", language)

        if use_cache:
            cached = _load_cache(cache_key)
            if cached:
                log.info("Transcript loaded from cache (key=%s)", cache_key)
                return cached

        log.info("Transcribing with faster-whisper model=%s ...", model_id)
        t0 = time.perf_counter()

        model = WhisperModel(
            model_id,
            device="cpu",
            compute_type="int8",
            download_root=str(MODEL_CACHE_DIR),
        )

        segments_raw, info = model.transcribe(
            str(audio_path),
            language=language,
            word_timestamps=True,
            beam_size=5,
            vad_filter=True,
        )

        segments: list[TranscriptSegment] = []
        seg_list = list(segments_raw)  # materialise generator
        for i, seg in enumerate(seg_list):
            words = []
            if seg.words:
                for w in seg.words:
                    words.append(WordTimestamp(
                        word=w.word,
                        start=round(w.start, 3),
                        end=round(w.end, 3),
                        probability=round(w.probability, 4),
                    ))
            segments.append(TranscriptSegment(
                id=i,
                start=round(seg.start, 3),
                end=round(seg.end, 3),
                text=seg.text,
                words=words,
                avg_logprob=round(getattr(seg, "avg_logprob", 0.0), 4),
                no_speech_prob=round(getattr(seg, "no_speech_prob", 0.0), 4),
            ))
            if progress_callback and len(seg_list) > 0:
                progress_callback(i / len(seg_list))

        elapsed = time.perf_counter() - t0
        result = TranscriptionResult(
            segments=segments,
            language=info.language,
            model_id=f"fw-{model_id}",
            duration=info.duration,
            cache_key=cache_key,
            transcription_time=round(elapsed, 2),
        )

        if use_cache:
            _save_cache(result)

        log.info("Transcription complete in %.1fs (%d segments)", elapsed, len(segments))
        return result


# ── OpenAI Whisper fallback adapter ─────────────────────────────────────────

class OpenAIWhisperTranscriber(TranscriptionAdapter):
    """Fallback transcriber using openai-whisper."""

    @property
    def name(self) -> str:
        return "openai-whisper"

    def is_available(self) -> bool:
        try:
            import whisper  # noqa
            return True
        except ImportError:
            return False

    def transcribe(
        self,
        audio_path: pathlib.Path,
        model_id: str = DEFAULT_WHISPER_MODEL,
        language: Optional[str] = DEFAULT_LANGUAGE,
        use_cache: bool = True,
        progress_callback=None,
    ) -> TranscriptionResult:
        import whisper

        audio_path = pathlib.Path(audio_path)
        cache_key = _make_cache_key(audio_path, f"ow-{model_id}", language)

        if use_cache:
            cached = _load_cache(cache_key)
            if cached:
                log.info("Transcript loaded from cache (key=%s)", cache_key)
                return cached

        log.info("Transcribing with openai-whisper model=%s ...", model_id)
        t0 = time.perf_counter()

        model = whisper.load_model(model_id, download_root=str(MODEL_CACHE_DIR))
        options = {}
        if language:
            options["language"] = language
        raw = model.transcribe(str(audio_path), word_timestamps=True, **options)

        segments: list[TranscriptSegment] = []
        for i, seg in enumerate(raw.get("segments", [])):
            words = []
            for w in seg.get("words", []):
                words.append(WordTimestamp(
                    word=w.get("word", ""),
                    start=round(w.get("start", seg["start"]), 3),
                    end=round(w.get("end", seg["end"]), 3),
                    probability=round(w.get("probability", 1.0), 4),
                ))
            segments.append(TranscriptSegment(
                id=i,
                start=round(seg["start"], 3),
                end=round(seg["end"], 3),
                text=seg["text"],
                words=words,
                avg_logprob=round(seg.get("avg_logprob", 0.0), 4),
                no_speech_prob=round(seg.get("no_speech_prob", 0.0), 4),
            ))

        elapsed = time.perf_counter() - t0
        duration = raw.get("duration", 0.0) or (segments[-1].end if segments else 0.0)

        result = TranscriptionResult(
            segments=segments,
            language=raw.get("language", "unknown"),
            model_id=f"ow-{model_id}",
            duration=duration,
            cache_key=cache_key,
            transcription_time=round(elapsed, 2),
        )

        if use_cache:
            _save_cache(result)

        log.info("Transcription complete in %.1fs (%d segments)", elapsed, len(segments))
        return result


# ── Auto-selecting transcriber ───────────────────────────────────────────────

def get_transcriber() -> TranscriptionAdapter:
    """Return the best available transcriber (faster-whisper > openai-whisper)."""
    fw = FasterWhisperTranscriber()
    if fw.is_available():
        log.info("Using faster-whisper transcriber")
        return fw
    ow = OpenAIWhisperTranscriber()
    if ow.is_available():
        log.warning("faster-whisper unavailable, using openai-whisper fallback")
        return ow
    raise RuntimeError(
        "No Whisper transcriber available. "
        "Install faster-whisper: pip install faster-whisper"
    )

