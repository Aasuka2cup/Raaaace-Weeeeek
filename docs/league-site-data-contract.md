# League Site Data Contract

This repository is the data producer for a separate website repository.

The website should rely on the exported package shape, not on raw crawler output under `data/`.

## Contract boundary

- Raw crawler snapshots live under `data/league-results/` or `data/raaaace_weeeeek/`.
- `scripts/export_league_site_data.py` converts those raw files into the stable website-facing package.
- The website repo should only consume files exported under `build/league-site-data/` or the copied equivalent inside the web repo.

## Package layout

```text
league-site-data/
  manifests/
    league-index.json
  leagues/
    league_<league_id>/
      insights/
        overall.json
        chinese-grand-prix.json
      views/
        overall.json
        chinese-grand-prix.json
```

## Manifest contract

File: `manifests/league-index.json`

Top-level fields:

- `schemaVersion`: integer contract version. Current value: `1`.
- `generatedAt`: ISO-8601 UTC timestamp for the export run.
- `sourceRepo`: optional source repository name.
- `sourceCommit`: optional source commit SHA.
- `leagues`: array of exported leagues.

Each `leagues[]` entry contains:

- `leagueId`: string league identifier derived from the source filename.
- `leagueUrl`: public F1 Fantasy league URL.
- `latestViewKey`: default or newest view key for this league.
- `latestViewLabel`: human-readable label for the newest view.
- `views`: array of available views.

Each `views[]` entry contains:

- `key`: stable slug used in URLs and filenames, for example `overall`.
- `label`: human-readable label, for example `Overall`.
- `targetRace`: source race label or `null` for overall standings.
- `teamCount`: number of teams included in the exported view file.
- `scrapedAt`: ISO-8601 UTC timestamp from the crawler snapshot.
- `file`: relative path to the exported view JSON file.
- `insightFile`: optional relative path to the exported insights JSON file for the same view.
- `sourceFile`: original crawler filename.

Consumer guarantees:

- `latestViewKey` always matches one of the listed `views[].key` values.
- `file` always points to a JSON file inside the exported package.
- `insightFile`, when present, points to a JSON file inside the exported package.
- Views are sorted with `overall` first, then other views alphabetically by label.

## View file contract

File pattern: `leagues/league_<league_id>/views/<view_key>.json`

Top-level fields:

- `schemaVersion`: integer contract version. Current value: `1`.
- `exportedAt`: ISO-8601 UTC timestamp for the export run.
- `leagueId`: string league identifier.
- `leagueUrl`: public F1 Fantasy league URL.
- `scrapedAt`: ISO-8601 UTC timestamp from the crawler snapshot.
- `targetRace`: source race label or `null`.
- `viewKey`: stable slug for the selected view.
- `viewLabel`: human-readable view label.
- `teamCount`: number of team rows in `teams`.
- `sourceFile`: original crawler filename.
- `sourceRepo`: optional source repository name.
- `sourceCommit`: optional source commit SHA.
- `teams`: array of exported team entries.

Each `teams[]` entry is guaranteed to include:

- `rank`
- `teamName`
- `manager`
- `socialId` when the source response exposes the manager/user identifier
- `managerTeamNumber` when the source response exposes the manager's team slot, for example `3`
- `managerTeamCount` when the source response exposes the manager's total team count, for example `3`
- `managerTeamLabel` when `managerTeamNumber` is available, for example `T3`
- `lineup.drivers` with exactly 5 names
- `lineup.constructors` with exactly 2 names
- `drivers` with exactly 5 objects containing at least `name`
- `constructors` with exactly 2 objects containing at least `name`
- `chips` object
- `transfer` object

Chip semantics:

- Top-level `chip` / `chips` summarize chip usage detected from the broader captured team responses and may reflect chips used across available game days.
- `selectedRace.chip` / `selectedRace.chips` should be treated as the chip usage for the currently selected grand prix view when the scraper could match chip timing to that race.

## Insights file contract

File pattern: `leagues/league_<league_id>/insights/<view_key>.json`

Purpose:

- Precomputed statistics for the distribution page.
- Heuristic prediction and insight cards for the predictions page.
- Explicit mapping of which website features are powered by the view file versus the insights file.

Top-level fields:

- `schemaVersion`
- `exportedAt`
- `leagueId`
- `leagueUrl`
- `scrapedAt`
- `targetRace`
- `viewKey`
- `viewLabel`
- `teamCount`
- `sourceFile`
- `sourceRepo`
- `sourceCommit`
- `generatedFrom`
- `featureInputs`
- `ownership`
- `groups`
- `teamInsights`
- `predictions`

Key sections:

- `generatedFrom.viewFile`: the sibling view JSON that powers the all-team-picks screen.
- `featureInputs`: per-feature input mapping for:
  - `allTeamPicks`
  - `pickDistribution`
  - `predictions`
- `ownership`: precomputed ownership tables for drivers, constructors, and chips.
- `groups`: template picks, common pairs, and duplicate lineups.
- `teamInsights`: most unique teams, most template teams, and leader-overlap summaries.
- `predictions`: heuristic outputs such as pick momentum, underowned top-team picks, overexposed picks, and leader differentials.

Current interpretation:

- `allTeamPicks` should be rendered from the view file.
- `pickDistribution` can use both browser-derived calculations and `ownership` / `groups` from the insights file.
- `predictions` should use the insights file directly.

The exporter normalizes older crawler snapshots so the website can always expect:

- `chips.used`
- `chips.x3Boost`
- `chips.x3BoostDriver`
- `chips.noNegative`
- `chips.wildcard`
- `chips.limitless`
- `chips.finalFix`
- `chips.autopilot`
- `transfer.made`
- `transfer.allowed`
- `transfer.remaining`
- `transfer.excess`
- `transfer.overLimit`
- `transfer.penaltyPerTransfer`
- `transfer.penaltyPoints`

## Safe fields for the website to depend on

These fields are the intended stable contract:

- Manifest metadata and file references
- `leagueId`, `viewKey`, `viewLabel`, `targetRace`, `teamCount`
- Team identity fields: `rank`, `teamName`, `manager`
- Manager identity field: `socialId`
- Manager multi-team fields: `managerTeamNumber`, `managerTeamCount`, `managerTeamLabel`
- Team lineup fields: `lineup`, `drivers`, `constructors`
- Team strategy fields: `turboDriver`, `x3BoostDriver`, `chip`, `chips`, `transfer`, `excessTransfers`
- Team summary fields already present in crawler output, such as `totalPoints`, `costCap`, and `limitless`
- Insights sections: `featureInputs`, `ownership`, `groups`, `teamInsights`, `predictions`

If the website needs a new field, add it in the exporter and update this contract rather than reading directly from raw crawler JSON.

Notes:

- Current debug evidence suggests `socialId` is shared across multiple teams owned by the same user, so treat it as a manager/user identifier rather than a unique team identifier.

## Validation commands

Validate raw crawler outputs:

```bash
python scripts/validate_league_results.py
```

Validate the exported website package:

```bash
python scripts/export_league_site_data.py
python scripts/validate_league_site_package.py
```
