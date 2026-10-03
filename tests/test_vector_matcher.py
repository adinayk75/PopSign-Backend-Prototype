import json
from pathlib import Path

import pytest

from src.embeddings import HashingEmbeddingProvider
from src.story_demo import generate_demo_story
from src.vector_matcher import LocalEvidenceSource, VectorMatcher


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def matcher():
    return VectorMatcher(HashingEmbeddingProvider(), LocalEvidenceSource())


@pytest.mark.parametrize(
    ("phrase", "word", "video_key"),
    [
        ("Maya can cook dinner.", "can", "demo/can/ability.mp4"),
        ("She opened a can of soup.", "can", "demo/can/container.mp4"),
        ("About ten friends came to dinner.", "about", "demo/about/approximate.mp4"),
        ("The story is about Maya's family.", "about", "demo/about/topic.mp4"),
        ("Maya loves her family.", "love", "demo/love/person.mp4"),
        ("They love pizza and soup.", "love", "demo/love/thing.mp4"),
    ],
)
def test_demo_meanings_are_selected(matcher, phrase, word, video_key):
    result = matcher.match(phrase, word)

    assert result.accepted
    assert result.selected_video_key == video_key
    assert result.margin >= result.margin_threshold


@pytest.mark.parametrize(
    ("phrase", "word"),
    [
        ("The word can appears in this sentence.", "can"),
        ("This sentence is about.", "about"),
        ("I simply love.", "love"),
    ],
)
def test_unclear_context_is_not_silently_accepted(matcher, phrase, word):
    result = matcher.match(phrase, word)

    assert not result.accepted
    assert result.decision == "needs_review"
    assert result.selected_video_key is None
    assert result.recommended_video_key is not None


def test_all_evaluation_cases_match_expected_decision(matcher):
    cases = json.loads((ROOT / "data" / "evaluation_cases.json").read_text())
    predictions = []
    for case in cases:
        result = matcher.match(case["phrase"], case["word"])
        predictions.append(result.selected_video_key)

    assert predictions == [case["expected_video_key"] for case in cases]


def test_every_demo_story_page_selects_the_expected_video(matcher):
    story = generate_demo_story("A child cooks dinner.")
    expected = [
        "demo/can/ability.mp4",
        "demo/can/container.mp4",
        "demo/about/topic.mp4",
        "demo/about/approximate.mp4",
        "demo/love/person.mp4",
        "demo/love/thing.mp4",
    ]

    selected = [
        matcher.match(page.sentence, page.target_word).selected_video_key
        for page in story.pages
    ]

    assert selected == expected
