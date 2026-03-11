"""
Analyzes race results and computes fantasy points per driver/constructor.
Works with F1 API (f1api.dev) data format.
Implements 2026 F1 Fantasy rules.
"""

from collections import defaultdict
from typing import Optional

from .scoring import (
    RACE_DOTD,
    calculate_driver_points,
    calculate_driver_points_breakdown,
    compute_constructor_race_bonuses,
    compute_constructor_sprint_bonuses,
)


def compute_driver_points_from_results(
    qual_positions: Optional[dict],
    sprint_positions: Optional[dict],
    race_positions: dict,
    race_grid: Optional[dict] = None,
    sprint_grid: Optional[dict] = None,
    fastest_lap_driver: Optional[int] = None,
    dotd_driver: Optional[int] = None,
    overtakes_sprint: Optional[dict[int, int]] = None,
    overtakes_race: Optional[dict[int, int]] = None,
) -> tuple[dict[int, float], dict[int, dict[str, float]]]:
    """
    Compute fantasy points for each driver based on session results (2026 rules).
    DNFs are indicated by position > 20 or being absent from results.
    overtakes_sprint/race: driver_num -> overtake count (1 pt per overtake).
    Returns (driver_points, driver_breakdowns) where breakdowns is driver_num -> {term: pts}.
    """
    all_drivers = set(race_positions.keys())
    if qual_positions:
        all_drivers |= set(qual_positions.keys())
    if sprint_positions:
        all_drivers |= set(sprint_positions.keys())

    points: dict[int, float] = {}
    has_sprint = sprint_positions is not None and len(sprint_positions) > 0
    overtakes_sprint = overtakes_sprint or {}
    overtakes_race = overtakes_race or {}

    for driver_num in all_drivers:
        qual_pos = qual_positions.get(driver_num) if qual_positions else None
        sprint_pos = sprint_positions.get(driver_num) if sprint_positions else None
        race_pos = race_positions.get(driver_num)

        # DNF: not in results or position > 20
        qual_dnf = qual_pos is None or (qual_pos is not None and qual_pos > 20)
        sprint_dnf = (
            has_sprint
            and (sprint_pos is None or (sprint_pos is not None and sprint_pos > 20))
        )
        race_dnf = race_pos is None or (race_pos is not None and race_pos > 20)

        # Positions gained/lost (grid vs finish; unclassified = no positions lost)
        race_gained = 0
        race_lost = 0
        if race_grid and race_pos and not race_dnf:
            grid_pos = race_grid.get(driver_num, 20)
            if grid_pos and grid_pos <= 20:
                diff = grid_pos - race_pos
                race_gained = max(0, diff)
                race_lost = max(0, -diff)

        sprint_gained = 0
        sprint_lost = 0
        if has_sprint and sprint_grid and sprint_pos and not sprint_dnf:
            grid_pos = sprint_grid.get(driver_num, 20)
            if grid_pos and grid_pos <= 20:
                diff = grid_pos - sprint_pos
                sprint_gained = max(0, diff)
                sprint_lost = max(0, -diff)

        sprint_ov = overtakes_sprint.get(driver_num, 0)
        race_ov = overtakes_race.get(driver_num, 0)

        pts = calculate_driver_points(
            qual_pos=qual_pos if not qual_dnf else None,
            qual_dnf=qual_dnf,
            sprint_pos=sprint_pos if not sprint_dnf else None,
            sprint_dnf=sprint_dnf,
            sprint_positions_gained=sprint_gained,
            sprint_positions_lost=sprint_lost,
            sprint_overtakes=sprint_ov,
            sprint_fastest_lap=(fastest_lap_driver == driver_num and has_sprint),
            race_pos=race_pos if not race_dnf else None,
            race_dnf=race_dnf,
            race_positions_gained=race_gained,
            race_positions_lost=race_lost,
            race_overtakes=race_ov,
            race_fastest_lap=(fastest_lap_driver == driver_num),
            race_dotd=(dotd_driver == driver_num),
            has_sprint=has_sprint,
        )
        points[driver_num] = pts

    # Compute per-term breakdowns for logging
    breakdowns: dict[int, dict[str, float]] = {}
    for driver_num in all_drivers:
        qual_pos = qual_positions.get(driver_num) if qual_positions else None
        sprint_pos = sprint_positions.get(driver_num) if sprint_positions else None
        race_pos = race_positions.get(driver_num)
        qual_dnf = qual_pos is None or (qual_pos is not None and qual_pos > 20)
        sprint_dnf = has_sprint and (sprint_pos is None or (sprint_pos is not None and sprint_pos > 20))
        race_dnf = race_pos is None or (race_pos is not None and race_pos > 20)
        race_gained = race_lost = sprint_gained = sprint_lost = 0
        if race_grid and race_pos and not race_dnf:
            grid_pos = race_grid.get(driver_num, 20)
            if grid_pos and grid_pos <= 20:
                diff = grid_pos - race_pos
                race_gained = max(0, diff)
                race_lost = max(0, -diff)
        if has_sprint and sprint_grid and sprint_pos and not sprint_dnf:
            grid_pos = sprint_grid.get(driver_num, 20)
            if grid_pos and grid_pos <= 20:
                diff = grid_pos - sprint_pos
                sprint_gained = max(0, diff)
                sprint_lost = max(0, -diff)
        breakdowns[driver_num] = calculate_driver_points_breakdown(
            qual_pos=qual_pos if not qual_dnf else None,
            qual_dnf=qual_dnf,
            sprint_pos=sprint_pos if not sprint_dnf else None,
            sprint_dnf=sprint_dnf,
            sprint_positions_gained=sprint_gained,
            sprint_positions_lost=sprint_lost,
            sprint_overtakes=overtakes_sprint.get(driver_num, 0),
            sprint_fastest_lap=(fastest_lap_driver == driver_num and has_sprint),
            race_pos=race_pos if not race_dnf else None,
            race_dnf=race_dnf,
            race_positions_gained=race_gained,
            race_positions_lost=race_lost,
            race_overtakes=overtakes_race.get(driver_num, 0),
            race_fastest_lap=(fastest_lap_driver == driver_num),
            race_dotd=(dotd_driver == driver_num),
            has_sprint=has_sprint,
        )

    return points, breakdowns


