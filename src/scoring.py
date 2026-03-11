"""
F1 Fantasy scoring rules implementation.

Based on https://fantasy.formula1.com/en/game-rules
2026 rules: Sprint DNF/DSQ reduced to -10 points.
"""

from typing import Optional

# Positions gained/lost and overtakes (per official rules)
POSITION_GAINED_POINTS = 1
POSITION_LOST_POINTS = -1
OVERTAKE_POINTS = 1

# Qualifying - Driver positions
QUALIFYING_DRIVER_POINTS = {
    1: 10,
    2: 9,
    3: 8,
    4: 7,
    5: 6,
    6: 5,
    7: 4,
    8: 3,
    9: 2,
    10: 1,
}
QUALIFYING_PENALTY = -5  # NC/DSQ/No time set

# Qualifying - Constructor bonuses (Q2/Q3)
CONSTRUCTOR_QUALIFYING = {
    "neither_q2": -1,
    "one_q2": 1,
    "both_q2": 3,
    "one_q3": 5,
    "both_q3": 10,
    "disqualified_per_driver": -5,
}

# Sprint - Driver (separate rules from Race)
# Drivers: Positions Gained +1, Positions Lost -1, Overtakes +1, Fastest Lap +5
# Sprint Result: 1st=8, 2nd=7, ..., 8th=1; 9th-20th=0; DNF/DSQ/NC=-10
# Constructors: sum of two drivers + DQ penalty (-10 per driver)
SPRINT_DRIVER_POINTS = {
    1: 8,
    2: 7,
    3: 6,
    4: 5,
    5: 4,
    6: 3,
    7: 2,
    8: 1,
}
SPRINT_DNF_PENALTY = -10
SPRINT_FASTEST_LAP = 5

# Race - Driver positions
RACE_DRIVER_POINTS = {
    1: 25,
    2: 18,
    3: 15,
    4: 12,
    5: 10,
    6: 8,
    7: 6,
    8: 4,
    9: 2,
    10: 1,
}
RACE_DNF_PENALTY = -20
RACE_FASTEST_LAP = 10
RACE_DOTD = 10  # Driver of the Day (driver only, NOT counted for constructors)

# Constructor-specific penalties (2026: DQ penalties apply to constructor)
CONSTRUCTOR_SPRINT_DQ_PENALTY = -10  # per disqualified driver
CONSTRUCTOR_RACE_DQ_PENALTY = -20  # per disqualified driver

# Pitstop times (race only, not sprint) - constructor points by fastest pitstop
# Times in seconds; (min_inclusive, max_inclusive) -> points
PITSTOP_POINTS = [
    (3.01, float("inf"), 0),   # Over 3.0s
    (2.5, 2.99, 2),            # 2.50 - 2.99s
    (2.2, 2.49, 5),           # 2.20 - 2.49s
    (2.0, 2.19, 10),          # 2.00 - 2.19s
    (0, 1.99, 20),            # Under 2.0s
]
PITSTOP_FASTEST_BONUS = 5
PITSTOP_WORLD_RECORD_BONUS = 15  # current record 1.8s (McLaren Qatar 2023)


def pitstop_points(
    pitstop_time_seconds: float,
    is_fastest_of_race: bool = False,
    is_world_record: bool = False,
) -> int:
    """
    Constructor pitstop points (race only).
    pitstop_time_seconds: team's fastest pitstop in the race.
    """
    pts = 0
    for min_s, max_s, value in PITSTOP_POINTS:
        if min_s <= pitstop_time_seconds <= max_s:
            pts = value
            break
    if is_fastest_of_race:
        pts += PITSTOP_FASTEST_BONUS
    if is_world_record:
        pts += PITSTOP_WORLD_RECORD_BONUS
    return pts


