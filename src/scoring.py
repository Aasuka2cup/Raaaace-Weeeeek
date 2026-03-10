"""
F1 Fantasy scoring rules implementation.

Based on https://fantasy.formula1.com/en/game-rules
2026 rules: Sprint DNF/DSQ reduced to -10 points.
"""

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

# Sprint - Driver positions
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
RACE_DOTD = 10  # Driver of the Day (driver only)


def qualifying_driver_points(position: int, dnf_or_dsq: bool = False) -> int:
    """Points for driver qualifying result."""
    if dnf_or_dsq:
        return QUALIFYING_PENALTY
    return QUALIFYING_DRIVER_POINTS.get(position, 0)


def sprint_driver_points(
    position: int,
    dnf_or_dsq: bool = False,
    positions_gained: int = 0,
    fastest_lap: bool = False,
) -> int:
    """Points for driver sprint result."""
    if dnf_or_dsq:
        return SPRINT_DNF_PENALTY
    pts = SPRINT_DRIVER_POINTS.get(position, 0)
    pts += positions_gained  # 1 per position gained
    if fastest_lap:
        pts += SPRINT_FASTEST_LAP
    return pts


def race_driver_points(
    position: int,
    dnf_or_dsq: bool = False,
    positions_gained: int = 0,
    fastest_lap: bool = False,
    driver_of_day: bool = False,
) -> int:
    """Points for driver race result."""
    if dnf_or_dsq:
        return RACE_DNF_PENALTY
    pts = RACE_DRIVER_POINTS.get(position, 0)
    pts += positions_gained
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
    sprint_fastest_lap: bool = False,
    race_pos=None,
    race_dnf: bool = False,
    race_positions_gained: int = 0,
    race_fastest_lap: bool = False,
    race_dotd: bool = False,
    has_sprint: bool = False,
) -> int:
    """
    Calculate total fantasy points for a driver in a race weekend.
    """
    total = 0

    # Qualifying
    if qual_pos is not None or qual_dnf:
        total += qualifying_driver_points(qual_pos or 20, qual_dnf)

    # Sprint (if weekend has sprint)
    if has_sprint and (sprint_pos is not None or sprint_dnf):
        total += sprint_driver_points(
            sprint_pos or 20, sprint_dnf, sprint_positions_gained, sprint_fastest_lap
        )

    # Race
    if race_pos is not None or race_dnf:
        total += race_driver_points(
            race_pos or 20, race_dnf, race_positions_gained, race_fastest_lap, race_dotd
        )

    return total
