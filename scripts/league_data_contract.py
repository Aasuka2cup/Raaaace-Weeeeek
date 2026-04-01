from __future__ import annotations

from collections import Counter
import json
import re
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
LEAGUE_FILE_RE = re.compile(r"^league_(?P<league_id>[^_]+?)(?:_(?P<view_slug>.+))?\.json$")
SCHEMA_VERSION = 1
DEFAULT_SITE_DATA_DIR = REPO_ROOT / "build" / "league-site-data"


def resolve_default_league_results_dir() -> Path:
    candidates = [
        REPO_ROOT / "data" / "league-results",
        REPO_ROOT / "data" / "raaaace_weeeeek",
        REPO_ROOT / "data",
    ]
    for candidate in candidates:
        if any(path.is_file() and LEAGUE_FILE_RE.match(path.name) for path in candidate.rglob("league_*.json")):
            return candidate
    return candidates[0]


DEFAULT_LEAGUE_RESULTS_DIR = resolve_default_league_results_dir()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def slugify(value: str | None) -> str:
    if not value:
        return "overall"
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "overall"


def discover_league_result_files(source_dir: Path) -> list[Path]:
    if not source_dir.exists():
        return []
    return sorted(
        path
        for path in source_dir.rglob("league_*.json")
        if path.is_file() and LEAGUE_FILE_RE.match(path.name)
    )


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level JSON value must be an object")
    return data


def parse_league_filename(path: Path) -> dict[str, str | None]:
    match = LEAGUE_FILE_RE.match(path.name)
    if not match:
        raise ValueError(f"{path}: filename must match league_<league_id>[_view].json")
    return {
        "leagueId": match.group("league_id"),
        "viewSlugFromFile": match.group("view_slug"),
    }


def _validate_lineup(team: dict[str, Any], team_label: str, errors: list[str]) -> None:
    lineup = team.get("lineup")
    if not isinstance(lineup, dict):
        errors.append(f"{team_label}: missing object field 'lineup'")
        return

    drivers = lineup.get("drivers")
    constructors = lineup.get("constructors")
    if not isinstance(drivers, list) or len(drivers) != 5:
        errors.append(f"{team_label}: lineup.drivers must contain 5 items")
    if not isinstance(constructors, list) or len(constructors) != 2:
        errors.append(f"{team_label}: lineup.constructors must contain 2 items")


def _validate_optional_manager_team_fields(team: dict[str, Any], team_label: str, errors: list[str]) -> None:
    team_number = team.get("managerTeamNumber")
    team_count = team.get("managerTeamCount")
    team_label_value = team.get("managerTeamLabel")

    if team_number is not None and (not isinstance(team_number, int) or team_number < 1):
        errors.append(f"{team_label}: managerTeamNumber must be a positive integer when present")
    if team_count is not None and (not isinstance(team_count, int) or team_count < 1):
        errors.append(f"{team_label}: managerTeamCount must be a positive integer when present")
    if team_number is not None and team_count is not None and team_number > team_count:
        errors.append(f"{team_label}: managerTeamNumber cannot exceed managerTeamCount")
    if team_label_value is not None and (
        not isinstance(team_label_value, str) or not re.match(r"^T\d+$", team_label_value)
    ):
        errors.append(f"{team_label}: managerTeamLabel must match T<number> when present")
    social_id = team.get("socialId")
    if social_id is not None and (not isinstance(social_id, int) or social_id < 1):
        errors.append(f"{team_label}: socialId must be a positive integer when present")


def _validate_team(team: Any, index: int, errors: list[str]) -> None:
    team_label = f"teams[{index}]"
    if not isinstance(team, dict):
        errors.append(f"{team_label}: team entry must be an object")
        return

    required_fields = [
        "rank",
        "teamName",
        "manager",
        "lineup",
        "drivers",
        "constructors",
    ]
    for field in required_fields:
        if field not in team:
            errors.append(f"{team_label}: missing field '{field}'")

    _validate_lineup(team, team_label, errors)
    _validate_optional_manager_team_fields(team, team_label, errors)

    drivers = team.get("drivers")
    constructors = team.get("constructors")
    if not isinstance(drivers, list) or len(drivers) != 5:
        errors.append(f"{team_label}: drivers must contain 5 items")
    if not isinstance(constructors, list) or len(constructors) != 2:
        errors.append(f"{team_label}: constructors must contain 2 items")


