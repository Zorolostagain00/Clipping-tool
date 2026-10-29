"""
Tests for HighlightScorer.
"""

import pytest
from engine.highlight_scorer import score_candidate, CandidateScore


# Mock segments for context (word timestamps not needed for scorer)
MOCK_SEGMENTS = []


class TestHighlightScorer:
    def test_returns_candidate_score(self):
        text = "This is an absolutely insane play! No way that happened."
        result = score_candidate(text, 0.0, 60.0, MOCK_SEGMENTS, 600.0)
        assert isinstance(result, CandidateScore)
        assert 0.0 <= result.total <= 1.0

    def test_high_keyword_density_scores_higher(self):
        rich = "Wait what?! That's insane! The biggest comeback ever! Oh my god bro!"
        plain = "The weather today is partly cloudy with a mild breeze."
        rich_score = score_candidate(rich, 0.0, 60.0, MOCK_SEGMENTS, 600.0)
        plain_score = score_candidate(plain, 0.0, 60.0, MOCK_SEGMENTS, 600.0)
        assert rich_score.total > plain_score.total

    def test_breakdown_contains_all_signals(self):
        text = "This is a great moment. Check this out!"
        result = score_candidate(text, 0.0, 45.0, MOCK_SEGMENTS, 300.0)
        expected_keys = {"keyword", "structural", "duration", "speech_density", "completeness"}
        assert expected_keys.issubset(result.breakdown.keys())

    def test_short_clip_penalised(self):
        text = "Quick tip."
        short = score_candidate(text, 0.0, 5.0, MOCK_SEGMENTS, 600.0,
                                min_dur=20.0, max_dur=120.0)
        normal = score_candidate("This is a full segment with content and detail. " * 5,
                                 0.0, 60.0, MOCK_SEGMENTS, 600.0)
        # Duration score component should be lower for short clip
        assert short.breakdown["duration"] < normal.breakdown["duration"]

    def test_ideal_duration_scores_well(self):
        text = "Great moment here. Something exciting happened! Watch this."
        result = score_candidate(text, 0.0, 60.0, MOCK_SEGMENTS, 600.0)
        assert result.breakdown["duration"] == 1.0  # 60s is in ideal range

    def test_empty_text_returns_low_score(self):
        result = score_candidate("", 0.0, 60.0, MOCK_SEGMENTS, 600.0)
        assert result.total < 0.3

    def test_score_is_deterministic(self):
        text = "This is the best moment ever! No way this happened!"
        r1 = score_candidate(text, 10.0, 70.0, MOCK_SEGMENTS, 600.0)
        r2 = score_candidate(text, 10.0, 70.0, MOCK_SEGMENTS, 600.0)
        assert r1.total == r2.total

    def test_matched_keywords_populated(self):
        text = "Insane clutch play! The biggest win ever!"
        result = score_candidate(text, 0.0, 60.0, MOCK_SEGMENTS, 600.0)
        assert len(result.matched_keywords) > 0

    def test_completeness_warning_for_mid_sentence_end(self):
        text = "This is really exciting and we can see that the"  # ends mid-sentence
        result = score_candidate(text, 0.0, 60.0, MOCK_SEGMENTS, 600.0)
        assert any("mid-sentence" in w.lower() for w in result.warnings)

