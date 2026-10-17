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

from src.context_bank import (
    build_import_payload,
    load_context_bank,
    public_summary,
    reconcile_with_audit,
)
from src.supabase_import import SupabaseContextBankImporter


DEFAULT_AUDIT_PATH = ROOT / "data" / "context_bank_audit.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and import the complete PopSign context bank into the "
            "production popsign_* Supabase tables."
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
        help="Path to the private context_bank.xlsx source file.",
    )
    parser.add_argument("--sheet", help="Worksheet name; defaults to the active sheet.")
    parser.add_argument(
        "--audit",
        type=Path,
        default=DEFAULT_AUDIT_PATH,
        help="Public Phase 1 audit used for exact reconciliation.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write to Supabase. Without this flag, the command is read-only.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("POPSIGN_IMPORT_BATCH_SIZE", "100")),
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help="Override the private local resume-checkpoint path.",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart this idempotent import from its first batch.",
    )
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
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    reconcile_with_audit(payload, audit)

    print(json.dumps(public_summary(payload), indent=2, sort_keys=True))
    if not args.apply:
        print(
            "Dry run complete. Every source row reconciled; Supabase was not contacted."
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
        / f"context-bank-{payload.workbook_sha256[:16]}.json"
    )
    importer = SupabaseContextBankImporter(
        create_client(url, secret_key),
        batch_size=args.batch_size,
    )
    result = importer.import_payload(
        payload,
        checkpoint_path,
        restart=args.restart,
    )
    action = "resumed" if result.resumed else "started"
    print(
        f"Import {action} and completed for {result.import_run_id}. "
        f"Checkpoint: {checkpoint_path}"
    )


if __name__ == "__main__":
    main()