def compute_constructor_points(
    driver_points: dict[int, float],
    driver_to_team: dict[int, str],
    dotd_driver: Optional[int] = None,
    pitstop_by_team: Optional[dict[str, float]] = None,
    fastest_pitstop_team: Optional[str] = None,
    pitstop_world_record_team: Optional[str] = None,
    sprint_dq_by_team: Optional[dict[str, int]] = None,
    race_dq_by_team: Optional[dict[str, int]] = None,
    has_sprint: bool = False,
) -> dict[str, float]:
    """
    Constructor points = sum of their two drivers' points (2026 rules).
    - DOTD is driver-only: excluded from constructor total.
    - Pitstop points added per team (race only).
    - DQ penalties: -10 per driver (sprint), -20 per driver (race).
    """
    team_drivers: dict[str, list[int]] = defaultdict(list)
    for driver_num, team in driver_to_team.items():
        team_drivers[team].append(driver_num)

    pitstop_by_team = pitstop_by_team or {}
    sprint_dq_by_team = sprint_dq_by_team or {}
    race_dq_by_team = race_dq_by_team or {}

    result: dict[str, float] = {}
    for team, drivers in team_drivers.items():
        pts = sum(driver_points.get(d, 0) for d in drivers)
        # Exclude DOTD (driver-only bonus)
        if dotd_driver and dotd_driver in drivers:
            pts -= RACE_DOTD
        # Sprint DQ penalty
        if has_sprint:
            pts += compute_constructor_sprint_bonuses(sprint_dq_by_team.get(team, 0))
        # Race pitstop + DQ
        pitstop_time = pitstop_by_team.get(team)
        pts += compute_constructor_race_bonuses(
            pitstop_time_seconds=pitstop_time,
            is_fastest_pitstop=(team == fastest_pitstop_team),
            is_pitstop_world_record=(team == pitstop_world_record_team),
            disqualified_drivers=race_dq_by_team.get(team, 0),
        )
        result[team] = pts

    return result
