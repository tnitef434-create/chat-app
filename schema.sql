-- World Football Database schema (SQLite)
PRAGMA foreign_keys = ON;

CREATE TABLE confederations (
  code         TEXT PRIMARY KEY,          -- UEFA, CONMEBOL, CONCACAF, AFC, CAF, OFC, FIFA
  name         TEXT NOT NULL,
  region       TEXT,
  founded      INTEGER,
  headquarters TEXT
);

CREATE TABLE countries (
  code          TEXT PRIMARY KEY,         -- short key used in competition codes (eng, de, es, br ...)
  fifa_code     TEXT NOT NULL UNIQUE,     -- FIFA trigram (ENG, GER, ESP, BRA ...)
  name          TEXT NOT NULL,
  confederation TEXT NOT NULL REFERENCES confederations(code),
  fifa_member   INTEGER NOT NULL,
  top_league    TEXT,
  notes         TEXT
);

CREATE TABLE competitions (
  id            INTEGER PRIMARY KEY,
  code          TEXT NOT NULL UNIQUE,     -- eng.1, de.cup, uefa.cl, conmebol.lib ...
  name          TEXT NOT NULL,
  type          TEXT NOT NULL,            -- league | cup | continental | intercontinental
  tier          INTEGER,                  -- 1 = top division / premier continental cup
  country_code  TEXT REFERENCES countries(code),          -- NULL for continental competitions
  confederation TEXT REFERENCES confederations(code),
  first_season  TEXT,
  last_season   TEXT,
  notes         TEXT
);

CREATE TABLE seasons (
  id             INTEGER PRIMARY KEY,
  competition_id INTEGER NOT NULL REFERENCES competitions(id),
  season         TEXT NOT NULL,           -- '2023/24' or '2023'
  start_year     INTEGER NOT NULL,
  title          TEXT,                    -- name as published by the source
  source         TEXT,                    -- source file(s) the data came from
  matches_count  INTEGER DEFAULT 0,
  UNIQUE (competition_id, season)
);

CREATE TABLE teams (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL,
  country_code TEXT REFERENCES countries(code),
  founded      INTEGER,
  city         TEXT,
  stadium      TEXT,
  UNIQUE (name, country_code)
);

CREATE TABLE team_aliases (
  alias   TEXT NOT NULL,
  team_id INTEGER NOT NULL REFERENCES teams(id),
  PRIMARY KEY (alias, team_id)
);

CREATE TABLE matches (
  id           INTEGER PRIMARY KEY,
  season_id    INTEGER NOT NULL REFERENCES seasons(id),
  stage        TEXT,                      -- e.g. 'Qualifying', 'Apertura', 'Group A', 'Final'
  round        TEXT,                      -- round label from the source
  match_date   TEXT,                      -- YYYY-MM-DD
  kickoff      TEXT,                      -- HH:MM local time when known
  home_team_id INTEGER NOT NULL REFERENCES teams(id),
  away_team_id INTEGER NOT NULL REFERENCES teams(id),
  home_ft INTEGER, away_ft INTEGER,       -- full time (90 min)
  home_ht INTEGER, away_ht INTEGER,       -- half time
  home_et INTEGER, away_et INTEGER,       -- after extra time
  home_pen INTEGER, away_pen INTEGER,     -- penalty shoot-out
  status       TEXT NOT NULL,             -- played | scheduled
  neutral      INTEGER DEFAULT 0,
  ground       TEXT
);
CREATE INDEX idx_matches_season ON matches(season_id);
CREATE INDEX idx_matches_home ON matches(home_team_id);
CREATE INDEX idx_matches_away ON matches(away_team_id);
CREATE INDEX idx_matches_date ON matches(match_date);

-- League tables computed from results (3 pts win / 1 draw; no point deductions applied).
-- For league competitions: one table per season and phase (e.g. Apertura/Clausura).
-- For continental competitions: one table per group / league phase.
CREATE TABLE standings (
  season_id INTEGER NOT NULL REFERENCES seasons(id),
  phase     TEXT NOT NULL,
  position  INTEGER NOT NULL,
  team_id   INTEGER NOT NULL REFERENCES teams(id),
  played INTEGER, won INTEGER, drawn INTEGER, lost INTEGER,
  goals_for INTEGER, goals_against INTEGER, goal_diff INTEGER, points INTEGER,
  PRIMARY KEY (season_id, phase, team_id)
);

-- Winners of continental / intercontinental club competitions.
CREATE TABLE continental_champions (
  competition_id INTEGER NOT NULL REFERENCES competitions(id),
  season         TEXT NOT NULL,
  winner         TEXT NOT NULL,
  winner_country TEXT,
  team_id        INTEGER REFERENCES teams(id),
  PRIMARY KEY (competition_id, season)
);

-- Which competitions each association's clubs can qualify for.
CREATE TABLE competition_access (
  country_code   TEXT NOT NULL REFERENCES countries(code),
  competition_id INTEGER NOT NULL REFERENCES competitions(id),
  PRIMARY KEY (country_code, competition_id)
);

CREATE VIEW v_matches AS
SELECT m.id, c.code AS competition, c.name AS competition_name, s.season,
       m.stage, m.round, m.match_date, m.kickoff,
       ht.name AS home_team, at.name AS away_team,
       m.home_ft, m.away_ft, m.home_ht, m.away_ht,
       m.home_et, m.away_et, m.home_pen, m.away_pen, m.status
FROM matches m
JOIN seasons s ON s.id = m.season_id
JOIN competitions c ON c.id = s.competition_id
JOIN teams ht ON ht.id = m.home_team_id
JOIN teams at ON at.id = m.away_team_id;

CREATE VIEW v_standings AS
SELECT c.code AS competition, c.name AS competition_name, s.season, st.phase, st.position,
       t.name AS team, st.played, st.won, st.drawn, st.lost,
       st.goals_for, st.goals_against, st.goal_diff, st.points
FROM standings st
JOIN seasons s ON s.id = st.season_id
JOIN competitions c ON c.id = s.competition_id
JOIN teams t ON t.id = st.team_id;
