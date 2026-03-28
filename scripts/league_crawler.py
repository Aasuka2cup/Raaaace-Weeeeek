from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_LEAGUE_URL = "https://fantasy.formula1.com/en/leagues/leaderboard/public/871710"
REPO_ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = REPO_ROOT / "scripts" / "fantasy_scraper_league.js"
PLAYWRIGHT_PACKAGE = REPO_ROOT / "scripts" / "node_modules" / "playwright"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch the F1 Fantasy league crawler via the existing Playwright script."
    )
    parser.add_argument(
        "--league-url",
        default=DEFAULT_LEAGUE_URL,
        help="F1 Fantasy league leaderboard URL.",
    )
    parser.add_argument(
        "--race",
        "--view",
        dest="race",
        default=None,
        help='Optional dropdown selection, for example "Overall" or "Chinese Grand Prix".',
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON output path.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory for generated JSON/debug files.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Playwright without opening a browser window.",
    )
    parser.add_argument(
        "--browser",
        choices=("chrome", "chromium"),
        default="chrome",
        help="Browser engine to use. Default is chrome.",
    )
    parser.add_argument(
        "--cdp-url",
        default=None,
        help="Attach to an already running local Chrome started with remote debugging, for example http://127.0.0.1:9222.",
    )
    parser.add_argument(
        "--no-profile",
        action="store_true",
        help="Do not reuse the saved Playwright browser profile.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save debug HTML when the crawler cannot find leaderboard rows.",
    )
    return parser.parse_args()


def build_command(args: argparse.Namespace) -> list[str]:
    command = ["node", str(NODE_SCRIPT), "--league-url", args.league_url, "--browser", args.browser]

    if args.race:
        command.extend(["--race", args.race])
    if args.output:
        command.extend(["--output", args.output])
    if args.output_dir:
        command.extend(["--output-dir", args.output_dir])
    if args.cdp_url:
        command.extend(["--cdp-url", args.cdp_url])
    if args.headless:
        command.append("--headless")
    if args.no_profile:
        command.append("--no-profile")
    if args.debug:
        command.append("--debug")

    return command


def ensure_runtime() -> None:
    if not NODE_SCRIPT.exists():
        raise SystemExit(f"Missing crawler script: {NODE_SCRIPT}")

    if shutil.which("node") is None:
        raise SystemExit(
            "Node.js is not installed or not on PATH. Install Node.js first, then rerun this script."
        )

    if not PLAYWRIGHT_PACKAGE.exists():
        raise SystemExit(
            "Playwright is not available under scripts/node_modules.\n"
            "Try:\n"
            "  cd scripts\n"
            "  npm install\n"
            "  npx playwright install chromium"
        )


def main() -> int:
    args = parse_args()
    ensure_runtime()

    command = build_command(args)

    print("Launching F1 Fantasy league crawler...")
    print(f"League URL: {args.league_url}")
    if args.race:
        print(f"Race filter: {args.race}")
    else:
        print("Race filter: current page selection")
    if args.cdp_url:
        print(f"Connected browser: {args.cdp_url}")
    print("")
    if args.cdp_url:
        print("Make sure your normal Chrome is already logged in and was started with")
        print("remote debugging enabled before running this command.")
    else:
        print("If the site redirects you to login, sign in in the Playwright browser window")
        print("and then press Enter in the terminal when the Node crawler prompts you.")
    print("")

    completed = subprocess.run(command, cwd=REPO_ROOT)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
