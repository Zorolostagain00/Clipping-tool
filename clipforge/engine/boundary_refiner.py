"""
Boundary refiner — snaps clip boundaries to natural word/sentence boundaries.

Uses word-level timestamps from the transcriber so that clips start and end
at actual speech boundaries rather than arbitrary time offsets.
"""

from typing import Optional
from engine.transcriber import TranscriptSegment


def _all_words(segments: list[TranscriptSegment]) -> list[tuple[float, float, str]]:
    """Flatten all word timestamps into (start, end, word) tuples."""
    words = []
    for seg in segments:
        if seg.words:
            for w in seg.words:
                words.append((w.start, w.end, w.word))
        else:
            # Fall back to segment-level if no word timestamps
            words.append((seg.start, seg.end, seg.text.strip()))
    return sorted(words, key=lambda x: x[0])


def snap_to_word_boundary(
    t: float,
    segments: list[TranscriptSegment],
    direction: str = "nearest",  # "nearest" | "before" | "after"
    tolerance: float = 3.0,
) -> float:
    """
    Snap time t to the nearest word boundary within tolerance.

    Args:
        t: Target time in seconds.
        segments: All transcript segments.
        direction: Which side to prefer.
        tolerance: Max seconds to shift.

    Returns:
        Snapped time, or original t if no word found within tolerance.
    """
    words = _all_words(segments)
    if not words:
        return t

    best = None
    best_dist = float("inf")

    for start, end, word in words:
        if direction == "before":
            candidates = [(end, abs(end - t))]
        elif direction == "after":
            candidates = [(start, abs(start - t))]
        else:
            candidates = [(start, abs(start - t)), (end, abs(end - t))]

        for candidate_t, dist in candidates:
            if dist <= tolerance and dist < best_dist:
                best = candidate_t
                best_dist = dist

    return best if best is not None else t


def find_sentence_end(
    t: float,
    segments: list[TranscriptSegment],
    tolerance: float = 5.0,
) -> float:
    """
    Find the nearest segment end that coincides with a sentence boundary
    (.!? endings) within tolerance seconds of t.

    Returns the segment end time, or t if none found.
    """
    candidates = []
    for seg in segments:
        text = seg.text.strip()
        if text and text[-1] in ".!?…":
            dist = abs(seg.end - t)
            if dist <= tolerance:
                candidates.append((dist, seg.end))

    if not candidates:
        return t

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def find_sentence_start(
    t: float,
    segments: list[TranscriptSegment],
    tolerance: float = 5.0,
) -> float:
    """
    Find the nearest segment start that follows a sentence-ending segment,
    within tolerance seconds of t.
    """
    ends_at = {seg.end for seg in segments if seg.text.strip() and seg.text.strip()[-1] in ".!?…"}
    candidates = []
    for seg in segments:
        prev_end = None
        for e in ends_at:
            if abs(e - seg.start) < 0.5:
                prev_end = e
                break
        if prev_end is not None:
            dist = abs(seg.start - t)
            if dist <= tolerance:
                candidates.append((dist, seg.start))

    # Also consider first segment
    if segments:
        dist = abs(segments[0].start - t)
        if dist <= tolerance:
            candidates.append((dist, segments[0].start))

    if not candidates:
        return t

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def refine_boundaries(
    start: float,
    end: float,
    segments: list[TranscriptSegment],
    total_duration: float,
    min_duration: float = 20.0,
    max_duration: float = 120.0,
) -> tuple[float, float]:
    """
    Refine both boundaries of a candidate clip.

    Returns (refined_start, refined_end) clamped to valid range.
    """
    refined_start = snap_to_word_boundary(start, segments, direction="after", tolerance=3.0)
    refined_start = find_sentence_start(refined_start, segments, tolerance=4.0)

    refined_end = snap_to_word_boundary(end, segments, direction="before", tolerance=3.0)
    refined_end = find_sentence_end(refined_end, segments, tolerance=5.0)

    # Clamp
    refined_start = max(0.0, refined_start)
    refined_end = min(total_duration, refined_end)

    # Ensure duration constraints
    if refined_end - refined_start < min_duration:
        refined_end = min(refined_start + min_duration, total_duration)
    if refined_end - refined_start > max_duration:
        refined_end = refined_start + max_duration

    return round(refined_start, 3), round(refined_end, 3)

