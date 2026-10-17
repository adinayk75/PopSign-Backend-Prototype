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
from src.context_bank_embeddings import build_embedding_plan
from src.embedding_export import export_embedding_csv_bundle
from src.embeddings import build_embedding_provider


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate resumable dashboard-import CSV batches containing real "
            "semantic embeddings for the complete PopSign context bank."
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
        choices=("mpnet", "embeddinggemma"),
        default="mpnet",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--restart", action="store_true")
    return parser.parse_args()


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()
    if args.workbook is None:
        raise SystemExit(
            "Provide --workbook or set POPSIGN_CONTEXT_BANK_PATH in the local .env file."
        )

    bank = load_context_bank(args.workbook, args.sheet)
    payload = build_import_payload(bank)
    audit = json.loads((ROOT / "data" / "context_bank_audit.json").read_text())
    reconcile_with_audit(payload, audit)
    provider = build_embedding_provider(args.provider)
    plan = build_embedding_plan(payload, provider)
    output_dir = args.output_dir or (
        ROOT
        / ".popsign-state"
        / (
            f"embedding-export-{payload.workbook_sha256[:12]}-"
            f"{plan.model_row['id']}"
        )
    )
    manifest_path = export_embedding_csv_bundle(
        payload,
        plan,
        provider,
        output_dir,
        batch_size=args.batch_size,
        restart=args.restart,
    )
    print(f"Embedding export complete: {manifest_path}")


if __name__ == "__main__":
    main()
