from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "pilot_catalog.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from src.embeddings import EmbeddingProvider, build_embedding_provider


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def build_rows(catalog: dict, provider: EmbeddingProvider) -> dict[str, list[dict]]:
    words: dict[str, dict] = {}
    senses: list[dict] = []
    contexts: list[dict] = []
    embeddings: list[dict] = []

    for sense in catalog["senses"]:
        word = sense["word"].casefold().strip()
        words[word] = {
            "word": word,
            "display_word": sense["word"],
            "review_status": "pilot",
        }
        senses.append(
            {
                "video_key": sense["video_key"],
                "word": word,
                "sense_label": sense["sense_label"],
                "definition": sense["definition"],
                "is_default": bool(sense.get("is_default", False)),
                "review_status": sense["review_status"],
                "human_approved": bool(sense.get("human_approved", False)),
            }
        )

        for context in sense["contexts"]:
            text = context["text"].strip()
            contexts.append(
                {
                    "context_id": context["id"],
                    "video_key": sense["video_key"],
                    "context_text": text,
                    "source_type": context["source_type"],
                    "human_approved": bool(context.get("human_approved", False)),
                }
            )
            source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            embeddings.append(
                {
                    "context_id": context["id"],
                    "model_name": provider.model_name,
                    "model_version": provider.model_version,
                    "dimensions": provider.dimensions,
                    "source_hash": source_hash,
                    "embedding": provider.embed(text, word),
                }
            )

    return {
        "words": list(words.values()),
        "sign_senses": senses,
        "context_phrases": contexts,
        "phrase_embeddings": embeddings,
    }


def chunks(rows: list[dict], size: int = 10) -> Iterable[list[dict]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def seed(rows: dict[str, list[dict]]) -> None:
    from supabase import create_client

    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        raise RuntimeError(
            "Set SUPABASE_URL and SUPABASE_SECRET_KEY in .env before seeding."
        )

    client = create_client(url, secret_key)
    conflict_columns = {
        "words": "word",
        "sign_senses": "video_key",
        "context_phrases": "context_id",
        "phrase_embeddings": "context_id,model_name,model_version",
    }
    for table in ("words", "sign_senses", "context_phrases", "phrase_embeddings"):
        for batch in chunks(rows[table]):
            client.table(table).upsert(
                batch,
                on_conflict=conflict_columns[table],
            ).execute()
        print(f"Upserted {len(rows[table])} rows into {table}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed PopSign pilot vectors into Supabase.")
    parser.add_argument(
        "--provider",
        choices=("hashing", "embeddinggemma"),
        default=os.getenv("POPSIGN_EMBEDDING_PROVIDER", "hashing"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate every row without contacting Supabase.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()
    provider = build_embedding_provider(args.provider)
    rows = build_rows(load_catalog(), provider)
    print(
        f"Prepared {len(rows['sign_senses'])} senses, "
        f"{len(rows['context_phrases'])} phrases, and "
        f"{len(rows['phrase_embeddings'])} {provider.dimensions}-D embeddings "
        f"with {provider.model_name}@{provider.model_version}."
    )
    if args.dry_run:
        print("Dry run complete; Supabase was not contacted.")
        return
    seed(rows)


if __name__ == "__main__":
    main()
