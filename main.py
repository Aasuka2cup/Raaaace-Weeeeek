#!/usr/bin/env python3
"""
F1 Fantasy Strategist - Calculate best possible team for a race.

Uses data from F1 API (f1api.dev) - same source as https://f1fantasytools.com/statistics
Prices from data/fallback_prices.json (update from f1fantasytools.com)

Usage:
    python main.py                    # Analyze last race
    python main.py --round r1         # Round 1 (Australia)
    python main.py --round monaco     # Monaco GP
    python main.py --year 2026 --round 1
    python main.py --round monaco --mode lastyear   # Use Monaco 2025 data
    python main.py --round monaco --mode lastrace   # Use previous round data
    python main.py --data-dir ./fantasy-data/latest # Use local scraper output (freshest data)

Modes:
    target   - Use data from the target round (default)
    lastyear - Use data from same round last season
    lastrace - Use data from most recent race this season
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
    fetch_openf1_overtakes,
    load_fallback_prices,
    parse_f1api_qualy_results,
    parse_f1api_race_results,
    resolve_round,
)

# Round number -> venue name for display when circuit not from API
ROUND_TO_VENUE = {
    1: "Australia", 2: "China", 3: "Japan", 4: "Bahrain", 5: "Saudi Arabia",
    6: "Miami", 7: "Imola", 8: "Monaco", 9: "Spain", 10: "Canada",
    11: "Austria", 12: "Britain", 13: "Hungary", 14: "Belgium", 15: "Netherlands",
    16: "Italy", 17: "Azerbaijan", 18: "Singapore", 19: "Austin", 20: "Mexico",
    21: "Brazil", 22: "Las Vegas", 23: "Qatar", 24: "Abu Dhabi",
}
from src.fantasy_data import (
    fetch_overtakes_from_fantasy_data,
    get_constructor_points_from_fantasy_data,
    get_driver_breakdown_from_fantasy_data,
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


def _last_name(name: str) -> str:
    """Extract last name for matching."""
    return (name or "").strip().split()[-1].lower() if name else ""


def _build_name_to_points(driver_points: dict, driver_info: dict) -> dict[str, float]:
    """Build last_name -> points for mapping to fallback drivers."""
    result: dict[str, float] = {}
    for driver_num, pts in driver_points.items():
        name = driver_info.get(driver_num, {}).get("name", "")
        ln = _last_name(name)
        if ln:
            result[ln] = pts  # Last write wins if duplicate last names (rare)
    return result


# Max rounds per season (Abu Dhabi)
MAX_ROUNDS = 24

MODE_TARGET = "target"
MODE_LASTYEAR = "lastyear"
MODE_LASTRACE = "lastrace"
MODES = (MODE_TARGET, MODE_LASTYEAR, MODE_LASTRACE)


def _resolve_data_source(
    target_season: int,
    target_round: int,
    mode: str,
) -> tuple[int, int]:
    """Return (data_season, data_round) for fetching performance data."""
    if mode == MODE_TARGET:
        return target_season, target_round
    if mode == MODE_LASTYEAR:
        return target_season - 1, target_round
    if mode == MODE_LASTRACE:
        if target_round > 1:
            return target_season, target_round - 1
        return target_season - 1, MAX_ROUNDS
    return target_season, target_round


def main():
    parser = argparse.ArgumentParser(description="F1 Fantasy - Best team for a race")
    parser.add_argument("--year", type=int, default=2026, help="F1 season year")
    parser.add_argument(
        "--round", "-r",
        dest="round_input",
        metavar="ROUND",
        help="Round to analyze: number (1), r1, venue (aus, bahrain, monaco), or 'r1 aus'",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=MODES,
        default=MODE_TARGET,
        help="Data source: target (default), lastyear (same race last season), lastrace (previous round)",
    )
    parser.add_argument(
        "--computed",
        action="store_true",
        help="Force computed points (skip fantasy-data); use to verify scoring vs f1fantasytools.com",
    )
    parser.add_argument(
        "--data-dir",
        metavar="PATH",
        help="Local fantasy-data directory. Can be a specific folder (e.g. .../latest or .../2026) "
        "or a base path (e.g. .../fantasy-data) – then uses {path}/{year} or {path}/latest.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve() if args.data_dir else None
    if data_dir and not data_dir.is_dir():
        logger.error("--data-dir %s is not a directory", data_dir)
        return 1

    # data_dir resolution by year happens after we know data_season (for lastyear mode)
    data_dir_base = data_dir  # base path for year subdirs

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("F1 Fantasy Strategist")
    logger.info("Data source: f1api.dev (f1fantasytools.com)")
    if data_dir:
        logger.info("Fantasy data: local %s", data_dir)
    else:
        logger.info("Fantasy data: GitHub (JoshCBruce/fantasy-data)")
    logger.info("=" * 60)

    # Resolve target round if specified
    target_round = None
    if args.round_input:
        target_round = resolve_round(args.round_input)
        if target_round is None:
            logger.error("Unknown round: %r. Use 1, r1, aus, bahrain, etc.", args.round_input)
            return 1

    # 1. Determine target (season, round) and data source
    target_season = args.year
    data_season, data_round = target_season, target_round

    target_circuit = None  # Circuit name for target round (for display)
    if target_round is not None:
        data_season, data_round = _resolve_data_source(target_season, target_round, args.mode)
        # Fetch data round (for lastyear/lastrace we fetch historical data, not target)
        race_data = fetch_f1api_race(data_season, data_round)
        if not race_data:
            logger.error("Could not fetch data for %d Round %d.", data_season, data_round)
            return 1
        data_circuit = race_data.get("races", {}).get("circuit", {}).get("circuitName", "Unknown")
        # For lastyear, target and data same round -> same circuit. For lastrace, use venue name.
        if data_round == target_round:
            target_circuit = data_circuit
        else:
            target_circuit = ROUND_TO_VENUE.get(target_round, f"Round {target_round}")
    else:
        race_data = fetch_f1api_last_race()
        if not race_data:
            logger.error("Could not fetch race results. Check network.")
            return 1
        races = race_data.get("races", {})
        target_season = race_data.get("season", target_season)
        target_round = int(races.get("round", 1))
        data_season, data_round = _resolve_data_source(target_season, target_round, args.mode)
        target_circuit = race_data.get("races", {}).get("circuit", {}).get("circuitName", "Unknown")
        if (data_season, data_round) != (target_season, target_round):
            race_data = fetch_f1api_race(data_season, data_round)
            if not race_data:
                logger.error("Could not fetch data for %d Round %d.", data_season, data_round)
                return 1

    if args.mode != MODE_TARGET:
        logger.info("\nMode: %s (using data from %d Round %d)", args.mode, data_season, data_round)
    logger.info("\nTarget: %s (Round %d)", target_circuit, target_round)

    # Resolve data_dir by data_season (for lastyear: use 2025 folder)
    if data_dir_base:
        base = data_dir_base
        # If path is .../latest or .../2026, treat parent as base so we can pick data_season
        if (data_dir_base / "driver_data").is_dir() and data_dir_base.name in ("latest", "2024", "2025", "2026"):
            base = data_dir_base.parent
        if not (base / "driver_data").is_dir():
            year_dir = base / str(data_season)
            latest_dir = base / "latest"
            if year_dir.is_dir():
                data_dir = year_dir
                if data_season != args.year:
                    logger.info("Fantasy data: using %d folder %s", data_season, data_dir)
            elif latest_dir.is_dir():
                data_dir = latest_dir
                if data_season != args.year:
                    logger.warning(
                        "Fantasy data: no %d folder, using latest (may mismatch lastyear)",
                        data_season,
                    )
            else:
                data_dir = data_dir_base
        else:
            data_dir = data_dir_base

    races = race_data.get("races", {})
    round_num = data_round
    season = data_season
    logger.info("  Data: Round %d, %d", round_num, season)

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
        sprint_results = (
            races_obj.get("sprintRaceResults")
            or races_obj.get("sprintResults")
            or races_obj.get("results", [])
        )
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

    # Race grid for positions gained/lost: use actual grid from race API (has penalties applied).
    # For sprint weekends, race grid = sprint result; else use race_grid from race data.
    if sprint_positions:
        race_grid_for_positions = sprint_positions
    else:
        race_grid_for_positions = race_grid  # race_grid from API has actual start positions

    # Overtakes: prefer fantasy-data (local or GitHub), else OpenF1
    overtakes_race = (
        fetch_overtakes_from_fantasy_data(round_num, driver_info, data_dir)
        if round_num
        else {}
    )
    if not overtakes_race and round_num:
        overtakes_race = fetch_openf1_overtakes(season, round_num)

    # 5. Compute fantasy points (use f1fantasytools.com data when available)
    computed_driver_points, driver_breakdowns = compute_driver_points_from_results(
        qual_positions=qual_positions,
        sprint_positions=sprint_positions,
        race_positions=race_positions,
        race_grid=race_grid_for_positions or race_grid,
        sprint_grid=sprint_grid,
        fastest_lap_driver=fastest_lap_driver,
        dotd_driver=None,
        overtakes_race=overtakes_race,
    )

    # Build driver -> team mapping from race results
    driver_to_team: dict[int, str] = {}
    for num, info in driver_info.items():
        team_id = info.get("team_id", "unknown")
        driver_to_team[num] = team_id

    # Prefer official fantasy points from f1fantasytools (via fantasy-data) when it matches our season.
    # fantasy-data "latest" can be previous season - we validate by checking race winner points.
    race_winner = next(
        (num for num, pos in race_positions.items() if pos == 1),
        None,
    )
    fantasy_driver_pts = None
    if round_num and data_dir and not args.computed:
        fantasy_driver_pts = get_driver_points_from_fantasy_data(
            driver_info, round_num, race_winner_driver_num=race_winner, data_dir=data_dir
        )
    if fantasy_driver_pts:
        driver_points = {
            num: fantasy_driver_pts.get(num, computed_driver_points[num])
            for num in computed_driver_points
        }
        logger.info(
            "  Using fantasy points from %s",
            "local data" if data_dir else "f1fantasytools.com (fantasy-data)",
        )
    else:
        driver_points = computed_driver_points
        logger.info("  Using computed fantasy points")

    # Constructor points: prefer fantasy-data, else computed (2026 rules)
    computed_constructor_points = compute_constructor_points(
        computed_driver_points,
        driver_to_team,
        dotd_driver=None,
        has_sprint=bool(sprint_positions),
    )
    fantasy_const_pts = None
    if round_num and fantasy_driver_pts:
        fantasy_const_pts = get_constructor_points_from_fantasy_data(
            set(driver_to_team.values()), round_num, data_dir=data_dir
        )
    if fantasy_const_pts:
        constructor_points = {
            tid: fantasy_const_pts.get(tid, computed_constructor_points.get(tid, 0))
            for tid in set(driver_to_team.values()) | set(computed_constructor_points)
        }
    else:
        constructor_points = computed_constructor_points

    # Log driver breakdown table (always show; helps verify vs f1fantasytools.com)
    pts_to_log = fantasy_driver_pts if fantasy_driver_pts else computed_driver_points
    const_pts_to_log = fantasy_const_pts if fantasy_const_pts else computed_constructor_points
    team_id_to_name = {info.get("team_id", ""): info.get("team_name", "") for info in driver_info.values()}

    # Use fantasy-data breakdown when available (has sprint info from 2025 dir, etc.)
    fantasy_breakdown_result = None
    if fantasy_driver_pts and data_dir:
        fantasy_breakdown_result = get_driver_breakdown_from_fantasy_data(
            driver_info, round_num, data_dir=data_dir
        )
    driver_breakdowns_to_show = driver_breakdowns
    has_sprint = sprint_positions is not None and len(sprint_positions) > 0
    if fantasy_breakdown_result:
        driver_breakdowns_to_show, has_sprint = fantasy_breakdown_result

    logger.info("")
    logger.info("  Points from %d Round %d:", data_season, data_round)
    if not fantasy_driver_pts and not overtakes_race:
        logger.info("  (Computed points are lower than f1fantasytools.com: no overtake data available)")
    if fantasy_driver_pts and fantasy_breakdown_result:
        logger.info("  (Breakdown from fantasy-data)")
    elif fantasy_driver_pts:
        logger.info("  (Breakdown from API; optimizer uses fantasy totals)")
    # Driver points breakdown table (include Sprint breakdown when round has sprint)
    if has_sprint:
        cols = ["Driver", "Qualy", "Sprint", "S+G", "S-L", "SOvt", "SFL", "Race", "+Gain", "-Lost", "Ovt", "FL", "DOTD", "Total"]
        col_widths = [20, 5, 5, 4, 4, 4, 3, 5, 5, 5, 3, 3, 5, 5]
    else:
        cols = ["Driver", "Qualy", "Race", "+Gain", "-Lost", "Ovt", "FL", "DOTD", "Total"]
        col_widths = [20, 6, 6, 6, 6, 4, 4, 6, 6]
    header = "  " + "".join(c.ljust(w) for c, w in zip(cols, col_widths))
    logger.info("  %s", header)
    logger.info("  %s", "-" * (sum(col_widths) + 2))
    for driver_num, pts in sorted(pts_to_log.items(), key=lambda x: -x[1]):
        b = driver_breakdowns_to_show.get(driver_num, {})
        name = driver_info.get(driver_num, {}).get("name", f"Driver {driver_num}")
        short_name = (name[:17] + "..") if len(name) > 19 else name
        if has_sprint:
            row = (
                f"  {short_name.ljust(20)}"
                f"{b.get('qualy', 0):>4.0f} "
                f"{b.get('sprint_pos', 0):>4.0f} "
                f"{b.get('sprint_gained', 0):>3.0f} "
                f"{b.get('sprint_lost', 0):>3.0f} "
                f"{b.get('sprint_overtakes', 0):>3.0f} "
                f"{b.get('sprint_fl', 0):>2.0f} "
                f"{b.get('race_pos', 0):>4.0f} "
                f"{b.get('race_gained', 0):>4.0f} "
                f"{b.get('race_lost', 0):>4.0f} "
                f"{b.get('race_overtakes', 0):>2.0f} "
                f"{b.get('race_fl', 0):>2.0f} "
                f"{b.get('race_dotd', 0):>4.0f} "
                f"{b.get('total', pts):>4.0f}"
            )
        else:
            row = (
                f"  {short_name.ljust(20)}"
                f"{b.get('qualy', 0):>5.0f} "
                f"{b.get('race_pos', 0):>5.0f} "
                f"{b.get('race_gained', 0):>5.0f} "
                f"{b.get('race_lost', 0):>5.0f} "
                f"{b.get('race_overtakes', 0):>3.0f} "
                f"{b.get('race_fl', 0):>3.0f} "
                f"{b.get('race_dotd', 0):>5.0f} "
                f"{b.get('total', pts):>5.0f}"
            )
        logger.info("%s", row)
    logger.info("")
    logger.info("  Constructors:")
    for tid, pts in sorted(const_pts_to_log.items(), key=lambda x: -x[1]):
        name = team_id_to_name.get(tid, tid.replace("_", " ").title())
        logger.info("    %s: %.0f pts", name, pts)
    logger.info("")

    # 6. Load prices and build optimizer lists
    fallback = load_fallback_prices()
    if not fallback:
        logger.error("No price data. Add data/fallback_prices.json (update from f1fantasytools.com)")
        return 1

    # Build driver list for optimizer. For lastyear/lastrace we map points to current grid by name.
    drivers_for_optimizer: list[Driver] = []
    if args.mode in (MODE_LASTYEAR, MODE_LASTRACE):
        name_to_pts = _build_name_to_points(driver_points, driver_info)
        for fd in fallback.get("drivers", []):
            ln = _last_name(fd["name"])
            pts = name_to_pts.get(ln, 0.0)
            drivers_for_optimizer.append(
                Driver(fd["id"], fd["name"], fd["team_id"], fd["price"], pts)
            )
        # Constructor points = sum of their drivers' points (from fallback team mapping)
        team_driver_pts: dict[str, float] = {}
        for d in drivers_for_optimizer:
            team_driver_pts[d.team_id] = team_driver_pts.get(d.team_id, 0) + d.points
        constructor_points = team_driver_pts
    else:
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

    # 7. Run optimizer (includes Boost / Mega Driver: one driver gets 2x points)
    logger.info("\nFinding optimal team (5 drivers + 2 constructors, $100M cap)...")
    best_drivers, best_constructors, total_points, boosted_driver = find_optimal_team(
        unique_drivers, constructors_for_optimizer
    )

    # 8. Output
    logger.info("\n" + "=" * 60)
    logger.info("OPTIMAL TEAM FOR %s (Round %d)", str(target_circuit).upper(), target_round)
    logger.info("=" * 60)
    logger.info("\nDrivers:")
    driver_cost = 0
    for d in best_drivers:
        boost_tag = " [BOOST]" if boosted_driver and d.name == boosted_driver.name else ""
        logger.info("  %s - $%.1fM - %.0f pts%s", d.name, d.price, d.points, boost_tag)
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
