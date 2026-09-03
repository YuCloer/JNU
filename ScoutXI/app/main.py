from __future__ import annotations

import json
import hashlib
import http.client
import os
import re
import sqlite3
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .scouting import ability_profile, recommend_xi, select_xi, sort_players_by_ability

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "scoutxi.db"
STATIC_DIR = ROOT / "static"


def load_local_env() -> None:
    """Load local server-only settings before the ASGI app is initialised."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()
app = FastAPI(title="ScoutXI", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
full_sync_lock = threading.Lock()
full_sync_status = {"running": False, "remaining": None, "completed": 0, "error": None}
transfer_sync_status = {"running": False, "remaining": None, "completed": 0, "mapped": 0, "error": None}
ea_rating_sync_lock = threading.Lock()
ea_rating_sync_status = {"running": False, "completed_pages": 0, "next_page": 0, "matched": 0, "error": None}

TEAM_SOURCES = {"man-city": 65, "arsenal": 57, "real-madrid": 86, "liverpool": 64, "man-utd": 66, "chelsea": 61, "barcelona": 81, "bayern": 5}
TEAM_SEARCH_NAMES = {"man-city": "Manchester City", "arsenal": "Arsenal", "real-madrid": "Real Madrid", "liverpool": "Liverpool", "man-utd": "Manchester United", "chelsea": "Chelsea", "barcelona": "Barcelona", "bayern": "Bayern Munich"}
FOOTBALL_DATA_LEAGUES = {"PL": "英超", "PD": "西甲", "SA": "意甲", "BL1": "德甲", "FL1": "法甲"}
API_FOOTBALL_LEAGUES = {"PL": (39, "英超"), "PD": (140, "西甲"), "SA": (135, "意甲"), "BL1": (78, "德甲"), "FL1": (61, "法甲")}
API_FOOTBALL_FEATURED_CLUBS = {50: "man-city", 42: "arsenal", 541: "real-madrid", 40: "liverpool", 33: "man-utd", 49: "chelsea", 529: "barcelona", 157: "bayern"}
# football-data.org's free plan covers the five major leagues only.  These
# prominent clubs add the requested Portuguese, Scottish and other well-known
# leagues through TheSportsDB's public player directory; the sync endpoint
# below records its own source and timestamp rather than pretending it is the
# five-league provider.
SUPPLEMENTAL_CLUBS = (
    ("Benfica", "葡萄牙", "葡超"), ("Porto", "葡萄牙", "葡超"), ("Sporting CP", "葡萄牙", "葡超"),
    ("Celtic", "苏格兰", "苏超"), ("Rangers", "苏格兰", "苏超"),
    ("Ajax", "荷兰", "荷甲"), ("PSV Eindhoven", "荷兰", "荷甲"), ("Feyenoord", "荷兰", "荷甲"),
    ("Galatasaray", "土耳其", "土超"), ("Fenerbahce", "土耳其", "土超"),
    ("Inter Miami", "美国", "美职联"), ("Al Nassr", "沙特阿拉伯", "沙特联"),
)
# These two globally recognised active players are intentionally retained even
# when their domestic competitions are outside the five-league provider plan.
# The portrait URLs are public TheSportsDB remote assets; no image is stored.
PRESTIGE_PLAYERS = (
    ("prestige-lionel-messi", "Lionel Messi", "梅西", "RW", "1987-06-24", "阿根廷", "左", "tsdb-137699", 10,
     "Inter Miami", "美国", "美职联", "https://r2.thesportsdb.com/images/media/player/thumb/kpfsvp1725295651.jpg"),
    ("prestige-cristiano-ronaldo", "Cristiano Ronaldo", "C 罗", "ST", "1985-02-05", "葡萄牙", "右", "tsdb-136022", 7,
     "Al-Nassr", "沙特阿拉伯", "沙特联", "https://r2.thesportsdb.com/images/media/player/thumb/bkre241600892282.jpg"),
)
# These names have ambiguous (or historically incorrect) matches in free image
# providers, so they always use an exact public Wikimedia page instead.
WIKIMEDIA_PLAYER_TITLES = {
    "Rodri": "Rodri (footballer, born 1996)",
    "Sávio": "Sávio (footballer, born 2004)",
}
OFFICIAL_AVATAR_URLS = {
    # Premier League player id 220566, taken from its public profile metadata.
    "Rodri": "https://resources.premierleague.com/premierleague25/photos/players/110x140/220566.png",
}
CURATED_AVATAR_NAMES = frozenset(WIKIMEDIA_PLAYER_TITLES)

# Verified transfer events are data, not roster code.  They are seeded once
# into SQLite with source URLs, then the same reconciliation algorithm applies
# to every event and every club.
# Roster membership comes from the active provider snapshot and its verified
# transfer feed.  Do not keep player-specific transfer exceptions in code.
OFFICIAL_TRANSFER_SEED: tuple[tuple, ...] = ()

# API-Football's free roster endpoint may lag the current transfer window, but
# its team transfer history includes the recent moves.  We therefore use it as
# a reconciliation source for *every* club, rather than keeping player-level
# exceptions in code.  The date is intentionally derived from the season, not
# hard-coded, so the same process continues to work next summer.
TRANSFER_MAPPING_SEASON_OFFSET = 2
TRANSFER_SYNC_REQUEST_BUDGET = 90

# football-data.org exposes broad roles for some people. These current-squad
# corrections retain the detailed tactical role required by the lineup editor.
POSITION_OVERRIDES = {
    "Ben White": "RB", "Bruno Guimarães": "CM", "Bukayo Saka": "RW", "Christian Nørgaard": "DM", "Christos Tzolis": "LW", "Cristhian Mosquera": "CB", "David Raya": "GK", "Declan Rice": "CM", "Eberechi Eze": "AM", "Ethan Nwaneri": "AM", "Fabio Vieira": "AM", "Gabriel Jesus": "ST", "Gabriel Magalhães": "CB", "Illan Meslier": "GK", "Jurrien Timber": "RB", "Kai Havertz": "ST", "Kepa Arrizabalaga": "GK", "Martin Ødegaard": "AM", "Martinelli": "LW", "Martín Zubimendi": "DM", "Max Dowman": "AM", "Mikel Merino": "CM", "Myles Lewis-Skelly": "LB", "Noni Madueke": "RW", "Piero Hincapié": "CB", "Reiss Nelson": "RW", "Riccardo Calafiori": "CB", "Tommy Setford": "GK", "Viktor Gyökeres": "ST", "William Saliba": "CB",
    "Abdukodir Khusanov": "CB", "Antoine Semenyo": "RW", "Claudio Echeverri": "AM", "Elliot Anderson": "CM", "Erling Haaland": "ST", "Gianluigi Donnarumma": "GK", "Géronimo Rulli": "GK", "Issa Kaboré": "RB", "Jack Grealish": "LW", "James Trafford": "GK", "Jeremy Doku": "LW", "Jeremy Monga": "RW", "Josh Wilson-Esbrand": "LB", "Joško Gvardiol": "CB", "Juma Bah": "CB", "Kalvin Phillips": "DM", "Marc Guéhi": "CB", "Marcus Bettinelli": "GK", "Mateo Kovačić": "CM", "Matheus Nunes": "CM", "Max Alleyne": "CB", "Nico Gonzalez": "DM", "Nico O'Reilly": "CM", "Omar Marmoush": "ST", "Phil Foden": "AM", "Rayan Aït Nouri": "LB", "Rayan Cherki": "AM", "Rico Lewis": "RB", "Rodri": "DM", "Ryan McAidoo": "RW", "Rúben Dias": "CB", "Sávio": "RW", "Tijjani Reijnders": "CM", "Vitor Reis": "CB",
    "Andriy Lunin": "GK", "Antonio Rüdiger": "CB", "Arda Guler": "AM", "Aurélien Tchouameni": "DM", "Bernardo Silva": "AM", "Brahim Diaz": "AM", "Carlos Espí": "ST", "Cucurella": "LB", "David Jiménez": "RB", "Dean Huijsen": "CB", "Denzel Dumfries": "RB", "Eduardo Camavinga": "CM", "Endrick": "ST", "Federico Valverde": "CM", "Ferland Mendy": "LB", "Ibrahima Konaté": "CB", "Jude Bellingham": "AM", "Kylian Mbappé": "ST", "Manuel Angel": "CM", "Raúl": "CB", "Rodrygo": "RW", "Thiago Pitarch": "CM", "Thibaut Courtois": "GK", "Trent Alexander-Arnold": "RB", "Vinicius Junior": "LW", "Yan Diomandé": "RW", "Álvaro Carreras": "LB", "Éder Militão": "CB",
}

# Each starter occupies one fixed tactical zone. The attack direction is bottom -> top.
# Position allowances mirror real tactical responsibilities: centre-backs do not silently
# become full-backs or wing-backs, while wide forwards retain realistic flexibility.
FORMATION_ZONES = {
    "4-3-3": {
        "GK": (.50, .91, {"GK"}), "LB": (.16, .76, {"LB"}), "LCB": (.39, .77, {"CB"}), "RCB": (.61, .77, {"CB"}), "RB": (.84, .76, {"RB"}),
        "LCM": (.25, .54, {"CM", "DM"}), "CM": (.50, .59, {"CM", "DM"}), "RCM": (.75, .54, {"CM", "DM"}),
        "LW": (.18, .27, {"LW", "AM", "RW"}), "ST": (.50, .16, {"ST", "LW", "RW"}), "RW": (.82, .27, {"RW", "AM", "LW"}),
    },
    "4-2-3-1": {
        "GK": (.50, .91, {"GK"}), "LB": (.16, .76, {"LB"}), "LCB": (.39, .77, {"CB"}), "RCB": (.61, .77, {"CB"}), "RB": (.84, .76, {"RB"}),
        "LDM": (.35, .60, {"DM", "CM"}), "RDM": (.65, .60, {"DM", "CM"}), "LW": (.20, .39, {"LW", "AM", "RW"}),
        "AM": (.50, .34, {"AM", "CM"}), "RW": (.80, .39, {"RW", "AM", "LW"}), "ST": (.50, .16, {"ST", "LW", "RW"}),
    },
    "4-4-2": {
        "GK": (.50, .91, {"GK"}), "LB": (.15, .76, {"LB"}), "LCB": (.38, .77, {"CB"}), "RCB": (.62, .77, {"CB"}), "RB": (.85, .76, {"RB"}),
        "LM": (.17, .52, {"LW", "AM"}), "LCM": (.39, .56, {"CM", "DM"}), "RCM": (.61, .56, {"CM", "DM"}), "RM": (.83, .52, {"RW", "AM"}),
        "LST": (.38, .19, {"ST", "LW", "RW"}), "RST": (.62, .19, {"ST", "LW", "RW"}),
    },
    "4-1-4-1": {
        "GK": (.50, .91, {"GK"}), "LB": (.15, .76, {"LB"}), "LCB": (.38, .77, {"CB"}), "RCB": (.62, .77, {"CB"}), "RB": (.85, .76, {"RB"}),
        "DM": (.50, .64, {"DM", "CM"}), "LW": (.16, .42, {"LW", "AM", "RW"}), "LCM": (.38, .48, {"CM", "DM"}), "RCM": (.62, .48, {"CM", "DM"}),
        "RW": (.84, .42, {"RW", "AM", "LW"}), "ST": (.50, .16, {"ST", "LW", "RW"}),
    },
    "4-3-1-2": {
        "GK": (.50, .91, {"GK"}), "LB": (.15, .76, {"LB"}), "LCB": (.38, .77, {"CB"}), "RCB": (.62, .77, {"CB"}), "RB": (.85, .76, {"RB"}),
        "LCM": (.30, .55, {"CM", "DM"}), "DM": (.50, .62, {"DM", "CM"}), "RCM": (.70, .55, {"CM", "DM"}), "AM": (.50, .35, {"AM", "CM"}),
        "LST": (.38, .18, {"ST", "LW", "RW"}), "RST": (.62, .18, {"ST", "LW", "RW"}),
    },
    "4-2-2-2": {
        "GK": (.50, .91, {"GK"}), "LB": (.15, .76, {"LB"}), "LCB": (.38, .77, {"CB"}), "RCB": (.62, .77, {"CB"}), "RB": (.85, .76, {"RB"}),
        "LDM": (.36, .61, {"DM", "CM"}), "RDM": (.64, .61, {"DM", "CM"}), "LAM": (.34, .39, {"AM", "LW", "CM"}), "RAM": (.66, .39, {"AM", "RW", "CM"}),
        "LST": (.38, .18, {"ST", "LW", "RW"}), "RST": (.62, .18, {"ST", "LW", "RW"}),
    },
    "4-3-2-1": {
        "GK": (.50, .91, {"GK"}), "LB": (.15, .76, {"LB"}), "LCB": (.38, .77, {"CB"}), "RCB": (.62, .77, {"CB"}), "RB": (.85, .76, {"RB"}),
        "LCM": (.30, .56, {"CM", "DM"}), "CM": (.50, .61, {"CM", "DM"}), "RCM": (.70, .56, {"CM", "DM"}), "LAM": (.36, .36, {"AM", "LW", "CM"}),
        "RAM": (.64, .36, {"AM", "RW", "CM"}), "ST": (.50, .16, {"ST", "LW", "RW"}),
    },
    "3-4-3": {
        "GK": (.50, .91, {"GK"}), "LCB": (.25, .76, {"CB"}), "CB": (.50, .80, {"CB"}), "RCB": (.75, .76, {"CB"}),
        "LWB": (.13, .53, {"LB", "LW"}), "LCM": (.38, .56, {"CM", "DM"}), "RCM": (.62, .56, {"CM", "DM"}), "RWB": (.87, .53, {"RB", "RW"}),
        "LW": (.18, .25, {"LW", "AM", "RW"}), "ST": (.50, .16, {"ST", "LW", "RW"}), "RW": (.82, .25, {"RW", "AM", "LW"}),
    },
    "3-5-2": {
        "GK": (.50, .91, {"GK"}), "LCB": (.24, .76, {"CB"}), "CB": (.50, .80, {"CB"}), "RCB": (.76, .76, {"CB"}),
        "LWB": (.12, .53, {"LB", "LW"}), "LCM": (.32, .56, {"CM", "DM"}), "CM": (.50, .50, {"CM", "DM"}), "RCM": (.68, .56, {"CM", "DM"}), "RWB": (.88, .53, {"RB", "RW"}),
        "LST": (.38, .19, {"ST", "LW", "RW"}), "RST": (.62, .19, {"ST", "LW", "RW"}),
    },
    "3-4-2-1": {
        "GK": (.50, .91, {"GK"}), "LCB": (.24, .76, {"CB"}), "CB": (.50, .80, {"CB"}), "RCB": (.76, .76, {"CB"}),
        "LWB": (.13, .54, {"LB", "LW"}), "LCM": (.38, .57, {"CM", "DM"}), "RCM": (.62, .57, {"CM", "DM"}), "RWB": (.87, .54, {"RB", "RW"}),
        "LAM": (.34, .34, {"AM", "LW", "CM"}), "RAM": (.66, .34, {"AM", "RW", "CM"}), "ST": (.50, .16, {"ST", "LW", "RW"}),
    },
    "3-1-4-2": {
        "GK": (.50, .91, {"GK"}), "LCB": (.25, .76, {"CB"}), "CB": (.50, .80, {"CB"}), "RCB": (.75, .76, {"CB"}),
        "DM": (.50, .64, {"DM", "CM"}), "LWB": (.12, .48, {"LB", "LW"}), "LCM": (.38, .52, {"CM", "DM"}), "RCM": (.62, .52, {"CM", "DM"}),
        "RWB": (.88, .48, {"RB", "RW"}), "LST": (.38, .18, {"ST", "LW", "RW"}), "RST": (.62, .18, {"ST", "LW", "RW"}),
    },
    "5-3-2": {
        "GK": (.50, .91, {"GK"}), "LWB": (.12, .62, {"LB", "LW"}), "LCB": (.28, .77, {"CB"}), "CB": (.50, .80, {"CB"}), "RCB": (.72, .77, {"CB"}),
        "RWB": (.88, .62, {"RB", "RW"}), "LCM": (.30, .49, {"CM", "DM"}), "CM": (.50, .54, {"CM", "DM"}), "RCM": (.70, .49, {"CM", "DM"}),
        "LST": (.38, .18, {"ST", "LW", "RW"}), "RST": (.62, .18, {"ST", "LW", "RW"}),
    },
    "5-4-1": {
        "GK": (.50, .91, {"GK"}), "LWB": (.12, .68, {"LB", "LW"}), "LCB": (.30, .78, {"CB"}), "CB": (.50, .80, {"CB"}), "RCB": (.70, .78, {"CB"}),
        "RWB": (.88, .68, {"RB", "RW"}), "LM": (.18, .47, {"LW", "AM"}), "LCM": (.40, .52, {"CM", "DM"}), "RCM": (.60, .52, {"CM", "DM"}),
        "RM": (.82, .47, {"RW", "AM"}), "ST": (.50, .17, {"ST", "LW", "RW"}),
    },
}


def formation_zone_payload(formation: str = "4-3-3") -> list[dict]:
    """Expose one canonical formation definition to API consumers."""
    return [
        {"role": role, "x": x, "y": y, "allow": sorted(allow)}
        for role, (x, y, allow) in FORMATION_ZONES[formation].items()
    ]


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def rows(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(item) for item in cursor.fetchall()]


def player_payload(value: sqlite3.Row | dict) -> dict:
    payload = dict(value)
    payload.update(ability_profile(payload))
    if not payload.get("avatar_url") and payload.get("ea_avatar_url"):
        payload["avatar_url"] = payload["ea_avatar_url"]
        payload["avatar_kind"] = "official_rating"
    elif payload.get("avatar_url"):
        payload["avatar_kind"] = "verified"
    else:
        # A deliberately neutral black silhouette is preferable to a fabricated
        # portrait when a provider cannot supply a verifiable player image.
        payload["avatar_url"] = None
        payload["avatar_kind"] = "default"
    return payload


def player_payloads(values: list[dict]) -> list[dict]:
    return [player_payload(value) for value in values]


def seed_transfer_events(connection: sqlite3.Connection) -> None:
    connection.executemany("""INSERT OR IGNORE INTO transfer_events
        (id,player_name,from_club_id,to_club_id,transfer_type,effective_at,source_url,source_name,verified_at)
        VALUES(?,?,?,?,?,?,?,?,?)""", [(*event, datetime.now(timezone.utc).isoformat()) for event in OFFICIAL_TRANSFER_SEED])


def remove_legacy_transfer_overrides(connection: sqlite3.Connection) -> None:
    """Remove earlier hard-coded corrections so they cannot outvote a refresh."""
    connection.execute("DELETE FROM transfer_events WHERE id IN ('2026-trafford-leeds','2026-marmoush-spurs')")


def retire_duplicate_seed_players(connection: sqlite3.Connection) -> int:
    """A provider record supersedes the old demonstration copy of a player."""
    legacy = rows(connection.execute("SELECT id,name,club_id FROM players WHERE is_current=1 AND data_source='seed'"))
    retired = 0
    for player in legacy:
        duplicate = connection.execute("SELECT 1 FROM players WHERE is_current=1 AND data_source<>'seed' AND club_id=? AND name=?", (player["club_id"], player["name"])).fetchone()
        if duplicate:
            connection.execute("UPDATE players SET is_current=0 WHERE id=?", (player["id"],))
            retired += 1
    return retired


def transfer_window_start() -> str:
    return f"{current_season_year()}-06-01"


def normalize_club_name(value: str) -> str:
    """A conservative normaliser for provider spelling differences only."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    value = value.replace("saint", "st")
    value = re.sub(r"\b(football|club|fc|cf|ac|as|ssc|vfl|vfb|sc)\b", " ", value)
    key = re.sub(r"[^a-z0-9]", "", value)
    aliases = {
        "bayernmunchen": "bayernmunich", "parisstgermain": "parissg", "intermilan": "inter",
        "athleticclub": "athletic", "borussiamonchengladbach": "borussiamgladbach",
        "1unionberlin": "unionberlin", "bayer04leverkusen": "bayerleverkusen",
        "svwerderbremen": "werderbremen", "tsg1899hoffenheim": "1899hoffenheim",
        "fsvmainz05": "mainz05", "1fsvmainz05": "mainz05", "vflwolfsburg": "wolfsburg", "vflbochum": "bochum",
        "afcbournemouth": "bournemouth", "brightonhovealbion": "brighton",
        "tottenhamhotspur": "tottenham", "newcastleunited": "newcastle", "leedsunited": "leeds",
        "tottenhamhotspur": "tottenham", "newcastleunited": "newcastle", "leedsunited": "leeds",
        "nottinghamforest": "nottinghamforest", "asmonaco": "monaco", "angerssco": "angers",
        "ajauxerre": "auxerre", "lilleosc": "lille", "ogcnice": "nice",
        "olympiquelyonnais": "lyon", "olympiquedemarseille": "marseille",
        "racingdelens": "lens", "staderennais1901": "rennes", "rcstrasbourgalsace": "strasbourg",
        "caosasuna": "osasuna", "atleticodemadrid": "atleticomadrid", "deportivoalaves": "alaves",
        "rcceltadevigo": "celtavigo", "rcdespanyoldebarcelona": "espanyol",
        "rayovallecanodemadrid": "rayovallecano", "realbetisbalompie": "realbetis",
        "realsociedaddefutbol": "realsociedad", "acffiorentina": "fiorentina",
        "atalantabc": "atalanta", "bologna1909": "bologna", "cagliaricalcio": "cagliari",
        "como1907": "como", "internazionalemilano": "inter", "genoacfc": "genoa",
        "parmacalcio1913": "parma", "sslazio": "lazio", "uslecce": "lecce",
        "sassuolocalcio": "sassuolo", "udinesecalcio": "udinese",
    }
    return aliases.get(key, key)


