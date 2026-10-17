from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from src.context_bank import build_import_payload, load_context_bank, reconcile_with_audit
from src.context_bank_embeddings import (
    SupabaseEmbeddingImporter,
    build_embedding_plan,
    validate_embedding_plan,
)
from src.embeddings import build_embedding_provider


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate versioned target-word phrase embeddings for the complete "
            "PopSign context bank."
        )
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=(
            Path(os.environ["POPSIGN_CONTEXT_BANK_PATH"])
            if os.getenv("POPSIGN_CONTEXT_BANK_PATH")
            else None
        ),
    )
    parser.add_argument("--sheet")
    parser.add_argument(
        "--provider",
        choices=("hashing", "mpnet", "embeddinggemma"),
        default=os.getenv("POPSIGN_EMBEDDING_PROVIDER", "hashing"),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Upload embeddings to Supabase; default behavior is validation only.",
    )
    parser.add_argument(
        "--allow-demo-provider",
        action="store_true",
        help="Permit uploading hashing-demo vectors. Never use them as production evidence.",
    )
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--restart", action="store_true")
    return parser.parse_args()


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()
    if args.workbook is None:
        raise SystemExit(
            "Provide --workbook or set POPSIGN_CONTEXT_BANK_PATH in the local .env file."
        )
    if args.apply and args.provider == "hashing" and not args.allow_demo_provider:
        raise SystemExit(
            "Refusing to upload hashing-demo vectors. Use MPNet or EmbeddingGemma, "
            "or pass --allow-demo-provider only for an isolated non-production database."
        )
    if (
        args.apply
        and args.provider == "embeddinggemma"
        and not os.getenv("POPSIGN_EMBEDDING_MODEL_REVISION")
    ):
        raise SystemExit(
            "Set POPSIGN_EMBEDDING_MODEL_REVISION to an immutable Hugging Face "
            "commit SHA before uploading production embeddings."
        )

    bank = load_context_bank(args.workbook, args.sheet)
    payload = build_import_payload(bank)
    audit = json.loads((ROOT / "data" / "context_bank_audit.json").read_text())
    reconcile_with_audit(payload, audit)
    provider = build_embedding_provider(args.provider)
    plan = build_embedding_plan(payload, provider)

    print(
        f"Prepared {len(plan.word_phrases)} word-specific phrase embeddings for "
        f"{provider.model_name}@{provider.model_version}."
    )
    if not args.apply:
        validated = validate_embedding_plan(
            plan,
            provider,
            batch_size=args.batch_size,
        )
        print(
            f"Dry run complete; validated all {validated} embeddings and did not "
            "contact Supabase."
        )
        return

    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        raise SystemExit(
            "SUPABASE_URL and SUPABASE_SECRET_KEY are required with --apply."
        )

    from supabase import create_client

    checkpoint_path = args.checkpoint or (
        ROOT
        / ".popsign-state"
        / f"embeddings-{payload.workbook_sha256[:12]}-{plan.model_row['id']}.json"
    )
    importer = SupabaseEmbeddingImporter(
        create_client(url, secret_key),
        batch_size=args.batch_size,
    )
    result = importer.import_plan(
        payload,
        plan,
        provider,
        checkpoint_path,
        restart=args.restart,
    )
    action = "resumed" if result.resumed else "started"
    print(
        f"Embedding import {action} and completed: {result.total_embeddings} rows "
        f"for model {result.embedding_model_id}."
    )


if __name__ == "__main__":
    main()