def _validate_chip_info(chips: Any, team_label: str, errors: list[str]) -> None:
    if not isinstance(chips, dict):
        errors.append(f"{team_label}: chips must be an object")
        return

    required_fields = [
        "x3Boost",
        "x3BoostDriver",
        "noNegative",
        "wildcard",
        "limitless",
        "finalFix",
        "autopilot",
        "used",
    ]
    for field in required_fields:
        if field not in chips:
            errors.append(f"{team_label}: chips missing field '{field}'")

    used = chips.get("used")
    if not isinstance(used, list):
        errors.append(f"{team_label}: chips.used must be a list")


def _validate_transfer_info(transfer: Any, team_label: str, errors: list[str]) -> None:
    if not isinstance(transfer, dict):
        errors.append(f"{team_label}: transfer must be an object")
        return

    required_fields = [
        "made",
        "allowed",
        "remaining",
        "excess",
        "overLimit",
        "penaltyPerTransfer",
        "penaltyPoints",
    ]
    for field in required_fields:
        if field not in transfer:
            errors.append(f"{team_label}: transfer missing field '{field}'")


def _validate_named_entries(
    entries: Any,
    expected_count: int,
    entry_type: str,
    team_label: str,
    errors: list[str],
) -> None:
    if not isinstance(entries, list) or len(entries) != expected_count:
        errors.append(f"{team_label}: {entry_type} must contain {expected_count} items")
        return

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{team_label}: {entry_type}[{index}] must be an object")
            continue
        if not isinstance(entry.get("name"), str) or not entry["name"].strip():
            errors.append(f"{team_label}: {entry_type}[{index}].name must be a non-empty string")


def validate_league_payload(payload: dict[str, Any], path: Path, *, allow_empty: bool = False) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    filename_metadata = parse_league_filename(path)

    required_fields = ["leagueUrl", "scrapedAt", "teams"]
    for field in required_fields:
        if field not in payload:
            errors.append(f"{path}: missing top-level field '{field}'")

    teams = payload.get("teams")
    if not isinstance(teams, list):
        errors.append(f"{path}: top-level field 'teams' must be a list")
        teams = []
    elif not teams and not allow_empty:
        errors.append(f"{path}: 'teams' list is empty")

    for index, team in enumerate(teams):
        _validate_team(team, index, errors)

    league_id = filename_metadata["leagueId"]
    target_race = payload.get("targetRace")
    view_key = slugify(target_race)
    view_label = target_race or "Overall"
    team_count = len(teams)

    metadata = {
        "leagueId": league_id,
        "leagueUrl": payload.get("leagueUrl"),
        "targetRace": target_race,
        "viewKey": view_key,
        "viewLabel": view_label,
        "teamCount": team_count,
        "scrapedAt": payload.get("scrapedAt"),
        "sourceFile": path.name,
    }
    return metadata, errors


def validate_exported_team(team: Any, index: int, errors: list[str]) -> None:
    team_label = f"teams[{index}]"
    _validate_team(team, index, errors)
    if not isinstance(team, dict):
        return

    _validate_named_entries(team.get("drivers"), 5, "drivers", team_label, errors)
    _validate_named_entries(team.get("constructors"), 2, "constructors", team_label, errors)
    _validate_chip_info(team.get("chips"), team_label, errors)
    _validate_transfer_info(team.get("transfer"), team_label, errors)


def validate_export_payload(payload: dict[str, Any], path: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    required_fields = [
        "schemaVersion",
        "exportedAt",
        "leagueId",
        "leagueUrl",
        "scrapedAt",
        "viewKey",
        "viewLabel",
        "teamCount",
        "sourceFile",
        "teams",
    ]
    for field in required_fields:
        if field not in payload:
            errors.append(f"{path}: missing top-level field '{field}'")

    if payload.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"{path}: schemaVersion must equal {SCHEMA_VERSION}")
    if not is_utc_timestamp(payload.get("exportedAt")):
        errors.append(f"{path}: exportedAt must be an ISO-8601 UTC timestamp")
    if not is_utc_timestamp(payload.get("scrapedAt")):
        errors.append(f"{path}: scrapedAt must be an ISO-8601 UTC timestamp")
    league_id = payload.get("leagueId")
    view_key = payload.get("viewKey")
    view_label = payload.get("viewLabel")
    if not isinstance(league_id, str) or not league_id:
        errors.append(f"{path}: leagueId must be a non-empty string")
    if not isinstance(view_key, str) or not view_key:
        errors.append(f"{path}: viewKey must be a non-empty string")
    if not isinstance(view_label, str) or not view_label:
        errors.append(f"{path}: viewLabel must be a non-empty string")

    teams = payload.get("teams")
    if not isinstance(teams, list):
        errors.append(f"{path}: top-level field 'teams' must be a list")
        teams = []
    for index, team in enumerate(teams):
        validate_exported_team(team, index, errors)

    team_count = payload.get("teamCount")
    if not isinstance(team_count, int):
        errors.append(f"{path}: teamCount must be an integer")
        team_count = None
    elif team_count != len(teams):
        errors.append(f"{path}: teamCount does not match teams length")

    metadata = {
        "leagueId": league_id,
        "viewKey": view_key,
        "viewLabel": view_label,
        "teamCount": team_count,
        "sourceFile": payload.get("sourceFile"),
    }
    return metadata, errors