def best_club_match(candidates: list[dict], provider_name: str) -> str | None:
    """Return a club only when the name match is unambiguous."""
    wanted = normalize_club_name(provider_name)
    exact = [club["club_id"] for club in candidates if normalize_club_name(club["team_name"]) == wanted]
    if len(exact) == 1:
        return exact[0]
    close = [club["club_id"] for club in candidates if wanted and (wanted in normalize_club_name(club["team_name"]) or normalize_club_name(club["team_name"]) in wanted)]
    return close[0] if len(close) == 1 else None


def player_matches_event(player_name: str, event_name: str) -> bool:
    """Match full names and API-Football's common 'A. Surname' shorthand."""
    player = normalize_person_name(player_name)
    event = normalize_person_name(event_name)
    if player == event:
        return True
    raw_player, raw_event = player_name.split(), event_name.split()
    if len(raw_player) < 2 or len(raw_event) < 2:
        return False
    return (normalize_person_name(raw_player[-1]) == normalize_person_name(raw_event[-1])
            and normalize_person_name(raw_player[0])[:1] == normalize_person_name(raw_event[0])[:1])


def reconcile_current_rosters(connection: sqlite3.Connection) -> dict:
    """Resolve verified transfers after each provider squad snapshot is imported."""
    applied, removed, pending = 0, 0, []
    events = rows(connection.execute("SELECT * FROM transfer_events WHERE verified_at IS NOT NULL ORDER BY effective_at"))
    for event in events:
        people = rows(connection.execute("SELECT * FROM players WHERE is_current=1"))
        matches = [player for player in people if player_matches_event(player["name"], event["player_name"])]
        if not matches:
            pending.append(event["id"])
            continue
        target_exists = bool(connection.execute("SELECT 1 FROM clubs WHERE id=?", (event["to_club_id"],)).fetchone())
        target = next((player for player in matches if player["club_id"] == event["to_club_id"]), None)
        if target:
            connection.execute("UPDATE players SET is_current=0 WHERE id<>? AND is_current=1 AND id IN ({})".format(
                ",".join("?" for _ in matches)), [target["id"], *[player["id"] for player in matches]])
            continue
        source = next((player for player in matches if player["club_id"] == event["from_club_id"]), None)
        if source and target_exists:
            connection.execute("""UPDATE players SET club_id=?, is_current=1, data_source=?, source_updated_at=?,
                bio=?, avatar_url=NULL, avatar_club_id=NULL, avatar_verified_at=NULL WHERE id=?""", (event["to_club_id"], f"官方转会校正：{event['source_name']}", event["verified_at"],
                f"{event['transfer_type']}；以官方公告为准：{event['source_url']}", source["id"]))
            applied += 1
        elif source and not target_exists:
            # The player left the five-league scope.  Do not invent a new club
            # record; simply remove the stale source-roster entry.
            connection.execute("UPDATE players SET is_current=0, data_source=?, source_updated_at=? WHERE id=?",
                (f"转会校正：{event['source_name']}", event["verified_at"], source["id"]))
            removed += 1
        elif target_exists:
            # The source squad may already have been superseded by a different
            # provider.  Move an unambiguous current record into the target.
            source = matches[0] if len(matches) == 1 else None
            if source:
                connection.execute("""UPDATE players SET club_id=?, is_current=1, data_source=?, source_updated_at=?,
                    avatar_url=NULL, avatar_club_id=NULL, avatar_verified_at=NULL WHERE id=?""",
                    (event["to_club_id"], f"转会校正：{event['source_name']}", event["verified_at"], source["id"]))
                applied += 1
            else:
                pending.append(event["id"])
        else:
            pending.append(event["id"])
    return {"applied": applied, "removed": removed, "pending_count": len(pending), "pending": pending[:30]}


