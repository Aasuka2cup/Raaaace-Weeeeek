"""
Data fetcher for F1 Fantasy Strategist.

Fetches race results from F1 API (f1api.dev) - the same data source used by
https://f1fantasytools.com/statistics

Driver/constructor prices from fallback JSON (f1api.dev does not provide fantasy prices).
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

# F1 API - data source for f1fantasytools.com
F1API_BASE = "https://f1api.dev/api"

# OpenF1 API - overtake data (f1api.dev has no overtakes)
OPENF1_BASE = "https://api.openf1.org/v1"

# Round/venue abbreviations -> round number (2026 calendar order)
ROUND_ALIASES = {
    "1": 1, "r1": 1, "aus": 1, "australia": 1, "melbourne": 1, "albert_park": 1,
    "2": 2, "r2": 2, "chn": 2, "china": 2, "shanghai": 2,
    "3": 3, "r3": 3, "jpn": 3, "japan": 3, "suzuka": 3,
    "4": 4, "r4": 4, "bah": 4, "bahrain": 4, "sakhir": 4,
    "5": 5, "r5": 5, "sau": 5, "saudi": 5, "jeddah": 5,
    "6": 6, "r6": 6, "mia": 6, "miami": 6,
    "7": 7, "r7": 7, "imo": 7, "imola": 7,
    "8": 8, "r8": 8, "mon": 8, "monaco": 8, "monte_carlo": 8,
    "9": 9, "r9": 9, "esp": 9, "spain": 9, "barcelona": 9, "catalunya": 9,
    "10": 10, "r10": 10, "can": 10, "canada": 10, "montreal": 10,
    "11": 11, "r11": 11, "aut": 11, "austria": 11, "spielberg": 11,
    "12": 12, "r12": 12, "gbr": 12, "britain": 12, "silverstone": 12,
    "13": 13, "r13": 13, "hun": 13, "hungary": 13, "budapest": 13, "hungaroring": 13,
    "14": 14, "r14": 14, "bel": 14, "belgium": 14, "spa": 14,
    "15": 15, "r15": 15, "ned": 15, "netherlands": 15, "zandvoort": 15,
    "16": 16, "r16": 16, "ita": 16, "italy": 16, "monza": 16,
    "17": 17, "r17": 17, "aze": 17, "azerbaijan": 17, "baku": 17,
    "18": 18, "r18": 18, "sgp": 18, "singapore": 18,
    "19": 19, "r19": 19, "usa": 19, "austin": 19, "cota": 19,
    "20": 20, "r20": 20, "mex": 20, "mexico": 20,
    "21": 21, "r21": 21, "bra": 21, "brazil": 21, "interlagos": 21, "sao_paulo": 21,
    "22": 22, "r22": 22, "usa_lv": 22, "vegas": 22, "las_vegas": 22,
    "23": 23, "r23": 23, "qat": 23, "qatar": 23, "lusail": 23,
    "24": 24, "r24": 24, "uae": 24, "abu_dhabi": 24, "yas_marina": 24,
}


def resolve_round(round_input: str) -> Optional[int]:
    """Resolve round input (e.g. 'r1', 'aus', '1', 'r1 aus') to round number."""
    if not round_input:
        return None
    # Support "r1 aus" - try first token, then full string
    s = str(round_input).strip().lower()
    for part in [s.split()[0] if s.split() else s, s.replace(" ", "_")]:
        if part:
            n = ROUND_ALIASES.get(part)
            if n is not None:
                return n
    return None


def fetch_f1api_race(year: int, round_num: int) -> Optional[dict]:
    """Fetch race results for a given round."""
    url = f"{F1API_BASE}/{year}/{round_num}/race"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning("F1 API race fetch failed: %s", e)
        return None


def fetch_f1api_qualy(year: int, round_num: int) -> Optional[dict]:
    """Fetch qualifying results for a given round."""
    url = f"{F1API_BASE}/{year}/{round_num}/qualy"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning("F1 API qualy fetch failed: %s", e)
        return None


def fetch_f1api_sprint_race(year: int, round_num: int) -> Optional[dict]:
    """Fetch sprint race results (if round has sprint)."""
    url = f"{F1API_BASE}/{year}/{round_num}/sprint/race"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("races", {}).get("sprintResults"):
            return data
        return None
    except requests.RequestException:
        return None


def fetch_f1api_last_race() -> Optional[dict]:
    """Fetch the most recent race results (current season)."""
    url = f"{F1API_BASE}/current/last/race"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning("F1 API last race fetch failed: %s", e)
        return None


def fetch_f1api_last_qualy() -> Optional[dict]:
    """Fetch qualifying for the most recent race."""
    url = f"{F1API_BASE}/current/last/qualy"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning("F1 API last qualy fetch failed: %s", e)
        return None


def parse_f1api_race_results(data: dict) -> tuple[dict, dict, dict, Optional[int]]:
    """
    Parse f1api race response into driver_number -> position, grid, and driver info.
    Returns (race_positions, race_grid, driver_info, fastest_lap_driver_number).
    """
    results = data.get("races", {}).get("results", [])
    circuit = data.get("races", {}).get("circuit", {})
    circuit_name = circuit.get("circuitName", "Unknown") if circuit else "Unknown"

    positions: dict[int, int] = {}
    grid: dict[int, int] = {}
    driver_info: dict[int, dict] = {}
    fastest_driver_id = None
    best_lap_time = None

    for r in results:
        driver = r.get("driver", {})
        team = r.get("team", {})
        num = driver.get("number")
        if num is None:
            continue

        # Position: "NC", "-" = DNF, else int
        pos_str = r.get("position")
        if pos_str in ("NC", "-", None):
            positions[num] = 99  # DNF marker
        else:
            try:
                positions[num] = int(pos_str)
            except (ValueError, TypeError):
                positions[num] = 99

        # Grid position
        g = r.get("grid")
        if g is not None:
            try:
                grid[num] = int(g)
            except (ValueError, TypeError):
                grid[num] = 20

        name = f"{driver.get('name', '')} {driver.get('surname', '')}".strip()
        driver_info[num] = {
            "name": name or "Unknown",
            "team_name": team.get("teamName", "Unknown"),
            "team_id": team.get("teamId", "unknown"),
        }

        # Fastest lap: compare fastLap times (string comparison works for M:SS.mmm format)
        lap = r.get("fastLap")
        if lap and r.get("retired") is None and positions.get(num, 99) <= 20:
            if best_lap_time is None or lap < best_lap_time:
                best_lap_time = lap
                fastest_driver_id = num  # Use driver number for consistency

    return positions, grid, driver_info, fastest_driver_id


def parse_f1api_qualy_results(data: dict) -> tuple[dict[int, int], dict[int, dict]]:
    """Parse f1api qualy response. Returns (positions, driver_info)."""
    results = data.get("races", {}).get("qualyResults", [])
    positions: dict[int, int] = {}
    driver_info: dict[int, dict] = {}

    for r in results:
        driver = r.get("driver", {})
        team = r.get("team", {})
        num = driver.get("number")
        if num is None:
            continue

        # No time set in Q1 = NC/DSQ penalty (-5 pts)
        q1 = r.get("q1")
        if q1 in (None, "", "-"):
            positions[num] = 99  # NC/No time set
        else:
            grid_pos = r.get("gridPosition")
            if grid_pos not in (None, "-", ""):
                try:
                    positions[num] = int(grid_pos)
                except (ValueError, TypeError):
                    positions[num] = 99
            else:
                positions[num] = 99  # DNQ

        name = f"{driver.get('name', '')} {driver.get('surname', '')}".strip()
        driver_info[num] = {
            "name": name or "Unknown",
            "team_name": team.get("teamName", "Unknown"),
            "team_id": team.get("teamId", "unknown"),
        }

    return positions, driver_info


def fetch_openf1_overtakes(year: int, round_num: int) -> dict[int, int]:
    """
    Fetch overtake counts per driver from OpenF1 API.
    Returns driver_number -> overtake count. Empty dict on failure.
    OpenF1 has overtake data from 2023 onward; f1api.dev has none.
    """
    try:
        sessions_url = f"{OPENF1_BASE}/sessions?year={year}&session_name=Race"
        resp = requests.get(sessions_url, timeout=15)
        resp.raise_for_status()
        sessions = resp.json()
        if not sessions:
            return {}
        # Sort by date_start; round 1 = first race, etc.
        sessions.sort(key=lambda s: s.get("date_start", ""))
        if round_num < 1 or round_num > len(sessions):
            return {}
        session_key = sessions[round_num - 1].get("session_key")
        if session_key is None:
            return {}
        overtakes_url = f"{OPENF1_BASE}/overtakes?session_key={session_key}"
        resp = requests.get(overtakes_url, timeout=15)
        resp.raise_for_status()
        overtakes = resp.json()
        counts: dict[int, int] = {}
        for o in overtakes:
            num = o.get("overtaking_driver_number")
            if num is not None:
                counts[num] = counts.get(num, 0) + 1
        return counts
    except requests.RequestException as e:
        logger.debug("OpenF1 overtakes fetch failed: %s", e)
        return {}


def load_fallback_prices(path: Optional[Path] = None) -> Optional[dict]:
    """
    Load driver/constructor prices from a local JSON file.
    f1api.dev does not provide fantasy prices - use fallback from f1fantasytools.com or manual update.
    """
    if path is None:
        path = Path(__file__).parent.parent / "data" / "fallback_prices.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)