def validate_insights_payload(payload: dict[str, Any], path: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    required_fields = [
        "schemaVersion",
        "exportedAt",
        "leagueId",
        "leagueUrl",
        "scrapedAt",
        "viewKey",
        "viewLabel",
        "teamCount",
        "sourceFile",
        "generatedFrom",
        "featureInputs",
        "ownership",
        "groups",
        "teamInsights",
        "predictions",
    ]
    for field in required_fields:
        if field not in payload:
            errors.append(f"{path}: missing top-level field '{field}'")

    if payload.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"{path}: schemaVersion must equal {SCHEMA_VERSION}")
    if not is_utc_timestamp(payload.get("exportedAt")):
        errors.append(f"{path}: exportedAt must be an ISO-8601 UTC timestamp")
    if not is_utc_timestamp(payload.get("scrapedAt")):
        errors.append(f"{path}: scrapedAt must be an ISO-8601 UTC timestamp")

    league_id = payload.get("leagueId")
    view_key = payload.get("viewKey")
    view_label = payload.get("viewLabel")
    if not isinstance(league_id, str) or not league_id:
        errors.append(f"{path}: leagueId must be a non-empty string")
    if not isinstance(view_key, str) or not view_key:
        errors.append(f"{path}: viewKey must be a non-empty string")
    if not isinstance(view_label, str) or not view_label:
        errors.append(f"{path}: viewLabel must be a non-empty string")

    team_count = payload.get("teamCount")
    if not isinstance(team_count, int):
        errors.append(f"{path}: teamCount must be an integer")

    generated_from = payload.get("generatedFrom")
    if not isinstance(generated_from, dict):
        errors.append(f"{path}: generatedFrom must be an object")
    else:
        if not isinstance(generated_from.get("viewFile"), str) or not generated_from.get("viewFile"):
            errors.append(f"{path}: generatedFrom.viewFile must be a non-empty string")
        if not isinstance(generated_from.get("insightFile"), str) or not generated_from.get("insightFile"):
            errors.append(f"{path}: generatedFrom.insightFile must be a non-empty string")

    feature_inputs = payload.get("featureInputs")
    if not isinstance(feature_inputs, dict):
        errors.append(f"{path}: featureInputs must be an object")
    else:
        for field in ["allTeamPicks", "pickDistribution", "predictions"]:
            if field not in feature_inputs:
                errors.append(f"{path}: featureInputs missing field '{field}'")

    ownership = payload.get("ownership")
    if not isinstance(ownership, dict):
        errors.append(f"{path}: ownership must be an object")
    else:
        for field in ["drivers", "constructors", "chips"]:
            if not isinstance(ownership.get(field), list):
                errors.append(f"{path}: ownership.{field} must be a list")

    groups = payload.get("groups")
    if not isinstance(groups, dict):
        errors.append(f"{path}: groups must be an object")
    else:
        template = groups.get("template")
        if not isinstance(template, dict):
            errors.append(f"{path}: groups.template must be an object")
        else:
            if not isinstance(template.get("drivers"), list):
                errors.append(f"{path}: groups.template.drivers must be a list")
            if not isinstance(template.get("constructors"), list):
                errors.append(f"{path}: groups.template.constructors must be a list")
        for field in ["mostCommonDriverPairs", "mostCommonConstructorPairs", "duplicateLineups"]:
            if not isinstance(groups.get(field), list):
                errors.append(f"{path}: groups.{field} must be a list")

    team_insights = payload.get("teamInsights")
    if not isinstance(team_insights, dict):
        errors.append(f"{path}: teamInsights must be an object")
    else:
        for field in ["mostUniqueTeams", "mostTemplateTeams", "leaderOverlap"]:
            if not isinstance(team_insights.get(field), list):
                errors.append(f"{path}: teamInsights.{field} must be a list")

    predictions = payload.get("predictions")
    if not isinstance(predictions, dict):
        errors.append(f"{path}: predictions must be an object")
    else:
        for field in ["method", "topTeamSampleSize", "pickMomentum", "underownedTopPicks", "overexposedPicks", "leaderDifferentials"]:
            if field not in predictions:
                errors.append(f"{path}: predictions missing field '{field}'")
        if not isinstance(predictions.get("pickMomentum"), list):
            errors.append(f"{path}: predictions.pickMomentum must be a list")

    metadata = {
        "leagueId": league_id,
        "viewKey": view_key,
        "viewLabel": view_label,
        "teamCount": team_count,
        "sourceFile": payload.get("sourceFile"),
    }
    return metadata, errors


