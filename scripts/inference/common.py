"""Quy ước lỗi, định danh và I/O cho Phase 8."""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import tempfile

from scripts.prepare_training_features import ROOT

MODEL_DIR = ROOT / "models"
HISTORY_PATH = ROOT / "data/history/laliga_history.sqlite3"
OUTPUT_DIR = ROOT / "outputs/inference"
MODEL_VERSION = "1.0.0"
SNAPSHOT_PROVIDER = "fbref_opta_snapshot"

# Mapping tường minh; không fuzzy matching hoặc tự gộp đội không biết.
CANONICAL_TEAMS = (
    "Alaves", "Almeria", "Athletic Club", "Atletico Madrid", "Barcelona", "Cadiz", "Celta Vigo",
    "Eibar", "Elche", "Espanyol", "Getafe", "Girona", "Granada", "Huesca", "Las Palmas", "Leganes",
    "Levante", "Mallorca", "Osasuna", "Oviedo", "Rayo Vallecano", "Real Betis", "Real Madrid",
    "Real Sociedad", "Sevilla", "Valencia", "Valladolid", "Villarreal",
)
TEAM_IDS = {name: name.lower().replace(" ", "-") for name in CANONICAL_TEAMS}
ALIASES = {name.casefold(): name for name in CANONICAL_TEAMS}
ALIASES.update({value: key for key, value in TEAM_IDS.items()})
ALIASES.update({"alavés": "Alaves", "almería": "Almeria", "atlético madrid": "Atletico Madrid",
                "cádiz": "Cadiz", "leganés": "Leganes", "betis": "Real Betis"})


class InferenceError(ValueError):
    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code, self.details = code, details

    def result(self, mode=None):
        return dict(status="error", mode=mode, error=dict(code=self.code, message=str(self), details=self.details))


def check(condition, code, message, **details):
    if not condition:
        raise InferenceError(code, message, **details)


def resolve_team(value):
    check(isinstance(value, str) and value.strip().casefold() in ALIASES,
          "UNKNOWN_TEAM", "Đội chưa có trong canonical mapping.", team=str(value))
    return ALIASES[value.strip().casefold()]


def parse_date(value):
    check(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None,
          "INVALID_DATE", "Ngày phải có định dạng YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InferenceError("INVALID_DATE", "Ngày không hợp lệ.") from exc


def validate_fixture(home, away, match_date, season):
    home, away = resolve_team(home), resolve_team(away)
    check(home != away, "DUPLICATE_TEAM", "Hai phía phải là hai đội khác nhau.")
    day = parse_date(match_date)
    check(type(season) is int and 1900 <= season <= 2200 and day.year in (season, season + 1),
          "INVALID_SEASON", "Season là năm bắt đầu mùa; ngày phải thuộc năm đó hoặc năm kế tiếp.")
    return home, away, day


def fixture_key(season, home, away):
    return f"laliga:{season}:{TEAM_IDS[home]}:{TEAM_IDS[away]}"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def versions():
    import platform
    return dict(python=platform.python_version(), packages={name: importlib.metadata.version(name)
        for name in ("numpy", "pandas", "scipy", "scikit-learn", "joblib", "threadpoolctl")})


def write_json(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if exclusive:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return
    # Tạo ngay trong thư mục đích để giữ ACL kế thừa trên Windows.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".inference-", suffix=".tmp", delete=False) as handle:
        staging = Path(handle.name)
    try:
        staging.write_text(text, encoding="utf-8")
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def cli_output(function):
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        result = function()
    except InferenceError as exc:
        print(json.dumps(exc.result(), ensure_ascii=False, allow_nan=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 0
