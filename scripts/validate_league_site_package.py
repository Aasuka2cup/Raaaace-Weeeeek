from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from league_data_contract import (
    DEFAULT_SITE_DATA_DIR,
    read_json,
    validate_export_payload,
    validate_insights_payload,
    validate_manifest_payload,
)


DEFAULT_MANIFEST_PATH = Path("manifests") / "league-index.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an exported league site data package."
    )
    parser.add_argument(
        "--site-data-dir",
        type=Path,
        default=DEFAULT_SITE_DATA_DIR,
        help="Directory containing the exported site data package.",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Manifest path relative to the site data directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = args.site_data_dir / args.manifest_path
    if not manifest_path.is_file():
        raise SystemExit(f"Manifest file not found: {manifest_path}")

    manifest = read_json(manifest_path)
    referenced_files, manifest_errors = validate_manifest_payload(manifest, args.site_data_dir)

    file_summaries: list[dict[str, object]] = []
    all_errors = list(manifest_errors)

    for artifact in referenced_files:
        artifact_path = artifact["file"]
        payload = read_json(artifact_path)
        if artifact["kind"] == "insight":
            metadata, errors = validate_insights_payload(payload, Path(artifact["relativeFile"]))
        else:
            metadata, errors = validate_export_payload(payload, Path(artifact["relativeFile"]))

        if payload.get("leagueId") != artifact["leagueId"]:
            errors.append(
                f"{artifact['relativeFile']}: leagueId does not match manifest entry ({artifact['leagueId']})"
            )
        if payload.get("viewKey") != artifact["viewKey"]:
            errors.append(
                f"{artifact['relativeFile']}: viewKey does not match manifest entry ({artifact['viewKey']})"
            )

        file_summaries.append(
            {
                "file": artifact["relativeFile"],
                "kind": artifact["kind"],
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
                    "siteDataDir": str(args.site_data_dir),
                    "manifest": args.manifest_path.as_posix(),
                    "checkedFiles": len(file_summaries),
                    "files": file_summaries,
                    "errors": all_errors,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"Checked site data package at {args.site_data_dir}")
        print(f"- Manifest: {args.manifest_path.as_posix()}")
        print(f"- Export files: {len(file_summaries)}")
        for summary in file_summaries:
            status = "OK" if not summary["errors"] else "ERROR"
            print(
                f"- {status}: {summary['file']} [{summary['kind']}] "
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