def seed(connection: sqlite3.Connection) -> None:
    if connection.execute("SELECT COUNT(*) FROM players").fetchone()[0]:
        return
    clubs = [
        ("man-city", "Manchester City", "英格兰", "英超"),
        ("real-madrid", "Real Madrid", "西班牙", "西甲"),
        ("arsenal", "Arsenal", "英格兰", "英超"),
    ]
    players = [
        ("ederson", "Ederson", "埃德森", "GK", 31, "巴西", "右", "man-city", 31, 188, "出球稳健，善于参与后场组织。", 38, 0, 0, 91),
        ("ruben-dias", "Ruben Dias", "鲁本·迪亚斯", "CB", 28, "葡萄牙", "右", "man-city", 3, 187, "防守指挥与对抗能力突出。", 35, 2, 0, 89),
        ("josko-gvardiol", "Josko Gvardiol", "格瓦迪奥尔", "LB", 24, "克罗地亚", "左", "man-city", 24, 185, "能在左路提供推进与内收选择。", 34, 5, 3, 88),
        ("rodri", "Rodri", "罗德里", "DM", 29, "西班牙", "右", "man-city", 16, 191, "节奏控制与防守覆盖核心。", 32, 4, 8, 93),
        ("phil-foden", "Phil Foden", "福登", "AM", 26, "英格兰", "左", "man-city", 47, 171, "狭小空间持球和最后一传优秀。", 36, 15, 10, 91),
        ("erling-haaland", "Erling Haaland", "哈兰德", "ST", 26, "挪威", "左", "man-city", 9, 195, "禁区终结效率极高，冲刺威胁明确。", 31, 27, 5, 94),
        ("kevin-de-bruyne", "Kevin De Bruyne", "德布劳内", "AM", 35, "比利时", "右", "man-city", 17, 181, "传球视野出色，能创造高质量机会。", 28, 6, 12, 90),
        ("bernardo-silva", "Bernardo Silva", "贝尔纳多·席尔瓦", "RW", 32, "葡萄牙", "左", "man-city", 20, 173, "高压下控球可靠，跑动积极。", 33, 8, 9, 89),
        ("bukayo-saka", "Bukayo Saka", "萨卡", "RW", 25, "英格兰", "左", "arsenal", 7, 178, "右路持球突破与反抢俱佳。", 35, 16, 11, 90),
        ("martin-odegaard", "Martin Odegaard", "厄德高", "AM", 27, "挪威", "左", "arsenal", 8, 178, "擅长在半空间组织与压迫。", 34, 10, 12, 89),
        ("kylian-mbappe", "Kylian Mbappe", "姆巴佩", "LW", 27, "法国", "右", "real-madrid", 9, 178, "速度与一对一突破能力顶尖。", 36, 29, 7, 95),
        ("jude-bellingham", "Jude Bellingham", "贝林厄姆", "CM", 23, "英格兰", "右", "real-madrid", 5, 186, "覆盖范围大，禁区前插威胁强。", 37, 15, 10, 92),
    ]
    connection.executemany("INSERT INTO clubs(id,name,country,league) VALUES (?, ?, ?, ?)", clubs)
    connection.executemany("""INSERT INTO players
        (id, name, name_zh, position, age, nationality, foot, club_id, shirt_no, height_cm, bio, appearances, goals, assists, rating)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", players)
    connection.executemany("INSERT INTO seasons VALUES (?, ?)", [("2025-26", "2025/26"), ("2024-25", "2024/25")])
    connection.executemany("INSERT INTO sync_jobs VALUES (?, ?, ?, ?, ?, ?)", [
        ("seed-2026-08-29", "本地演示数据", "SUCCESS", "2026-08-29T09:00:00Z", 15, None),
        ("demo-man-city", "本地演示数据", "SUCCESS", "2026-08-29T09:01:00Z", 8, None),
    ])
    connection.commit()


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with closing(db()) as connection:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS clubs (id TEXT PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL, league TEXT NOT NULL, logo_url TEXT);
        CREATE TABLE IF NOT EXISTS players (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, name_zh TEXT NOT NULL, position TEXT NOT NULL, age INTEGER NOT NULL,
            nationality TEXT NOT NULL, foot TEXT NOT NULL, club_id TEXT NOT NULL REFERENCES clubs(id), shirt_no INTEGER,
            height_cm INTEGER, bio TEXT, appearances INTEGER DEFAULT 0, goals INTEGER DEFAULT 0, assists INTEGER DEFAULT 0, rating INTEGER DEFAULT 0,
            data_source TEXT NOT NULL DEFAULT 'seed', source_updated_at TEXT, is_current INTEGER NOT NULL DEFAULT 1,
            avatar_url TEXT, avatar_club_id TEXT REFERENCES clubs(id), avatar_verified_at TEXT,
            ea_overall INTEGER, ea_pace INTEGER, ea_shooting INTEGER, ea_passing INTEGER, ea_dribbling INTEGER,
            ea_defending INTEGER, ea_physical INTEGER, ea_avatar_url TEXT, ea_reference_url TEXT, ea_updated_at TEXT);
        CREATE TABLE IF NOT EXISTS seasons (id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS favorites (player_id TEXT PRIMARY KEY REFERENCES players(id), created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lineups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, formation TEXT NOT NULL, season TEXT NOT NULL, captain_id TEXT, notes TEXT DEFAULT '', tactic_style TEXT NOT NULL DEFAULT '均衡', mentality TEXT NOT NULL DEFAULT '均衡', attacking_width TEXT NOT NULL DEFAULT '标准', pressing TEXT NOT NULL DEFAULT '中位', updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lineup_slots (lineup_id INTEGER NOT NULL REFERENCES lineups(id) ON DELETE CASCADE, player_id TEXT NOT NULL REFERENCES players(id), role TEXT NOT NULL CHECK(role IN ('STARTER','SUBSTITUTE')), x REAL NOT NULL CHECK(x >= 0 AND x <= 1), y REAL NOT NULL CHECK(y >= 0 AND y <= 1), tactical_role TEXT, player_role TEXT, duty TEXT, PRIMARY KEY(lineup_id, player_id));
        CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, player_id TEXT NOT NULL REFERENCES players(id), technical INTEGER NOT NULL CHECK(technical BETWEEN 1 AND 10), tactical INTEGER NOT NULL CHECK(tactical BETWEEN 1 AND 10), physical INTEGER NOT NULL CHECK(physical BETWEEN 1 AND 10), mental INTEGER NOT NULL CHECK(mental BETWEEN 1 AND 10), strengths TEXT NOT NULL, risks TEXT NOT NULL, tags TEXT NOT NULL, recommendation TEXT NOT NULL, observed_at TEXT NOT NULL, notes TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_reports_player_id ON reports(player_id);
        CREATE TABLE IF NOT EXISTS sync_jobs (id TEXT PRIMARY KEY, provider TEXT NOT NULL, status TEXT NOT NULL, finished_at TEXT, entity_count INTEGER DEFAULT 0, error TEXT);
        CREATE TABLE IF NOT EXISTS provider_teams (external_id INTEGER PRIMARY KEY, club_id TEXT NOT NULL UNIQUE, league_code TEXT NOT NULL, team_name TEXT NOT NULL, last_synced_at TEXT);
        CREATE TABLE IF NOT EXISTS api_football_team_map (
            club_id TEXT PRIMARY KEY REFERENCES clubs(id), external_id INTEGER NOT NULL UNIQUE,
            mapped_at TEXT NOT NULL, last_transfer_checked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS featured_players (
            player_id TEXT PRIMARY KEY REFERENCES players(id), league_code TEXT NOT NULL,
            goals INTEGER NOT NULL DEFAULT 0, assists INTEGER NOT NULL DEFAULT 0,
            rank_score INTEGER NOT NULL, source_updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS club_lineup_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, club_id TEXT NOT NULL REFERENCES clubs(id),
            season TEXT NOT NULL, view_kind TEXT NOT NULL CHECK(view_kind IN ('SEASON_APPEARANCES','LAST_MATCH')),
            fixture_date TEXT, formation TEXT NOT NULL DEFAULT '4-3-3', source TEXT NOT NULL,
            slots_json TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(club_id, season, view_kind)
        );
        CREATE TABLE IF NOT EXISTS transfer_events (
            id TEXT PRIMARY KEY, player_name TEXT NOT NULL, from_club_id TEXT NOT NULL, to_club_id TEXT NOT NULL,
            transfer_type TEXT NOT NULL CHECK(transfer_type IN ('PERMANENT','LOAN','RETURN')),
            effective_at TEXT NOT NULL, source_url TEXT NOT NULL, source_name TEXT NOT NULL, verified_at TEXT
        );
        """)
        player_columns = {column[1] for column in connection.execute("PRAGMA table_info(players)")}
        for statement in [
            "ALTER TABLE players ADD COLUMN data_source TEXT NOT NULL DEFAULT 'seed'",
            "ALTER TABLE players ADD COLUMN source_updated_at TEXT",
            "ALTER TABLE players ADD COLUMN is_current INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE players ADD COLUMN avatar_url TEXT",
            "ALTER TABLE players ADD COLUMN avatar_club_id TEXT",
            "ALTER TABLE players ADD COLUMN avatar_verified_at TEXT",
            "ALTER TABLE players ADD COLUMN ea_overall INTEGER",
            "ALTER TABLE players ADD COLUMN ea_pace INTEGER",
            "ALTER TABLE players ADD COLUMN ea_shooting INTEGER",
            "ALTER TABLE players ADD COLUMN ea_passing INTEGER",
            "ALTER TABLE players ADD COLUMN ea_dribbling INTEGER",
            "ALTER TABLE players ADD COLUMN ea_defending INTEGER",
            "ALTER TABLE players ADD COLUMN ea_physical INTEGER",
            "ALTER TABLE players ADD COLUMN ea_avatar_url TEXT",
            "ALTER TABLE players ADD COLUMN ea_reference_url TEXT",
            "ALTER TABLE players ADD COLUMN ea_updated_at TEXT",
        ]:
            column = statement.split()[5]
            if column not in player_columns:
                connection.execute(statement)
        club_columns = {column[1] for column in connection.execute("PRAGMA table_info(clubs)")}
        if "logo_url" not in club_columns:
            connection.execute("ALTER TABLE clubs ADD COLUMN logo_url TEXT")
        slot_columns = {column[1] for column in connection.execute("PRAGMA table_info(lineup_slots)")}
        for statement in [
            "ALTER TABLE lineup_slots ADD COLUMN tactical_role TEXT",
            "ALTER TABLE lineup_slots ADD COLUMN player_role TEXT",
            "ALTER TABLE lineup_slots ADD COLUMN duty TEXT",
        ]:
            column = statement.split()[5]
            if column not in slot_columns:
                connection.execute(statement)
        lineup_columns = {column[1] for column in connection.execute("PRAGMA table_info(lineups)")}
        for statement in [
            "ALTER TABLE lineups ADD COLUMN tactic_style TEXT NOT NULL DEFAULT '均衡'",
            "ALTER TABLE lineups ADD COLUMN mentality TEXT NOT NULL DEFAULT '均衡'",
            "ALTER TABLE lineups ADD COLUMN attacking_width TEXT NOT NULL DEFAULT '标准'",
            "ALTER TABLE lineups ADD COLUMN pressing TEXT NOT NULL DEFAULT '中位'",
        ]:
            column = statement.split()[5]
            if column not in lineup_columns:
                connection.execute(statement)
        seed(connection)
        seed_transfer_events(connection)
        remove_legacy_transfer_overrides(connection)
        retire_duplicate_seed_players(connection)
        reconcile_current_rosters(connection)
        ensure_prestige_players(connection, datetime.now(timezone.utc).isoformat())
        connection.commit()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    api_football = bool(os.getenv("API_FOOTBALL_KEY"))
    football_data = bool(os.getenv("FOOTBALL_DATA_API_TOKEN"))
    configured = api_football or football_data
    provider = "API-Football" if api_football else ("football-data.org" if football_data else "")
    with closing(db()) as connection:
        newest = connection.execute("SELECT source_updated_at FROM players WHERE is_current=1 AND source_updated_at IS NOT NULL ORDER BY source_updated_at DESC LIMIT 1").fetchone()
    return {"status": "ok", "data_mode": "provider_ready" if configured else "local_demo", "updated_at": newest["source_updated_at"] if newest else None, "provider_configured": configured, "provider": provider}


@app.get("/api/players")
def list_players(q: str = "", position: str = "", club_id: str = "", age_min: int | None = None, age_max: int | None = None) -> list[dict]:
    filters, params = [], []
    if q.strip():
        filters.append("(p.name LIKE ? OR p.name_zh LIKE ? OR c.name LIKE ?)")
        term = f"%{q.strip()}%"; params.extend([term, term, term])
    if position: filters.append("p.position = ?"); params.append(position)
    if club_id: filters.append("p.club_id = ?"); params.append(club_id)
    if age_min is not None: filters.append("p.age >= ?"); params.append(age_min)
    if age_max is not None: filters.append("p.age <= ?"); params.append(age_max)
    where = " WHERE " + " AND ".join(filters) if filters else ""
    with closing(db()) as connection:
        values = player_payloads(rows(connection.execute(f"""SELECT p.*, c.name AS club_name,
            EXISTS(SELECT 1 FROM favorites f WHERE f.player_id=p.id) AS favorite,
            (SELECT COUNT(*) FROM reports r WHERE r.player_id=p.id) AS scout_report_count,
            (SELECT ROUND(AVG((r.technical+r.tactical+r.physical+r.mental)/4.0),1) FROM reports r WHERE r.player_id=p.id) AS scout_rating
            FROM players p JOIN clubs c ON c.id=p.club_id WHERE p.is_current=1 {('AND ' + ' AND '.join(filters)) if filters else ''}""", params)))
        return sort_players_by_ability(values)


@app.get("/api/players/{player_id}")
def get_player(player_id: str) -> dict:
    with closing(db()) as connection:
        result = connection.execute("""SELECT p.*, c.name AS club_name, c.league,
          EXISTS(SELECT 1 FROM favorites f WHERE f.player_id=p.id) AS favorite FROM players p JOIN clubs c ON c.id=p.club_id WHERE p.id=?""", (player_id,)).fetchone()
        if not result: raise HTTPException(404, "未找到球员")
        payload = player_payload(result)
        payload["reports"] = rows(connection.execute("SELECT * FROM reports WHERE player_id=? ORDER BY updated_at DESC", (player_id,)))
        payload["scout_report_count"] = len(payload["reports"])
        payload["scout_rating"] = round(sum((item["technical"] + item["tactical"] + item["physical"] + item["mental"]) / 4 for item in payload["reports"]) / len(payload["reports"]), 1) if payload["reports"] else None
        return payload


@app.get("/api/featured-players")
def list_featured_players(limit: int = Query(default=12, ge=1, le=30)) -> list[dict]:
    """Recent league performers, joined by provider player ID (never name matching)."""
    with closing(db()) as connection:
        return player_payloads(rows(connection.execute("""SELECT p.*,c.name AS club_name,c.logo_url,f.league_code,f.goals AS recent_goals,
            f.assists AS recent_assists,f.rank_score,f.source_updated_at AS featured_updated_at,
            (SELECT COUNT(*) FROM reports r WHERE r.player_id=p.id) AS scout_report_count,
            (SELECT ROUND(AVG((r.technical+r.tactical+r.physical+r.mental)/4.0),1) FROM reports r WHERE r.player_id=p.id) AS scout_rating
            FROM featured_players f JOIN players p ON p.id=f.player_id JOIN clubs c ON c.id=p.club_id
            WHERE p.is_current=1
            ORDER BY f.rank_score DESC,f.goals DESC,f.assists DESC,p.name LIMIT ?""", (limit,))))


@app.get("/api/clubs")
def list_clubs() -> list[dict]:
    with closing(db()) as connection:
        return rows(connection.execute("SELECT c.*, COUNT(p.id) AS player_count FROM clubs c LEFT JOIN players p ON p.club_id=c.id AND p.is_current=1 GROUP BY c.id ORDER BY c.name"))


