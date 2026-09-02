from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "asl_signs.json"
TOKEN_RE = re.compile(r"[a-z0-9']+")


@dataclass(frozen=True)
class MatchResult:
    word: str
    sense: str
    video_key: str
    score: int
    matched_tags: tuple[str, ...]
    used_default: bool


def normalize_text(text: str) -> str:
    """Lowercase text and collapse punctuation/whitespace for simple matching."""
    tokens = TOKEN_RE.findall(text.lower())
    return " ".join(tokens)


def load_signs(path: Path = DATA_PATH) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("ASL sign data must be a JSON list.")

    return data


def get_candidates(signs: Iterable[dict], word: str) -> list[dict]:
    target = word.strip().lower()
    return [sign for sign in signs if str(sign.get("word", "")).lower() == target]


def _tag_score(normalized_story: str, tag: str) -> int:
    """Score one tag against the story.

    Multi-word tags receive a larger weight because they are more specific.
    Single-word tags are matched as normalized tokens.
    """
    normalized_tag = normalize_text(tag)
    if not normalized_tag:
        return 0

    if " " in normalized_tag:
        return 4 if normalized_tag in normalized_story else 0

    story_tokens = set(normalized_story.split())
    return 3 if normalized_tag in story_tokens else 0


def score_candidate(story: str, candidate: dict) -> tuple[int, tuple[str, ...]]:
    normalized_story = normalize_text(story)
    matched_tags: list[str] = []
    score = 0

    for tag in candidate.get("tags", []):
        tag_points = _tag_score(normalized_story, str(tag))
        if tag_points:
            score += tag_points
            matched_tags.append(str(tag))

    # A sense label appearing directly in the story is useful supporting evidence.
    sense_text = normalize_text(str(candidate.get("sense", ""))).replace("_", " ")
    if sense_text and sense_text in normalized_story:
        score += 2

    return score, tuple(matched_tags)


def choose_sign(story: str, target_word: str, signs: Iterable[dict]) -> MatchResult:
    candidates = get_candidates(signs, target_word)
    if not candidates:
        raise LookupError(f"No ASL sign candidates found for word: {target_word}")

    scored: list[tuple[int, tuple[str, ...], dict]] = []
    for candidate in candidates:
        score, matched_tags = score_candidate(story, candidate)
        scored.append((score, matched_tags, candidate))

    best_score = max(score for score, _, _ in scored)

    if best_score > 0:
        # Preserve source-data order as a deterministic tie breaker.
        score, matched_tags, winner = next(item for item in scored if item[0] == best_score)
        return MatchResult(
            word=str(winner["word"]),
            sense=str(winner["sense"]),
            video_key=str(winner["video_key"]),
            score=score,
            matched_tags=matched_tags,
            used_default=False,
        )

    default_candidate = next((candidate for candidate in candidates if candidate.get("default")), candidates[0])
    return MatchResult(
        word=str(default_candidate["word"]),
        sense=str(default_candidate["sense"]),
        video_key=str(default_candidate["video_key"]),
        score=0,
        matched_tags=(),
        used_default=True,
    )


def match_story(story: str, target_word: str, path: Path = DATA_PATH) -> MatchResult:
    return choose_sign(story, target_word, load_signs(path))


def demo() -> None:
    examples = [
        ("I listen to music. My favorite genre is rock.", "rock"),
        ("We found a rock near the mountain trail.", "rock"),
        ("He swung the bat and hit the baseball.", "bat"),
        ("We sat on the bank beside the river and watched the water.", "bank"),
    ]

    print("PopSign contextual ASL matching demo\n")

    for story, target_word in examples:
        result = match_story(story, target_word)
        print(f"Story: {story}")
        print(f"Target word: {target_word}")
        print(f"Selected sense: {result.sense}")
        print(f"Selected video: {result.video_key}")
        print(f"Matched tags: {', '.join(result.matched_tags) if result.matched_tags else 'none'}")
        print(f"Score: {result.score}")
        print(f"Used default: {result.used_default}")
        print("-" * 60)


if __name__ == "__main__":
    demo()
