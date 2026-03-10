"""
Analyzes race results and computes fantasy points per driver/constructor.
Works with F1 API (f1api.dev) data format.
"""

from collections import defaultdict
from typing import Optional

from .scoring import calculate_driver_points


def compute_driver_points_from_results(
    qual_positions: Optional[dict],
    sprint_positions: Optional[dict],
    race_positions: dict,
    race_grid: Optional[dict] = None,
    sprint_grid: Optional[dict] = None,
    fastest_lap_driver: Optional[int] = None,
    dotd_driver: Optional[int] = None,
) -> dict:
    """
    Compute fantasy points for each driver based on session results.
    DNFs are indicated by position > 20 or being absent from results.
    """
    all_drivers = set(race_positions.keys())
    if qual_positions:
        all_drivers |= set(qual_positions.keys())
    if sprint_positions:
        all_drivers |= set(sprint_positions.keys())

    points: dict[int, float] = {}
    has_sprint = sprint_positions is not None and len(sprint_positions) > 0

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

        # Positions gained (race: grid vs finish)
        race_gained = 0
        if race_grid and race_pos and not race_dnf:
            grid_pos = race_grid.get(driver_num, 20)
            if grid_pos and grid_pos <= 20:
                race_gained = max(0, grid_pos - race_pos)

        sprint_gained = 0
        if has_sprint and sprint_grid and sprint_pos and not sprint_dnf:
            grid_pos = sprint_grid.get(driver_num, 20)
            if grid_pos and grid_pos <= 20:
                sprint_gained = max(0, grid_pos - sprint_pos)

        pts = calculate_driver_points(
            qual_pos=qual_pos if not qual_dnf else None,
            qual_dnf=qual_dnf,
            sprint_pos=sprint_pos if not sprint_dnf else None,
            sprint_dnf=sprint_dnf,
            sprint_positions_gained=sprint_gained,
            sprint_fastest_lap=(fastest_lap_driver == driver_num and has_sprint),
            race_pos=race_pos if not race_dnf else None,
            race_dnf=race_dnf,
            race_positions_gained=race_gained,
            race_fastest_lap=(fastest_lap_driver == driver_num),
            race_dotd=(dotd_driver == driver_num),
            has_sprint=has_sprint,
        )
        points[driver_num] = pts

    return points


def compute_constructor_points(
    driver_points: dict[int, float],
    driver_to_team: dict[int, str],
) -> dict[str, float]:
    """
    Constructor points = sum of their two drivers' points.
    """
    team_drivers: dict[str, list[int]] = defaultdict(list)
    for driver_num, team in driver_to_team.items():
        team_drivers[team].append(driver_num)

    return {
        team: sum(driver_points.get(d, 0) for d in drivers)
        for team, drivers in team_drivers.items()
    }
