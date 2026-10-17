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
    reconcile_with_audit,
)
from src.dashboard_import import export_dashboard_csv_bundle


DEFAULT_AUDIT_PATH = ROOT / "data" / "context_bank_audit.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export the complete private PopSign context bank as CSV files for "
            "the authenticated Supabase dashboard."
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
        "--output-dir",
        type=Path,
        help="Private output directory; defaults under .popsign-state/.",
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

    output_dir = args.output_dir or (
        ROOT
        / ".popsign-state"
        / f"dashboard-import-{payload.workbook_sha256[:16]}"
    )
    manifest_path = export_dashboard_csv_bundle(payload, output_dir)
    print(f"Prepared complete dashboard import: {manifest_path}")


if __name__ == "__main__":
    main()
