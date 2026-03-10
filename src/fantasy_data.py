"""
Fetches official F1 Fantasy points from JoshCBruce/fantasy-data on GitHub.

This repo mirrors data from https://f1fantasytools.com/statistics (official fantasy points).
Used when available; falls back to computed points for future rounds or new drivers.
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

FANTASY_DATA_BASE = "https://raw.githubusercontent.com/JoshCBruce/fantasy-data/main/latest"

# Driver last name -> fantasy-data abbreviation (3-letter code)
NAME_TO_ABBREV = {
    "verstappen": "VER", "russell": "RUS", "antonelli": "ANT", "leclerc": "LEC",
    "hamilton": "HAM", "norris": "NOR", "piastri": "PIA", "sainz": "SAI",
    "perez": "PER", "alonso": "ALO", "gasly": "GAS", "albon": "ALB",
    "stroll": "STR", "bearman": "BEA", "lindblad": "LIN", "bortoleto": "BOR",
    "lawson": "LAW", "ocon": "OCO", "colapinto": "COL", "bottas": "BOT",
    "hadjar": "HAD", "hulkenberg": "HUL", "tsunoda": "TSU", "doohan": "DOO",
}

# team_id (from f1api/fallback) -> fantasy-data constructor abbreviation
TEAM_TO_ABBREV = {
    "red_bull": "RBR", "mercedes": "MER", "ferrari": "FER", "mclaren": "MCL",
    "williams": "WIL", "aston_martin": "AMR", "alpine": "ALP", "rb": "RB",
    "haas": "HAS", "audi": "AUD", "cadillac": "CAD", "sauber": "SAU",
}


def _get_abbrev_from_name(name: str) -> Optional[str]:
    """Map driver name to fantasy-data abbreviation."""
    if not name:
        return None
    last = name.strip().split()[-1].lower() if name else ""
    return NAME_TO_ABBREV.get(last)


def fetch_driver_points_for_round(round_num: int) -> dict[str, float]:
    """
    Fetch driver fantasy points for a round from fantasy-data.
    Returns dict: abbreviation -> totalPoints for that round.
    """
    # Get list of driver files
    list_url = "https://api.github.com/repos/JoshCBruce/fantasy-data/contents/latest/driver_data"
    try:
        resp = requests.get(list_url, timeout=10)
        resp.raise_for_status()
        files = resp.json()
    except requests.RequestException as e:
        logger.debug("fantasy-data driver list fetch failed: %s", e)
        return {}

    round_str = str(round_num)
    result: dict[str, float] = {}

    for item in files:
        if item.get("type") != "file" or not item.get("name", "").endswith(".json"):
            continue
        abbrev = item["name"].replace(".json", "")
        url = f"{FANTASY_DATA_BASE}/driver_data/{abbrev}.json"
        try:
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException:
            continue

        races = data.get("races", [])
        for race in races:
            if race.get("round") == round_str:
                pts = race.get("totalPoints")
                if pts is not None:
                    # Handle multiple entries for same round (e.g. sprint + race)
                    if abbrev in result:
                        result[abbrev] = max(result[abbrev], float(pts))
                    else:
                        result[abbrev] = float(pts)
                break

    return result


def fetch_constructor_points_for_round(round_num: int) -> dict[str, float]:
    """
    Fetch constructor fantasy points for a round from fantasy-data.
    Returns dict: abbreviation -> totalPoints for that round.
    """
    list_url = "https://api.github.com/repos/JoshCBruce/fantasy-data/contents/latest/constructor_data"
    try:
        resp = requests.get(list_url, timeout=10)
        resp.raise_for_status()
        files = resp.json()
    except requests.RequestException as e:
        logger.debug("fantasy-data constructor list fetch failed: %s", e)
        return {}

    round_str = str(round_num)
    result: dict[str, float] = {}

    for item in files:
        if item.get("type") != "file" or not item.get("name", "").endswith(".json"):
            continue
        abbrev = item["name"].replace(".json", "")
        url = f"{FANTASY_DATA_BASE}/constructor_data/{abbrev}.json"
        try:
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException:
            continue

        races = data.get("races", [])
        for race in races:
            if race.get("round") == round_str:
                pts = race.get("totalPoints")
                if pts is not None:
                    if abbrev in result:
                        result[abbrev] = max(result[abbrev], float(pts))
                    else:
                        result[abbrev] = float(pts)
                break

    return result


def get_driver_points_from_fantasy_data(
    driver_info: dict[int, dict],
    round_num: int,
) -> Optional[dict[int, float]]:
    """
    Fetch driver points from fantasy-data and map to driver numbers.
    Returns None if fetch fails or no data for round; else dict driver_num -> points.
    """
    abbrev_to_points = fetch_driver_points_for_round(round_num)
    if not abbrev_to_points:
        return None

    result: dict[int, float] = {}
    for driver_num, info in driver_info.items():
        name = info.get("name", "")
        abbrev = _get_abbrev_from_name(name)
        if abbrev and abbrev in abbrev_to_points:
            result[driver_num] = abbrev_to_points[abbrev]

    return result if result else None


def get_constructor_points_from_fantasy_data(
    team_ids: set[str],
    round_num: int,
) -> Optional[dict[str, float]]:
    """
    Fetch constructor points from fantasy-data and map to team_id.
    Returns None if fetch fails; else dict team_id -> points.
    """
    abbrev_to_points = fetch_constructor_points_for_round(round_num)
    if not abbrev_to_points:
        return None

    result: dict[str, float] = {}
    for team_id in team_ids:
        abbrev = TEAM_TO_ABBREV.get(team_id)
        if abbrev and abbrev in abbrev_to_points:
            result[team_id] = abbrev_to_points[abbrev]

    return result if result else None