def build_export_payload(
    payload: dict[str, Any],
    metadata: dict[str, Any],
    *,
    exported_at: str,
    source_repo: str | None = None,
    source_commit: str | None = None,
) -> dict[str, Any]:
    enriched = dict(payload)
    enriched["teams"] = [normalize_team_for_export(team) for team in payload.get("teams", [])]
    enriched["schemaVersion"] = SCHEMA_VERSION
    enriched["exportedAt"] = exported_at
    enriched["leagueId"] = metadata["leagueId"]
    enriched["viewKey"] = metadata["viewKey"]
    enriched["viewLabel"] = metadata["viewLabel"]
    enriched["teamCount"] = metadata["teamCount"]
    enriched["sourceFile"] = metadata["sourceFile"]
    if source_repo:
        enriched["sourceRepo"] = source_repo
    if source_commit:
        enriched["sourceCommit"] = source_commit
    return enriched


def _default_chip_info(team: dict[str, Any]) -> dict[str, Any]:
    limitless = bool(team.get("limitless"))
    x3_boost_driver = team.get("x3BoostDriver")
    x3_boost = bool(x3_boost_driver)
    used: list[str] = []
    if x3_boost:
        used.append("x3 Boost")
    if limitless:
        used.append("Limitless")
    return {
        "x3Boost": x3_boost,
        "x3BoostDriver": x3_boost_driver or None,
        "noNegative": False,
        "wildcard": False,
        "limitless": limitless,
        "finalFix": False,
        "autopilot": False,
        "used": used,
    }


def _default_transfer_info(team: dict[str, Any]) -> dict[str, Any]:
    excess = team.get("excessTransfers")
    if excess is not None:
        excess = int(excess)
    return {
        "made": None,
        "allowed": None,
        "remaining": None,
        "excess": excess,
        "overLimit": bool(excess and excess > 0),
        "penaltyPerTransfer": None,
        "penaltyPoints": None,
    }


def normalize_team_for_export(team: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(team)
    normalized["chips"] = team.get("chips") if isinstance(team.get("chips"), dict) else _default_chip_info(team)
    normalized["transfer"] = team.get("transfer") if isinstance(team.get("transfer"), dict) else _default_transfer_info(team)
    normalized["chip"] = team.get("chip")
    normalized["x3BoostDriver"] = team.get("x3BoostDriver") or normalized["chips"].get("x3BoostDriver")
    normalized["excessTransfers"] = team.get("excessTransfers")
    if normalized["excessTransfers"] is None:
        normalized["excessTransfers"] = normalized["transfer"].get("excess")

    selected_race = team.get("selectedRace")
    if isinstance(selected_race, dict):
        selected_race_normalized = dict(selected_race)
        selected_race_normalized["chips"] = (
            selected_race.get("chips")
            if isinstance(selected_race.get("chips"), dict)
            else normalized["chips"]
        )
        selected_race_normalized["chip"] = selected_race.get("chip", normalized.get("chip"))
        selected_race_normalized["x3BoostDriver"] = selected_race.get("x3BoostDriver", normalized["x3BoostDriver"])
        selected_race_normalized["transfer"] = (
            selected_race.get("transfer")
            if isinstance(selected_race.get("transfer"), dict)
            else normalized["transfer"]
        )
        selected_race_normalized["excessTransfers"] = selected_race.get(
            "excessTransfers",
            normalized["excessTransfers"],
        )
        normalized["selectedRace"] = selected_race_normalized

    return normalized


def _percentage(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100, 1)


def _team_reference(team: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": team.get("rank"),
        "teamName": team.get("teamName"),
        "manager": team.get("manager"),
        "socialId": team.get("socialId"),
        "managerTeamNumber": team.get("managerTeamNumber"),
        "managerTeamCount": team.get("managerTeamCount"),
        "managerTeamLabel": team.get("managerTeamLabel"),
        "totalPoints": team.get("totalPoints"),
    }


def _team_pick_names(team: dict[str, Any], key: str) -> list[str]:
    values = team.get("lineup", {}).get(key, [])
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str) and value]