@app.get("/api/clubs/{club_id}")
def get_club(club_id: str) -> dict:
    with closing(db()) as connection:
        club = connection.execute("SELECT * FROM clubs WHERE id=?", (club_id,)).fetchone()
        if not club: raise HTTPException(404, "未找到俱乐部")
        newest = connection.execute("""SELECT data_source, source_updated_at FROM players
            WHERE club_id=? AND is_current=1 ORDER BY source_updated_at DESC LIMIT 1""", (club_id,)).fetchone()
        return {"club": dict(club), "season": "当前阵容", "source": newest["data_source"] if newest else "本地演示数据", "synced_at": newest["source_updated_at"] if newest else None, "players": player_payloads(rows(connection.execute("""SELECT p.*, (SELECT COUNT(*) FROM reports r WHERE r.player_id=p.id) AS scout_report_count,
            (SELECT ROUND(AVG((r.technical+r.tactical+r.physical+r.mental)/4.0),1) FROM reports r WHERE r.player_id=p.id) AS scout_rating
            FROM players p WHERE p.club_id=? AND p.is_current=1 ORDER BY CASE p.position WHEN 'GK' THEN 1 WHEN 'CB' THEN 2 WHEN 'LB' THEN 3 WHEN 'RB' THEN 4 WHEN 'DM' THEN 5 WHEN 'CM' THEN 6 WHEN 'AM' THEN 7 WHEN 'LW' THEN 8 WHEN 'RW' THEN 9 ELSE 10 END, p.shirt_no""", (club_id,))))}


def unavailable_squad_view(view_id: str, label: str, detail: str) -> dict:
    return {"id": view_id, "label": label, "status": "unavailable", "formation": "4-3-3", "slots": [], "source": detail}


@app.get("/api/clubs/{club_id}/squad-views")
def get_club_squad_views(club_id: str, season: str = "2026/27") -> dict:
    """Team XI views with explicit provenance and no invented match history."""
    previous = f"{int(season[:4]) - 1}/{season[5:]}" if re.match(r"^\d{4}/\d{2}$", season) else "上赛季"
    with closing(db()) as connection:
        club = connection.execute("SELECT id,name FROM clubs WHERE id=?", (club_id,)).fetchone()
        if not club:
            raise HTTPException(404, "未找到俱乐部")
        team = player_payloads(rows(connection.execute("SELECT p.* FROM players p WHERE p.club_id=? AND p.is_current=1", (club_id,))))
        zones = formation_zone_payload()
        views = [recommend_xi(team, zones, "4-3-3")]
        snapshots = {
            (item["season"], item["view_kind"]): dict(item)
            for item in connection.execute("SELECT * FROM club_lineup_snapshots WHERE club_id=?", (club_id,)).fetchall()
        }
        season_snapshot = snapshots.get((season, "SEASON_APPEARANCES"))
        if season_snapshot:
            views.append({"id": "season-appearances", "label": f"{season} 出场最多 XI", "status": "ready", "formation": season_snapshot["formation"],
                          "slots": json.loads(season_snapshot["slots_json"]), "source": season_snapshot["source"]})
        elif any(int(item.get("appearances") or 0) > 0 for item in team):
            ranked = sorted(team, key=lambda item: (-int(item.get("appearances") or 0), -int(item.get("overall") or 0), item["name"]))
            views.append(select_xi(ranked, zones, "4-3-3", view_id="season-appearances", label=f"{season} 出场最多 XI",
                                   source="ScoutXI 当前赛季出场数据"))
        else:
            views.append(unavailable_squad_view("season-appearances", f"{season} 出场最多 XI", "尚未导入本赛季出场数据；不会用能力值冒充出场次数。"))
        previous_snapshot = snapshots.get((previous, "SEASON_APPEARANCES"))
        views.append({"id": "previous-season", "label": f"{previous} 出场最多 XI", "status": "ready", "formation": previous_snapshot["formation"],
                      "slots": json.loads(previous_snapshot["slots_json"]), "source": previous_snapshot["source"]}
                     if previous_snapshot else unavailable_squad_view("previous-season", f"{previous} 出场最多 XI", "需同步上一赛季的出场数据后提供。"))
        last_snapshot = snapshots.get((season, "LAST_MATCH"))
        views.append({"id": "last-match", "label": "上一场比赛首发", "status": "ready", "formation": last_snapshot["formation"],
                      "slots": json.loads(last_snapshot["slots_json"]), "source": last_snapshot["source"], "fixture_date": last_snapshot["fixture_date"]}
                     if last_snapshot else unavailable_squad_view("last-match", "上一场比赛首发", "需从比赛数据源同步首发名单后提供。"))
        return {"club": dict(club), "season": season, "players": team, "views": views}


def save_lineup_snapshot(connection: sqlite3.Connection, club_id: str, season: str, kind: str, formation: str, source: str, slots: list[dict], fixture_date: str | None = None) -> None:
    connection.execute("""INSERT INTO club_lineup_snapshots(club_id,season,view_kind,fixture_date,formation,source,slots_json,updated_at)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(club_id,season,view_kind) DO UPDATE SET fixture_date=excluded.fixture_date,
        formation=excluded.formation,source=excluded.source,slots_json=excluded.slots_json,updated_at=excluded.updated_at""",
        (club_id, season, kind, fixture_date, formation, source, json.dumps(slots), datetime.now(timezone.utc).isoformat()))


@app.post("/api/clubs/{club_id}/squad-views/refresh")
def refresh_club_squad_views(club_id: str, season: str = "2026/27") -> dict:
    """Cache provider-supported appearances and latest starting XI for one club.

    It is intentionally user-triggered because fixture data consumes the
    configured provider quota.  An unavailable plan returns a clear error,
    rather than a historical fixture masquerading as a current one.
    """
    token = os.getenv("API_FOOTBALL_KEY")
    if not token:
        raise HTTPException(503, "未配置 API-Football 密钥，无法同步比赛阵容。")
    season_year = int(season[:4]) if re.match(r"^\d{4}/\d{2}$", season) else current_season_year()
    with closing(db()) as connection:
        club = connection.execute("SELECT id,name FROM clubs WHERE id=?", (club_id,)).fetchone()
        mapping = connection.execute("SELECT external_id FROM api_football_team_map WHERE club_id=?", (club_id,)).fetchone()
        if not club:
            raise HTTPException(404, "未找到俱乐部")
        if not mapping:
            raise HTTPException(409, "该俱乐部尚无可核验的 API-Football 球队映射；请先执行名单同步。")
        roster = player_payloads(rows(connection.execute("SELECT p.* FROM players p WHERE p.club_id=? AND p.is_current=1", (club_id,))))
    team_id = mapping["external_id"]
    zones = formation_zone_payload()
    updated: list[str] = []
    try:
        stats_payload = api_football_json("players", token, {"team": team_id, "season": season_year})
        appearances = {}
        for item in stats_payload.get("response") or []:
            person = item.get("player") or {}
            stats = (item.get("statistics") or [{}])[0].get("games") or {}
            appearances[normalize_person_name(person.get("name") or "")] = int(stats.get("appearences") or 0)
        ranked = sorted(roster, key=lambda item: (-appearances.get(normalize_person_name(item["name"]), 0), -item["overall"], item["name"]))
        season_view = select_xi(ranked, zones, "4-3-3", view_id="season-appearances", label=f"{season} 出场最多 XI", source="API-Football 球员出场数据")
        with closing(db()) as connection:
            save_lineup_snapshot(connection, club_id, season, "SEASON_APPEARANCES", "4-3-3", season_view["source"], season_view["slots"])
            connection.commit()
        updated.append("season-appearances")
    except HTTPException as error:
        if error.status_code in (401, 403, 429):
            raise error
    try:
        fixture_payload = api_football_json("fixtures", token, {"team": team_id, "last": 1})
        fixture = (fixture_payload.get("response") or [{}])[0]
        fixture_id = (fixture.get("fixture") or {}).get("id")
        if not isinstance(fixture_id, int):
            raise ValueError("未返回上一场比赛")
        lineups = api_football_json("fixtures/lineups", token, {"fixture": fixture_id}).get("response") or []
        lineup = next((item for item in lineups if (item.get("team") or {}).get("id") == team_id), None)
        starters = [item.get("player") or {} for item in (lineup or {}).get("startXI") or []]
        by_name = {normalize_person_name(item["name"]): item for item in roster}
        actual = [by_name[normalize_person_name(item.get("name") or "")] for item in starters if normalize_person_name(item.get("name") or "") in by_name]
        if len(actual) < 7:
            raise ValueError("无法把比赛首发与当前名单可靠匹配")
        formation = (lineup or {}).get("formation") if (lineup or {}).get("formation") in FORMATION_ZONES else "4-3-3"
        last_view = select_xi(actual, formation_zone_payload(formation), formation, view_id="last-match", label="上一场比赛首发", source="API-Football 比赛首发")
        with closing(db()) as connection:
            save_lineup_snapshot(connection, club_id, season, "LAST_MATCH", formation, last_view["source"], last_view["slots"], (fixture.get("fixture") or {}).get("date"))
            connection.commit()
        updated.append("last-match")
    except (HTTPException, ValueError) as error:
        if isinstance(error, HTTPException) and error.status_code in (401, 403, 429):
            raise error
    return {"club_id": club_id, "season": season, "updated": updated, "message": "已缓存可用的比赛阵容视图。"}


class FavoriteIn(BaseModel):
    favorite: bool


@app.put("/api/players/{player_id}/favorite")
def set_favorite(player_id: str, payload: FavoriteIn) -> dict:
    with closing(db()) as connection:
        if not connection.execute("SELECT 1 FROM players WHERE id=?", (player_id,)).fetchone(): raise HTTPException(404, "未找到球员")
        if payload.favorite: connection.execute("INSERT OR IGNORE INTO favorites VALUES (?, ?)", (player_id, datetime.now(timezone.utc).isoformat()))
        else: connection.execute("DELETE FROM favorites WHERE player_id=?", (player_id,))
        connection.commit()
    return {"player_id": player_id, "favorite": payload.favorite}


class SlotIn(BaseModel):
    player_id: str
    role: Literal["STARTER", "SUBSTITUTE"]
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    tactical_role: str | None = None
    player_role: str | None = Field(default=None, max_length=40)
    duty: Literal["防守", "支援", "进攻"] | None = None


class LineupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    formation: Literal["4-3-3", "4-2-3-1", "4-4-2", "4-1-4-1", "4-3-1-2", "4-2-2-2", "4-3-2-1", "3-4-3", "3-5-2", "3-4-2-1", "3-1-4-2", "5-3-2", "5-4-1"]
    season: str = "2025/26"
    captain_id: str | None = None
    notes: str = Field(default="", max_length=1000)
    tactic_style: Literal["均衡", "控球", "快速反击", "高位压迫"] = "均衡"
    mentality: Literal["防守", "谨慎", "均衡", "积极", "进攻"] = "均衡"
    attacking_width: Literal["窄", "标准", "宽"] = "标准"
    pressing: Literal["低位", "中位", "高位"] = "中位"
    slots: list[SlotIn] = Field(default_factory=list, max_length=22)


def validate_lineup(connection: sqlite3.Connection, payload: LineupIn) -> None:
    ids = [slot.player_id for slot in payload.slots]
    if len(ids) != len(set(ids)): raise HTTPException(422, "同一球员不能在同一阵容重复出现")
    if sum(slot.role == "STARTER" for slot in payload.slots) > 11: raise HTTPException(422, "首发最多 11 人")
    if payload.captain_id and payload.captain_id not in ids: raise HTTPException(422, "队长必须在阵容中")
    if ids:
        found = connection.execute(f"SELECT COUNT(*) FROM players WHERE id IN ({','.join('?' for _ in ids)})", ids).fetchone()[0]
        if found != len(ids): raise HTTPException(422, "阵容含有不存在的球员")
    zones = FORMATION_ZONES[payload.formation]
    starter_roles = [slot.tactical_role for slot in payload.slots if slot.role == "STARTER"]
    if len(starter_roles) != len(set(starter_roles)): raise HTTPException(422, "每个战术区域只能放置一名首发")
    positions = {row["id"]: row["position"] for row in connection.execute(f"SELECT id, position FROM players WHERE id IN ({','.join('?' for _ in ids)})", ids)} if ids else {}
    for slot in payload.slots:
        if slot.role == "STARTER":
            if slot.tactical_role not in zones: raise HTTPException(422, "首发必须放在有效的战术区域")
            if positions[slot.player_id] not in zones[slot.tactical_role][2]:
                raise HTTPException(422, f"{positions[slot.player_id]} 不能放入 {slot.tactical_role} 区域")


def lineup_detail(connection: sqlite3.Connection, lineup_id: int) -> dict:
    lineup = connection.execute("SELECT * FROM lineups WHERE id=?", (lineup_id,)).fetchone()
    if not lineup: raise HTTPException(404, "未找到阵容")
    result = dict(lineup)
    result["slots"] = rows(connection.execute("""SELECT s.*, p.name, p.name_zh, p.position, p.shirt_no, p.club_id FROM lineup_slots s JOIN players p ON p.id=s.player_id WHERE s.lineup_id=? ORDER BY s.role, s.y, s.x""", (lineup_id,)))
    return result


@app.get("/api/lineups")
def list_lineups() -> list[dict]:
    with closing(db()) as connection:
        return rows(connection.execute("SELECT l.*, COUNT(s.player_id) AS player_count FROM lineups l LEFT JOIN lineup_slots s ON s.lineup_id=l.id GROUP BY l.id ORDER BY l.updated_at DESC"))


