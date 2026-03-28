#!/usr/bin/env python3
"""
Update data/fallback_prices.json from data/fantasy-data/latest.

Reads driver_data/*.json and constructor_data/*.json, extracts prices (value field),
and writes an updated fallback_prices.json with correct prices and team mappings.
"""

import argparse
import json
import sys
from pathlib import Path

# Driver team name (from fantasy-data) -> team_id
DRIVER_TEAM_TO_ID = {
    "red bull racing": "red_bull",
    "mercedes": "mercedes",
    "ferrari": "ferrari",
    "mclaren": "mclaren",
    "williams": "williams",
    "aston martin": "aston_martin",
    "alpine": "alpine",
    "racing bulls": "rb",
    "haas f1 team": "haas",
    "audi": "audi",
    "cadillac": "cadillac",
}

# Constructor abbreviation -> team_id (matches fantasy-data file names)
CONSTRUCTOR_ABBREV_TO_ID = {
    "RBR": "red_bull",
    "MER": "mercedes",
    "FER": "ferrari",
    "MCL": "mclaren",
    "WIL": "williams",
    "AMR": "aston_martin",
    "ALP": "alpine",
    "RB": "rb",
    "HAA": "haas",
    "HAS": "haas",  # scraper may use either
    "AUD": "audi",
    "CAD": "cadillac",
}

# team_id -> display name for constructors
TEAM_ID_TO_DISPLAY_NAME = {
    "red_bull": "Red Bull Racing",
    "mercedes": "Mercedes",
    "ferrari": "Ferrari",
    "mclaren": "McLaren",
    "williams": "Williams",
    "aston_martin": "Aston Martin",
    "alpine": "Alpine",
    "rb": "Racing Bulls",
    "haas": "Haas",
    "audi": "Audi",
    "cadillac": "Cadillac",
}

# Driver abbreviation -> full name (for consistent output)
ABBREV_TO_FULL_NAME = {
    "VER": "Max Verstappen",
    "RUS": "George Russell",
    "ANT": "Kimi Antonelli",
    "LEC": "Charles Leclerc",
    "HAM": "Lewis Hamilton",
    "NOR": "Lando Norris",
    "PIA": "Oscar Piastri",
    "SAI": "Carlos Sainz",
    "PER": "Sergio Perez",
    "ALO": "Fernando Alonso",
    "GAS": "Pierre Gasly",
    "ALB": "Alexander Albon",
    "STR": "Lance Stroll",
    "BEA": "Oliver Bearman",
    "LIN": "Arvid Lindblad",
    "BOR": "Gabriel Bortoleto",
    "LAW": "Liam Lawson",
    "OCO": "Esteban Ocon",
    "COL": "Franco Colapinto",
    "BOT": "Valtteri Bottas",
    "HAD": "Isack Hadjar",
    "HUL": "Nico Hulkenberg",
}


def _parse_value(value_str: str) -> float:
    """Parse '28M' or '27.1M' or '28.5M' to float."""
    if not value_str:
        return 0.0
    s = str(value_str).strip().upper().rstrip("M")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _driver_team_to_id(team: str) -> str:
    """Map driver team name to team_id."""
    if not team:
        return "unknown"
    key = team.strip().lower()
    return DRIVER_TEAM_TO_ID.get(key, key.replace(" ", "_").lower())


def load_drivers(data_dir: Path) -> list[dict]:
    """Load driver data and return list of {id, name, team_id, price}."""
    driver_dir = data_dir / "driver_data"
    if not driver_dir.is_dir():
        return []

    drivers = []
    for path in sorted(driver_dir.glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        abbrev = data.get("abbreviation", path.stem)
        value = data.get("value", "0M")
        team = data.get("team", "")
        team_id = _driver_team_to_id(team)
        name = ABBREV_TO_FULL_NAME.get(abbrev)
        if not name:
            # Fallback: title-case displayName with space before capitals
            dn = data.get("displayName", abbrev)
            name = dn.replace("_", " ").title() if dn else abbrev

        drivers.append({
            "id": "",  # assigned after sort
            "name": name,
            "team_id": team_id,
            "price": _parse_value(value),
        })

    # Sort by price descending (most valuable first)
    drivers.sort(key=lambda d: d["price"], reverse=True)
    for i, d in enumerate(drivers, start=1):
        d["id"] = str(i)

    return drivers


def load_constructors(data_dir: Path) -> list[dict]:
    """Load constructor data and return list of {id, name, price}."""
    const_dir = data_dir / "constructor_data"
    if not const_dir.is_dir():
        return []

    constructors = []
    for path in sorted(const_dir.glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        abbrev = data.get("abbreviation", path.stem)
        team_id = CONSTRUCTOR_ABBREV_TO_ID.get(abbrev)
        if not team_id:
            team_id = abbrev.lower()

        value = data.get("value", "0M")
        display_name = TEAM_ID_TO_DISPLAY_NAME.get(
            team_id, data.get("displayName", team_id).replace("_", " ").title()
        )

        constructors.append({
            "id": team_id,
            "name": display_name,
            "price": _parse_value(value),
        })

    return constructors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update fallback_prices.json from data/fantasy-data/latest"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "fantasy-data" / "latest",
        help="Path to fantasy-data directory (e.g. .../latest or .../2026)",
    )
    parser.add_argument(
        "--season",
        type=int,
        metavar="YEAR",
        help="Use {data-dir parent}/{year} instead of --data-dir (e.g. --season 2026)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "fallback_prices.json",
        help="Output path for fallback_prices.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print result without writing",
    )
    args = parser.parse_args()

    data_dir = args.data_dir
    if args.season:
        data_dir = args.data_dir.parent / str(args.season)
        if not data_dir.is_dir():
            print(f"Error: season dir not found: {data_dir}", file=sys.stderr)
            return 1

    if not data_dir.is_dir():
        print(f"Error: data dir not found: {data_dir}", file=sys.stderr)
        return 1

    drivers = load_drivers(data_dir)
    constructors = load_constructors(data_dir)

    if not drivers:
        print("Warning: no driver data found", file=sys.stderr)
    if not constructors:
        print("Warning: no constructor data found", file=sys.stderr)

    result = {
        "_comment": "Updated from data/fantasy-data/latest (f1fantasytools.com)",
        "drivers": drivers,
        "constructors": constructors,
    }

    if args.dry_run:
        print(json.dumps(result, indent=2))
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")

    print(f"Updated {args.output} with {len(drivers)} drivers, {len(constructors)} constructors (from {data_dir})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