def compute_constructor_race_bonuses(
    pitstop_time_seconds: Optional[float] = None,
    is_fastest_pitstop: bool = False,
    is_pitstop_world_record: bool = False,
    disqualified_drivers: int = 0,
) -> int:
    """
    Constructor race bonuses: pitstop points + DQ penalties.
    Returns 0 if no pitstop data (grand prix only, not sprint).
    """
    bonus = 0
    if pitstop_time_seconds is not None:
        bonus += pitstop_points(
            pitstop_time_seconds, is_fastest_pitstop, is_pitstop_world_record
        )
    bonus += disqualified_drivers * CONSTRUCTOR_RACE_DQ_PENALTY
    return bonus


def compute_constructor_sprint_bonuses(disqualified_drivers: int = 0) -> int:
    """Constructor sprint bonuses: DQ penalty only (-10 per driver)."""
    return disqualified_drivers * CONSTRUCTOR_SPRINT_DQ_PENALTY


def qualifying_driver_points(position: int, dnf_or_dsq: bool = False) -> int:
    """Points for driver qualifying result."""
    if dnf_or_dsq:
        return QUALIFYING_PENALTY
    return QUALIFYING_DRIVER_POINTS.get(position, 0)


def sprint_driver_points(
    position: int,
    dnf_or_dsq: bool = False,
    positions_gained: int = 0,
    positions_lost: int = 0,
    overtakes: int = 0,
    fastest_lap: bool = False,
) -> int:
    """
    Points for driver sprint result (2026 rules).
    Sprint has its own rules: position pts (1-8), +gained -lost, +overtakes, +fastest lap (5), DNF=-10.
    """
    if dnf_or_dsq:
        return SPRINT_DNF_PENALTY
    pts = SPRINT_DRIVER_POINTS.get(position, 0)
    pts += positions_gained * POSITION_GAINED_POINTS
    pts += positions_lost * POSITION_LOST_POINTS
    pts += overtakes * OVERTAKE_POINTS
    if fastest_lap:
        pts += SPRINT_FASTEST_LAP
    return pts


def race_driver_points(
    position: int,
    dnf_or_dsq: bool = False,
    positions_gained: int = 0,
    positions_lost: int = 0,
    overtakes: int = 0,
    fastest_lap: bool = False,
    driver_of_day: bool = False,
) -> int:
    """Points for driver race result (2026 rules)."""
    if dnf_or_dsq:
        return RACE_DNF_PENALTY
    pts = RACE_DRIVER_POINTS.get(position, 0)
    pts += positions_gained * POSITION_GAINED_POINTS
    pts += positions_lost * POSITION_LOST_POINTS
    pts += overtakes * OVERTAKE_POINTS
    if fastest_lap:
        pts += RACE_FASTEST_LAP
    if driver_of_day:
        pts += RACE_DOTD
    return pts


def calculate_driver_points(
    qual_pos=None,
    qual_dnf: bool = False,
    sprint_pos=None,
    sprint_dnf: bool = False,
    sprint_positions_gained: int = 0,
    sprint_positions_lost: int = 0,
    sprint_overtakes: int = 0,
    sprint_fastest_lap: bool = False,
    race_pos=None,
    race_dnf: bool = False,
    race_positions_gained: int = 0,
    race_positions_lost: int = 0,
    race_overtakes: int = 0,
    race_fastest_lap: bool = False,
    race_dotd: bool = False,
    has_sprint: bool = False,
) -> int:
    """
    Calculate total fantasy points for a driver in a race weekend (2026 rules).
    """
    total = 0

    # Qualifying
    if qual_pos is not None or qual_dnf:
        total += qualifying_driver_points(qual_pos or 20, qual_dnf)

    # Sprint (if weekend has sprint)
    if has_sprint and (sprint_pos is not None or sprint_dnf):
        total += sprint_driver_points(
            sprint_pos or 20,
            sprint_dnf,
            sprint_positions_gained,
            sprint_positions_lost,
            sprint_overtakes,
            sprint_fastest_lap,
        )

    # Race
    if race_pos is not None or race_dnf:
        total += race_driver_points(
            race_pos or 20,
            race_dnf,
            race_positions_gained,
            race_positions_lost,
            race_overtakes,
            race_fastest_lap,
            race_dotd,
        )

    return total


