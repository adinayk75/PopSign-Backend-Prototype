from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StoryPage:
    sentence: str
    target_word: str
    grammar: str
    illustration: str


@dataclass(frozen=True)
class DemoStory:
    story_id: str
    title: str
    author: str
    difficulty: str
    prompt: str
    cover: str
    pages: tuple[StoryPage, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def generate_demo_story(prompt: str, difficulty: str = "Level A") -> DemoStory:
    """Return a deterministic story that exercises all six pilot meanings.

    The generated pages are deliberately stable so tomorrow's demonstration is
    repeatable. The existing PopSign LLM generator can replace this function
    later without changing the frontend or matcher contracts.
    """
    return DemoStory(
        story_id="maya-makes-dinner",
        title="Maya Makes Dinner",
        author="PopSign Prototype",
        difficulty=difficulty,
        prompt=prompt.strip(),
        cover="/assets/story-cover.svg",
        pages=(
            StoryPage(
                sentence="Maya can cook dinner.",
                target_word="can",
                grammar="Subject + Modal + Verb + Object",
                illustration="/assets/cooking.svg",
            ),
            StoryPage(
                sentence="She opened a can of soup.",
                target_word="can",
                grammar="Subject + Verb + Object",
                illustration="/assets/soup-can.svg",
            ),
            StoryPage(
                sentence="The story is about her family dinner.",
                target_word="about",
                grammar="Subject + Verb + Topic",
                illustration="/assets/story-book.svg",
            ),
            StoryPage(
                sentence="About ten friends came to dinner.",
                target_word="about",
                grammar="Approximate Quantity + Subject + Verb",
                illustration="/assets/friends.svg",
            ),
            StoryPage(
                sentence="Maya and her family love each other.",
                target_word="love",
                grammar="Subject + Verb + Person",
                illustration="/assets/family.svg",
            ),
            StoryPage(
                sentence="They love the delicious soup.",
                target_word="love",
                grammar="Subject + Verb + Thing",
                illustration="/assets/soup-can.svg",
            ),
        ),
    )
