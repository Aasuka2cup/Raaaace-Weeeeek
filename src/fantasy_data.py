"""
Fetches official F1 Fantasy points from JoshCBruce/fantasy-data on GitHub,
or from a local directory (e.g. output of fantasy_scraper_V3.1.js).

Local structure: data_dir/driver_data/{ABBREV}.json, data_dir/constructor_data/{ABBREV}.json
"""

import json
import logging
from pathlib import Path
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


def _load_driver_data(abbrev: str, data_dir: Optional[Path] = None) -> Optional[dict]:
    """Load driver JSON from local path or GitHub."""
    if data_dir:
        path = data_dir / "driver_data" / f"{abbrev}.json"
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.debug("Failed to load %s: %s", path, e)
        return None
    url = f"{FANTASY_DATA_BASE}/driver_data/{abbrev}.json"
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def _list_driver_files(data_dir: Optional[Path] = None) -> list[str]:
    """List driver abbreviations (without .json)."""
    if data_dir:
        driver_dir = data_dir / "driver_data"
        if not driver_dir.is_dir():
            return []
        return [f.stem for f in driver_dir.glob("*.json")]
    try:
        resp = requests.get(
            "https://api.github.com/repos/JoshCBruce/fantasy-data/contents/latest/driver_data",
            timeout=10,
        )
        resp.raise_for_status()
        files = resp.json()
        return [
            item["name"].replace(".json", "")
            for item in files
            if item.get("type") == "file" and item.get("name", "").endswith(".json")
        ]
    except requests.RequestException as e:
        logger.debug("fantasy-data driver list fetch failed: %s", e)
        return []


def fetch_driver_points_for_round(
    round_num: int,
    data_dir: Optional[Path] = None,
) -> dict[str, float]:
    """
    Fetch driver fantasy points for a round from fantasy-data.
    Returns dict: abbreviation -> totalPoints for that round.
    Uses data_dir if provided (local scraper output); else GitHub.
    """
    abbrevs = _list_driver_files(data_dir)
    round_str = str(round_num)
    result: dict[str, float] = {}

    for abbrev in abbrevs:
        data = _load_driver_data(abbrev, data_dir)
        if not data:
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


def _list_constructor_files(data_dir: Optional[Path] = None) -> list[str]:
    """List constructor abbreviations (without .json)."""
    if data_dir:
        const_dir = data_dir / "constructor_data"
        if not const_dir.is_dir():
            return []
        return [f.stem for f in const_dir.glob("*.json")]
    try:
        resp = requests.get(
            "https://api.github.com/repos/JoshCBruce/fantasy-data/contents/latest/constructor_data",
            timeout=10,
        )
        resp.raise_for_status()
        files = resp.json()
        return [
            item["name"].replace(".json", "")
            for item in files
            if item.get("type") == "file" and item.get("name", "").endswith(".json")
        ]
    except requests.RequestException as e:
        logger.debug("fantasy-data constructor list fetch failed: %s", e)
        return []


def _load_constructor_data(abbrev: str, data_dir: Optional[Path] = None) -> Optional[dict]:
    """Load constructor JSON from local path or GitHub."""
    if data_dir:
        path = data_dir / "constructor_data" / f"{abbrev}.json"
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.debug("Failed to load %s: %s", path, e)
        return None
    url = f"{FANTASY_DATA_BASE}/constructor_data/{abbrev}.json"
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def fetch_constructor_points_for_round(
    round_num: int,
    data_dir: Optional[Path] = None,
) -> dict[str, float]:
    """
    Fetch constructor fantasy points for a round from fantasy-data.
    Returns dict: abbreviation -> totalPoints for that round.
    Uses data_dir if provided; else GitHub.
    """
    abbrevs = _list_constructor_files(data_dir)
    round_str = str(round_num)
    result: dict[str, float] = {}

    for abbrev in abbrevs:
        data = _load_constructor_data(abbrev, data_dir)
        if not data:
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