def _top_team_sample(teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not teams:
        return []
    sample_size = max(1, len(teams) // 4)
    return sorted(teams, key=lambda team: (team.get("rank", 10**9), team.get("teamName") or ""))[:sample_size]


def _pick_distribution(
    names_by_team: list[list[str]],
    *,
    top_names_by_team: list[list[str]] | None = None,
    turbo_counter: Counter[str] | None = None,
    x3_counter: Counter[str] | None = None,
) -> list[dict[str, Any]]:
    team_count = len(names_by_team)
    counter = Counter(name for names in names_by_team for name in names)
    top_counter = Counter(name for names in (top_names_by_team or []) for name in names)
    turbo_counter = turbo_counter or Counter()
    x3_counter = x3_counter or Counter()

    entries: list[dict[str, Any]] = []
    for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        top_count = top_counter.get(name, 0)
        entries.append(
            {
                "name": name,
                "count": count,
                "percentage": _percentage(count, team_count),
                "topTeamCount": top_count,
                "topTeamPercentage": _percentage(top_count, len(top_names_by_team or [])),
                "turboCount": turbo_counter.get(name, 0),
                "x3BoostCount": x3_counter.get(name, 0),
            }
        )
    return entries


def _pair_distribution(names_by_team: list[list[str]], *, pair_size: int = 2) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, ...]] = Counter()
    for names in names_by_team:
        for combo in combinations(sorted(set(names)), pair_size):
            counter[combo] += 1

    entries: list[dict[str, Any]] = []
    for names, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        if count < 2:
            continue
        entries.append(
            {
                "names": list(names),
                "count": count,
                "percentage": _percentage(count, len(names_by_team)),
            }
        )
    return entries[:10]


