from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from league_data_contract import (
    DEFAULT_LEAGUE_RESULTS_DIR,
    build_export_payload,
    build_insights_payload,
    build_manifest,
    discover_league_result_files,
    read_json,
    utc_timestamp,
    validate_league_payload,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "build" / "league-site-data"
DEFAULT_MANIFEST_PATH = Path("manifests") / "league-index.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export crawler league JSON files into a stable, web-consumable data package."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_LEAGUE_RESULTS_DIR,
        help="Directory containing source league_*.json files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Destination directory for exported site data.",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Manifest path relative to the output directory.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow empty teams arrays in source files.",
    )
    parser.add_argument(
        "--source-repo",
        default=os.environ.get("GITHUB_REPOSITORY"),
        help="Optional source repository name to embed in exports.",
    )
    parser.add_argument(
        "--source-commit",
        default=os.environ.get("GITHUB_SHA"),
        help="Optional source commit SHA to embed in exports.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def main() -> int:
    args = parse_args()
    files = discover_league_result_files(args.source_dir)
    if not files:
        raise SystemExit(f"No league result files found under {args.source_dir}")

    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    generated_at = utc_timestamp()
    league_views: dict[str, list[dict[str, object]]] = {}
    exported_count = 0
    skipped_empty_files: list[str] = []

    for path in files:
        payload = read_json(path)
        teams = payload.get("teams")
        if (
            not args.allow_empty
            and isinstance(teams, list)
            and len(teams) == 0
        ):
            skipped_empty_files.append(path.name)
            continue

        metadata, errors = validate_league_payload(payload, path, allow_empty=args.allow_empty)
        if errors:
            joined = "\n".join(f"- {error}" for error in errors)
            raise SystemExit(f"Validation failed for {path.name}:\n{joined}")

        export_relative_path = Path("leagues") / f"league_{metadata['leagueId']}" / "views" / f"{metadata['viewKey']}.json"
        insight_relative_path = Path("leagues") / f"league_{metadata['leagueId']}" / "insights" / f"{metadata['viewKey']}.json"
        export_payload = build_export_payload(
            payload,
            metadata,
            exported_at=generated_at,
            source_repo=args.source_repo,
            source_commit=args.source_commit,
        )
        insight_payload = build_insights_payload(
            payload,
            metadata,
            exported_at=generated_at,
            view_file=export_relative_path.as_posix(),
            insight_file=insight_relative_path.as_posix(),
            source_repo=args.source_repo,
            source_commit=args.source_commit,
        )
        write_json(args.output_dir / export_relative_path, export_payload)
        write_json(args.output_dir / insight_relative_path, insight_payload)
        exported_count += 1

        league_views.setdefault(str(metadata["leagueId"]), []).append(
            {
                **metadata,
                "file": export_relative_path.as_posix(),
                "insightFile": insight_relative_path.as_posix(),
            }
        )

    manifest = build_manifest(
        league_views,
        generated_at=generated_at,
        source_repo=args.source_repo,
        source_commit=args.source_commit,
    )
    write_json(args.output_dir / args.manifest_path, manifest)

    print(f"Exported {exported_count} league file(s) to {args.output_dir}")
    if skipped_empty_files:
        print("Skipped empty league file(s):")
        for name in skipped_empty_files:
            print(f"- {name}")
    print(f"Manifest: {(args.output_dir / args.manifest_path).relative_to(args.output_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
