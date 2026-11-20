#!/usr/bin/env python3
"""Build the World Football Database (SQLite) from seeds + openfootball sources.

Pipeline:
    scripts/fetch_sources.sh   # clone openfootball repos into ./sources
    scripts/convert_txt.sh     # Football.TXT -> JSON into ./build/json
    python3 scripts/build_db.py

Output: data/football.sqlite (+ CSV exports in data/csv/)
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import shutil
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEEDS = ROOT / "seeds"
SOURCES = ROOT / "sources"
JSON_DIR = ROOT / "build" / "json"
OUT_DB = ROOT / "data" / "football.sqlite"
CSV_DIR = ROOT / "data" / "csv"
WEB_DB = ROOT / "web" / "football.sqlite.gz"

# --------------------------------------------------------------------------
# Source file classification
# --------------------------------------------------------------------------

# Country repos with their own file naming:  <repo>/<season>/<stem>.json
NATIONAL = {
    "england": ("eng", {"1-premierleague": "1", "2-championship": "2", "3-league1": "3",
                        "4-league2": "4", "5-nationalleague": "5", "facup": "cup", "eflcup": "lcup"}),
    "deutschland": ("de", {"1-bundesliga": "1", "2-bundesliga2": "2", "3-liga3": "3",
                           "4-regionalliga-bayern": "4.bayern", "4-regionalliga-nord": "4.nord",
                           "4-regionalliga-nordost": "4.nordost", "4-regionalliga-suedwest": "4.suedwest",
                           "4-regionalliga-west": "4.west", "cup": "cup"}),
    "espana": ("es", {"1-liga": "1", "2-liga2": "2", "cup": "cup"}),
    "italy": ("it", {"1-seriea": "1", "2-serieb": "2", "3-seriec_a": "3.a", "3-seriec_b": "3.b",
                     "3-seriec_c": "3.c", "cup": "cup"}),
    "austria": ("at", {"1-bundesliga": "1", "2-liga1": "2", "2-liga2": "2",
                       "3-regionalliga-ost": "3.ost", "3-regionalliga-mitte": "3.mitte", "cup": "cup"}),
    "belgium": ("be", {"be1": "1", "becup": "cup"}),
}

# Special stems inside the regional repos (europe / south-america / world)
REGIONAL_SPECIAL = {
    "copal": "conmebol.lib", "copas": "conmebol.sud", "concacafcl": "concacaf.cl",
    "cafcl": "caf.cl", "afl": "caf.afl", "mls": "us.1",
}

UEFA_FILES = {"cl": ("uefa.cl", "main"), "clq": ("uefa.cl", "q"), "el": ("uefa.el", "main"),
              "elq": ("uefa.el", "q"), "conf": ("uefa.ecl", "main"), "confq": ("uefa.ecl", "q")}

FOOTBALL_JSON_PREFIX = {"en": "eng"}
FOOTBALL_JSON_SPECIAL = {"uefa.cl": "uefa.cl", "copa.l": "conmebol.lib", "mls": "us.1"}

# Lower number wins when two sources cover the same competition season part
SOURCE_PRIORITY = {"national": 0, "uefa": 0, "regional": 1, "cwc": 0, "football.json": 2,
                   "wfb": 3, "footballdata": 4, "fbdat": 5}

# footballcsv cache codes that differ from ours
CSV_CODE_MAP = {"at.3.o": "at.3.ost", "de.4.n": "de.4.nord", "de.4.no": "de.4.nordost",
                "de.4.sw": "de.4.suedwest", "de.4.w": "de.4.west", "copa.l": "conmebol.lib"}
CSV_KIND = {"fc-cache.wfb": "wfb", "fc-cache.footballdata": "footballdata", "fc-cache.api.fbdat": "fbdat"}

SEASON_RE = r"(\d{4}(?:-\d{2})?)"

NAME_OVERRIDES = {
    "eng.2": "EFL Championship", "eng.3": "EFL League One", "eng.4": "EFL League Two",
    "eng.5": "National League", "eng.cup": "FA Cup", "eng.lcup": "EFL Cup",
    "de.2": "2. Bundesliga", "de.3": "3. Liga", "de.cup": "DFB-Pokal",
    "de.4.bayern": "Regionalliga Bayern", "de.4.nord": "Regionalliga Nord",
    "de.4.nordost": "Regionalliga Nordost", "de.4.suedwest": "Regionalliga Südwest",
    "de.4.west": "Regionalliga West",
    "es.2": "Segunda División", "es.cup": "Copa del Rey",
    "it.2": "Serie B", "it.3.a": "Serie C – Girone A", "it.3.b": "Serie C – Girone B",
    "it.3.c": "Serie C – Girone C", "it.cup": "Coppa Italia",
    "at.2": "2. Liga (Austria)", "at.3.ost": "Regionalliga Ost", "at.3.mitte": "Regionalliga Mitte",
    "at.cup": "ÖFB-Cup",
    "be.cup": "Belgian Cup", "fr.2": "Ligue 2", "fr.cup": "Coupe de France",
    "nl.2": "Eerste Divisie", "nl.cup": "KNVB Cup", "pt.2": "Liga Portugal 2",
    "pt.cup": "Taça de Portugal", "ch.2": "Swiss Challenge League", "ch.cup": "Swiss Cup",
    "tr.2": "TFF 1. Lig", "tr.cup": "Turkish Cup", "br.2": "Campeonato Brasileiro Série B",
    "br.cup": "Copa do Brasil", "mx.2": "Liga de Expansión MX (Ascenso MX until 2020)",
    "ru.2": "Russian First League", "cz.2": "Czech National Football League", "cz.cup": "Czech Cup",
    "dk.2": "Danish 1st Division", "dk.cup": "Danish Cup", "no.2": "Norwegian First Division",
    "no.cup": "Norwegian Cup", "se.2": "Superettan", "se.3.s": "Ettan Södra", "pl.2": "I liga",
    "il.2": "Liga Leumit", "il.cup": "Israel State Cup", "ng.2": "Nigeria National League",
    "hu.cup": "Hungarian Cup", "gr.cup": "Greek Cup", "ro.cup": "Romanian Cup",
    "bg.cup": "Bulgarian Cup", "cy.cup": "Cypriot Cup", "si.cup": "Slovenian Cup",
    "is.cup": "Icelandic Cup", "br.3": "Campeonato Brasileiro Série C",
    "br.4": "Campeonato Brasileiro Série D", "br.carioca": "Campeonato Carioca",
    "br.gauchao": "Campeonato Gaúcho", "br.mineiro": "Campeonato Mineiro",
    "br.paranaense": "Campeonato Paranaense", "br.paulistao": "Campeonato Paulista",
    "ar.2.metro": "Primera B Metropolitana", "ar.2.nacional": "Primera Nacional",
    "sco.2": "Scottish Championship", "sco.3": "Scottish League One", "sco.4": "Scottish League Two",
    "jp.2": "J2 League", "jp.cup": "Emperor's Cup", "us.2": "USL Championship",
    "us.cup": "U.S. Open Cup", "co.2": "Categoría Primera B", "co.cup": "Copa Colombia",
    "mx.cup": "Copa MX", "cz.3": "Czech Fourth Tier", "be.2": "Challenger Pro League",
 "li.cup": "Liechtenstein Cup", "ba.cup": "Bosnia and Herzegovina Cup",
}

# Countries whose clubs regularly play in a neighbour's league system
NEIGHBOURS = {"eng": ["wal"], "fr": ["mc"], "ch": ["li"], "us": ["ca"], "es": ["ad"]}

GENERIC_TOKENS = set("""fc cf sc ac afc cd sd ud fk sk nk if bk ik as ss ca club de the football
calcio sv vfb vfl tsv fsv cfc sfc ff kv kaa krc rc rsc rcd ssc us asd sad cp sl""".split())

KNOCKOUT_RE = re.compile(
    r"(final|semi|quarter|play-?off|liguilla|repech|relegation|promotion|round of|knockout|"
    r"eighth|cuartos|octavos|barrage|reclasif|championship round|leagues? cup|decider|"
    r"preliminary|qualif|tiebreak|test match|1/8|1/4|1/2)", re.I)
GROUP_RE = re.compile(r"^(group|gruppe|grupo|league|zone|zona)\b", re.I)


def season_key(raw: str) -> tuple[str, int]:
    raw = raw.strip()
    if "-" in raw:
        a, b = raw.split("-")
        return f"{a}/{b[-2:]}", int(a)
    return raw, int(raw)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("ı", "i").replace("ß", "ss").replace("ø", "o").replace("æ", "ae").replace("ł", "l")
    s = re.sub(r"\[[a-z]{2}\]", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def strip_key(s: str) -> str:
    toks = [t for t in norm(s).split() if t not in GENERIC_TOKENS and not t.isdigit()]
    return " ".join(toks) or norm(s)


# --------------------------------------------------------------------------
# Seeds
# --------------------------------------------------------------------------

def read_csv(name: str) -> list[dict]:
    with open(SEEDS / name, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------
# Clubs reference (openfootball/clubs) -> alias index per country
# --------------------------------------------------------------------------

class ClubIndex:
    def __init__(self) -> None:
        self.by_norm: dict[str, dict[str, dict]] = defaultdict(dict)
        self.by_strip: dict[str, dict[str, dict | None]] = defaultdict(dict)

    def add(self, country: str, rec: dict) -> None:
        for name in [rec["name"], *rec["aliases"]]:
            n = norm(name)
            if n and n not in self.by_norm[country]:
                self.by_norm[country][n] = rec
            k = strip_key(name)
            if k:
                cur = self.by_strip[country].get(k, rec)
                self.by_strip[country][k] = rec if cur is rec else None  # ambiguity -> None

    def lookup(self, country: str, name: str) -> dict | None:
        rec = self.by_norm.get(country, {}).get(norm(name))
        if rec:
            return rec
        return self.by_strip.get(country, {}).get(strip_key(name))


def load_clubs(index: ClubIndex, known_codes: set[str]) -> int:
    count = 0
    for path in sorted((SOURCES / "clubs").rglob("*.clubs.txt")):
        code = path.name.split(".")[0]
        if code not in known_codes:
            continue
        rec = None
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = re.sub(r"\s#.*$", "", line).rstrip()
            if not line.strip() or line.lstrip().startswith(("#", "=")):
                continue
            if line.lstrip().startswith("|"):
                if rec is not None:
                    rec["aliases"] += [a.strip() for a in re.sub(r"\[[a-z]{2}\]", "", line).split("|") if a.strip()]
                continue
            if line[0].isspace():  # address / misc lines
                continue
            line = re.sub(r"^[ivx]+\)\s*", "", line)
            if rec is not None:
                index.add(code, rec)
                count += 1
            parts = [p.strip() for p in line.split(",")]
            names = [n.strip() for n in parts[0].split("|") if n.strip()]
            rec = {"name": names[0], "aliases": names[1:], "founded": None, "stadium": None,
                   "city": None, "country": code}
            for p in parts[1:]:
                if re.fullmatch(r"\d{4}", p):
                    rec["founded"] = int(p)
                elif p.startswith("@"):
                    rec["stadium"] = p[1:].strip()
                elif p and rec["city"] is None:
                    rec["city"] = re.sub(r"\s*\(.*?\)", "", p).strip() or None
        if rec is not None:
            index.add(code, rec)
            count += 1
    return count


# --------------------------------------------------------------------------
# Match source discovery
# --------------------------------------------------------------------------

def classify(rel: str, country_codes: set[str]) -> tuple[str, str, str, str] | None:
    """Return (competition_code, season_raw, part, source_kind) or None to skip."""
    if "-full" in rel or "/more/" in rel or "/rsssf/" in rel or "/openliga/" in rel:
        return None
    m = re.fullmatch(rf"football\.json/{SEASON_RE}/([a-z.]+)\.json", rel)
    if m:
        season, stem = m.groups()
        if stem in FOOTBALL_JSON_SPECIAL:
            return FOOTBALL_JSON_SPECIAL[stem], season, "main", "football.json"
        cc, _, rest = stem.partition(".")
        cc = FOOTBALL_JSON_PREFIX.get(cc, cc)
        if cc in country_codes and rest:
            return f"{cc}.{rest}", season, "main", "football.json"
        return None
    m = re.fullmatch(rf"champions-league/{SEASON_RE}/([a-z]+)\.json", rel)
    if m:
        season, stem = m.groups()
        if stem in UEFA_FILES:
            code, part = UEFA_FILES[stem]
            return code, season, part, "uefa"
        return None
    m = re.fullmatch(rf"club-worldcup/{SEASON_RE}/clubworldcup\.json", rel)
    if m:
        return "fifa.cwc", m.group(1), "main", "cwc"
    m = re.fullmatch(rf"([a-z]+)/{SEASON_RE}/([\w-]+)\.json", rel)
    if m and m.group(1) in NATIONAL:
        repo, season, stem = m.groups()
        cc, stems = NATIONAL[repo]
        if stem in stems:
            return f"{cc}.{stems[stem]}", season, "main", "national"
        return None
    m = re.fullmatch(rf"(?:europe|south-america|world)/(?:[\w-]+/)*{SEASON_RE}_([a-z0-9]+)\.json", rel)
    if m:
        season, stem = m.groups()
        if stem in REGIONAL_SPECIAL:
            return REGIONAL_SPECIAL[stem], season, "main", "regional"
        mm = re.fullmatch(r"([a-z]+?)(\d|cup)([a-z]*)", stem)
        if mm and mm.group(1) in country_codes:
            cc, tier, suffix = mm.groups()
            code = f"{cc}.{tier}"
            if suffix in ("s", "n"):  # e.g. se3s = third tier, southern group
                code += f".{suffix}"
            return code, season, "main", "regional"
    return None


def classify_csv(rel: str, country_codes: set[str]) -> tuple[str, str, str, str] | None:
    m = re.fullmatch(rf"(fc-cache\.[\w.]+?)/{SEASON_RE}/([a-z0-9.]+)\.csv", rel)
    if not m or m.group(1) not in CSV_KIND:
        return None
    repo, season, stem = m.groups()
    code = CSV_CODE_MAP.get(stem, stem)
    if code in ("uefa.cl", "uefa.el", "conmebol.lib") or code.split(".")[0] in country_codes:
        return code, season, "main", CSV_KIND[repo]
    return None


def _score(txt: str | None) -> list[int] | None:
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", txt or "")
    return [int(m.group(1)), int(m.group(2))] if m else None


def load_csv_matches(path: Path) -> dict:
    from datetime import datetime
    matches = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                date = datetime.strptime(" ".join((row.get("Date") or "").split()), "%a %b %d %Y").date().isoformat()
            except ValueError:
                date = None
            score = {k: v for k, v in (("ft", _score(row.get("FT"))), ("ht", _score(row.get("HT"))),
                                       ("et", _score(row.get("ET"))), ("p", _score(row.get("P")))) if v}
            rnd = row.get("Round") or row.get("Matchday") or row.get("Stage") or None
            if rnd and rnd.isdigit():
                rnd = f"Matchday {rnd}"
            mt = {"round": rnd, "date": date, "time": row.get("Time") or None,
                  "team1": row.get("Team 1"), "team2": row.get("Team 2"), "score": score}
            if row.get("Group"):
                mt["group"] = row["Group"]
            matches.append(mt)
    return {"name": None, "matches": matches}


def parse_score(sc) -> dict:
    if sc is None:
        return {}
    if isinstance(sc, list):
        return {"ft": sc}
    if isinstance(sc, dict):
        return sc
    return {}


def pair(sc: dict, key: str) -> tuple[int | None, int | None]:
    v = sc.get(key)
    if isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) for x in v):
        return v[0], v[1]
    return None, None


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-year", type=int, default=2013, help="first season start year to include")
    ap.add_argument("--no-csv", action="store_true")
    args = ap.parse_args()

    confeds = read_csv("confederations.csv")
    countries = read_csv("countries.csv")
    seed_comps = read_csv("competitions.csv")
    champions = read_csv("continental_champions.csv")
    country_by_code = {c["code"]: c for c in countries}
    code_by_fifa = {c["fifa"]: c["code"] for c in countries}
    country_codes = set(country_by_code)

    manual_alias = {(r["country"], norm(r["alias"])): r["team"] for r in read_csv("team_aliases.csv")}

    clubs = ClubIndex()
    n_clubs = load_clubs(clubs, country_codes)
    print(f"club reference records: {n_clubs}")

    # ---- discover & select source files -------------------------------------------------
    candidates: dict[tuple[str, str, str], list] = defaultdict(list)
    roots = [(JSON_DIR, ""), (SOURCES, "football.json/")]
    for base, only_prefix in roots:
        if not base.exists():
            continue
        for path in base.rglob("*.json"):
            rel = path.relative_to(base).as_posix()
            if only_prefix and not rel.startswith(only_prefix):
                continue
            cl = classify(rel, country_codes)
            if not cl:
                continue
            code, season_raw, part, kind = cl
            season, start = season_key(season_raw)
            if start < args.min_year:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            matches = data.get("matches") or []
            if not matches:
                continue
            candidates[(code, season, part)].append(
                (SOURCE_PRIORITY[kind], -len(matches), rel, data, start))

    for path in SOURCES.glob("fc-cache.*/**/*.csv"):
        rel = path.relative_to(SOURCES).as_posix()
        cl = classify_csv(rel, country_codes)
        if not cl:
            continue
        code, season_raw, part, kind = cl
        season, start = season_key(season_raw)
        if start < args.min_year:
            continue
        data = load_csv_matches(path)
        if data["matches"]:
            candidates[(code, season, part)].append(
                (SOURCE_PRIORITY[kind], -len(data["matches"]), rel, data, start))

    selected: dict[tuple[str, str], list] = defaultdict(list)
    for (code, season, part), cands in candidates.items():
        cands.sort(key=lambda c: (c[0], c[1]))
        # prefer higher-priority source unless a lower one has clearly more matches
        best = cands[0]
        for c in cands[1:]:
            if -c[1] > -best[1] * 1.2:
                best = c
        selected[(code, season)].append((part, best))
    print(f"competition seasons selected: {len(selected)}")

    # ---- create database ----------------------------------------------------------------
    OUT_DB.parent.mkdir(parents=True, exist_ok=True)
    if OUT_DB.exists():
        OUT_DB.unlink()
    db = sqlite3.connect(OUT_DB)
    db.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))

    db.executemany("INSERT INTO confederations VALUES (?,?,?,?,?)",
                   [(c["code"], c["name"], c["region"], int(c["founded"]), c["headquarters"]) for c in confeds])
    db.executemany("INSERT INTO countries VALUES (?,?,?,?,?,?,?)",
                   [(c["code"], c["fifa"], c["name"], c["confederation"], int(c["fifa_member"]),
                     c["top_league"] or None, c["notes"] or None) for c in countries])

    comp_ids: dict[str, int] = {}

    def add_comp(code, name, ctype, tier, country, confed, first=None, last=None, notes=None) -> int:
        cur = db.execute(
            "INSERT INTO competitions (code,name,type,tier,country_code,confederation,first_season,last_season,notes)"
            " VALUES (?,?,?,?,?,?,?,?,?)", (code, name, ctype, tier, country, confed, first, last, notes))
        comp_ids[code] = cur.lastrowid
        return cur.lastrowid

    for c in seed_comps:
        add_comp(c["code"], c["name"], c["scope"], int(c["tier"]), None, c["confederation"],
                 c["first_season"] or None, c["last_season"] or None, c["notes"] or None)

    # Every association's top division, even without match data
    for c in countries:
        if c["top_league"]:
            add_comp(f"{c['code']}.1", c["top_league"], "league", 1, c["code"], c["confederation"])

    def domestic_comp(code: str, title: str) -> int:
        if code in comp_ids:
            return comp_ids[code]
        cc, _, rest = code.partition(".")
        country = country_by_code[cc]
        tier_s = rest.split(".")[0]
        if tier_s.isdigit():
            ctype, tier = "league", int(tier_s)
        elif tier_s not in ("cup", "lcup"):
            ctype, tier = "league", None  # regional / state championship
        else:
            ctype, tier = "cup", None
        name = NAME_OVERRIDES.get(code)
        if not name:
            name = re.sub(rf"\s*{SEASON_RE.replace('-', '[-/]')}\s*$", "", title)
            name = re.sub(r"\s*\d{4}/\d{2,4}\s*$", "", name).split("|")[-1].strip()
            name = name or code
        return add_comp(code, name, ctype, tier, cc, country["confederation"])

    # ---- teams ------------------------------------------------------------------------------
    team_ids: dict[tuple[str | None, str], int] = {}
    team_by_strip: dict[tuple[str | None, str], int] = {}
    alias_rows: set[tuple[str, int]] = set()

    def team_row(name, country, founded=None, city=None, stadium=None) -> int:
        key = (country, name)
        if key in team_ids:
            return team_ids[key]
        cur = db.execute("INSERT INTO teams (name,country_code,founded,city,stadium) VALUES (?,?,?,?,?)",
                         (name, country, founded, city, stadium))
        team_ids[key] = cur.lastrowid
        return cur.lastrowid

    confed_countries: dict[str, list[str]] = defaultdict(list)
    for c in countries:
        confed_countries[c["confederation"]].append(c["code"])
        confed_countries["FIFA"].append(c["code"])

    def guess_country(name: str, confed: str | None) -> str | None:
        if not confed:
            return None
        hits = {c for c in confed_countries[confed] if clubs.lookup(c, name)}
        if len(hits) != 1:
            k = strip_key(name)
            hits = {c for c in confed_countries[confed] if (c, k) in team_by_strip} if not hits else hits
        return hits.pop() if len(hits) == 1 else None

    def resolve(raw: str, default_country: str | None, create: bool = True, confed: str | None = None) -> int | None:
        name, country = raw.strip(), default_country
        m = re.fullmatch(r"(.*?)\s*\(([A-Z]{3})\)", name)
        if m:
            name, fifa = m.group(1).strip(), m.group(2)
            country = code_by_fifa.get(fifa, country)
        if country is None:
            country = guess_country(name, confed)
        name = manual_alias.get((country, norm(name)), name)
        tries = [country] + NEIGHBOURS.get(country or "", [])
        for c in tries:
            rec = clubs.lookup(c, name) if c else None
            if rec:
                tid = team_row(rec["name"], c, rec["founded"], rec["city"], rec["stadium"])
                alias_rows.add((name, tid))
                for a in rec["aliases"]:
                    alias_rows.add((a, tid))
                team_by_strip.setdefault((c, strip_key(name)), tid)
                return tid
        sk = (country, strip_key(name))
        if sk in team_by_strip:
            tid = team_by_strip[sk]
            alias_rows.add((name, tid))
            return tid
        if not create:
            return None
        tid = team_row(name, country)
        team_by_strip[sk] = tid
        alias_rows.add((name, tid))
        return tid

    # ---- seasons & matches -------------------------------------------------------------------
    n_matches = 0
    for (code, season), parts in sorted(selected.items()):
        first = parts[0][1]
        title = next((p[1][3].get("name") for p in parts if p[1][3].get("name")), None) or code
        confed = None
        if code in comp_ids and code.split(".")[0] not in country_codes:
            comp_id = comp_ids[code]
            default_country = None
            confed = db.execute("SELECT confederation FROM competitions WHERE id=?", (comp_id,)).fetchone()[0]
        else:
            comp_id = domestic_comp(code, title)
            default_country = code.split(".")[0]
        if code == "us.1":
            default_country = "us"
        start = first[4]
        sources = ";".join(sorted(p[1][2] for p in parts))
        cur = db.execute("INSERT INTO seasons (competition_id,season,start_year,title,source) VALUES (?,?,?,?,?)",
                         (comp_id, season, start, re.sub(r"\s*-\s*Quali", "", title), sources))
        season_id = cur.lastrowid
        seen: set[tuple] = set()
        rows = []
        for part, (_, _, rel, data, _) in sorted(parts, key=lambda p: p[0] != "q"):
            for mt in data.get("matches", []):
                t1, t2 = mt.get("team1"), mt.get("team2")
                if isinstance(t1, dict):
                    t1 = t1.get("name")
                if isinstance(t2, dict):
                    t2 = t2.get("name")
                if not t1 or not t2:
                    continue
                h = resolve(t1, default_country, confed=confed)
                a = resolve(t2, default_country, confed=confed)
                date = mt.get("date")
                key = (date, h, a)
                if key in seen:
                    continue
                seen.add(key)
                sc = parse_score(mt.get("score"))
                hft, aft = pair(sc, "ft")
                hht, aht = pair(sc, "ht")
                het, aet = pair(sc, "et")
                hp, ap_ = pair(sc, "p")
                played = hft is not None or het is not None
                rnd = mt.get("round")
                group = mt.get("group")
                if part == "q":
                    stage = "Qualifying"
                elif group:
                    stage = group
                elif rnd and "," in rnd:
                    stage = rnd.split(",")[0].strip()
                elif rnd and (GROUP_RE.match(rnd) or KNOCKOUT_RE.search(rnd)):
                    stage = rnd
                else:
                    stage = None
                rows.append((season_id, stage, rnd, date, mt.get("time"), h, a, hft, aft, hht, aht,
                             het, aet, hp, ap_, "played" if played else "scheduled",
                             mt.get("ground") if isinstance(mt.get("ground"), str) else None))
        rows.sort(key=lambda r: (r[3] or "", r[4] or ""))
        db.executemany(
            "INSERT INTO matches (season_id,stage,round,match_date,kickoff,home_team_id,away_team_id,"
            "home_ft,away_ft,home_ht,away_ht,home_et,away_et,home_pen,away_pen,status,ground)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        db.execute("UPDATE seasons SET matches_count=? WHERE id=?", (len(rows), season_id))
        n_matches += len(rows)
    print(f"matches loaded: {n_matches}")

    db.executemany("INSERT OR IGNORE INTO team_aliases (alias, team_id) VALUES (?,?)", sorted(alias_rows))

    # ---- standings -----------------------------------------------------------------------------
    comp_type = dict(db.execute("SELECT id, type FROM competitions"))
    season_rows = db.execute("SELECT id, competition_id FROM seasons").fetchall()
    st_rows = []
    for season_id, comp_id in season_rows:
        is_league = comp_type[comp_id] == "league"
        tables: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0] * 7))
        for stage, rnd, h, a, hg, ag in db.execute(
                "SELECT stage, round, home_team_id, away_team_id, home_ft, away_ft FROM matches"
                " WHERE season_id=? AND status='played' AND home_ft IS NOT NULL", (season_id,)):
            label = stage or rnd or ""
            if is_league:
                if KNOCKOUT_RE.search(label):
                    continue
                phase = stage if stage and "," in (rnd or "") else "Regular season"
            else:
                if not stage or not GROUP_RE.match(stage):
                    continue
                phase = stage
            for tid, gf, ga in ((h, hg, ag), (a, ag, hg)):
                r = tables[phase][tid]
                r[0] += 1
                if gf > ga:
                    r[1] += 1
                elif gf == ga:
                    r[2] += 1
                else:
                    r[3] += 1
                r[4] += gf
                r[5] += ga
        for phase, tbl in tables.items():
            ordered = sorted(tbl.items(), key=lambda kv: (-(kv[1][1] * 3 + kv[1][2]),
                                                            -(kv[1][4] - kv[1][5]), -kv[1][4], kv[0]))
            for pos, (tid, r) in enumerate(ordered, 1):
                st_rows.append((season_id, phase, pos, tid, r[0], r[1], r[2], r[3], r[4], r[5],
                                r[4] - r[5], r[1] * 3 + r[2]))
    db.executemany("INSERT INTO standings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", st_rows)
    print(f"standings rows: {len(st_rows)}")

    # ---- continental champions --------------------------------------------------------------
    for ch in champions:
        tid = resolve(f"{ch['winner']} ({ch['winner_country']})", None, create=False)
        db.execute("INSERT INTO continental_champions VALUES (?,?,?,?,?)",
                   (comp_ids[ch["competition"]], ch["season"], ch["winner"], ch["winner_country"], tid))

    # ---- competition access ------------------------------------------------------------------
    cont = db.execute("SELECT id, confederation FROM competitions WHERE type IN ('continental','intercontinental')"
                      " AND (last_season IS NULL)").fetchall()
    access = []
    for c in countries:
        if c["code"] == "mc" or (c["code"] == "ru"):
            continue  # Monaco plays via France; Russia suspended from UEFA competitions
        for cid, confed in cont:
            if confed in (c["confederation"], "FIFA"):
                access.append((c["code"], cid))
    db.executemany("INSERT INTO competition_access VALUES (?,?)", access)

    db.commit()
    db.execute("VACUUM")
    db.execute("ANALYZE")
    db.close()

    # ---- exports -----------------------------------------------------------------------------
    WEB_DB.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_DB, "rb") as src, gzip.open(WEB_DB, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    if not args.no_csv:
        export_csv()
    write_coverage()
    summary()
    return 0


def export_csv() -> None:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(OUT_DB)
    for table in ["confederations", "countries", "competitions", "seasons", "teams", "team_aliases",
                  "continental_champions", "competition_access", "v_matches", "v_standings"]:
        cur = db.execute(f"SELECT * FROM {table}")
        name = table.removeprefix("v_")
        opener = gzip.open if name in ("matches", "standings") else open
        fname = CSV_DIR / (f"{name}.csv.gz" if opener is gzip.open else f"{name}.csv")
        with opener(fname, "wt", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow([d[0] for d in cur.description])
            w.writerows(cur)
    db.close()


def write_coverage() -> None:
    """data/COVERAGE.md: which seasons exist for each competition."""
    db = sqlite3.connect(OUT_DB)
    years = [r[0] for r in db.execute("SELECT DISTINCT start_year FROM seasons ORDER BY 1")]
    rows = db.execute("""
        SELECT c.code, c.name, COALESCE(co.name, c.confederation), c.type,
               GROUP_CONCAT(s.start_year), SUM(s.matches_count)
        FROM competitions c JOIN seasons s ON s.competition_id = c.id
        LEFT JOIN countries co ON co.code = c.country_code
        GROUP BY c.id
        ORDER BY c.country_code IS NOT NULL, COALESCE(co.name, c.confederation), c.tier IS NULL, c.tier, c.code
    """).fetchall()
    total = db.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    out = ["# Coverage", "", f"Generated by `scripts/build_db.py`. {total:,} matches, {len(rows)} competitions with data.",
           "", "`●` = season present (season labelled by its start year).", "",
           "| Country / Confed | Code | Competition | Matches | " + " | ".join(f"{y % 100:02d}" for y in years) + " |",
           "|---|---|---|---:|" + "|".join([":-:"] * len(years)) + "|"]
    for code, name, owner, ctype, ys, n in rows:
        have = {int(y) for y in ys.split(",")}
        out.append(f"| {owner} | `{code}` | {name} | {n:,} | " + " | ".join("●" if y in have else "" for y in years) + " |")
    no_data = db.execute("""SELECT co.name, c.name FROM competitions c JOIN countries co ON co.code=c.country_code
        WHERE NOT EXISTS (SELECT 1 FROM seasons s WHERE s.competition_id=c.id) ORDER BY co.confederation, co.name""").fetchall()
    out += ["", f"## Leagues registered without match data yet ({len(no_data)})", "",
            ", ".join(f"{a} ({b})" for a, b in no_data), ""]
    (OUT_DB.parent / "COVERAGE.md").write_text("\n".join(out), encoding="utf-8")
    db.close()


def summary() -> None:
    db = sqlite3.connect(OUT_DB)
    q = lambda s: db.execute(s).fetchone()[0]
    print("---- summary ----")
    for t in ["countries", "competitions", "seasons", "teams", "matches", "standings", "continental_champions"]:
        print(f"{t:24s}{q(f'SELECT COUNT(*) FROM {t}'):>10,}")
    print(f"{'countries with matches':24s}{q('SELECT COUNT(DISTINCT country_code) FROM competitions c JOIN seasons s ON s.competition_id=c.id WHERE country_code IS NOT NULL'):>10,}")
    db.close()


if __name__ == "__main__":
    sys.exit(main())