def build_insights_payload(
    payload: dict[str, Any],
    metadata: dict[str, Any],
    *,
    exported_at: str,
    view_file: str,
    insight_file: str,
    source_repo: str | None = None,
    source_commit: str | None = None,
) -> dict[str, Any]:
    teams = [normalize_team_for_export(team) for team in payload.get("teams", [])]
    team_count = len(teams)
    top_teams = _top_team_sample(teams)
    driver_names = [_team_pick_names(team, "drivers") for team in teams]
    constructor_names = [_team_pick_names(team, "constructors") for team in teams]
    top_driver_names = [_team_pick_names(team, "drivers") for team in top_teams]
    top_constructor_names = [_team_pick_names(team, "constructors") for team in top_teams]

    turbo_counter = Counter(
        team.get("turboDriver")
        for team in teams
        if isinstance(team.get("turboDriver"), str) and team.get("turboDriver")
    )
    x3_counter = Counter(
        team.get("x3BoostDriver")
        for team in teams
        if isinstance(team.get("x3BoostDriver"), str) and team.get("x3BoostDriver")
    )

    driver_distribution = _pick_distribution(
        driver_names,
        top_names_by_team=top_driver_names,
        turbo_counter=turbo_counter,
        x3_counter=x3_counter,
    )
    constructor_distribution = _pick_distribution(
        constructor_names,
        top_names_by_team=top_constructor_names,
    )

    chip_counter = Counter(
        chip_name
        for team in teams
        for chip_name in team.get("chips", {}).get("used", [])
        if isinstance(chip_name, str) and chip_name
    )
    chip_distribution = [
        {
            "name": name,
            "count": count,
            "percentage": _percentage(count, team_count),
        }
        for name, count in sorted(chip_counter.items(), key=lambda item: (-item[1], item[0]))
    ]

    driver_lookup = {entry["name"]: entry for entry in driver_distribution}
    constructor_lookup = {entry["name"]: entry for entry in constructor_distribution}

    template_drivers = [entry["name"] for entry in driver_distribution[:5]]
    template_constructors = [entry["name"] for entry in constructor_distribution[:2]]
    leader_team = min(teams, key=lambda team: (team.get("rank", 10**9), team.get("teamName") or ""), default=None)
    leader_driver_set = set(_team_pick_names(leader_team, "drivers")) if leader_team else set()
    leader_constructor_set = set(_team_pick_names(leader_team, "constructors")) if leader_team else set()

    lineup_groups: dict[tuple[tuple[str, ...], tuple[str, ...]], list[dict[str, Any]]] = {}
    team_uniqueness: list[dict[str, Any]] = []
    team_template_overlap: list[dict[str, Any]] = []
    leader_overlap: list[dict[str, Any]] = []
    top_owned_threshold = max(2, (team_count + 4) // 5)

    for team in teams:
        driver_set = set(_team_pick_names(team, "drivers"))
        constructor_set = set(_team_pick_names(team, "constructors"))
        lineup_key = (tuple(sorted(driver_set)), tuple(sorted(constructor_set)))
        lineup_groups.setdefault(lineup_key, []).append(team)

        unique_driver_names = sorted(
            name
            for name in driver_set
            if driver_lookup.get(name, {}).get("count", 0) <= 1
        )
        unique_constructor_names = sorted(
            name
            for name in constructor_set
            if constructor_lookup.get(name, {}).get("count", 0) <= 1
        )
        low_owned_driver_names = sorted(
            name
            for name in driver_set
            if driver_lookup.get(name, {}).get("count", 0) <= top_owned_threshold
        )
        low_owned_constructor_names = sorted(
            name
            for name in constructor_set
            if constructor_lookup.get(name, {}).get("count", 0) <= top_owned_threshold
        )

        average_ownership = round(
            sum(driver_lookup.get(name, {}).get("percentage", 0.0) for name in driver_set)
            + sum(constructor_lookup.get(name, {}).get("percentage", 0.0) for name in constructor_set),
            1,
        ) / 7 if team_count else 0.0

        team_uniqueness.append(
            {
                **_team_reference(team),
                "uniqueDriverCount": len(unique_driver_names),
                "uniqueConstructorCount": len(unique_constructor_names),
                "uniquePickCount": len(unique_driver_names) + len(unique_constructor_names),
                "lowOwnedDrivers": low_owned_driver_names,
                "lowOwnedConstructors": low_owned_constructor_names,
                "averagePickOwnership": round(average_ownership, 1),
            }
        )

        matching_drivers = sorted(driver_set.intersection(template_drivers))
        matching_constructors = sorted(constructor_set.intersection(template_constructors))
        overlap_count = len(matching_drivers) + len(matching_constructors)
        team_template_overlap.append(
            {
                **_team_reference(team),
                "matchingDrivers": matching_drivers,
                "matchingConstructors": matching_constructors,
                "overlapCount": overlap_count,
                "overlapPercentage": _percentage(overlap_count, 7),
            }
        )

        leader_matching_drivers = sorted(driver_set.intersection(leader_driver_set))
        leader_matching_constructors = sorted(constructor_set.intersection(leader_constructor_set))
        leader_overlap.append(
            {
                **_team_reference(team),
                "matchingDrivers": leader_matching_drivers,
                "matchingConstructors": leader_matching_constructors,
                "overlapCount": len(leader_matching_drivers) + len(leader_matching_constructors),
                "overlapPercentage": _percentage(len(leader_matching_drivers) + len(leader_matching_constructors), 7),
            }
        )

    duplicate_lineups = []
    for lineup_key, grouped_teams in sorted(
        lineup_groups.items(),
        key=lambda item: (-len(item[1]), item[0]),
    ):
        if len(grouped_teams) < 2:
            continue
        drivers_key, constructors_key = lineup_key
        duplicate_lineups.append(
            {
                "drivers": list(drivers_key),
                "constructors": list(constructors_key),
                "teamCount": len(grouped_teams),
                "teams": [_team_reference(team) for team in sorted(grouped_teams, key=lambda team: team.get("rank", 10**9))],
            }
        )

    pick_momentum = []
    for entry in driver_distribution:
        momentum_score = round(entry["topTeamPercentage"] - entry["percentage"], 1)
        pick_momentum.append(
            {
                "name": entry["name"],
                "type": "driver",
                "overallCount": entry["count"],
                "overallPercentage": entry["percentage"],
                "topTeamCount": entry["topTeamCount"],
                "topTeamPercentage": entry["topTeamPercentage"],
                "momentumScore": momentum_score,
            }
        )
    for entry in constructor_distribution:
        momentum_score = round(entry["topTeamPercentage"] - entry["percentage"], 1)
        pick_momentum.append(
            {
                "name": entry["name"],
                "type": "constructor",
                "overallCount": entry["count"],
                "overallPercentage": entry["percentage"],
                "topTeamCount": entry["topTeamCount"],
                "topTeamPercentage": entry["topTeamPercentage"],
                "momentumScore": momentum_score,
            }
        )
    pick_momentum.sort(key=lambda item: (-item["momentumScore"], -item["topTeamCount"], item["name"]))

    underowned_top_picks = [
        entry
        for entry in pick_momentum
        if entry["topTeamCount"] > 0 and entry["overallPercentage"] <= 35.0 and entry["momentumScore"] > 0
    ][:10]
    overexposed_picks = [
        entry
        for entry in sorted(pick_momentum, key=lambda item: (item["momentumScore"], -item["overallPercentage"], item["name"]))
        if entry["overallPercentage"] >= 40.0 and entry["momentumScore"] < 0
    ][:10]

    leader_differentials = []
    if leader_team:
        for name in sorted(leader_driver_set):
            distribution = driver_lookup.get(name)
            if distribution and distribution["percentage"] <= 35.0:
                leader_differentials.append(
                    {
                        "name": name,
                        "type": "driver",
                        "overallCount": distribution["count"],
                        "overallPercentage": distribution["percentage"],
                    }
                )
        for name in sorted(leader_constructor_set):
            distribution = constructor_lookup.get(name)
            if distribution and distribution["percentage"] <= 35.0:
                leader_differentials.append(
                    {
                        "name": name,
                        "type": "constructor",
                        "overallCount": distribution["count"],
                        "overallPercentage": distribution["percentage"],
                    }
                )

    insights_payload = {
        "schemaVersion": SCHEMA_VERSION,
        "exportedAt": exported_at,
        "leagueId": metadata["leagueId"],
        "leagueUrl": payload.get("leagueUrl"),
        "scrapedAt": payload.get("scrapedAt"),
        "targetRace": payload.get("targetRace"),
        "viewKey": metadata["viewKey"],
        "viewLabel": metadata["viewLabel"],
        "teamCount": metadata["teamCount"],
        "sourceFile": metadata["sourceFile"],
        "generatedFrom": {
            "viewFile": view_file,
            "insightFile": insight_file,
        },
        "featureInputs": {
            "allTeamPicks": {
                "source": "view",
                "viewFile": view_file,
            },
            "pickDistribution": {
                "source": "view+insights",
                "viewFile": view_file,
                "insightFile": insight_file,
            },
            "predictions": {
                "source": "insights",
                "insightFile": insight_file,
            },
        },
        "ownership": {
            "drivers": driver_distribution,
            "constructors": constructor_distribution,
            "chips": chip_distribution,
        },
        "groups": {
            "template": {
                "drivers": template_drivers,
                "constructors": template_constructors,
            },
            "mostCommonDriverPairs": _pair_distribution(driver_names),
            "mostCommonConstructorPairs": _pair_distribution(constructor_names),
            "duplicateLineups": duplicate_lineups[:10],
        },
        "teamInsights": {
            "mostUniqueTeams": sorted(
                team_uniqueness,
                key=lambda entry: (-entry["uniquePickCount"], entry["averagePickOwnership"], entry["rank"]),
            )[:10],
            "mostTemplateTeams": sorted(
                team_template_overlap,
                key=lambda entry: (-entry["overlapCount"], entry["rank"]),
            )[:10],
            "leaderOverlap": sorted(
                leader_overlap,
                key=lambda entry: (-entry["overlapCount"], entry["rank"]),
            )[:10],
        },
        "predictions": {
            "method": "heuristic",
            "topTeamSampleSize": len(top_teams),
            "pickMomentum": pick_momentum[:15],
            "underownedTopPicks": underowned_top_picks,
            "overexposedPicks": overexposed_picks,
            "leaderDifferentials": leader_differentials[:10],
        },
    }
    if source_repo:
        insights_payload["sourceRepo"] = source_repo
    if source_commit:
        insights_payload["sourceCommit"] = source_commit
    return insights_payload


def build_manifest(
    league_views: dict[str, list[dict[str, Any]]],
    *,
    generated_at: str,
    source_repo: str | None = None,
    source_commit: str | None = None,
) -> dict[str, Any]:
    leagues: list[dict[str, Any]] = []

    for league_id in sorted(league_views):
        views = sorted(
            league_views[league_id],
            key=lambda entry: (
                0 if entry["viewKey"] == "overall" else 1,
                entry["viewLabel"].lower(),
            ),
        )
        latest_view = max(
            views,
            key=lambda entry: (
                entry.get("scrapedAt") or "",
                entry["viewKey"],
            ),
        )
        leagues.append(
            {
                "leagueId": league_id,
                "leagueUrl": views[0]["leagueUrl"],
                "latestViewKey": latest_view["viewKey"],
                "latestViewLabel": latest_view["viewLabel"],
                "views": [
                    {
                        "key": view["viewKey"],
                        "label": view["viewLabel"],
                        "targetRace": view["targetRace"],
                        "teamCount": view["teamCount"],
                        "scrapedAt": view["scrapedAt"],
                        "file": view["file"],
                        "insightFile": view.get("insightFile"),
                        "sourceFile": view["sourceFile"],
                    }
                    for view in views
                ],
            }
        )

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "leagues": leagues,
    }
    if source_repo:
        manifest["sourceRepo"] = source_repo
    if source_commit:
        manifest["sourceCommit"] = source_commit
    return manifest


