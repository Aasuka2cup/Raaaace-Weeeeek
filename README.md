# F1 Fantasy Strategist

Calculate the best possible F1 Fantasy team for the last race based on actual results.

## Rules Reference

- **Team composition**: 5 drivers + 2 constructors, $100M budget
- **Scoring**: [Game Rules](https://fantasy.formula1.com/en/game-rules)
- **How to play**: [How to Play](https://fantasy.formula1.com/en/how-to-play)

## Data Sources

1. **F1 API** ([f1api.dev](https://f1api.dev)) – Race results (qualifying, sprint, race)
   - Same data source as [f1fantasytools.com/statistics](https://f1fantasytools.com/statistics)
2. **Fantasy points & overtakes** – [JoshCBruce/fantasy-data](https://github.com/JoshCBruce/fantasy-data)
   - **Default**: fetched from GitHub
   - **Freshest**: use `--data-dir thirdparty/fantasy-data/latest` (run scraper in submodule first)
   - Falls back to computed points and [OpenF1](https://api.openf1.org) overtakes when no fantasy-data
3. **Fallback prices** – `data/fallback_prices.json` (update from f1fantasytools.com)

## Setup

```bash
pip install -r requirements.txt

# Optional: clone fantasy-data (third-party scraper) for freshest data
git submodule update --init
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

# Freshest data: run scraper in thirdparty, then use local output
cd thirdparty/fantasy-data && npm install && node fantasy_scraper_V3.1.js && cd ../..
python main.py --data-dir thirdparty/fantasy-data/latest

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

The `thirdparty/fantasy-data` submodule contains a scraper that pulls data from the official F1 Fantasy site:

```bash
cd thirdparty/fantasy-data
npm install
node fantasy_scraper_V3.1.js
cd ../..
python main.py --data-dir thirdparty/fantasy-data/latest
```

**Save to year-specific directories** (e.g. for 2026 and 2025):

```bash
node fantasy_scraper_V3.1.js --season 2026 --output-dir .
# Writes to 2026/ only (latest/ unchanged)
```

**Run drivers or constructors separately** (e.g. if one fails):

```bash
node fantasy_scraper_V3.1.js --drivers-only    # or -d
node fantasy_scraper_V3.1.js --constructors-only  # or -c
```

**Use year-specific data in main.py**:

```bash
# Pass base path; main.py resolves to {path}/{year} or {path}/latest
python main.py --data-dir thirdparty/fantasy-data --year 2026 --round 1

# lastyear mode: uses {path}/{data_season} (e.g. 2025 folder for Monaco 2025)
python main.py --data-dir thirdparty/fantasy-data --round monaco --mode lastyear
```

Requires Node.js. The scraper opens a browser and extracts driver/constructor breakdowns.

## Updating Fallback Prices

Update `data/fallback_prices.json` from fantasy-data:

```bash
python scripts/update_fallback_prices.py
# Uses thirdparty/fantasy-data/latest by default

python scripts/update_fallback_prices.py --season 2026
# Uses thirdparty/fantasy-data/2026
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
├── thirdparty/
│   └── fantasy-data/    # Git submodule – scraper + driver/constructor JSON
├── data/
│   └── fallback_prices.json
└── requirements.txt
```

## Known Limitations

- **Fantasy points**: fantasy-data (mirrors f1fantasytools.com) is used when it matches the requested season. For 2026+, computed points are used until fantasy-data is updated. Use `--computed` to force computed and compare with f1fantasytools.com.
- **Overtakes**: 1 pt per overtake. Sourced from fantasy-data (f1fantasytools.com) when available; OpenF1 fallback for 2023+ historical races.
- **Driver of the Day**: Not available (fan vote).
- **Constructor bonuses**: Q2/Q3 and pitstop bonuses are simplified (constructor = sum of 2 drivers).
- **Prices**: f1api.dev does not provide fantasy prices; use fallback JSON updated from f1fantasytools.com.