def fetch_overtakes_from_fantasy_data(
    round_num: int,
    driver_info: dict[int, dict],
    data_dir: Optional[Path] = None,
) -> dict[int, int]:
    """
    Fetch race overtake counts from fantasy-data.
    Returns driver_num -> overtake count. Empty dict on failure.
    overtakeBonus = 1 pt per overtake = overtake count.
    Uses data_dir if provided; else GitHub.
    """
    abbrevs = _list_driver_files(data_dir)
    round_str = str(round_num)
    abbrev_to_overtakes: dict[str, int] = {}

    for abbrev in abbrevs:
        data = _load_driver_data(abbrev, data_dir)
        if not data:
            continue
        races = data.get("races", [])
        for race in races:
            if race.get("round") == round_str:
                race_obj = race.get("race", {})
                if race_obj is not None:
                    bonus = race_obj.get("overtakeBonus", 0)
                    if bonus is not None:
                        abbrev_to_overtakes[abbrev] = int(bonus)
                break

    result: dict[int, int] = {}
    for driver_num, info in driver_info.items():
        abbrev = _get_abbrev_from_name(info.get("name", ""))
        if abbrev and abbrev in abbrev_to_overtakes:
            result[driver_num] = abbrev_to_overtakes[abbrev]

    return result


def get_driver_points_from_fantasy_data(
    driver_info: dict[int, dict],
    round_num: int,
    race_winner_driver_num: Optional[int] = None,
    data_dir: Optional[Path] = None,
) -> Optional[dict[int, float]]:
    """
    Fetch driver points from fantasy-data and map to driver numbers.
    Returns None if fetch fails or no data for round; else dict driver_num -> points.
    Uses data_dir if provided; else GitHub.
    """
    abbrev_to_points = fetch_driver_points_for_round(round_num, data_dir)
    if not abbrev_to_points:
        return None

    result: dict[int, float] = {}
    for driver_num, info in driver_info.items():
        name = info.get("name", "")
        abbrev = _get_abbrev_from_name(name)
        if abbrev and abbrev in abbrev_to_points:
            result[driver_num] = abbrev_to_points[abbrev]

    if not result:
        return None

    # Validate: if we have race winner, check fantasy-data matches our season.
    # 2026 Australia: Russell (P1) has 39. 2025 Australia: Norris won, Russell was P15 with ~25.
    # Race winner in correct season typically has 30+ (P1=25 + qualy/bonuses). Reject if < 25.
    if race_winner_driver_num is not None and race_winner_driver_num in result:
        winner_pts = result[race_winner_driver_num]
        if winner_pts < 28:
            logger.debug(
                "fantasy-data race winner has %.0f pts (expected 30+); likely wrong season, using computed",
                winner_pts,
            )
            return None

    return result


