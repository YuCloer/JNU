"""Pure, source-labelled player evaluation and XI selection helpers.

The app deliberately keeps an official reference separate from its own
baseline.  A missing official reference must never be silently represented as
an EA SPORTS FC rating.
"""

from __future__ import annotations

import hashlib
from typing import Any

ABILITY_KEYS = ("pace", "shooting", "passing", "dribbling", "defending", "physical")

# Public EA SPORTS FC 26 references intentionally kept small and exact.  The
# full EA database is not bundled or scraped; a player not in this mapping gets
# a clearly labelled ScoutXI baseline instead.
EA_FC_26_REFERENCES: dict[str, dict[str, Any]] = {
    "Kylian Mbappé": {"overall": 91, "pace": 97, "shooting": 90, "passing": 81, "dribbling": 92, "defending": 37, "physical": 76,
                       "url": "https://www.ea.com/games/ea-sports-fc/ratings/player-ratings/kylian-mbappe/231747"},
    "Erling Haaland": {"overall": 90, "pace": 86, "shooting": 91, "passing": 70, "dribbling": 80, "defending": 45, "physical": 88,
                       "url": "https://www.ea.com/games/ea-sports-fc/ratings/player-ratings/erling-haaland/239085"},
    "Ousmane Dembélé": {"overall": 90, "pace": 91, "shooting": 88, "passing": 83, "dribbling": 93, "defending": 50, "physical": 69,
                         "url": "https://www.ea.com/games/ea-sports-fc/ratings/player-ratings/ousmane-dembele/231443"},
}

POSITION_PROFILES = {
    "GK": (61, 35, 65, 61, 68, 72), "CB": (64, 42, 61, 59, 72, 74),
    "LB": (73, 53, 65, 66, 68, 67), "RB": (73, 53, 65, 66, 68, 67),
    "DM": (65, 57, 71, 67, 72, 72), "CM": (69, 63, 72, 71, 63, 68),
    "AM": (71, 72, 75, 75, 49, 63), "LW": (77, 72, 68, 76, 42, 63),
    "RW": (77, 72, 68, 76, 42, 63), "ST": (73, 76, 62, 70, 40, 72),
}


def _stable_jitter(player_id: str, index: int) -> int:
    raw = hashlib.blake2s(f"{player_id}:{index}".encode("utf-8"), digest_size=1).digest()[0]
    return raw % 13 - 6


def ability_profile(player: dict[str, Any]) -> dict[str, Any]:
    """Return a FIFA-style 60–100 profile with an honest source label."""
    if player.get("ea_overall") is not None:
        attributes = {
            "pace": max(60, int(player.get("ea_pace") or 60)),
            "shooting": max(60, int(player.get("ea_shooting") or 60)),
            "passing": max(60, int(player.get("ea_passing") or 60)),
            "dribbling": max(60, int(player.get("ea_dribbling") or 60)),
            "defending": max(60, int(player.get("ea_defending") or 60)),
            "physical": max(60, int(player.get("ea_physical") or 60)),
        }
        return {
            "overall": max(60, int(player["ea_overall"])),
            "ability_source": "EA SPORTS FC 官方评分参考",
            "ability_reference_url": player.get("ea_reference_url"),
            "ability_is_reference": True,
            "attributes": attributes,
        }
    reference = EA_FC_26_REFERENCES.get(player.get("name", ""))
    if reference:
        return {
            "overall": reference["overall"],
            "ability_source": "EA SPORTS FC 26 官方参考",
            "ability_reference_url": reference["url"],
            "ability_is_reference": True,
            "attributes": {key: reference[key] for key in ABILITY_KEYS},
        }

    position = player.get("position") or "CM"
    profile = POSITION_PROFILES.get(position, POSITION_PROFILES["CM"])
    player_id = str(player.get("id") or player.get("name") or "unknown")
    age = int(player.get("age") or 21)
    development = 3 if 22 <= age <= 29 else (1 if age <= 21 else -2 if age >= 34 else 0)
    attributes = {
        key: max(60, min(90, base + development + _stable_jitter(player_id, index)))
        for index, (key, base) in enumerate(zip(ABILITY_KEYS, profile))
    }
    # The value is a baseline for unscouted players, not a claim of real-world
    # ability.  It intentionally has a lower 60 floor for academy-level use.
    overall = max(60, min(84, round(sum(attributes.values()) / len(attributes))))
    return {
        "overall": overall,
        "ability_source": "ScoutXI 基准值（位置/年龄模型，非官方）",
        "ability_reference_url": None,
        "ability_is_reference": False,
        "attributes": attributes,
    }


def sort_players_by_ability(players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(players, key=lambda item: (-int(item.get("overall") or 0), item.get("name") or ""))


def compatible(zone: dict[str, Any], player: dict[str, Any]) -> bool:
    return player.get("position") in zone["allow"]


def select_xi(players: list[dict[str, Any]], zones: list[dict[str, Any]], formation: str, *, view_id: str, label: str, source: str) -> dict[str, Any]:
    """Fill a formation with a caller-provided, already ordered player list."""
    remaining = list(players)
    slots: list[dict[str, Any]] = []
    for zone in zones:
        candidates = [player for player in remaining if compatible(zone, player)]
        if not candidates:
            continue
        player = candidates[0]
        remaining.remove(player)
        slots.append({"player_id": player["id"], "role": "STARTER", "tactical_role": zone["role"], "x": zone["x"], "y": zone["y"]})
    return {
        "id": view_id, "label": label, "formation": formation, "status": "ready", "source": source, "slots": slots,
    }


def recommend_xi(players: list[dict[str, Any]], zones: list[dict[str, Any]], formation: str) -> dict[str, Any]:
    """Deterministic, explainable best XI — deliberately not an AI claim."""
    return select_xi(sort_players_by_ability(players), zones, formation, view_id="recommendation", label="智能推荐 XI",
                     source="ScoutXI：综合能力值 + 位置兼容，非生成式 AI")
