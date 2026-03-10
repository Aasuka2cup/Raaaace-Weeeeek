#!/usr/bin/env python3
"""
F1 Fantasy Strategist - Calculate best possible team for a race.

Uses data from F1 API (f1api.dev) - same source as https://f1fantasytools.com/statistics
Prices from data/fallback_prices.json (update from f1fantasytools.com)

Usage:
    python main.py                    # Analyze last race
    python main.py --round r1         # Round 1 (Australia)
    python main.py --round aus        # Same, by venue
    python main.py --round "r1 aus"   # Round 1
    python main.py --year 2026 --round 1
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.data_fetcher import (
    fetch_f1api_qualy,
    fetch_f1api_last_qualy,
    fetch_f1api_last_race,
    fetch_f1api_race,
    fetch_f1api_sprint_race,
    load_fallback_prices,
    parse_f1api_qualy_results,
    parse_f1api_race_results,
    resolve_round,
)
from src.fantasy_data import (
    get_constructor_points_from_fantasy_data,
    get_driver_points_from_fantasy_data,
)
from src.optimizer import Constructor, Driver, find_optimal_team
from src.race_analyzer import (
    compute_constructor_points,
    compute_driver_points_from_results,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def map_driver_to_fantasy(driver_num: int, driver_info: dict, fallback: dict):
    """Map driver number to fantasy driver data from fallback (by name match)."""
    info = driver_info.get(driver_num, {})
    name = info.get("name", "")
    if not name:
        return None
    last_name = name.split()[-1] if name else ""
    for d in fallback.get("drivers", []):
        if last_name in d["name"] or d["name"] in name:
            return d
    return None


def main():
    parser = argparse.ArgumentParser(description="F1 Fantasy - Best team for a race")
    parser.add_argument("--year", type=int, default=2026, help="F1 season year")
    parser.add_argument(
        "--round", "-r",
        dest="round_input",
        metavar="ROUND",
        help="Round to analyze: number (1), r1, venue (aus, bahrain, monaco), or 'r1 aus'",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("F1 Fantasy Strategist")
    logger.info("Data source: f1api.dev (f1fantasytools.com)")
    logger.info("=" * 60)

    # Resolve round if specified
    round_num = None
    if args.round_input:
        round_num = resolve_round(args.round_input)
        if round_num is None:
            logger.error("Unknown round: %r. Use 1, r1, aus, bahrain, etc.", args.round_input)
            return 1

    # 1. Fetch race from F1 API
    season = args.year
    if round_num is not None:
        logger.info("\nFetching Round %d results...", round_num)
        race_data = fetch_f1api_race(season, round_num)
    else:
        logger.info("\nFetching last race results...")
        race_data = fetch_f1api_last_race()

    if not race_data:
        logger.error("Could not fetch race results. Check network.")
        return 1

    races = race_data.get("races", {})
    season = race_data.get("season", season)
    round_num = round_num or int(races.get("round", 1))
    circuit = races.get("circuit", {}).get("circuitName", "Unknown")
    logger.info("%s (Round %d)", circuit, round_num)

    # 2. Parse race results
    race_positions, race_grid, driver_info, fastest_lap_driver = parse_f1api_race_results(
        race_data
    )
    logger.info("  Race: %d drivers", len(race_positions))

    # 3. Fetch qualifying
    qual_positions = None
    qual_driver_info = {}
    if round_num is not None:
        qual_data = fetch_f1api_qualy(season, round_num)
    else:
        qual_data = fetch_f1api_last_qualy()
    if qual_data:
        qual_positions, qual_driver_info = parse_f1api_qualy_results(qual_data)
        driver_info.update(qual_driver_info)
        logger.info("  Qualifying: %d drivers", len(qual_positions))

    # 4. Check for sprint (404 = no sprint that round)
    sprint_positions = None
    sprint_grid = None
    sprint_data = fetch_f1api_sprint_race(season, round_num)
    if sprint_data:
        races_obj = sprint_data.get("races", {})
        sprint_results = races_obj.get("sprintResults") or races_obj.get("results", [])
        if sprint_results:
            # Parse sprint - format similar to race
            sprint_positions = {}
            for r in sprint_results:
                driver = r.get("driver", {})
                num = driver.get("number")
                if num is None:
                    continue
                pos_str = r.get("position")
                if pos_str in ("NC", "-", None):
                    sprint_positions[num] = 99
                else:
                    try:
                        sprint_positions[num] = int(pos_str)
                    except (ValueError, TypeError):
                        sprint_positions[num] = 99
            sprint_grid = sprint_positions  # Sprint grid from qualy
            logger.info("  Sprint: %d drivers", len(sprint_positions))

    # For sprint weekends, race grid = sprint result; else grid = qualy
    if sprint_positions:
        race_grid_from = sprint_positions
    else:
        race_grid_from = qual_positions if qual_positions else race_grid

    # 5. Compute fantasy points (use f1fantasytools.com data when available)
    computed_driver_points = compute_driver_points_from_results(
        qual_positions=qual_positions,
        sprint_positions=sprint_positions,
        race_positions=race_positions,
        race_grid=race_grid_from or race_grid,
        sprint_grid=sprint_grid,
        fastest_lap_driver=fastest_lap_driver,
        dotd_driver=None,
    )

    # Build driver -> team mapping from race results
    driver_to_team: dict[int, str] = {}
    for num, info in driver_info.items():
        team_id = info.get("team_id", "unknown")
        driver_to_team[num] = team_id

    # Prefer official fantasy points from f1fantasytools.com (via fantasy-data)
    fantasy_driver_pts = (
        get_driver_points_from_fantasy_data(driver_info, round_num)
        if round_num else None
    )
    if fantasy_driver_pts:
        driver_points = {
            num: fantasy_driver_pts.get(num, computed_driver_points[num])
            for num in computed_driver_points
        }
        logger.info("  Using fantasy points from f1fantasytools.com (fantasy-data)")
    else:
        driver_points = computed_driver_points
        logger.info("  Using computed fantasy points (fantasy-data not available for this round)")

    # Constructor points: prefer fantasy-data, else sum of driver points
    computed_constructor_points = compute_constructor_points(
        computed_driver_points, driver_to_team
    )
    fantasy_const_pts = (
        get_constructor_points_from_fantasy_data(
            set(driver_to_team.values()), round_num
        )
        if round_num else None
    )
    if fantasy_const_pts:
        constructor_points = {
            tid: fantasy_const_pts.get(tid, computed_constructor_points.get(tid, 0))
            for tid in set(driver_to_team.values()) | set(computed_constructor_points)
        }
    else:
        constructor_points = computed_constructor_points

    # 6. Load prices (fallback only - f1api.dev has no fantasy prices)
    fallback = load_fallback_prices()
    if not fallback:
        logger.error("No price data. Add data/fallback_prices.json (update from f1fantasytools.com)")
        return 1

    drivers_for_optimizer: list[Driver] = []
    for driver_num, pts in driver_points.items():
        fd = map_driver_to_fantasy(driver_num, driver_info, fallback)
        if fd:
            drivers_for_optimizer.append(
                Driver(fd["id"], fd["name"], fd["team_id"], fd["price"], pts)
            )
        else:
            info = driver_info.get(driver_num, {})
            name = info.get("name", f"Driver {driver_num}")
            team_id = driver_to_team.get(driver_num, "unknown")
            drivers_for_optimizer.append(
                Driver(f"d{driver_num}", name, team_id, 12.0, pts)
            )

    # Add constructors from fallback
    team_abbrev = {
        "red_bull": "red_bull",
        "mercedes": "mercedes",
        "ferrari": "ferrari",
        "mclaren": "mclaren",
        "williams": "williams",
        "aston_martin": "aston_martin",
        "alpine": "alpine",
        "rb": "rb",
        "haas": "haas",
        "audi": "audi",
        "cadillac": "cadillac",
    }
    constructors_for_optimizer: list[Constructor] = []
    for c in fallback.get("constructors", []):
        cid = c["id"]
        pts = constructor_points.get(cid) or constructor_points.get(
            team_abbrev.get(cid, cid)
        )
        constructors_for_optimizer.append(
            Constructor(c["id"], c["name"], c["price"], pts or 0)
        )

    # Deduplicate drivers by name
    seen = set()
    unique_drivers = []
    for d in drivers_for_optimizer:
        if d.name not in seen:
            seen.add(d.name)
            unique_drivers.append(d)

    if len(unique_drivers) < 5 or len(constructors_for_optimizer) < 2:
        logger.error(
            "Insufficient data: %d drivers, %d constructors",
            len(unique_drivers),
            len(constructors_for_optimizer),
        )
        return 1

    # 7. Run optimizer
    logger.info("\nFinding optimal team (5 drivers + 2 constructors, $100M cap)...")
    best_drivers, best_constructors, total_points = find_optimal_team(
        unique_drivers, constructors_for_optimizer
    )

    # 8. Output
    logger.info("\n" + "=" * 60)
    logger.info("OPTIMAL TEAM FOR %s", circuit.upper())
    logger.info("=" * 60)
    logger.info("\nDrivers:")
    driver_cost = 0
    for d in best_drivers:
        logger.info("  %s - $%.1fM - %.0f pts", d.name, d.price, d.points)
        driver_cost += d.price
    logger.info("\nConstructors:")
    const_cost = 0
    for c in best_constructors:
        logger.info("  %s - $%.1fM - %.0f pts", c.name, c.price, c.points)
        const_cost += c.price
    logger.info("\nTotal cost: $%.1fM", driver_cost + const_cost)
    logger.info("Total points: %.0f", total_points)
    logger.info("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