@app.post("/api/lineups", status_code=201)
def create_lineup(payload: LineupIn) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with closing(db()) as connection:
        validate_lineup(connection, payload)
        cursor = connection.execute("""INSERT INTO lineups(name,formation,season,captain_id,notes,tactic_style,mentality,attacking_width,pressing,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", (payload.name, payload.formation, payload.season, payload.captain_id, payload.notes,
                payload.tactic_style, payload.mentality, payload.attacking_width, payload.pressing, now))
        connection.executemany("""INSERT INTO lineup_slots(lineup_id,player_id,role,x,y,tactical_role,player_role,duty)
            VALUES (?,?,?,?,?,?,?,?)""", [(cursor.lastrowid, s.player_id, s.role, s.x, s.y, s.tactical_role, s.player_role, s.duty) for s in payload.slots])
        connection.commit()
        return lineup_detail(connection, cursor.lastrowid)


@app.get("/api/lineups/{lineup_id}")
def get_lineup(lineup_id: int) -> dict:
    with closing(db()) as connection: return lineup_detail(connection, lineup_id)


@app.put("/api/lineups/{lineup_id}")
def update_lineup(lineup_id: int, payload: LineupIn) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with closing(db()) as connection:
        lineup_detail(connection, lineup_id); validate_lineup(connection, payload)
        connection.execute("""UPDATE lineups SET name=?,formation=?,season=?,captain_id=?,notes=?,tactic_style=?,mentality=?,attacking_width=?,pressing=?,updated_at=? WHERE id=?""",
            (payload.name, payload.formation, payload.season, payload.captain_id, payload.notes, payload.tactic_style, payload.mentality,
             payload.attacking_width, payload.pressing, now, lineup_id))
        connection.execute("DELETE FROM lineup_slots WHERE lineup_id=?", (lineup_id,))
        connection.executemany("""INSERT INTO lineup_slots(lineup_id,player_id,role,x,y,tactical_role,player_role,duty)
            VALUES (?,?,?,?,?,?,?,?)""", [(lineup_id, s.player_id, s.role, s.x, s.y, s.tactical_role, s.player_role, s.duty) for s in payload.slots])
        connection.commit(); return lineup_detail(connection, lineup_id)


class ReportIn(BaseModel):
    technical: int = Field(ge=1, le=10); tactical: int = Field(ge=1, le=10)
    physical: int = Field(ge=1, le=10); mental: int = Field(ge=1, le=10)
    strengths: str = Field(max_length=500); risks: str = Field(max_length=500)
    tags: str = Field(max_length=200); recommendation: Literal["重点关注", "持续观察", "不建议"]
    observed_at: str; notes: str = Field(max_length=2000)


@app.post("/api/players/{player_id}/reports", status_code=201)
def create_report(player_id: str, payload: ReportIn) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with closing(db()) as connection:
        if not connection.execute("SELECT 1 FROM players WHERE id=?", (player_id,)).fetchone(): raise HTTPException(404, "未找到球员")
        cursor = connection.execute("""INSERT INTO reports(player_id,technical,tactical,physical,mental,strengths,risks,tags,recommendation,observed_at,notes,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (player_id, payload.technical,payload.tactical,payload.physical,payload.mental,payload.strengths,payload.risks,payload.tags,payload.recommendation,payload.observed_at,payload.notes,now))
        connection.commit(); return dict(connection.execute("SELECT * FROM reports WHERE id=?", (cursor.lastrowid,)).fetchone())


@app.get("/api/sync-status")
def sync_status() -> dict:
    with closing(db()) as connection:
        api_football = bool(os.getenv("API_FOOTBALL_KEY"))
        football_data = bool(os.getenv("FOOTBALL_DATA_API_TOKEN"))
        configured = api_football or football_data
        # The roster sync pipeline deliberately prefers the dated football-data
        # snapshot when both providers are configured.  Say that in the UI so a
        # successful refresh is not mistaken for an API-Football-only refresh.
        message = "已配置 football-data.org；将按当前赛季阵容快照全量刷新，并以转会记录校验。" if football_data else ("已配置 API-Football；刷新时将校验本赛季权限并按额度分批处理。" if api_football else "当前使用离线演示数据。设置 API_FOOTBALL_KEY 或 FOOTBALL_DATA_API_TOKEN 后可刷新当前阵容。")
        return {"mode": "provider_ready" if configured else "local_demo", "message": message, "jobs": rows(connection.execute("SELECT * FROM sync_jobs ORDER BY finished_at DESC"))}


def provider_position(name: str, raw: str) -> str:
    if name in POSITION_OVERRIDES:
        return POSITION_OVERRIDES[name]
    return {"Goalkeeper": "GK", "Defender": "CB", "Midfielder": "CM", "Offence": "ST", "Attacker": "ST"}.get(raw, "CM")


def normalize_person_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]", "", value)


def detailed_position(raw: str | None) -> str | None:
    text = (raw or "").lower()
    if "goalkeeper" in text: return "GK"
    if "left-back" in text or "left back" in text: return "LB"
    if "right-back" in text or "right back" in text: return "RB"
    if "centre-back" in text or "center-back" in text or "centre back" in text or "center back" in text: return "CB"
    if "defensive midfield" in text: return "DM"
    if "attacking midfield" in text: return "AM"
    if "central midfield" in text or "centre midfield" in text: return "CM"
    if "left winger" in text or "left wing" in text: return "LW"
    if "right winger" in text or "right wing" in text: return "RW"
    if "striker" in text or "forward" in text: return "ST"
    return None


def fetch_sportsdb_profiles(team_name: str) -> dict[str, dict]:
    """Free, secondary enrichment only: detailed roles and direct player thumbnails."""
    try:
        query = urllib.parse.quote(team_name)
        with urllib.request.urlopen(f"https://www.thesportsdb.com/api/v1/json/123/searchteams.php?t={query}", timeout=15) as response:
            teams = json.load(response).get("teams") or []
        if not teams: return {}
        team_id = teams[0].get("idTeam")
        if not team_id: return {}
        with urllib.request.urlopen(f"https://www.thesportsdb.com/api/v1/json/123/lookup_all_players.php?id={team_id}", timeout=20) as response:
            people = json.load(response).get("player") or []
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return {}
    profiles: dict[str, dict] = {}
    for person in people:
        role = detailed_position(person.get("strPosition"))
        if role:
            profiles[normalize_person_name(person.get("strPlayer") or "")] = {"position": role, "avatar_url": person.get("strThumb")}
    return profiles


def fetch_sportsdb_player_avatar(name: str, expected_club_name: str | None = None) -> str | None:
    """Return a remote portrait only when its profile agrees with the current club."""
    try:
        query = urllib.parse.quote(name)
        with urllib.request.urlopen(f"https://www.thesportsdb.com/api/v1/json/123/searchplayers.php?p={query}", timeout=15) as response:
            people = json.load(response).get("player") or []
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None
    normalized = normalize_person_name(name)
    exact = next((person for person in people if normalize_person_name(person.get("strPlayer") or "") == normalized), None)
    if expected_club_name and (not exact or normalize_club_name(exact.get("strTeam") or "") != normalize_club_name(expected_club_name)):
        return None
    return exact.get("strThumb") if exact else None


def fetch_wikimedia_player_avatar(name: str) -> str | None:
    """Public fallback for a portrait when the sports database has no image."""
    try:
        title = WIKIMEDIA_PLAYER_TITLES.get(name)
        if title:
            query = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "pageimages", "pithumbsize": 500, "format": "json"})
            request = urllib.request.Request(f"https://en.wikipedia.org/w/api.php?{query}", headers={"User-Agent": "ScoutXI/0.2 (local player roster)"})
            with urllib.request.urlopen(request, timeout=15) as response:
                pages = (json.load(response).get("query") or {}).get("pages") or {}
            page = next(iter(pages.values()), {})
            return (page.get("thumbnail") or {}).get("source")
        query = urllib.parse.urlencode({
            "action": "query", "generator": "search", "gsrsearch": f"{name} footballer",
            "gsrlimit": 1, "prop": "pageimages", "pithumbsize": 500, "format": "json",
        })
        request = urllib.request.Request(f"https://en.wikipedia.org/w/api.php?{query}", headers={"User-Agent": "ScoutXI/0.2 (local player roster)"})
        with urllib.request.urlopen(request, timeout=15) as response:
            pages = (json.load(response).get("query") or {}).get("pages") or {}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None
    normalized = normalize_person_name(name)
    page = next((item for item in pages.values() if normalize_person_name((item.get("title") or "").split("(")[0]) == normalized), {})
    return (page.get("thumbnail") or {}).get("source")


EA_RATINGS_URL = "https://drop-api.ea.com/rating/ea-sports-fc?locale=en&limit=100&gender=0&offset={}"


def ea_person_name(item: dict) -> str:
    return " ".join(part for part in (item.get("firstName"), item.get("lastName")) if part).strip() or (item.get("commonName") or "")


def ea_person_names(item: dict) -> list[str]:
    """Return both legal/full and football-common names from EA's catalogue.

    A common name is essential for players such as Rodri, Cherki and Endrick;
    it is used as a matching alias only, never as a fuzzy match.
    """
    names = [ea_person_name(item), item.get("commonName") or ""]
    return list(dict.fromkeys(name for name in names if name.strip()))


def sync_ea_fc_ratings(max_pages: int = 190, start_page: int = 0) -> dict:
    """Import public EA rating references and portrait URLs without storing images.

    Matching is exact on normalised name plus current club; a name-only match is
    allowed only when it is unique in the local current roster.
    """
    with closing(db()) as connection:
        local = rows(connection.execute("SELECT p.id,p.name,c.name AS club_name FROM players p JOIN clubs c ON c.id=p.club_id WHERE p.is_current=1"))
    by_name: dict[str, list[dict]] = {}
    for player in local:
        by_name.setdefault(normalize_person_name(player["name"]), []).append(player)
    matched, pages, seen = 0, 0, set()
    refreshed_at = datetime.now(timezone.utc).isoformat()
    for page in range(start_page, start_page + max_pages):
        request = urllib.request.Request(EA_RATINGS_URL.format(page * 100), headers={"User-Agent": "ScoutXI/0.3 (local scouting application)"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=25) as response:
                    items = (json.load(response) or {}).get("items") or []
                break
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, http.client.IncompleteRead) as error:
                if attempt == 2:
                    raise HTTPException(502, f"无法读取 EA 公开评分数据：{error}")
                # A public catalogue occasionally stalls.  Retrying this exact
                # page is safe because updates are idempotent.
                time.sleep(1.5 * (attempt + 1))
        if not items:
            break
        pages += 1
        updates = []
        for item in items:
            candidates: list[dict] = []
            for name in ea_person_names(item):
                candidates.extend(by_name.get(normalize_person_name(name), []))
            candidates = list({candidate["id"]: candidate for candidate in candidates}.values())
            if not candidates:
                continue
            team_name = ((item.get("team") or {}).get("label") or "")
            exact = [player for player in candidates if normalize_club_name(player["club_name"]) == normalize_club_name(team_name)]
            candidate = exact[0] if len(exact) == 1 else (candidates[0] if len(candidates) == 1 else None)
            if not candidate or candidate["id"] in seen:
                continue
            stats = item.get("stats") or {}
            def stat(key: str) -> int | None:
                value = (stats.get(key) or {}).get("value")
                return int(value) if isinstance(value, (int, float)) else None
            overall = item.get("overallRating")
            if not isinstance(overall, (int, float)):
                continue
            ea_id = item.get("id")
            updates.append((max(60, int(overall)), stat("pac"), stat("sho"), stat("pas"), stat("dri"), stat("def"), stat("phy"),
                            item.get("avatarUrl"), f"https://www.ea.com/games/ea-sports-fc/ratings/player-ratings/{ea_id}", refreshed_at, candidate["id"]))
            seen.add(candidate["id"])
        if updates:
            with closing(db()) as connection:
                connection.executemany("""UPDATE players SET ea_overall=?,ea_pace=?,ea_shooting=?,ea_passing=?,ea_dribbling=?,
                    ea_defending=?,ea_physical=?,ea_avatar_url=?,ea_reference_url=?,ea_updated_at=? WHERE id=?""", updates)
                connection.commit()
            matched += len(updates)
        time.sleep(0.12)
    return {"source": "EA SPORTS FC 公开评分页", "start_page": start_page, "pages": pages, "next_page": start_page + pages,
            "matched": matched, "unmatched": len(local) - len(seen), "refreshed_at": refreshed_at}


@app.post("/api/admin/sync-ea-ratings")
def refresh_ea_fc_ratings(max_pages: int = Query(default=190, ge=1, le=220), start_page: int = Query(default=0, ge=0)) -> dict:
    return sync_ea_fc_ratings(max_pages, start_page)


def run_full_ea_rating_sync() -> None:
    ea_rating_sync_status["running"] = True
    ea_rating_sync_status["error"] = None
    try:
        page = ea_rating_sync_status["next_page"]
        while page < 220:
            result = sync_ea_fc_ratings(max_pages=8, start_page=page)
            ea_rating_sync_status["completed_pages"] = result["next_page"]
            ea_rating_sync_status["next_page"] = result["next_page"]
            ea_rating_sync_status["matched"] += result["matched"]
            if result["pages"] < 8:
                break
            page = result["next_page"]
    except Exception as error:
        ea_rating_sync_status["error"] = str(error)
    finally:
        ea_rating_sync_status["running"] = False
        ea_rating_sync_lock.release()


@app.post("/api/admin/start-ea-rating-sync")
def start_ea_rating_sync(start_page: int | None = Query(default=None, ge=0, le=220)) -> dict:
    if not ea_rating_sync_lock.acquire(blocking=False):
        return {"started": False, **ea_rating_sync_status}
    # A completed import starts a fresh audit; an interrupted one resumes from
    # the first page that was not committed.
    if start_page is not None:
        ea_rating_sync_status.update({"completed_pages": start_page, "next_page": start_page, "matched": 0, "error": None})
    elif not ea_rating_sync_status.get("error"):
        ea_rating_sync_status.update({"completed_pages": 0, "next_page": 0, "matched": 0})
    threading.Thread(target=run_full_ea_rating_sync, daemon=True, name="scoutxi-ea-ratings").start()
    return {"started": True, **ea_rating_sync_status}


@app.get("/api/admin/ea-rating-sync-progress")
def ea_rating_sync_progress() -> dict:
    return dict(ea_rating_sync_status)


