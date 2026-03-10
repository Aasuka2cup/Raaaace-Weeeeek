# F1 Fantasy Strategist

Calculate the best possible F1 Fantasy team for the last race based on actual results.

## Rules Reference

- **Team composition**: 5 drivers + 2 constructors, $100M budget
- **Scoring**: [Game Rules](https://fantasy.formula1.com/en/game-rules)
- **How to play**: [How to Play](https://fantasy.formula1.com/en/how-to-play)

## Data Sources

1. **F1 API** ([f1api.dev](https://f1api.dev)) – Race results (qualifying, sprint, race)
   - Same data source as [f1fantasytools.com/statistics](https://f1fantasytools.com/statistics)
2. **Fantasy points** – [JoshCBruce/fantasy-data](https://github.com/JoshCBruce/fantasy-data) (official points from f1fantasytools.com)
   - Used when available for the round; falls back to computed points for future rounds or new drivers
3. **Fallback prices** – `data/fallback_prices.json` (update from f1fantasytools.com)

## Setup

```bash
pip install -r requirements.txt
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

# Verbose output
python main.py -v
```

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

## Updating Fallback Prices

Update `data/fallback_prices.json` from [f1fantasytools.com/statistics](https://f1fantasytools.com/statistics) with current driver and constructor prices.

## Project Structure

```
F1-Fantasy-Strategist/
├── main.py              # Entry point
├── src/
│   ├── data_fetcher.py  # F1 API client (f1api.dev)
│   ├── fantasy_data.py # Official fantasy points (f1fantasytools.com via fantasy-data)
│   ├── scoring.py       # F1 Fantasy scoring rules
│   ├── race_analyzer.py # Result → points calculation
│   └── optimizer.py     # Team selection under budget
├── data/
│   └── fallback_prices.json
└── requirements.txt
```

## Known Limitations

- **Fantasy points**: fantasy-data "latest" reflects the most recent season. For future rounds or new seasons, computed points are used.
- **Fastest lap**: Not currently fetched (Open F1 lap data). Would add ~5–10 pts for one driver.
- **Driver of the Day**: Not available (fan vote).
- **Constructor bonuses**: Q2/Q3 and pitstop bonuses are simplified (constructor = sum of 2 drivers).
- **Prices**: f1api.dev does not provide fantasy prices; use fallback JSON updated from f1fantasytools.com.
