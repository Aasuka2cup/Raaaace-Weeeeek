# Website Repo Integration Guide

This repository should stay focused on data collection, normalization, validation, and export.

The separate website repository should own UI, routing, visualizations, styling, and deployment.

## Recommended repo split

Analysis repo responsibilities:

- Run the crawler locally when login is required.
- Commit refreshed league snapshot JSON files.
- Validate raw data and export a stable site package.
- Optionally publish the exported package into the website repo.

Website repo responsibilities:

- Store the copied site package under a static path such as `public/data/league-data/`.
- Fetch the manifest first, then fetch the selected view JSON file.
- Render league rankings, lineup cards, charts, filters, and comparisons.
- Deploy to Netlify independently of crawler changes.

## Suggested website repo structure

```text
your-web-repo/
  public/
    data/
      league-data/
        manifests/
          league-index.json
        leagues/
          league_871710/
            insights/
              overall.json
              chinese-grand-prix.json
            views/
              overall.json
              chinese-grand-prix.json
  src/
    lib/
      league-data.ts
    pages/
    components/
```

## Recommended loading flow

1. Fetch `public/data/league-data/manifests/league-index.json`.
2. Let the user choose a league from `leagues[]`.
3. Default to that league's `latestViewKey`.
4. Resolve the matching `views[].file`.
5. Fetch the matching `views[].insightFile` when present.
6. Render `teams[]` from the selected view file.
7. Render distribution and prediction screens from the insights file.

## Example consumer logic

This is intentionally framework-agnostic so the website repo can use plain JS or React.

```js
export async function loadLeagueManifest(basePath = "/data/league-data") {
  const response = await fetch(`${basePath}/manifests/league-index.json`);
  if (!response.ok) {
    throw new Error(`Failed to load league manifest: ${response.status}`);
  }
  return response.json();
}

export async function loadLeagueView(file, basePath = "/data/league-data") {
  const response = await fetch(`${basePath}/${file}`);
  if (!response.ok) {
    throw new Error(`Failed to load league view: ${response.status}`);
  }
  return response.json();
}

export async function loadLeagueInsights(file, basePath = "/data/league-data") {
  const response = await fetch(`${basePath}/${file}`);
  if (!response.ok) {
    throw new Error(`Failed to load league insights: ${response.status}`);
  }
  return response.json();
}

export async function loadDefaultLeaguePage(basePath) {
  const manifest = await loadLeagueManifest(basePath);
  const league = manifest.leagues[0];
  const defaultView = league.views.find((view) => view.key === league.latestViewKey);
  const viewData = await loadLeagueView(defaultView.file, basePath);
  const insightsData = defaultView.insightFile
    ? await loadLeagueInsights(defaultView.insightFile, basePath)
    : null;
  return { manifest, league, viewData, insightsData };
}
```

## Screen model

The first website version should be organized around three screens:

1. All team picks
2. Pick distribution
3. Predictions and insights

Recommended inputs per screen:

- All team picks:
  - primary input: view file
  - key fields: `teams`, `teamName`, `manager`, `socialId`, `managerTeamNumber`, `managerTeamCount`, `managerTeamLabel`, `lineup`, `drivers`, `constructors`, `chips`, `transfer`
- Pick distribution:
  - primary inputs: insights file plus optional browser-derived summaries from `teams`
  - key fields: `ownership`, `groups`
- Predictions and insights:
  - primary input: insights file
  - key fields: `teamInsights`, `predictions`

## Frontend modeling suggestions

The website repo should treat these structures as its primary inputs:

- `manifest.leagues[]` for navigation and available snapshots
- `viewData.teams[]` for tables and cards
- `team.socialId` for grouping multiple entries that belong to the same user or manager
- `team.managerTeamLabel` for badges like `T1`, `T2`, `T3` when a manager has multiple teams
- `insightsData.ownership` for precomputed ownership and distribution charts
- `insightsData.groups` for duplicate lineups and template analysis
- `insightsData.teamInsights` for unique-team and leader-overlap sections
- `insightsData.predictions` for heuristic prediction cards
- `team.lineup` for compact roster display
- `team.drivers` and `team.constructors` for richer row detail
- `team.chips` and `team.transfer` for strategy annotations

## Light vs heavy metrics

Keep these browser-derived in the website:

- Sorting and filtering of `teams[]`
- Simple ownership percentages recalculated from `teams[]` if needed for UI interactions
- Lightweight similarity views for currently loaded data only

Keep these precomputed in the analysis repo:

- Template team definition
- Duplicate lineup grouping
- Most common driver and constructor pairs
- Most unique teams
- Leader overlap tables
- Heuristic prediction cards such as momentum, underowned top-team picks, and overexposed picks

## Good visualization starting points

- League standings table with sorting and filtering
- Team detail drawer showing the 5 drivers and 2 constructors
- View selector for `overall` vs race-specific snapshots
- Chip usage summary counts
- Constructor and driver popularity charts derived from `teams[]`
- Template-versus-differential cards
- Duplicate lineup groups
- Heuristic prediction cards from `insightsData.predictions`

## Deployment notes

- Netlify can serve the copied JSON files as static assets with no backend.
- The website repo does not need Python or Playwright.
- A frontend rebuild is enough whenever the exported JSON changes.

## Automation boundary

The website repo should not try to run the crawler.

Recommended automation:

1. Run the crawler locally in this analysis repo when needed.
2. Commit refreshed `league_*.json` snapshots here.
3. Let the publish workflow export and sync the static package into the website repo.
4. Let Netlify deploy the website repo on push.
