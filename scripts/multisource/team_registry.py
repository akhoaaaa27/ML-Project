"""Verified research aliases; production identities and registry stay unchanged."""

from scripts.inference.common import TEAM_IDS
from .mapping import ALIASES, folded, team_name

CLUBS_SOURCE = "https://www.laliga.com/en-GB/laliga-easports/clubs"
NEW_CLUBS = {
    "Malaga": dict(id="malaga", official_name="Málaga CF",
                   source="https://www.laliga.com/en-GB/clubs/malaga-cf/squad"),
    "Racing Santander": dict(id="racing-santander", official_name="R. Racing Club",
                            source="https://www.laliga.com/en-GB/clubs/r-racing-club/squad"),
    "Deportivo La Coruna": dict(id="deportivo-la-coruna", official_name="RC Deportivo",
                               source="https://www.laliga.com/en-GB/clubs/rc-deportivo/squad"),
}
REVIEWED_ALIASES = dict(ALIASES)
REVIEWED_ALIASES.update({folded("Málaga CF"): "Malaga", folded("R. Racing Club"): "Racing Santander",
                         folded("RC Deportivo"): "Deportivo La Coruna"})


def resolve(value):
    key = folded(value)
    if key not in REVIEWED_ALIASES:
        raise ValueError("Unknown research team alias")
    return REVIEWED_ALIASES[key]


def stable_id(value):
    canonical = resolve(value)
    return TEAM_IDS[canonical] if canonical in TEAM_IDS else NEW_CLUBS[canonical]["id"]


def identity_manifest():
    return dict(new_clubs=NEW_CLUBS, verification_source=CLUBS_SOURCE, season=2026,
                production_registry_modified=False)
