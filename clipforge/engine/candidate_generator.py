"""
Candidate generator — produces ranked highlight candidate intervals from a transcript.

Strategy:
1. Sliding window (configurable size/step) produces raw windows.
2. Each window is scored with highlight_scorer.
3. Overlapping candidates (>50% overlap) are de-duplicated, keeping higher score.
4. Boundaries refined with boundary_refiner.
5. Results sorted by score descending.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
import uuid

from engine.transcriber import TranscriptSegment, TranscriptionResult
from engine.highlight_scorer import CandidateScore, score_candidate
from engine.boundary_refiner import refine_boundaries
from engine.config import (
    DEFAULT_MIN_DURATION, DEFAULT_MAX_DURATION,
    DEFAULT_WINDOW_SIZE, DEFAULT_WINDOW_STEP,
    DEFAULT_MIN_SCORE,
)

log = logging.getLogger(__name__)


@dataclass
class CandidateInterval:
    id: str
    start: float
    end: float
    duration: float
    score: CandidateScore
    transcript_text: str
    rank: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "start": self.start,
            "end": self.end,
            "duration": self.duration,
            "score": self.score.total,
            "score_breakdown": self.score.breakdown,
            "matched_keywords": self.score.matched_keywords,
            "warnings": self.warnings + self.score.warnings,
            "transcript_text": self.transcript_text,
            "rank": self.rank,
        }


def _get_text_in_window(
    segments: list[TranscriptSegment], start: float, end: float
) -> str:
    """Concatenate transcript text for segments that overlap the window."""
    parts = []
    for seg in segments:
        # Include segment if it overlaps the window
        overlap_start = max(seg.start, start)
        overlap_end = min(seg.end, end)
        if overlap_end > overlap_start:
            parts.append(seg.text.strip())
    return " ".join(parts)


def _overlap_ratio(a_start, a_end, b_start, b_end) -> float:
    """Return what fraction of the shorter interval is covered by the overlap."""
    overlap = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    shorter = min(a_end - a_start, b_end - b_start)
    return overlap / max(shorter, 1e-6)


def _deduplicate(candidates: list[CandidateInterval], overlap_threshold: float = 0.5) -> list[CandidateInterval]:
    """Remove candidates that overlap >threshold with a higher-scored one."""
    # Sort by score descending
    sorted_cands = sorted(candidates, key=lambda c: c.score.total, reverse=True)
    kept: list[CandidateInterval] = []
    for cand in sorted_cands:
        dominated = False
        for kept_cand in kept:
            if _overlap_ratio(cand.start, cand.end, kept_cand.start, kept_cand.end) > overlap_threshold:
                dominated = True
                break
        if not dominated:
            kept.append(cand)
    return kept


def generate_candidates(
    transcript: TranscriptionResult,
    total_duration: float,
    window_size: float = DEFAULT_WINDOW_SIZE,
    window_step: float = DEFAULT_WINDOW_STEP,
    min_duration: float = DEFAULT_MIN_DURATION,
    max_duration: float = DEFAULT_MAX_DURATION,
    min_score: float = DEFAULT_MIN_SCORE,
    max_candidates: int = 20,
    refine_boundaries: bool = True,
) -> list[CandidateInterval]:
    """
    Generate ranked highlight candidates from a transcription result.

    Args:
        transcript: The full transcription with word timestamps.
        total_duration: Source video duration in seconds.
        window_size: Sliding window width in seconds.
        window_step: Sliding window step in seconds.
        min_duration: Minimum clip duration.
        max_duration: Maximum clip duration.
        min_score: Minimum highlight score to include (0..1).
        max_candidates: Maximum number of candidates to return.
        refine_boundaries: Whether to snap boundaries to word boundaries.

    Returns:
        List of CandidateInterval objects sorted by score descending.
    """
    segments = transcript.segments
    if not segments:
        log.warning("No transcript segments — cannot generate candidates")
        return []

    raw_candidates: list[CandidateInterval] = []

    # Sliding window
    t = 0.0
    while t < total_duration:
        window_end = min(t + window_size, total_duration)
        actual_duration = window_end - t

        if actual_duration < min_duration:
            t += window_step
            continue

        text = _get_text_in_window(segments, t, window_end)
        if len(text.strip()) < 20:  # Skip near-silent windows
            t += window_step
            continue

        cand_score = score_candidate(
            text=text,
            start=t,
            end=window_end,
            all_segments=segments,
            total_duration=total_duration,
            min_dur=min_duration,
            max_dur=max_duration,
        )

        if cand_score.total >= min_score:
            raw_candidates.append(CandidateInterval(
                id=uuid.uuid4().hex[:12],
                start=round(t, 3),
                end=round(window_end, 3),
                duration=round(actual_duration, 3),
                score=cand_score,
                transcript_text=text,
                warnings=[],
            ))

        t += window_step

    log.info("Raw candidates before dedup: %d", len(raw_candidates))

    # De-duplicate
    deduped = _deduplicate(raw_candidates, overlap_threshold=0.5)
    log.info("Candidates after dedup: %d", len(deduped))

    # Refine boundaries
    if refine_boundaries:
        from engine import boundary_refiner as br
        refined = []
        for cand in deduped:
            new_start, new_end = br.refine_boundaries(
                cand.start, cand.end, segments, total_duration, min_duration, max_duration
            )
            cand.start = new_start
            cand.end = new_end
            cand.duration = round(new_end - new_start, 3)
            # Re-score with refined text
            refined_text = _get_text_in_window(segments, new_start, new_end)
            cand.transcript_text = refined_text
            refined.append(cand)
        deduped = refined

    # Final sort + rank
    deduped.sort(key=lambda c: c.score.total, reverse=True)
    for i, cand in enumerate(deduped[:max_candidates]):
        cand.rank = i + 1

    result = deduped[:max_candidates]
    log.info("Returning %d ranked candidates", len(result))
    return result

