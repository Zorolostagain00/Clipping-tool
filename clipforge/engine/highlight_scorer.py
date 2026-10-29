"""
Multi-signal highlight scorer for ClipForge Studio.

Scores transcript segments using several complementary signals.
Returns a CandidateScore with a breakdown dict — NOT a single magic number.
Label this "Highlight Score" in the UI. Do NOT call it "viral probability".
"""

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from engine.transcriber import TranscriptSegment, TranscriptionResult


# ── High-value keyword patterns (reused from clipper.py, extended) ──────────
HIGH_VALUE_PATTERNS: list[tuple[str, float]] = [
    # Strong engagement signals
    (r"\b(insane|insanely|absolutely|incredible|unbelievable|mind.?blowing)\b", 0.9),
    (r"\b(wait what|no way|what the|oh my god|omg|wtf|holy|bro)\b", 0.85),
    (r"\b(biggest|best|worst|greatest|most|ever|never|always|first time)\b", 0.7),
    (r"\b(secret|hidden|reveal|exposed|truth|actually|real reason)\b", 0.75),
    (r"\b(win|won|lose|lost|fail|failed|success|amazing|awesome)\b", 0.6),
    (r"\b(look at this|check this out|watch this|this is|this was)\b", 0.5),
    # Questions often signal compelling moments
    (r"\b(how|why|what|who|where|when)\b.*\?", 0.55),
    # Emotional peaks
    (r"\b(laugh|lol|haha|hilarious|funny|joke|serious|emotional|cry|sad|happy)\b", 0.6),
    # Action / gaming signals (from existing clipper)
    (r"\b(kill|died|alive|survive|escape|caught|found|epic|clutch|combo|perfect)\b", 0.65),
    # Instructional
    (r"\b(tip|trick|hack|tutorial|how to|step|method|technique|important)\b", 0.6),
]

_COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), w) for p, w in HIGH_VALUE_PATTERNS]


@dataclass
class CandidateScore:
    total: float                         # 0.0 .. 1.0
    breakdown: dict[str, float] = field(default_factory=dict)
    matched_keywords: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": round(self.total, 4),
            "breakdown": {k: round(v, 4) for k, v in self.breakdown.items()},
            "matched_keywords": self.matched_keywords,
            "warnings": self.warnings,
        }


def _keyword_score(text: str) -> tuple[float, list[str]]:
    """Keyword pattern score. Returns (score 0..1, matched_patterns)."""
    matched = []
    total_weight = 0.0
    max_possible = sum(w for _, w in _COMPILED_PATTERNS)
    for pattern, weight in _COMPILED_PATTERNS:
        m = pattern.search(text)
        if m:
            total_weight += weight
            matched.append(m.group(0).strip())
    return min(total_weight / max(max_possible * 0.3, 1e-6), 1.0), matched


def _structural_score(text: str) -> float:
    """
    Score based on structural richness:
    - Question density (sentences ending with ?)
    - Exclamation density
    - Sentence variety
    """
    sentences = re.split(r"[.!?]+", text)
    n = max(len(sentences), 1)
    q_count = text.count("?")
    ex_count = text.count("!")
    q_score = min(q_count / n, 1.0)
    ex_score = min(ex_count / n, 1.0)
    # Variety: prefer 2-8 sentences (mono-sentence clips feel incomplete)
    variety = min(n / 8.0, 1.0) if n >= 2 else 0.2
    return round((q_score * 0.35 + ex_score * 0.25 + variety * 0.4), 4)


def _duration_score(duration: float, min_dur: float = 20.0, max_dur: float = 120.0,
                    ideal_min: float = 30.0, ideal_max: float = 90.0) -> float:
    """
    Score favoring clips in the ideal 30-90s range.
    Outside min/max → heavy penalty.
    """
    if duration < min_dur or duration > max_dur:
        return 0.1
    if ideal_min <= duration <= ideal_max:
        return 1.0
    # Gradient on either side of the ideal range
    if duration < ideal_min:
        return 0.5 + 0.5 * (duration - min_dur) / max(ideal_min - min_dur, 1)
    return 0.5 + 0.5 * (max_dur - duration) / max(max_dur - ideal_max, 1)


