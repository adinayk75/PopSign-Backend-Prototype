from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "data" / "evaluation_cases.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.embeddings import HashingEmbeddingProvider
from src.vector_matcher import LocalEvidenceSource, VectorMatcher


@dataclass(frozen=True)
class Evaluation:
    accept_threshold: float
    margin_threshold: float
    correct: int
    accepted: int
    total: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def coverage(self) -> float:
        return self.accepted / self.total if self.total else 0.0


def load_cases(path: Path = CASES_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def score_cases() -> list[tuple[dict, dict]]:
    matcher = VectorMatcher(HashingEmbeddingProvider(), LocalEvidenceSource())
    return [(case, matcher.match(case["phrase"], case["word"]).to_dict()) for case in load_cases()]


def evaluate_grid() -> list[Evaluation]:
    scored = score_cases()
    results: list[Evaluation] = []
    for accept in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
        for margin in (0.00, 0.03, 0.05, 0.08, 0.10, 0.15):
            correct = 0
            accepted = 0
            for case, result in scored:
                decision = result["top_score"] >= accept and result["margin"] >= margin
                prediction = result["recommended_video_key"] if decision else None
                accepted += int(decision)
                correct += int(prediction == case.get("expected_video_key"))
            results.append(Evaluation(accept, margin, correct, accepted, len(scored)))
    return sorted(
        results,
        key=lambda item: (item.accuracy, item.coverage, item.margin_threshold),
        reverse=True,
    )


def main() -> None:
    print("Top provisional threshold combinations\n")
    print("accept  margin  accuracy  coverage")
    for result in evaluate_grid()[:10]:
        print(
            f"{result.accept_threshold:>6.2f}  "
            f"{result.margin_threshold:>6.2f}  "
            f"{result.accuracy:>8.1%}  "
            f"{result.coverage:>8.1%}"
        )
    print("\nThese values are demo-only until the ASL labels are human reviewed.")


if __name__ == "__main__":
    main()