@app.post("/api/admin/enrich-avatars")
def enrich_manchester_city_avatars() -> dict:
    """Fill and correct remote avatar URLs without storing image files."""
    with closing(db()) as connection:
        players_to_enrich = rows(connection.execute("""SELECT p.id,p.name,p.club_id,c.name AS club_name FROM players p
            JOIN clubs c ON c.id=p.club_id WHERE p.club_id='man-city' AND p.is_current=1
              AND (avatar_url IS NULL OR avatar_url='' OR name IN ('Rodri','Sávio')) ORDER BY name"""))
    updated, unavailable = [], []
    for player in players_to_enrich:
        if player["name"] in OFFICIAL_AVATAR_URLS:
            avatar_url = OFFICIAL_AVATAR_URLS[player["name"]]
        elif player["name"] in CURATED_AVATAR_NAMES:
            avatar_url = None
        else:
            avatar_url = fetch_sportsdb_player_avatar(player["name"], player["club_name"])
        if avatar_url:
            with closing(db()) as connection:
                connection.execute("UPDATE players SET avatar_url=?,avatar_club_id=?,avatar_verified_at=? WHERE id=?",
                    (avatar_url, player["club_id"], datetime.now(timezone.utc).isoformat(), player["id"]))
                connection.commit()
            updated.append(player["name"])
        else:
            unavailable.append(player["name"])
        time.sleep(0.15)
    return {"club": "Manchester City", "updated": len(updated), "unavailable": unavailable, "storage": "remote URLs only"}


@app.post("/api/admin/audit-avatars")
def audit_current_avatars(max_players: int = Query(default=120, ge=1, le=150)) -> dict:
    """Remove any portrait that cannot be tied to the player's current club.

    A public image service may retain an old kit even when the person record is
    valid.  We therefore accept only profiles whose current team field matches
    ScoutXI's current roster club; uncertain images become neutral placeholders.
    """
    verified_at = datetime.now(timezone.utc).isoformat()
    with closing(db()) as connection:
        candidates = rows(connection.execute("""SELECT p.id,p.name,p.club_id,c.name AS club_name FROM players p
            JOIN clubs c ON c.id=p.club_id WHERE p.is_current=1 AND p.avatar_url IS NOT NULL AND p.avatar_url<>''
            ORDER BY p.avatar_verified_at IS NULL DESC,p.name LIMIT ?""", (max_players,)))
    verified, cleared = 0, []
    for player in candidates:
        avatar_url = fetch_sportsdb_player_avatar(player["name"], player["club_name"])
        with closing(db()) as connection:
            if avatar_url:
                connection.execute("UPDATE players SET avatar_url=?,avatar_club_id=?,avatar_verified_at=? WHERE id=?",
                    (avatar_url, player["club_id"], verified_at, player["id"]))
                verified += 1
            else:
                connection.execute("UPDATE players SET avatar_url=NULL,avatar_club_id=NULL,avatar_verified_at=? WHERE id=?",
                    (verified_at, player["id"]))
                cleared.append(player["name"])
            connection.commit()
        time.sleep(0.12)
    return {"checked": len(candidates), "verified": verified, "cleared": len(cleared),
            "cleared_players": cleared[:30], "policy": "current-club profile match only"}


@app.post("/api/admin/curate-manchester-city")
def curate_manchester_city() -> dict:
    """Compatibility endpoint: reconcile all verified transfers, not one club."""
    with closing(db()) as connection:
        result = reconcile_current_rosters(connection)
        connection.execute("""INSERT OR REPLACE INTO sync_jobs(id,provider,status,finished_at,entity_count,error)
            VALUES(?,?,?,?,?,NULL)""", (f"roster-reconcile-{datetime.now(timezone.utc).isoformat()}", "官方转会校正",
                                           "SUCCESS", datetime.now(timezone.utc).isoformat(), result["applied"]))
        connection.commit()
    return result


def provider_age(date_of_birth: str | None) -> int:
    if not date_of_birth: return 0
    try:
        born = datetime.fromisoformat(date_of_birth).date()
    except ValueError:
        return 0
    today = datetime.now(timezone.utc).date()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def sportsdb_json(endpoint: str, **params: str) -> dict:
    query = urllib.parse.urlencode(params)
    url = f"https://www.thesportsdb.com/api/v1/json/123/{endpoint}"
    if query:
        url += f"?{query}"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as error:
        raise HTTPException(502, f"无法读取 TheSportsDB 补充联赛数据：{error}")


def sportsdb_team(name: str) -> dict | None:
    teams = sportsdb_json("searchteams.php", t=name).get("teams") or []
    wanted = normalize_club_name(name)
    return next((team for team in teams if normalize_club_name(team.get("strTeam") or "") == wanted), None)


def ensure_prestige_players(connection: sqlite3.Connection, refreshed_at: str) -> int:
    """Keep globally prominent active players searchable outside the five-league plan."""
    inserted = 0
    for player_id, name, name_zh, position, born, nation, foot, club_id, shirt_no, club_name, country, league, avatar_url in PRESTIGE_PLAYERS:
        connection.execute("""INSERT INTO clubs(id,name,country,league) VALUES(?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country,league=excluded.league""",
            (club_id, club_name, country, league))
        connection.execute("""INSERT INTO players(id,name,name_zh,position,age,nationality,foot,club_id,shirt_no,height_cm,bio,appearances,goals,assists,rating,data_source,source_updated_at,avatar_url,avatar_club_id,avatar_verified_at,is_current)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name,name_zh=excluded.name_zh,position=excluded.position,age=excluded.age,nationality=excluded.nationality,foot=excluded.foot,club_id=excluded.club_id,shirt_no=excluded.shirt_no,bio=excluded.bio,data_source=excluded.data_source,source_updated_at=excluded.source_updated_at,avatar_url=excluded.avatar_url,avatar_club_id=excluded.avatar_club_id,avatar_verified_at=excluded.avatar_verified_at,is_current=1""",
            (player_id, name, name_zh, position, provider_age(born), nation, foot, club_id, shirt_no, None,
             "高声望球员目录；俱乐部与肖像来自公开 TheSportsDB 资料，随补充联赛刷新校验。", 0, 0, 0, 95,
             "TheSportsDB 高声望球员目录", refreshed_at, avatar_url, club_id, refreshed_at))
        inserted += 1
    return inserted


def sync_supplemental_clubs() -> dict:
    """Synchronise prominent clubs in well-known non-five-league competitions."""
    refreshed_at = datetime.now(timezone.utc).isoformat()
    results, unavailable = [], []
    with closing(db()) as connection:
        for search_name, country, league in SUPPLEMENTAL_CLUBS:
            try:
                team = sportsdb_team(search_name)
                if not team or not team.get("idTeam"):
                    unavailable.append(search_name)
                    continue
                team_id = str(team["idTeam"])
                club_id = f"tsdb-{team_id}"
                people = sportsdb_json("lookup_all_players.php", id=team_id).get("player") or []
                connection.execute("""INSERT INTO clubs(id,name,country,league,logo_url) VALUES(?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country,league=excluded.league,logo_url=COALESCE(excluded.logo_url,clubs.logo_url)""",
                    (club_id, team.get("strTeam") or search_name, country, league, team.get("strBadge")))
                connection.execute("UPDATE players SET is_current=0 WHERE club_id=? AND data_source LIKE 'TheSportsDB%'", (club_id,))
                imported = 0
                for person in people:
                    external_id = person.get("idPlayer")
                    name = person.get("strPlayer") or ""
                    if not external_id or not name:
                        continue
                    avatar_url = person.get("strThumb") or None
                    connection.execute("""INSERT INTO players(id,name,name_zh,position,age,nationality,foot,club_id,shirt_no,height_cm,bio,appearances,goals,assists,rating,data_source,source_updated_at,avatar_url,avatar_club_id,avatar_verified_at,is_current)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                        ON CONFLICT(id) DO UPDATE SET name=excluded.name,name_zh=excluded.name_zh,position=excluded.position,age=excluded.age,nationality=excluded.nationality,club_id=excluded.club_id,bio=excluded.bio,data_source=excluded.data_source,source_updated_at=excluded.source_updated_at,avatar_url=COALESCE(excluded.avatar_url,players.avatar_url),avatar_club_id=CASE WHEN excluded.avatar_url IS NOT NULL THEN excluded.avatar_club_id ELSE players.avatar_club_id END,avatar_verified_at=CASE WHEN excluded.avatar_url IS NOT NULL THEN excluded.avatar_verified_at ELSE players.avatar_verified_at END,is_current=1""",
                        (f"tsdb-{team_id}-{external_id}", name, name, detailed_position(person.get("strPosition")) or "CM", provider_age(person.get("dateBorn")),
                         person.get("strNationality") or "未知", "未知", club_id, None, None,
                         "由 TheSportsDB 公开球队名单同步；真实肖像优先，缺失时使用无文字远程头像。", 0, 0, 0, 0,
                         "TheSportsDB 补充联赛", refreshed_at, avatar_url, club_id if avatar_url else None, refreshed_at if avatar_url else None))
                    imported += 1
                connection.execute("INSERT OR REPLACE INTO sync_jobs(id,provider,status,finished_at,entity_count,error) VALUES(?,?,?,?,?,NULL)",
                    (f"tsdb-{team_id}-{refreshed_at}", "TheSportsDB 补充联赛", "SUCCESS", refreshed_at, imported))
                results.append({"club_id": club_id, "club_name": team.get("strTeam") or search_name, "players": imported, "league": league})
            except HTTPException:
                unavailable.append(search_name)
        prestige = ensure_prestige_players(connection, refreshed_at)
        connection.commit()
    return {"source": "TheSportsDB 公开球队目录", "updated_at": refreshed_at, "clubs": results, "unavailable": unavailable, "prestige_players": prestige}


@app.post("/api/admin/sync-supplemental")
def refresh_supplemental_clubs() -> dict:
    return sync_supplemental_clubs()


