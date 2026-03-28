# F1 Fantasy Strategist

Calculate the best possible F1 Fantasy team for the last race based on actual results.

## Rules Reference

- **Team composition**: 5 drivers + 2 constructors, $100M budget
- **Scoring**: [Game Rules](https://fantasy.formula1.com/en/game-rules)
- **How to play**: [How to Play](https://fantasy.formula1.com/en/how-to-play)

## Data Sources

1. **F1 API** ([f1api.dev](https://f1api.dev)) – Race results (qualifying, sprint, race)
   - Same data source as [f1fantasytools.com/statistics](https://f1fantasytools.com/statistics)
2. **Fantasy points & overtakes** – local snapshots under `data/fantasy-data` or [JoshCBruce/fantasy-data](https://github.com/JoshCBruce/fantasy-data)
   - **Default**: fetched from GitHub
   - **Local snapshot**: use `--data-dir data/fantasy-data/latest`
   - Falls back to computed points and [OpenF1](https://api.openf1.org) overtakes when no fantasy-data
3. **Fallback prices** – `data/fallback_prices.json` (update from f1fantasytools.com)

## Setup

```bash
pip install -r requirements.txt

# Optional: install Playwright tooling for the league crawler
cd scripts && npm install && cd ..
```

## Usage

```bash
# Analyze the last completed race
python main.py

# Specify a round by number or venue
python main.py --round r1        # Round 1 (Australia)
python main.py --round aus       # Same, by venue
python main.py --round monaco    # Monaco GP
python main.py -r "r1 aus"      # Round 1

# Specify season year
python main.py --year 2026 --round 1

# Data source mode: use historical data to predict optimal team
python main.py --round monaco --mode lastyear   # Same race last season
python main.py --round monaco --mode lastrace   # Most recent race this season
python main.py --round monaco --mode target     # Target round (default)

# Use local fantasy-data snapshot
python main.py --data-dir data/fantasy-data/latest

# Verbose output
python main.py -v
```

### Supported round/venue names

`--round` accepts a number (1–24), `r1`–`r24`, or venue name:

| Round | Venue names |
|-------|-------------|
| 1 | aus, australia, melbourne |
| 2 | chn, china, shanghai |
| 3 | jpn, japan, suzuka |
| 4 | bah, bahrain, sakhir |
| 5 | sau, saudi, jeddah |
| 6 | mia, miami |
| 7 | imo, imola |
| 8 | mon, monaco, monte_carlo |
| 9 | esp, spain, barcelona, catalunya |
| 10 | can, canada, montreal |
| 11 | aut, austria, spielberg |
| 12 | gbr, britain, silverstone |
| 13 | hun, hungary, budapest, hungaroring |
| 14 | bel, belgium, spa |
| 15 | ned, netherlands, zandvoort |
| 16 | ita, italy, monza |
| 17 | aze, azerbaijan, baku |
| 18 | sgp, singapore |
| 19 | usa, austin, cota |
| 20 | mex, mexico |
| 21 | bra, brazil, interlagos, sao_paulo |
| 22 | vegas, las_vegas |
| 23 | qat, qatar, lusail |
| 24 | uae, abu_dhabi, yas_marina |

### Mode options

| Mode | Description |
|------|-------------|
| `target` | Use data from the target round (default) |
| `lastyear` | Use data from the same round last season (e.g. Monaco 2026 → Monaco 2025) |
| `lastrace` | Use data from the most recent race (e.g. Monaco → previous round; Round 1 → Abu Dhabi) |

## Output

The program outputs the optimal team that would have maximized points for the last race:

```
OPTIMAL TEAM FOR MELBOURNE
============================================================

Drivers:
  Lando Norris - $28.2M - 45 pts
  Charles Leclerc - $27.8M - 38 pts
  ...

Constructors:
  McLaren - $25.2M - 72 pts
  Ferrari - $24.8M - 65 pts

Total cost: $98.5M
Total points: 285
```

## Fetching Fresh Fantasy Data

This repo can consume local fantasy-data snapshots stored under `data/fantasy-data`:

```bash
python main.py --data-dir data/fantasy-data/latest
```

**Save to year-specific directories** (e.g. for 2026 and 2025):

**Use year-specific data in main.py**:

```bash
# Pass base path; main.py resolves to {path}/{year} or {path}/latest
python main.py --data-dir data/fantasy-data --year 2026 --round 1

# lastyear mode: uses {path}/{data_season} (e.g. 2025 folder for Monaco 2025)
python main.py --data-dir data/fantasy-data --round monaco --mode lastyear
```

The repo currently includes `data/fantasy-data/2025` and `data/fantasy-data/latest` snapshots.

## League Crawler

This repo also includes a separate league crawler for scraping team compositions from an F1 Fantasy public league leaderboard, for example:

`https://fantasy.formula1.com/en/leagues/leaderboard/public/871710`

The crawler is implemented in:

- `scripts/fantasy_scraper_league.js` – Playwright scraper
- `scripts/league_crawler.py` – small Python wrapper around the Node script

### What it extracts

For each team in the selected league view, the crawler writes a JSON file containing:

- Team rank, team name, and manager
- Team lineup: 5 drivers and 2 constructors
- `turboDriver`
- `x3BoostDriver`
- Chip usage summary: `chip` and `chips`
- Transfer summary: `excessTransfers` and `transfer`
- Basic metadata such as `totalPoints`, `costCap`, and `limitless`

### Prerequisites

Install the project Python dependencies first:

```bash
pip install -r requirements.txt
```

Install Playwright for the league crawler:

```bash
cd scripts
npm install
npx playwright install chromium
cd ../..
```

### Recommended usage

Run the Python wrapper from the repo root:

```bash
python scripts/league_crawler.py
```

This uses the default league URL and saves output under `data/raaaace_weeeeek/`.

Useful variants:

```bash
# Scrape a specific standings view from the dropdown
python scripts/league_crawler.py --view "Chinese Grand Prix"
python scripts/league_crawler.py --view "Overall"

# Scrape a custom league
python scripts/league_crawler.py --league-url "https://fantasy.formula1.com/en/leagues/leaderboard/public/871710"

# Write to a custom file
python scripts/league_crawler.py --output data/raaaace_weeeeek/my_league.json

# Or choose the default output directory for generated files
python scripts/league_crawler.py --output-dir data/raaaace_weeeeek/custom-run

# Run headless
python scripts/league_crawler.py --headless

# Use Chromium instead of local Chrome
python scripts/league_crawler.py --browser chromium
```

### Login options

The site may require login. There are 2 supported approaches.

#### Option 1: Reuse the Playwright profile

Default behavior:

```bash
python scripts/league_crawler.py
```

Notes:

- The scraper prefers local `Chrome` by default.
- It reuses a persistent browser profile stored in `data/playwright-fantasy-profile`.
- That profile directory is treated as local machine state and is not tracked in git.
- The first time, log in manually in the opened browser window.
- Later runs can usually reuse the saved session.

If you want a clean session without reusing the saved profile:

```bash
python scripts/league_crawler.py --no-profile
```

#### Option 2: Reuse your already logged-in normal Chrome

If the site behaves better in your normal Chrome session, start Chrome with remote debugging enabled and then connect the crawler to it:

```bash
python scripts/league_crawler.py --cdp-url "http://127.0.0.1:9222"
```

In this mode, the crawler can attach to an already open logged-in browser and reuse an existing league tab when possible.

### Output files

By default, output files are written to:

- `data/raaaace_weeeeek/league_<league_id>.json`
- `data/raaaace_weeeeek/league_<league_id>_<view>.json`

Examples:

- `data/raaaace_weeeeek/league_871710.json`
- `data/raaaace_weeeeek/league_871710_chinese-grand-prix.json`

When debug artifacts are captured, they are written under:

- `data/raaaace_weeeeek/debug/`

### Output field examples

The crawler output includes fields like:

```json
{
  "teamName": "THEMOSTPOINTSPOSSIBLE",
  "manager": "Minzer Teo",
  "turboDriver": "Lewis Hamilton",
  "x3BoostDriver": "Kimi Antonelli",
  "chip": "x3 Boost",
  "chips": {
    "used": ["x3 Boost"],
    "x3Boost": true,
    "x3BoostDriver": "Kimi Antonelli",
    "noNegative": false,
    "wildcard": false,
    "limitless": false,
    "finalFix": false,
    "autopilot": false
  },
  "excessTransfers": 2,
  "transfer": {
    "made": 4,
    "allowed": 2,
    "remaining": -2,
    "excess": 2,
    "overLimit": true,
    "penaltyPerTransfer": 10,
    "penaltyPoints": 20
  }
}
```

Notes:

- `chip` is only set when a single chip is clearly identified for that result.
- `chips.used` contains the fuller chip summary extracted by the crawler.
- `excessTransfers` is a convenience field equal to `transfer.excess`.

## Updating Fallback Prices

Update `data/fallback_prices.json` from fantasy-data:

```bash
python scripts/update_fallback_prices.py
# Uses data/fantasy-data/latest by default

python scripts/update_fallback_prices.py --season 2026
# Uses data/fantasy-data/2026
```

Run the scraper first to refresh data. Use `--dry-run` to preview without writing.

## Project Structure

```
F1-Fantasy-Strategist/
├── main.py              # Entry point
├── scripts/
│   └── update_fallback_prices.py  # Sync prices from fantasy-data
├── src/
│   ├── data_fetcher.py  # F1 API client (f1api.dev)
│   ├── fantasy_data.py  # Fantasy points (GitHub or local)
│   ├── scoring.py       # F1 Fantasy scoring rules
│   ├── race_analyzer.py # Result → points calculation
│   └── optimizer.py     # Team selection under budget
├── data/
│   ├── fallback_prices.json
│   └── fantasy-data/    # Local fantasy-data snapshots (e.g. 2025/, latest/)
├── scripts/
│   ├── fantasy_scraper_league.js
│   ├── league_crawler.py
│   └── package.json     # Playwright dependency for crawler tooling
└── requirements.txt
```

## Known Limitations

- **Fantasy points**: fantasy-data (mirrors f1fantasytools.com) is used when it matches the requested season. For 2026+, computed points are used until fantasy-data is updated. Use `--computed` to force computed and compare with f1fantasytools.com.
- **Overtakes**: 1 pt per overtake. Sourced from fantasy-data (f1fantasytools.com) when available; OpenF1 fallback for 2023+ historical races.
- **Driver of the Day**: Not available (fan vote).
- **Constructor bonuses**: Q2/Q3 and pitstop bonuses are simplified (constructor = sum of 2 drivers).
- **Prices**: f1api.dev does not provide fantasy prices; use fallback JSON updated from f1fantasytools.com.
