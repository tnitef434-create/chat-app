# World Football DB ⚽

An open SQLite database of **club football from 2013 onwards**. It covers domestic leagues and cups and the
continental competitions they qualify for: UEFA Champions League, Europa League, Conference League, Copa
Libertadores, Copa Sudamericana, CONCACAF Champions Cup, CAF Champions League, AFC Champions League, OFC
Champions League and the FIFA Club World Cup.

| | |
|---|---|
| Matches | **252,512** (2013/14 → 2026/27 fixtures) |
| Competitions with match data | **174** across **85** countries and all 6 confederations |
| Clubs | **4,724**, unified across domestic and continental competitions |
| Associations registered | **220**: all 211 FIFA members plus the non-FIFA confederation members (Zanzibar, Guadeloupe, …), each with its top division |
| Computed league tables | **16,518** rows (league tables, Apertura/Clausura, continental groups and league phases) |
| Continental champions | 140 titles across 12 competitions (2013 →) |

See **[data/COVERAGE.md](data/COVERAGE.md)** for a season-by-season grid of every competition.

## What's in the repo

```
data/football.sqlite     the database (SQLite 3)
data/csv/                the same data as CSV (matches & standings are gzipped)
data/COVERAGE.md         generated coverage report
web/                     static browser for the database (runs fully client-side)
seeds/                   hand-curated reference data (confederations, countries, competitions, champions, alias fixes)
schema.sql               database schema
scripts/                 pipeline that rebuilds everything from the open sources
```

## Using the data

**SQLite**

```bash
sqlite3 data/football.sqlite
```

```sql
-- Premier League 2015/16 final table
SELECT position, team, played, won, drawn, lost, goals_for, goals_against, points
FROM v_standings WHERE competition = 'eng.1' AND season = '2015/16' ORDER BY position;

-- Every Champions League final since 2013
SELECT season, home_team, home_ft, away_ft, away_team, home_pen, away_pen
FROM v_matches WHERE competition = 'uefa.cl' AND round = 'Final';

-- A club's full record across all competitions
SELECT competition_name, season, match_date, home_team, home_ft, away_ft, away_team
FROM v_matches WHERE 'Liverpool FC' IN (home_team, away_team) ORDER BY match_date;

-- Which continental competitions can Kenyan clubs qualify for?
SELECT c.name FROM competition_access a JOIN competitions c ON c.id = a.competition_id WHERE a.country_code = 'ke';
```

**Python / pandas**

```python
import sqlite3, pandas as pd
con = sqlite3.connect("data/football.sqlite")
df = pd.read_sql("SELECT * FROM v_matches WHERE competition LIKE 'conmebol.%'", con)
```

**Browser.** `web/index.html` loads the database in the browser with sql.js. You can browse leagues by
confederation, see tables and fixtures, search clubs, view club pages and run SQL directly. Run it locally:

```bash
cd web && python3 -m http.server 8000   # open http://localhost:8000
```

To deploy on Cloudflare Pages, run `npx wrangler pages deploy` (`wrangler.toml` points at `web/`). Any static host works.

## Schema

| Table | Contents |
|---|---|
| `confederations` | UEFA, CONMEBOL, CONCACAF, AFC, CAF, OFC, FIFA |
| `countries` | 220 associations: short code (`eng`, `de`, `br` …), FIFA trigram, confederation, top division |
| `competitions` | Domestic leagues and cups (`eng.1`, `de.cup`, `br.paulistao`, …) and continental ones (`uefa.cl`, `conmebol.lib`, `afc.cl`, …) |
| `seasons` | One row per competition season (`2023/24` or `2023` for calendar-year leagues), with its source file |
| `teams` / `team_aliases` | Clubs with country, founding year, city and stadium where known, plus every spelling seen in the sources |
| `matches` | Date, kickoff, stage, round, and scores at full time, half time, after extra time and on penalties |
| `standings` | Tables computed from results, for each league season and phase and each continental group |
| `continental_champions` | Winners of every continental and intercontinental club competition since 2013 |
| `competition_access` | Which continental competitions each association's clubs can qualify for |

Views: `v_matches` and `v_standings` join in team and competition names.

Competition codes are `<country>.<tier>` for leagues (`eng.1` = Premier League, `eng.2` = Championship,
`it.3.a` = Serie C group A), `<country>.cup` / `.lcup` for cups, and `<confed>.<comp>` for continental competitions.

## Rebuilding / updating

```bash
gem install fbtxt2json            # official Football.TXT -> JSON converter
./scripts/fetch_sources.sh        # clone/update the open data repos into ./sources
./scripts/convert_txt.sh          # convert Football.TXT files to JSON (./build/json)
python3 scripts/build_db.py       # build data/football.sqlite, CSVs, coverage report, web copy
```

The build:

- picks the best source for each competition season. Curated openfootball files come first, then the
  worldfootball and football-data caches;
- resolves team names against the openfootball clubs register, which has around 3,500 clubs and their
  alternative names, so that "Man Utd", "Manchester United" and "Manchester United (ENG)" become one club;
- recomputes the tables.

To fix a club that still appears twice, add a row to `seeds/team_aliases.csv`.

The GitHub Action in `.github/workflows/rebuild.yml` does the same build weekly, or on demand.

## Sources & licence

All match data comes from open-data projects that publish it in the **public domain (CC0)**:

- [openfootball](https://github.com/openfootball): football.json, champions-league, club-worldcup, england,
  deutschland, espana, italy, austria, belgium, europe, south-america, world, clubs
- [footballcsv](https://github.com/footballcsv): cache.wfb, cache.footballdata, cache.api.fbdat

The seed files in `seeds/` were curated for this project and are released under CC0 as well. The bundled
[sql.js](https://github.com/sql-js/sql.js) is MIT-licensed (`web/vendor/sql.js-LICENSE`).

## Known gaps

The coverage is what the open sources contain, and some areas are thin:

- **Asian club competitions (AFC Champions League Elite / Two, AFC Cup) have no match data** in any open
  source we found. They are in the database as competitions, with their champions, and access rules for all
  AFC members. Asian domestic data covers Japan, China, Saudi Arabia, South Korea (one season)
  and Australia.
- The Europa League only has match data from 2020/21. For both the Europa League and the Conference League,
  the 2025/26 data stops at qualifying. The CAF Champions League only has 2023/24 and 2024/25.
- Many smaller UEFA, CAF and CONCACAF leagues only have data from 2023/24. The other **148 registered top
  divisions** have no match data yet; they are listed at the bottom of `data/COVERAGE.md`.
- Tables are computed from results: 3 points per win, no official point deductions, and tie-breaks by goal
  difference and then goals scored. Championship and relegation splits (for example in Scotland and Belgium)
  are added into one table.

You can extend the database by adding sources: any Football.TXT file or CSV with `Date, Team 1, FT, HT, Team 2`
columns can be dropped in with a few lines in `scripts/build_db.py`. Corrections are welcome.