def fetch_current_squad(team_id: int, token: str) -> dict:
    request = urllib.request.Request(f"https://api.football-data.org/v4/teams/{team_id}", headers={"X-Auth-Token": token, "User-Agent": "ScoutXI/0.2"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise HTTPException(502, f"数据服务请求失败（HTTP {error.code}）：{detail}")
    except urllib.error.URLError as error:
        raise HTTPException(502, f"无法连接数据服务：{error.reason}")


def fetch_competition_scorers(league_code: str, token: str) -> dict:
    request = urllib.request.Request(
        f"https://api.football-data.org/v4/competitions/{league_code}/scorers?limit=12",
        headers={"X-Auth-Token": token, "User-Agent": "ScoutXI/0.2"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise HTTPException(502, f"无法读取 {league_code} 射手榜（HTTP {error.code}）。")
    except urllib.error.URLError as error:
        raise HTTPException(502, f"无法连接射手榜数据服务：{error.reason}")


def enrich_featured_player_avatars(limit: int = 18) -> dict:
    """Store only trustworthy remote portrait URLs for the visible focus cards."""
    with closing(db()) as connection:
        featured = rows(connection.execute("""SELECT p.id,p.name,p.club_id,c.name AS club_name FROM featured_players f JOIN players p ON p.id=f.player_id
            JOIN clubs c ON c.id=p.club_id
            WHERE p.is_current=1 AND (p.avatar_url IS NULL OR p.avatar_url='') ORDER BY f.rank_score DESC LIMIT ?""", (limit,)))
    updated, unavailable = 0, []
    for player in featured:
        avatar_url = fetch_sportsdb_player_avatar(player["name"], player["club_name"])
        if avatar_url:
            with closing(db()) as connection:
                connection.execute("UPDATE players SET avatar_url=?,avatar_club_id=?,avatar_verified_at=? WHERE id=?",
                    (avatar_url, player["club_id"], datetime.now(timezone.utc).isoformat(), player["id"]))
                connection.commit()
            updated += 1
        else:
            unavailable.append(player["name"])
        time.sleep(0.12)
    return {"updated": updated, "unavailable": unavailable}


def refresh_featured_players(token: str) -> dict:
    """Build homepage focus cards from current five-league scorer tables.

    This is a transparent rank (goals first, then assists), not a model-generated
    recommendation. Provider team and player identifiers form the join key.
    """
    refreshed_at = datetime.now(timezone.utc).isoformat()
    entries: list[tuple] = []
    for league_code in FOOTBALL_DATA_LEAGUES:
        payload = fetch_competition_scorers(league_code, token)
        for position, scorer in enumerate(payload.get("scorers") or [], start=1):
            player = scorer.get("player") or {}
            team = scorer.get("team") or {}
            player_external_id, team_external_id = player.get("id"), team.get("id")
            if not isinstance(player_external_id, int) or not isinstance(team_external_id, int):
                continue
            goals, assists = int(scorer.get("goals") or 0), int(scorer.get("assists") or 0)
            # Ties are resolved by provider table order; the score itself remains
            # entirely explainable in the UI.
            rank_score = goals * 100 + assists * 20 + max(0, 13 - position)
            entries.append((f"fd-{team_external_id}-{player_external_id}", league_code, goals, assists, rank_score, refreshed_at))
        time.sleep(0.2)
    with closing(db()) as connection:
        valid = [entry for entry in entries if connection.execute("SELECT 1 FROM players WHERE id=? AND is_current=1", (entry[0],)).fetchone()]
        connection.execute("DELETE FROM featured_players")
        connection.executemany("""INSERT INTO featured_players(player_id,league_code,goals,assists,rank_score,source_updated_at)
            VALUES(?,?,?,?,?,?)""", valid)
        connection.commit()
    avatars = enrich_featured_player_avatars()
    return {"source": "football-data.org 射手榜", "updated_at": refreshed_at, "featured": len(valid), "avatars": avatars}


def discover_football_data_teams(token: str) -> int:
    """Discover every club in the five included leagues before squad refreshes."""
    featured = {team_id: club_id for club_id, team_id in TEAM_SOURCES.items()}
    discovered = 0
    for league_code, league_name in FOOTBALL_DATA_LEAGUES.items():
        request = urllib.request.Request(f"https://api.football-data.org/v4/competitions/{league_code}/teams",
                                         headers={"X-Auth-Token": token, "User-Agent": "ScoutXI/0.2"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:160]
            raise HTTPException(502, f"无法读取 {league_code} 球队列表（HTTP {error.code}）：{detail}")
        for team in payload.get("teams") or []:
            external_id = team.get("id")
            if not isinstance(external_id, int):
                continue
            club_id = featured.get(external_id, f"fd-team-{external_id}")
            team_name = team.get("name") or f"球队 {external_id}"
            area = team.get("area") or {}
            with closing(db()) as connection:
                connection.execute("""INSERT INTO clubs(id,name,country,league,logo_url) VALUES(?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country,league=excluded.league,
                    logo_url=COALESCE(excluded.logo_url,clubs.logo_url)""",
                    (club_id, team_name, area.get("name") or "未知", league_name, team.get("crest")))
                connection.execute("""INSERT INTO provider_teams(external_id,club_id,league_code,team_name,last_synced_at)
                    VALUES(?,?,?,?,NULL) ON CONFLICT(external_id) DO UPDATE SET club_id=excluded.club_id,
                    league_code=excluded.league_code,team_name=excluded.team_name""",
                    (external_id, club_id, league_code, team_name))
                connection.commit()
            discovered += 1
    return discovered


def refresh_football_data_squads(token: str, max_teams: int) -> dict:
    """Refresh one rate-safe batch; repeat the action until remaining is zero."""
    with closing(db()) as connection:
        known_teams = connection.execute("SELECT COUNT(*) FROM provider_teams").fetchone()[0]
    discovered = discover_football_data_teams(token) if known_teams < 90 else 0
    # Registered free accounts allow 10 calls/minute.  Nine team calls plus a
    # six-second interval stays below that limit after the one-time discovery.
    batch_limit = min(max_teams, 9)
    with closing(db()) as connection:
        teams = rows(connection.execute("""SELECT external_id,club_id,league_code,team_name,last_synced_at
            FROM provider_teams ORDER BY CASE WHEN last_synced_at IS NULL THEN 0 ELSE 1 END,
            last_synced_at ASC, external_id ASC LIMIT ?""", (batch_limit,)))
    refreshed_at, results, failures = datetime.now(timezone.utc).isoformat(), [], []
    for index, team in enumerate(teams):
        try:
            payload = fetch_current_squad(team["external_id"], token)
            squad = payload.get("squad") or []
            if not squad:
                raise ValueError("未返回当前球员名单")
            with closing(db()) as connection:
                connection.execute("UPDATE players SET is_current=0 WHERE club_id=?", (team["club_id"],))
                for person in squad:
                    person_id = person.get("id")
                    if person_id is None:
                        continue
                    name = person.get("name") or "未知球员"
                    player_id = f"fd-{team['external_id']}-{person_id}"
                    connection.execute("""INSERT INTO players(id,name,name_zh,position,age,nationality,foot,club_id,shirt_no,height_cm,bio,appearances,goals,assists,rating,data_source,source_updated_at,avatar_url,is_current)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                    ON CONFLICT(id) DO UPDATE SET name=excluded.name,name_zh=excluded.name_zh,position=excluded.position,age=excluded.age,nationality=excluded.nationality,club_id=excluded.club_id,bio=excluded.bio,data_source=excluded.data_source,source_updated_at=excluded.source_updated_at,is_current=1""",
                    (player_id, name, name, provider_position(name, person.get("position", "")), provider_age(person.get("dateOfBirth")), person.get("nationality") or "未知", "未知", team["club_id"], None, None, "由 football-data.org 当前阵容同步；头像为远程链接，不在本机存储图片。", 0, 0, 0, 0, "football-data.org", refreshed_at, None))
                connection.execute("UPDATE provider_teams SET last_synced_at=? WHERE external_id=?", (refreshed_at, team["external_id"]))
                connection.execute("INSERT OR REPLACE INTO sync_jobs(id,provider,status,finished_at,entity_count,error) VALUES(?,?,?,?,?,NULL)",
                    (f"fd-{team['external_id']}-{refreshed_at}", "football-data.org", "SUCCESS", refreshed_at, len(squad)))
                connection.commit()
            results.append({"club_id": team["club_id"], "club_name": team["team_name"], "players": len(squad)})
        except (HTTPException, ValueError) as error:
            failures.append({"club_id": team["club_id"], "error": str(error.detail if isinstance(error, HTTPException) else error)})
        if index < len(teams) - 1:
            time.sleep(6.2)
    with closing(db()) as connection:
        remaining = connection.execute("SELECT COUNT(*) FROM provider_teams WHERE last_synced_at IS NULL").fetchone()[0]
    # Reconcile every verified official transfer after each provider batch.
    with closing(db()) as connection:
        reconcile_current_rosters(connection)
        connection.commit()
    return {"refreshed_at": refreshed_at, "source": "football-data.org", "discovered": discovered, "batch_size": len(results), "remaining": remaining, "results": results, "failures": failures}


def run_full_football_data_sync(token: str) -> None:
    """Continue rate-safe batches in the server background until every club is current."""
    full_sync_status.update({"running": True, "error": None})
    try:
        while True:
            result = refresh_football_data_squads(token, 8)
            full_sync_status["completed"] += result["batch_size"]
            full_sync_status["remaining"] = result["remaining"]
            if not result["remaining"]:
                break
            # The batch itself spaces requests six seconds apart.  This pause
            # keeps consecutive batches below the free plan's rolling limit.
            time.sleep(20)
        transfer_token = os.getenv("API_FOOTBALL_KEY")
        if transfer_token:
            transfer_sync_status.update({"running": True, "error": None})
            transfer_result = refresh_api_football_transfers(transfer_token, max_teams=60)
            transfer_sync_status.update({"completed": len(transfer_result["checked"]), "mapped": transfer_result["mapped"],
                                         "remaining": transfer_result["remaining"], "error": transfer_result["failures"] or None})
    except Exception as error:
        full_sync_status["error"] = str(error)
    finally:
        full_sync_status["running"] = False
        transfer_sync_status["running"] = False
        full_sync_lock.release()


@app.post("/api/admin/sync-all")
def sync_all_current_squads() -> dict:
    token = os.getenv("FOOTBALL_DATA_API_TOKEN")
    if not token:
        raise HTTPException(503, "未配置 football-data.org 密钥，无法同步五大联赛全部球队。")
    if not full_sync_lock.acquire(blocking=False):
        return {"started": False, **full_sync_status}
    # A manual *full* refresh must not treat an old successful batch as fresh.
    # Reset every provider cursor first, then the worker traverses all clubs in
    # rate-safe batches instead of stopping after only the previously-pending
    # teams.
    with closing(db()) as connection:
        connection.execute("UPDATE provider_teams SET last_synced_at=NULL")
        connection.commit()
    full_sync_status.update({"running": True, "remaining": None, "completed": 0, "error": None})
    threading.Thread(target=run_full_football_data_sync, args=(token,), daemon=True, name="scoutxi-full-squad-sync").start()
    return {"started": True, **full_sync_status}


@app.get("/api/admin/sync-progress")
def full_squad_sync_progress() -> dict:
    return {"squads": dict(full_sync_status), "transfers": dict(transfer_sync_status)}


@app.post("/api/admin/sync-transfers")
def sync_current_transfers(max_teams: int = Query(default=60, ge=1, le=90)) -> dict:
    """Run the transparent transfer reconciliation independently when needed."""
    token = os.getenv("API_FOOTBALL_KEY")
    if not token:
        raise HTTPException(503, "未配置 API-Football 密钥，无法进行转会核验。")
    if transfer_sync_status["running"]:
        raise HTTPException(409, "转会核验正在进行中。")
    transfer_sync_status.update({"running": True, "completed": 0, "mapped": 0, "remaining": None, "error": None})
    try:
        result = refresh_api_football_transfers(token, max_teams)
        transfer_sync_status.update({"completed": len(result["checked"]), "mapped": result["mapped"],
                                     "remaining": result["remaining"], "error": result["failures"] or None})
        return result
    finally:
        transfer_sync_status["running"] = False


@app.get("/api/admin/roster-quality")
def roster_quality() -> dict:
    """Expose freshness and unresolved transfer evidence without exposing API keys."""
    with closing(db()) as connection:
        clubs = rows(connection.execute("""SELECT c.id,c.name,COUNT(p.id) AS current_players,
            MAX(p.source_updated_at) AS last_updated FROM clubs c LEFT JOIN players p
            ON p.club_id=c.id AND p.is_current=1 GROUP BY c.id ORDER BY c.name"""))
        transfers = rows(connection.execute("SELECT id,player_name,from_club_id,to_club_id,transfer_type,effective_at,source_url,source_name FROM transfer_events ORDER BY effective_at DESC"))
        transfer_coverage = rows(connection.execute("""SELECT p.club_id,p.team_name,p.league_code,m.external_id,m.last_transfer_checked_at
            FROM provider_teams p LEFT JOIN api_football_team_map m ON m.club_id=p.club_id ORDER BY p.league_code,p.team_name"""))
    return {"clubs": clubs, "verified_transfers": transfers, "transfer_coverage": transfer_coverage,
            "sync": {"squads": dict(full_sync_status), "transfers": dict(transfer_sync_status)}}


@app.post("/api/admin/enrich-club-logos")
def enrich_club_logos() -> dict:
    """Refresh remote crest URLs for every included club; no image files are stored."""
    token = os.getenv("FOOTBALL_DATA_API_TOKEN")
    if not token:
        raise HTTPException(503, "未配置 football-data.org 密钥，无法刷新俱乐部队标。")
    discover_football_data_teams(token)
    with closing(db()) as connection:
        total = connection.execute("SELECT COUNT(*) FROM clubs").fetchone()[0]
        populated = connection.execute("SELECT COUNT(*) FROM clubs WHERE logo_url IS NOT NULL AND logo_url<>''").fetchone()[0]
    return {"source": "football-data.org", "clubs": total, "logo_urls": populated,
            "storage": "remote URLs only"}


@app.post("/api/admin/refresh-featured-players")
def refresh_homepage_featured_players() -> dict:
    token = os.getenv("FOOTBALL_DATA_API_TOKEN")
    if not token:
        raise HTTPException(503, "未配置 football-data.org 密钥，无法刷新近期表现球员。")
    return refresh_featured_players(token)


def api_football_json(path: str, token: str, params: dict[str, int | str]) -> dict:
    """Request API-Football without ever putting the private token in a URL."""
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"https://v3.football.api-sports.io/{path}?{query}",
        headers={"x-apisports-key": token, "User-Agent": "ScoutXI/0.2"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        # The key is in a request header, but do not expose upstream details either.
        if error.code == 429:
            raise HTTPException(429, "API-Football 今日免费请求额度已用完，请在额度重置后继续刷新。")
        raise HTTPException(502, f"API-Football 请求失败（HTTP {error.code}）。")
    except urllib.error.URLError as error:
        raise HTTPException(502, f"无法连接 API-Football：{error.reason}")
    errors = payload.get("errors") or {}
    if errors:
        detail = "; ".join(str(value) for value in errors.values())[:240]
        if "free plans do not have access to this season" in detail.lower():
            raise HTTPException(409, "当前 API-Football 免费方案不开放本赛季数据（该密钥仅可访问至 2024）；已停止同步，避免将旧名单冒充最新名单。")
        raise HTTPException(502, f"API-Football 返回错误：{detail}")
    return payload


def api_football_position(name: str, raw: str | None) -> str:
    """Convert the provider's broad roster role into ScoutXI's tactical labels."""
    if name in POSITION_OVERRIDES:
        return POSITION_OVERRIDES[name]
    return {"Goalkeeper": "GK", "Defender": "CB", "Midfielder": "CM", "Attacker": "ST", "Forward": "ST"}.get(raw or "", "CM")


def current_season_year() -> int:
    # European league seasons start in the calendar year shown by API-Football.
    return datetime.now(timezone.utc).year


def refresh_api_football_team_map(token: str) -> dict:
    """Map ScoutXI's five-league clubs to API-Football IDs using one request per league.

    API-Football free accounts cannot list the current season, but team IDs are
    stable across seasons.  A permitted historical directory therefore gives a
    low-cost, reproducible mapping for most clubs; the few promoted teams are
    resolved individually by the transfer synchroniser.
    """
    mapping_season = current_season_year() - TRANSFER_MAPPING_SEASON_OFFSET
    mapped, unmatched = 0, set()
    with closing(db()) as connection:
        local_by_league = {
            league: rows(connection.execute("SELECT club_id,team_name FROM provider_teams WHERE league_code=?", (league,)))
            for league in API_FOOTBALL_LEAGUES
        }
    for league_code, (league_id, _) in API_FOOTBALL_LEAGUES.items():
        payload = api_football_json("teams", token, {"league": league_id, "season": mapping_season})
        remote = payload.get("response") or []
        remote_by_key: dict[str, list[int]] = {}
        for item in remote:
            team = item.get("team") or {}
            external_id = team.get("id")
            key = normalize_club_name(team.get("name") or "")
            if isinstance(external_id, int) and key:
                remote_by_key.setdefault(key, []).append(external_id)
        for local in local_by_league[league_code]:
            ids = remote_by_key.get(normalize_club_name(local["team_name"]), [])
            # Do not use fuzzy matching here. A wrong team identifier is worse
            # than an unmapped promoted club, which is resolved by exact search.
            external_id = ids[0] if len(ids) == 1 else None
            if isinstance(external_id, int):
                with closing(db()) as connection:
                    connection.execute("""INSERT INTO api_football_team_map(club_id,external_id,mapped_at,last_transfer_checked_at)
                        VALUES(?,?,?,NULL) ON CONFLICT(club_id) DO UPDATE SET external_id=excluded.external_id,mapped_at=excluded.mapped_at""",
                        (local["club_id"], external_id, datetime.now(timezone.utc).isoformat()))
                    connection.commit()
                mapped += 1
            else:
                unmatched.add(local["club_id"])
        time.sleep(0.2)
    return {"mapped": mapped, "unmatched": sorted(unmatched), "mapping_season": mapping_season,
            "requests": len(API_FOOTBALL_LEAGUES)}


def resolve_missing_api_football_team(token: str, team: dict) -> int | None:
    """Resolve a promoted/renamed club without guessing an identifier."""
    search_name = unicodedata.normalize("NFKD", team["team_name"]).encode("ascii", "ignore").decode("ascii")
    search_name = re.sub(r"[^A-Za-z0-9 ]", " ", search_name).strip()
    payload = api_football_json("teams", token, {"search": search_name})
    candidates = []
    for item in payload.get("response") or []:
        remote = item.get("team") or {}
        if normalize_club_name(remote.get("name") or "") == normalize_club_name(team["team_name"]):
            external_id = remote.get("id")
            if isinstance(external_id, int):
                candidates.append(external_id)
    if len(candidates) != 1:
        return None
    with closing(db()) as connection:
        connection.execute("""INSERT INTO api_football_team_map(club_id,external_id,mapped_at,last_transfer_checked_at)
            VALUES(?,?,?,NULL) ON CONFLICT(club_id) DO UPDATE SET external_id=excluded.external_id,mapped_at=excluded.mapped_at""",
            (team["club_id"], candidates[0], datetime.now(timezone.utc).isoformat()))
        connection.commit()
    return candidates[0]


def club_id_for_provider_name(connection: sqlite3.Connection, name: str) -> str | None:
    candidates = rows(connection.execute("SELECT club_id,team_name FROM provider_teams"))
    return best_club_match(candidates, name)


def import_api_football_transfers(connection: sqlite3.Connection, source_club_id: str, payload: dict, checked_at: str) -> int:
    """Import only current-window records involving this club, with stable IDs."""
    imported = 0
    start = transfer_window_start()
    for record in payload.get("response") or []:
        player = record.get("player") or {}
        player_name = player.get("name") or ""
        for transfer in record.get("transfers") or []:
            effective_at = transfer.get("date") or ""
            if not player_name or effective_at < start:
                continue
            teams = transfer.get("teams") or {}
            from_club = club_id_for_provider_name(connection, ((teams.get("out") or {}).get("name") or ""))
            to_club = club_id_for_provider_name(connection, ((teams.get("in") or {}).get("name") or ""))
            # The endpoint was requested for source_club_id.  Treat a move to
            # a club outside our five leagues as an outgoing event too.
            if from_club != source_club_id and to_club != source_club_id:
                continue
            resolved_from = from_club or source_club_id
            resolved_to = to_club or f"external-{normalize_club_name(((teams.get('in') or {}).get('name') or 'unknown'))}"
            raw_type = (transfer.get("type") or "").lower()
            transfer_type = "LOAN" if "loan" in raw_type else "PERMANENT"
            identity = "|".join((player_name, effective_at, resolved_from, resolved_to, transfer_type))
            event_id = "af-transfer-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
            cursor = connection.execute("""INSERT OR IGNORE INTO transfer_events
                (id,player_name,from_club_id,to_club_id,transfer_type,effective_at,source_url,source_name,verified_at)
                VALUES(?,?,?,?,?,?,?,?,?)""", (event_id, player_name, resolved_from, resolved_to, transfer_type,
                effective_at, "https://www.api-football.com/documentation-v3#tag/Transfers", "API-Football 转会记录", checked_at))
            imported += int(cursor.rowcount > 0)
    return imported


def refresh_api_football_transfers(token: str, max_teams: int = 60) -> dict:
    """Verify five-league rosters in request-safe batches using transfer history."""
    if max_teams < 1:
        raise HTTPException(422, "至少需要同步一支球队")
    checked_at = datetime.now(timezone.utc).isoformat()
    map_result = refresh_api_football_team_map(token)
    requests_used = map_result["requests"]
    with closing(db()) as connection:
        teams = rows(connection.execute("""SELECT p.club_id,p.team_name,p.league_code,m.external_id,m.last_transfer_checked_at
            FROM provider_teams p LEFT JOIN api_football_team_map m ON m.club_id=p.club_id
            ORDER BY CASE WHEN m.external_id IS NULL THEN 1 ELSE 0 END,
                CASE WHEN m.last_transfer_checked_at IS NULL THEN 0 ELSE 1 END,
                m.last_transfer_checked_at ASC, p.club_id"""))
    mapped, unresolved, imported, checked, failures = 0, [], 0, [], []
    for team in teams:
        if requests_used >= TRANSFER_SYNC_REQUEST_BUDGET or len(checked) >= max_teams:
            break
        external_id = team["external_id"]
        if not isinstance(external_id, int):
            try:
                external_id = resolve_missing_api_football_team(token, team)
                requests_used += 1
            except HTTPException as error:
                failures.append({"club_id": team["club_id"], "error": error.detail})
                if error.status_code == 429:
                    break
                continue
        if not external_id:
            unresolved.append(team["club_id"])
            continue
        mapped += 1
        try:
            payload = api_football_json("transfers", token, {"team": external_id})
            requests_used += 1
            with closing(db()) as connection:
                imported += import_api_football_transfers(connection, team["club_id"], payload, checked_at)
                connection.execute("UPDATE api_football_team_map SET last_transfer_checked_at=? WHERE club_id=?", (checked_at, team["club_id"]))
                connection.commit()
            checked.append(team["club_id"])
        except HTTPException as error:
            failures.append({"club_id": team["club_id"], "error": error.detail})
            if error.status_code == 429:
                break
        time.sleep(0.2)
    with closing(db()) as connection:
        reconciliation = reconcile_current_rosters(connection)
        connection.execute("""INSERT OR REPLACE INTO sync_jobs(id,provider,status,finished_at,entity_count,error)
            VALUES(?,?,?,?,?,?)""", (f"transfer-sync-{checked_at}", "API-Football 转会核验", "SUCCESS" if not failures else "PARTIAL",
            checked_at, len(checked), json.dumps(failures, ensure_ascii=False) if failures else None))
        connection.commit()
        remaining = connection.execute("SELECT COUNT(*) FROM provider_teams p LEFT JOIN api_football_team_map m ON m.club_id=p.club_id WHERE m.last_transfer_checked_at IS NULL").fetchone()[0]
    return {"checked_at": checked_at, "source": "API-Football 转会记录", "window_start": transfer_window_start(),
            "checked": checked, "mapped": mapped, "imported_events": imported, "reconciliation": reconciliation,
            "unresolved_clubs": unresolved, "failures": failures, "remaining": remaining,
            "requests_used": requests_used, "daily_budget": TRANSFER_SYNC_REQUEST_BUDGET}


def discover_api_football_teams(token: str, refreshed_at: str) -> int:
    """Store only team identifiers and labels; no remote images are downloaded."""
    discovered = 0
    season = current_season_year()
    for league_code, (league_id, league_name) in API_FOOTBALL_LEAGUES.items():
        payload = api_football_json("teams", token, {"league": league_id, "season": season})
        teams = payload.get("response") or []
        with closing(db()) as connection:
            for item in teams:
                team = item.get("team") or {}
                external_id = team.get("id")
                if not isinstance(external_id, int):
                    continue
                club_id = API_FOOTBALL_FEATURED_CLUBS.get(external_id, f"af-team-{external_id}")
                team_name = team.get("name") or f"球队 {external_id}"
                connection.execute("""INSERT INTO clubs(id,name,country,league,logo_url) VALUES(?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country,league=excluded.league,
                    logo_url=COALESCE(excluded.logo_url,clubs.logo_url)""", (club_id, team_name, team.get("country") or "未知", league_name, team.get("logo")))
                connection.execute("""INSERT INTO provider_teams(external_id,club_id,league_code,team_name,last_synced_at) VALUES(?,?,?,?,NULL)
                    ON CONFLICT(external_id) DO UPDATE SET club_id=excluded.club_id,league_code=excluded.league_code,team_name=excluded.team_name""", (external_id, club_id, league_code, team_name))
                discovered += 1
            connection.commit()
        # Stay comfortably below burst limits while keeping the one-day batch usable.
        time.sleep(0.2)
    return discovered


def refresh_api_football_squads(token: str, max_teams: int) -> dict:
    refreshed_at = datetime.now(timezone.utc).isoformat()
    with closing(db()) as connection:
        known_teams = connection.execute("SELECT COUNT(*) FROM provider_teams").fetchone()[0]
    discovery_requests = 0
    if known_teams < 90:
        discover_api_football_teams(token, refreshed_at)
        discovery_requests = len(API_FOOTBALL_LEAGUES)
    # API-Football's free plan has 100 daily calls.  Reserve a small margin and
    # account for the five discovery calls on the initial five-league import.
    batch_limit = min(max_teams, max(1, 95 - discovery_requests))
    with closing(db()) as connection:
        teams = rows(connection.execute("""SELECT external_id,club_id,league_code,team_name,last_synced_at
            FROM provider_teams ORDER BY CASE WHEN last_synced_at IS NULL THEN 0 ELSE 1 END,
            last_synced_at ASC, external_id ASC LIMIT ?""", (batch_limit,)))
    if not teams:
        raise HTTPException(502, "未发现五大联赛球队；请确认 API-Football 的赛季数据权限。")

    results, failures = [], []
    for team in teams:
        try:
            payload = api_football_json("players/squads", token, {"team": team["external_id"]})
            response = payload.get("response") or []
            squad = (response[0].get("players") or []) if response else []
            if not squad:
                raise ValueError("未返回当前球员名单")
            with closing(db()) as connection:
                connection.execute("UPDATE players SET is_current=0 WHERE club_id=?", (team["club_id"],))
                for person in squad:
                    external_id = person.get("id")
                    if not isinstance(external_id, int):
                        continue
                    name = person.get("name") or "未知球员"
                    player_id = f"af-{external_id}"
                    connection.execute("""INSERT INTO players(id,name,name_zh,position,age,nationality,foot,club_id,shirt_no,height_cm,bio,appearances,goals,assists,rating,data_source,source_updated_at,avatar_url,is_current)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                    ON CONFLICT(id) DO UPDATE SET name=excluded.name,name_zh=excluded.name_zh,position=excluded.position,age=excluded.age,club_id=excluded.club_id,shirt_no=excluded.shirt_no,bio=excluded.bio,data_source=excluded.data_source,source_updated_at=excluded.source_updated_at,is_current=1""", (player_id, name, name, api_football_position(name, person.get("position")), int(person.get("age") or 0), "未知", "未知", team["club_id"], person.get("number"), None, "由 API-Football 当前阵容同步；头像会经当前俱乐部资料核验后显示。", 0, 0, 0, 0, "API-Football", refreshed_at, None))
                connection.execute("UPDATE provider_teams SET last_synced_at=? WHERE external_id=?", (refreshed_at, team["external_id"]))
                connection.execute("INSERT OR REPLACE INTO sync_jobs(id,provider,status,finished_at,entity_count,error) VALUES(?,?,?,?,?,?)", (f"af-{team['external_id']}-{refreshed_at}", "API-Football", "SUCCESS", refreshed_at, len(squad), None))
                connection.commit()
            results.append({"club_id": team["club_id"], "club_name": team["team_name"], "players": len(squad)})
        except (HTTPException, ValueError) as error:
            if isinstance(error, HTTPException) and error.status_code == 429:
                raise error
            failures.append({"club_id": team["club_id"], "error": str(error.detail if isinstance(error, HTTPException) else error)})
        time.sleep(0.2)
    return {"refreshed_at": refreshed_at, "source": "API-Football", "batch_size": len(results), "remaining": max(0, 96 - len(results)), "results": results, "failures": failures}


@app.post("/api/admin/sync")
def refresh_current_squads(max_teams: int = Query(default=9, ge=1, le=95)) -> dict:
    # Prefer football-data.org when available: its verified free plan covers all
    # five leagues here, while the configured free API-Football key cannot read
    # the current season.
    token = os.getenv("FOOTBALL_DATA_API_TOKEN")
    if token:
        return refresh_football_data_squads(token, max_teams)
    api_football_token = os.getenv("API_FOOTBALL_KEY")
    if api_football_token:
        return refresh_api_football_squads(api_football_token, max_teams)
    if not token: raise HTTPException(503, "未配置 FOOTBALL_DATA_API_TOKEN；不会把 API 密钥暴露给前端。")
    refreshed_at = datetime.now(timezone.utc).isoformat()
    results = []
    for club_id, team_id in TEAM_SOURCES.items():
        payload = fetch_current_squad(team_id, token)
        squad = payload.get("squad", [])
        profiles = fetch_sportsdb_profiles(TEAM_SEARCH_NAMES[club_id])
        with closing(db()) as connection:
            area = payload.get("area") or {}
            competition = (payload.get("runningCompetitions") or [{}])[0]
            connection.execute("""INSERT INTO clubs(id,name,country,league) VALUES(?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country,league=excluded.league""", (club_id, payload.get("name") or TEAM_SEARCH_NAMES[club_id], area.get("name") or "未知", competition.get("name") or "联赛"))
            connection.execute("UPDATE players SET is_current=0 WHERE club_id=?", (club_id,))
            for person in squad:
                external_id = person.get("id")
                if external_id is None: continue
                player_id = f"fd-{team_id}-{external_id}"
                name = person.get("name") or "未知球员"
                profile = profiles.get(normalize_person_name(name), {})
                position = profile.get("position") or provider_position(name, person.get("position", ""))
                connection.execute("""INSERT INTO players(id,name,name_zh,position,age,nationality,foot,club_id,shirt_no,height_cm,bio,appearances,goals,assists,rating,data_source,source_updated_at,avatar_url,is_current)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,name_zh=excluded.name_zh,position=excluded.position,age=excluded.age,nationality=excluded.nationality,club_id=excluded.club_id,bio=excluded.bio,data_source=excluded.data_source,source_updated_at=excluded.source_updated_at,avatar_url=COALESCE(excluded.avatar_url,players.avatar_url),is_current=1""", (player_id, name, name, position, provider_age(person.get("dateOfBirth")), person.get("nationality") or "未知", "未知", club_id, None, None, "由 football-data.org 当前阵容同步，并经 ScoutXI 细分位置与头像资料补齐。", 0, 0, 0, 0, "football-data.org + TheSportsDB", refreshed_at, profile.get("avatar_url")))
            connection.execute("INSERT OR REPLACE INTO sync_jobs(id,provider,status,finished_at,entity_count,error) VALUES(?,?,?,?,?,?)", (f"fd-{club_id}-{refreshed_at}", "football-data.org", "SUCCESS", refreshed_at, len(squad), None))
            connection.commit()
        results.append({"club_id": club_id, "players": len(squad)})
    return {"refreshed_at": refreshed_at, "source": "football-data.org + TheSportsDB", "results": results}