def calculate_driver_points_breakdown(
    qual_pos=None,
    qual_dnf: bool = False,
    sprint_pos=None,
    sprint_dnf: bool = False,
    sprint_positions_gained: int = 0,
    sprint_positions_lost: int = 0,
    sprint_overtakes: int = 0,
    sprint_fastest_lap: bool = False,
    race_pos=None,
    race_dnf: bool = False,
    race_positions_gained: int = 0,
    race_positions_lost: int = 0,
    race_overtakes: int = 0,
    race_fastest_lap: bool = False,
    race_dotd: bool = False,
    has_sprint: bool = False,
) -> dict[str, float]:
    """
    Return per-term breakdown of driver points (for logging/debugging).
    Keys: qualy, sprint, sprint_gained, sprint_lost, sprint_overtakes, sprint_fl,
          race_pos, race_gained, race_lost, race_overtakes, race_fl, race_dotd, total
    """
    breakdown: dict[str, float] = {
        "qualy": 0, "sprint": 0, "sprint_pos": 0, "sprint_gained": 0, "sprint_lost": 0,
        "sprint_overtakes": 0, "sprint_fl": 0,
        "race_pos": 0, "race_gained": 0, "race_lost": 0,
        "race_overtakes": 0, "race_fl": 0, "race_dotd": 0,
    }
    qualy_pts = qualifying_driver_points(qual_pos or 20, qual_dnf) if (qual_pos is not None or qual_dnf) else 0
    breakdown["qualy"] = qualy_pts

    if has_sprint and (sprint_pos is not None or sprint_dnf):
        sprint_pos_pts = SPRINT_DNF_PENALTY if sprint_dnf else SPRINT_DRIVER_POINTS.get(sprint_pos or 20, 0)
        sprint_gained_pts = sprint_positions_gained * POSITION_GAINED_POINTS
        sprint_lost_pts = sprint_positions_lost * POSITION_LOST_POINTS
        sprint_ovt_pts = sprint_overtakes * OVERTAKE_POINTS
        sprint_fl_pts = SPRINT_FASTEST_LAP if sprint_fastest_lap else 0
        breakdown["sprint_pos"] = sprint_pos_pts
        breakdown["sprint_gained"] = sprint_gained_pts
        breakdown["sprint_lost"] = sprint_lost_pts
        breakdown["sprint_overtakes"] = sprint_ovt_pts
        breakdown["sprint_fl"] = sprint_fl_pts
        breakdown["sprint"] = sprint_pos_pts + sprint_gained_pts + sprint_lost_pts + sprint_ovt_pts + sprint_fl_pts

    if race_pos is not None or race_dnf:
        race_pos_pts = RACE_DRIVER_POINTS.get(race_pos or 20, 0) if not race_dnf else RACE_DNF_PENALTY
        breakdown["race_pos"] = race_pos_pts
        breakdown["race_gained"] = race_positions_gained * POSITION_GAINED_POINTS
        breakdown["race_lost"] = race_positions_lost * POSITION_LOST_POINTS
        breakdown["race_overtakes"] = race_overtakes * OVERTAKE_POINTS
        breakdown["race_fl"] = RACE_FASTEST_LAP if race_fastest_lap else 0
        breakdown["race_dotd"] = RACE_DOTD if race_dotd else 0

    breakdown["total"] = (
        breakdown["qualy"] + breakdown["sprint"] + breakdown["race_pos"]
        + breakdown["race_gained"] + breakdown["race_lost"] + breakdown["race_overtakes"]
        + breakdown["race_fl"] + breakdown["race_dotd"]
    )
    return breakdown
