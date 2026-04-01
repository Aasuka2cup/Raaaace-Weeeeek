from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from league_data_contract import DEFAULT_LEAGUE_RESULTS_DIR, discover_league_result_files, read_json, validate_league_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate generated league result JSON files."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_LEAGUE_RESULTS_DIR,
        help="Directory containing league_*.json files.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow empty teams arrays.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = discover_league_result_files(args.source_dir)
    summaries: list[dict[str, object]] = []
    all_errors: list[str] = []

    for path in files:
        payload = read_json(path)
        metadata, errors = validate_league_payload(payload, path, allow_empty=args.allow_empty)
        summaries.append(
            {
                "file": path.name,
                "leagueId": metadata["leagueId"],
                "viewKey": metadata["viewKey"],
                "viewLabel": metadata["viewLabel"],
                "teamCount": metadata["teamCount"],
                "errors": errors,
            }
        )
        all_errors.extend(errors)

    if args.json:
        print(
            json.dumps(
                {
                    "valid": not all_errors,
                    "checkedFiles": len(files),
                    "files": summaries,
                    "errors": all_errors,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"Checked {len(files)} league result file(s).")
        for summary in summaries:
            status = "OK" if not summary["errors"] else "ERROR"
            print(
                f"- {status}: {summary['file']} "
                f"({summary['viewLabel']}, {summary['teamCount']} teams)"
            )
        if all_errors:
            print("")
            print("Validation errors:")
            for error in all_errors:
                print(f"- {error}")

    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