def _speech_density_score(text: str, duration: float) -> float:
    """Score based on words-per-second. Penalise silent or very fast speech."""
    if duration <= 0:
        return 0.5
    words_per_sec = len(text.split()) / duration
    # Ideal: 1.5–3.5 w/s (natural conversational speech)
    if 1.5 <= words_per_sec <= 3.5:
        return 1.0
    if words_per_sec < 0.5:
        return 0.1  # Mostly silence
    if words_per_sec < 1.5:
        return 0.5 + 0.5 * (words_per_sec - 0.5) / 1.0
    # Fast speech (> 3.5 w/s) — still fine, mild penalty
    return max(0.6, 1.0 - (words_per_sec - 3.5) * 0.05)


def _completeness_score(
    text: str,
    start: float,
    end: float,
    all_segments: list[TranscriptSegment],
    total_duration: float,
) -> tuple[float, list[str]]:
    """
    Penalise clips that start or end mid-sentence.
    Returns (score 0..1, warnings).
    """
    warnings = []
    stripped = text.strip()
    if not stripped:
        return 0.0, ["No speech detected"]

    score = 1.0

    if stripped and not stripped[-1] in ".!?…":
        score -= 0.25
        warnings.append("Clip may end mid-sentence")

    # Very rough: check if the first word looks like a continuation
    first_word = stripped.split()[0] if stripped.split() else ""
    connectors = {"and", "but", "so", "or", "because", "which", "that", "then", "also"}
    if first_word.lower() in connectors:
        score -= 0.15
        warnings.append("Clip may start mid-sentence")

    return max(score, 0.1), warnings


def score_candidate(
    text: str,
    start: float,
    end: float,
    all_segments: list[TranscriptSegment],
    total_duration: float,
    min_dur: float = 20.0,
    max_dur: float = 120.0,
) -> CandidateScore:
    """
    Score a candidate clip interval.

    Args:
        text: Full transcript text of the clip.
        start: Clip start time (seconds).
        end: Clip end time (seconds).
        all_segments: All transcript segments (for completeness check context).
        total_duration: Total video duration.
        min_dur: Minimum acceptable duration.
        max_dur: Maximum acceptable duration.

    Returns:
        CandidateScore with total and per-signal breakdown.
    """
    if not text.strip():
        return CandidateScore(
            total=0.0,
            breakdown={
                "keyword": 0.0,
                "structural": 0.0,
                "duration": 0.0,
                "speech_density": 0.0,
                "completeness": 0.0,
            },
            matched_keywords=[],
            warnings=["No speech or text detected"],
        )

    duration = end - start
    keyword_s, matched = _keyword_score(text)
    structural_s = _structural_score(text)
    duration_s = _duration_score(duration, min_dur, max_dur)
    speech_s = _speech_density_score(text, duration)
    completeness_s, warnings = _completeness_score(text, start, end, all_segments, total_duration)

    # Weighted combination (weights sum to 1.0)
    weights = {
        "keyword":      0.35,
        "structural":   0.20,
        "duration":     0.20,
        "speech_density": 0.15,
        "completeness": 0.10,
    }
    scores = {
        "keyword":        keyword_s,
        "structural":     structural_s,
        "duration":       duration_s,
        "speech_density": speech_s,
        "completeness":   completeness_s,
    }
    total = sum(scores[k] * weights[k] for k in weights)
    total = round(min(max(total, 0.0), 1.0), 4)

    return CandidateScore(
        total=total,
        breakdown=scores,
        matched_keywords=matched[:10],  # cap for storage
        warnings=warnings,
    )