def get_driver_breakdown_from_fantasy_data(
    driver_info: dict[int, dict],
    round_num: int,
    data_dir: Optional[Path] = None,
) -> Optional[tuple[dict[int, dict], bool]]:
    """
    Fetch driver points breakdown from fantasy-data for the table.
    Returns (driver_breakdowns, has_sprint) or None.
    driver_breakdowns: driver_num -> {qualy, sprint, race_pos, race_gained, race_lost, race_overtakes, race_fl, race_dotd, total}
    """
    if not data_dir:
        return None
    round_str = str(round_num)
    abbrevs = _list_driver_files(data_dir)
    abbrev_to_breakdown: dict[str, dict] = {}
    has_sprint = False

    for abbrev in abbrevs:
        data = _load_driver_data(abbrev, data_dir)
        if not data:
            continue
        for race in data.get("races", []):
            if race.get("round") != round_str:
                continue
            qualy = race.get("qualifying", {})
            race_obj = race.get("race", {})
            sprint_obj = race.get("sprint")
            if sprint_obj is not None:
                has_sprint = True

            # Fantasy-data stores POINTS directly (from scraper), not raw positions/counts
            qualy_pts = float(qualy.get("position", 0) or 0)
            dq_penalty = float(qualy.get("disqualificationPenalty", 0) or 0)
            qualy_pts += dq_penalty

            sprint_pts = 0.0
            sprint_pos_pts = sprint_gained_pts = sprint_lost_pts = sprint_ovt_pts = sprint_fl_pts = 0.0
            if sprint_obj is not None:
                sprint_pos_pts = float(sprint_obj.get("position", 0) or 0)
                sprint_gained_pts = float(sprint_obj.get("positionsGained", 0) or 0)
                sprint_lost_pts = float(sprint_obj.get("positionsLost", 0) or 0)
                sprint_ovt_pts = float(sprint_obj.get("overtakeBonus", 0) or 0)
                sprint_fl_pts = float(sprint_obj.get("fastestLap", 0) or 0)
                dq_penalty = float(sprint_obj.get("disqualificationPenalty", 0) or 0)
                sprint_pts = sprint_pos_pts + sprint_gained_pts + sprint_lost_pts + sprint_ovt_pts + sprint_fl_pts + dq_penalty

            race_pos_pts = float(race_obj.get("position", 0) or 0)
            race_gained_pts = float(race_obj.get("positionsGained", 0) or 0)
            race_lost_pts = float(race_obj.get("positionsLost", 0) or 0)
            race_ovt_pts = float(race_obj.get("overtakeBonus", 0) or 0)
            race_fl_pts = float(race_obj.get("fastestLap", 0) or 0)
            race_dotd_pts = float(race_obj.get("dotd", 0) or 0)
            dq_penalty = float(race_obj.get("disqualificationPenalty", 0) or 0)
            race_pos_pts += dq_penalty

            total = qualy_pts + sprint_pts + race_pos_pts + race_gained_pts + race_lost_pts + race_ovt_pts + race_fl_pts + race_dotd_pts
            # Use totalPoints from fantasy-data when available (authoritative)
            race_total_pts = race.get("totalPoints")
            if race_total_pts is not None:
                total = float(race_total_pts)
            abbrev_to_breakdown[abbrev] = {
                "qualy": qualy_pts,
                "sprint": sprint_pts,
                "sprint_pos": sprint_pos_pts,
                "sprint_gained": sprint_gained_pts,
                "sprint_lost": sprint_lost_pts,
                "sprint_overtakes": sprint_ovt_pts,
                "sprint_fl": sprint_fl_pts,
                "race_pos": race_pos_pts,
                "race_gained": race_gained_pts,
                "race_lost": race_lost_pts,
                "race_overtakes": race_ovt_pts,
                "race_fl": race_fl_pts,
                "race_dotd": race_dotd_pts,
                "total": total,
            }
            break

    if not abbrev_to_breakdown:
        return None

    result: dict[int, dict] = {}
    for driver_num, info in driver_info.items():
        abbrev = _get_abbrev_from_name(info.get("name", ""))
        if abbrev and abbrev in abbrev_to_breakdown:
            result[driver_num] = abbrev_to_breakdown[abbrev]

    return (result, has_sprint) if result else None


def get_constructor_points_from_fantasy_data(
    team_ids: set[str],
    round_num: int,
    data_dir: Optional[Path] = None,
) -> Optional[dict[str, float]]:
    """
    Fetch constructor points from fantasy-data and map to team_id.
    Returns None if fetch fails; else dict team_id -> points.
    Uses data_dir if provided; else GitHub.
    """
    abbrev_to_points = fetch_constructor_points_for_round(round_num, data_dir)
    if not abbrev_to_points:
        return None

    result: dict[str, float] = {}
    for team_id in team_ids:
        abbrev = TEAM_TO_ABBREV.get(team_id)
        if abbrev and abbrev in abbrev_to_points:
            result[team_id] = abbrev_to_points[abbrev]

    return result if result else None
