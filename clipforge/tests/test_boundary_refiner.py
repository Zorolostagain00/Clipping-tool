"""
Tests for BoundaryRefiner.
"""

import pytest
from engine.boundary_refiner import (
    snap_to_word_boundary,
    find_sentence_end,
    refine_boundaries,
)
from engine.transcriber import TranscriptSegment, WordTimestamp


def make_segment(id, start, end, text, words=None):
    """Helper to create a TranscriptSegment with optional word timestamps."""
    ws = words or []
    return TranscriptSegment(id=id, start=start, end=end, text=text, words=ws)


def make_word(word, start, end):
    return WordTimestamp(word=word, start=start, end=end)


# Sample segments with word timestamps
SEGMENTS = [
    make_segment(0, 0.0, 5.0, "Hello world this is a test.", [
        make_word("Hello", 0.0, 0.5),
        make_word("world", 0.6, 1.0),
        make_word("this", 1.1, 1.4),
        make_word("is", 1.5, 1.7),
        make_word("a", 1.8, 1.9),
        make_word("test.", 2.0, 2.5),
    ]),
    make_segment(1, 8.0, 15.0, "What an incredible moment!", [
        make_word("What", 8.0, 8.3),
        make_word("an", 8.5, 8.7),
        make_word("incredible", 8.8, 9.4),
        make_word("moment!", 9.5, 10.0),
    ]),
    make_segment(2, 20.0, 30.0, "And then everything changed.", [
        make_word("And", 20.0, 20.3),
        make_word("then", 20.5, 20.8),
        make_word("everything", 21.0, 21.6),
        make_word("changed.", 21.8, 22.5),
    ]),
]


class TestSnapToWordBoundary:
    def test_snaps_to_nearest_word_start(self):
        # t=8.1 should snap to word start at 8.0
        snapped = snap_to_word_boundary(8.1, SEGMENTS, direction="after", tolerance=3.0)
        assert snapped == 8.0

    def test_snaps_to_nearest_word_end(self):
        # t=2.6 should snap to word end at 2.5
        snapped = snap_to_word_boundary(2.6, SEGMENTS, direction="before", tolerance=3.0)
        assert abs(snapped - 2.5) < 0.1

    def test_returns_original_if_no_word_in_tolerance(self):
        snapped = snap_to_word_boundary(100.0, SEGMENTS, direction="nearest", tolerance=1.0)
        assert snapped == 100.0

    def test_empty_segments_returns_original(self):
        snapped = snap_to_word_boundary(5.0, [], direction="nearest")
        assert snapped == 5.0


class TestFindSentenceEnd:
    def test_finds_period_ending(self):
        # Segment ending at 5.0 ends with "."
        t = find_sentence_end(5.5, SEGMENTS, tolerance=5.0)
        assert abs(t - 5.0) < 0.1

    def test_finds_exclamation_ending(self):
        # Segment ending at 15.0 ends with "!"
        t = find_sentence_end(14.5, SEGMENTS, tolerance=5.0)
        assert abs(t - 15.0) < 0.1

    def test_returns_original_if_no_sentence_end_in_range(self):
        t = find_sentence_end(50.0, SEGMENTS, tolerance=1.0)
        assert t == 50.0


class TestRefineBoundaries:
    def test_boundaries_are_within_duration(self):
        start, end = refine_boundaries(
            start=0.5, end=25.0, segments=SEGMENTS,
            total_duration=120.0, min_duration=20.0, max_duration=120.0,
        )
        assert start >= 0.0
        assert end <= 120.0

    def test_min_duration_enforced(self):
        start, end = refine_boundaries(
            start=0.0, end=10.0, segments=SEGMENTS,
            total_duration=120.0, min_duration=20.0, max_duration=120.0,
        )
        assert (end - start) >= 20.0

    def test_max_duration_enforced(self):
        start, end = refine_boundaries(
            start=0.0, end=200.0, segments=SEGMENTS,
            total_duration=300.0, min_duration=20.0, max_duration=120.0,
        )
        assert (end - start) <= 120.0

    def test_returns_floats(self):
        start, end = refine_boundaries(10.0, 70.0, SEGMENTS, 300.0)
        assert isinstance(start, float)
        assert isinstance(end, float)