def validate_manifest_payload(manifest: dict[str, Any], root_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if manifest.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"{root_dir}: manifest schemaVersion must equal {SCHEMA_VERSION}")
    if not is_utc_timestamp(manifest.get("generatedAt")):
        errors.append(f"{root_dir}: manifest generatedAt must be an ISO-8601 UTC timestamp")

    leagues = manifest.get("leagues")
    if not isinstance(leagues, list):
        errors.append(f"{root_dir}: manifest leagues must be a list")
        return [], errors

    referenced_files: list[dict[str, Any]] = []
    for league_index, league in enumerate(leagues):
        league_label = f"leagues[{league_index}]"
        if not isinstance(league, dict):
            errors.append(f"{root_dir}: {league_label} must be an object")
            continue

        for field in ["leagueId", "leagueUrl", "latestViewKey", "latestViewLabel", "views"]:
            if field not in league:
                errors.append(f"{root_dir}: {league_label} missing field '{field}'")

        views = league.get("views")
        if not isinstance(views, list) or not views:
            errors.append(f"{root_dir}: {league_label}.views must be a non-empty list")
            continue

        view_keys: set[str] = set()
        for view_index, view in enumerate(views):
            view_label = f"{league_label}.views[{view_index}]"
            if not isinstance(view, dict):
                errors.append(f"{root_dir}: {view_label} must be an object")
                continue
            for field in ["key", "label", "teamCount", "scrapedAt", "file", "sourceFile"]:
                if field not in view:
                    errors.append(f"{root_dir}: {view_label} missing field '{field}'")

            key = view.get("key")
            file_path = view.get("file")
            insight_file_path = view.get("insightFile")
            if isinstance(key, str):
                view_keys.add(key)
            if not is_utc_timestamp(view.get("scrapedAt")):
                errors.append(f"{root_dir}: {view_label}.scrapedAt must be an ISO-8601 UTC timestamp")
            if not isinstance(file_path, str) or not file_path:
                errors.append(f"{root_dir}: {view_label}.file must be a non-empty string")
                continue

            full_path = root_dir / file_path
            if not full_path.is_file():
                errors.append(f"{root_dir}: referenced export file does not exist: {file_path}")
                continue

            referenced_files.append(
                {
                    "kind": "view",
                    "leagueId": league.get("leagueId"),
                    "viewKey": key,
                    "file": full_path,
                    "relativeFile": file_path,
                }
            )

            if insight_file_path is not None:
                if not isinstance(insight_file_path, str) or not insight_file_path:
                    errors.append(f"{root_dir}: {view_label}.insightFile must be a non-empty string when present")
                else:
                    full_insight_path = root_dir / insight_file_path
                    if not full_insight_path.is_file():
                        errors.append(f"{root_dir}: referenced insight file does not exist: {insight_file_path}")
                    else:
                        referenced_files.append(
                            {
                                "kind": "insight",
                                "leagueId": league.get("leagueId"),
                                "viewKey": key,
                                "file": full_insight_path,
                                "relativeFile": insight_file_path,
                            }
                        )

        latest_view_key = league.get("latestViewKey")
        if isinstance(latest_view_key, str) and latest_view_key not in view_keys:
            errors.append(f"{root_dir}: {league_label}.latestViewKey must reference one of the listed views")

    return referenced_files, errors

