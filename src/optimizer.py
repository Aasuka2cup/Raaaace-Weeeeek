"""
Optimizer for F1 Fantasy team selection.

Finds the best combination of 5 drivers + 2 constructors under $100M budget
to maximize points for a given race.
"""

from itertools import combinations
from typing import NamedTuple


class Driver(NamedTuple):
    id: str
    name: str
    team_id: str
    price: float
    points: float


class Constructor(NamedTuple):
    id: str
    name: str
    price: float
    points: float


def find_optimal_team(
    drivers: list[Driver],
    constructors: list[Constructor],
    budget: float = 100.0,
) -> tuple[list[Driver], list[Constructor], float]:
    """
    Find the team (5 drivers + 2 constructors) that maximizes points under budget.
    """
    if len(drivers) < 5 or len(constructors) < 2:
        raise ValueError("Need at least 5 drivers and 2 constructors")

    best_drivers: list[Driver] = []
    best_constructors: list[Constructor] = []
    best_points = -1e9

    for const_combo in combinations(constructors, 2):
        const_cost = sum(c.price for c in const_combo)
        const_points = sum(c.points for c in const_combo)
        remaining_budget = budget - const_cost

        if remaining_budget < 0:
            continue

        # Sort drivers by points per million (efficiency), then take best 5 under budget
        # Use greedy: sort by points descending, try combinations
        for driver_combo in combinations(drivers, 5):
            cost = sum(d.price for d in driver_combo) + const_cost
            if cost <= budget:
                points = sum(d.points for d in driver_combo) + const_points
                if points > best_points:
                    best_points = points
                    best_drivers = list(driver_combo)
                    best_constructors = list(const_combo)

    return best_drivers, best_constructors, best_points


def find_top_n_teams(
    drivers: list[Driver],
    constructors: list[Constructor],
    budget: float = 100.0,
    n: int = 5,
) -> list[tuple[list[Driver], list[Constructor], float]]:
    """Find top N team combinations."""
    results: list[tuple[list[Driver], list[Constructor], float]] = []
    seen: set[frozenset] = set()

    for const_combo in combinations(constructors, 2):
        const_cost = sum(c.price for c in const_combo)
        const_points = sum(c.points for c in const_combo)
        remaining_budget = budget - const_cost

        if remaining_budget < 0:
            continue

        for driver_combo in combinations(drivers, 5):
            cost = sum(d.price for d in driver_combo) + const_cost
            if cost <= budget:
                points = sum(d.points for d in driver_combo) + const_points
                key = frozenset(d.id for d in driver_combo) | frozenset(
                    c.id for c in const_combo
                )
                if key not in seen:
                    seen.add(key)
                    results.append((list(driver_combo), list(const_combo), points))

    results.sort(key=lambda x: x[2], reverse=True)
    return results[:n]
