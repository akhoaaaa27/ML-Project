"""Adapters for checked snapshots, forecast orchestration and aggregate history."""

from collections import Counter
import csv
from datetime import date
import json
from statistics import mean

from scripts.inference.common import MODEL_DIR, ROOT, sha256
from scripts.inference.model_artifact import load_trusted_pipeline
from scripts.multisource.fixture_catalogue import fixture_catalogue
from scripts.multisource.forecast_eligibility import FIXTURE_MAX_AGE, utc, utc_text
from scripts.multisource.forecast_generation import generate_forecast
from scripts.multisource.forecast_service import ForecastService
from scripts.multisource.match_registry import VERIFIED_COMPLETED, require
from scripts.multisource.phase856_reporting import protected_integrity

from .settings import APP_VERSION, DEMO_CLOCKS, MODEL_METADATA_SHA256, MODEL_SHA256, REAL_SHA256, Mode


def page(items, query):
    return dict(items=items[query.offset:query.offset + query.limit],
                total=len(items), offset=query.offset, limit=query.limit)


def history_summary(rows):
    verified = [row for row, _ in rows]
    observed = [stats for _, stats in rows if stats.get("xg") is not None and stats.get("xga") is not None]
    shots = [stats for _, stats in rows if stats.get("sh") is not None and stats.get("sot") is not None]
    wins = sum(row["gf"] > row["ga"] for row in verified)
    draws = sum(row["gf"] == row["ga"] for row in verified)
    return dict(
        verified_fixtures=len(verified), observed_xg_fixtures=len(observed),
        missing_xg_fixtures=len(verified) - len(observed), wins=wins, draws=draws,
        losses=len(verified) - wins - draws, goals_for=sum(row["gf"] for row in verified),
        goals_against=sum(row["ga"] for row in verified),
        mean_xg=mean(row["xg"] for row in observed) if observed else None,
        mean_xga=mean(row["xga"] for row in observed) if observed else None,
        xg_sources=dict(Counter(row["xg_source"] for row in observed)),
        mean_shots=mean(row["sh"] for row in shots) if shots else None,
        mean_sot=mean(row["sot"] for row in shots) if shots else None,
        shots_sources=dict(Counter(row["shots_source"] for row in shots)),
        clean_sheets=sum(row["ga"] == 0 for row in verified),
    )


class ResearchService:
    def __init__(self, settings):
        self.settings = settings
        self.version = settings.snapshot_version
        self.mode = settings.mode
        synthetic = self.mode == Mode.SYNTHETIC_DEMO
        root = settings.demo_root if synthetic else None
        self.forecast = ForecastService(
            synthetic_history=root / "history" if synthetic else None,
            synthetic_ledger_base=root / "ledger" if synthetic else None,
            simulated_clock=(lambda: DEMO_CLOCKS[self.version]) if synthetic else None,
        )
        # Check the public baseline before deserializing the repository-owned model.
        protected_integrity()
        require(sha256(MODEL_DIR / "laliga_lr_pipeline.joblib") == MODEL_SHA256
                and sha256(MODEL_DIR / "model_metadata.json") == MODEL_METADATA_SHA256,
                "ARTIFACT_CORRUPT", "Model binding does not match the frozen artifact")
        _, self.metadata = load_trusted_pipeline()
        self.store = self.forecast.eligibility.open(self.version)
        self.digest = sha256(self.store.path)
        require(synthetic or self.digest == REAL_SHA256, "HISTORY_CORRUPT", "Snapshot binding mismatch")
        self.fixtures = {row["canonical_fixture_key"]: row for row in fixture_catalogue(self.store)}
        roster = {}
        for row in self.fixtures.values():
            for team in (row["home_team"], row["away_team"]):
                roster.setdefault(team, set()).add(row["season"])
        self.teams = {team: dict(id=team, name=team, seasons=sorted(seasons))
                      for team, seasons in sorted(roster.items())}
        self.seasons = sorted({season for team in self.teams.values() for season in team["seasons"]})
        self.summary = self._model_summary()

    def bootstrap(self):
        return dict(api_version=APP_VERSION, mode=self.mode, label=self.mode.replace("_", " "),
                    model_version=self.metadata["model_version"], snapshot_version=self.version,
                    seasons=self.seasons, current_season=self.seasons[-1],
                    operator_writes_enabled=bool(self.settings.operator_token))

    def _verify_bound_snapshot(self):
        self.store.verify_integrity()
        require(sha256(self.store.path) == self.digest, "HISTORY_CORRUPT", "Bound history changed")

    def _require_fixture(self, key):
        row = self.fixtures.get(key)
        require(row is not None, "FIXTURE_NOT_FOUND", "Fixture is absent from this snapshot")
        return row

    def _requires_forecasting(self):
        require(self.mode != Mode.HISTORICAL_REFERENCE, "HISTORICAL_ONLY", "Historical reference is read-only")

    def _upcoming(self, row, now):
        if row["observed_status"] != "scheduled" or row["match_date"] < now.date().isoformat():
            return False
        return row["kickoff_utc"] is None or utc(row["kickoff_utc"]) > now

    def list_teams(self, query):
        return page([row for row in self.teams.values() if query.season is None or query.season in row["seasons"]], query)

    def list_fixtures(self, query):
        now = self.forecast.eligibility.now()
        for team in (query.home, query.away):
            require(team is None or team in self.teams, "TEAM_NOT_FOUND", "Team is absent from this snapshot")
        require(query.home is None or query.home != query.away, "INVALID_MATCHUP", "Choose two distinct teams")
        rows = [row for row in self.fixtures.values()
                if (query.season is None or row["season"] == query.season)
                and (query.home is None or query.home == row["home_team"])
                and (query.away is None or query.away == row["away_team"])
                and (query.status is None or query.status == row["observed_status"])
                and (not query.upcoming or self._upcoming(row, now))]
        return page(rows, query)

    def data_status(self):
        self._verify_bound_snapshot()
        result = self.forecast.get_forecast_data_status(self.version)
        engine = self.forecast.eligibility
        now = engine.now()
        upcoming = [row for row in self.fixtures.values() if self._upcoming(row, now)]
        catalogues = {row["season"]: json.loads(row["payload"]) for row in
                      self.store.query("SELECT season, payload FROM catalogues")}
        recent = 0
        if self.mode != Mode.HISTORICAL_REFERENCE and (engine.dataset_kind == "synthetic"
                or utc(self.store.manifest["build_timestamp"]) <= now):
            for row in upcoming:
                catalogue = catalogues.get(row["season"])
                review = engine._schedule_evidence(self.store, row, catalogue) if catalogue and row["kickoff_utc"] else None
                if review is not None and review <= now and now - review <= FIXTURE_MAX_AGE:
                    recent += 1
        if self.mode == Mode.HISTORICAL_REFERENCE:
            freshness = "HISTORICAL_ONLY"
        elif not upcoming:
            freshness = "NO_UPCOMING"
        elif not recent:
            freshness = "UNVERIFIED"
        else:
            freshness = "VERIFIED" if recent == len(upcoming) else "PARTIAL"
        return dict(result, mode=self.mode, evaluated_at_utc=utc_text(now),
                    schedule_max_age_hours=int(FIXTURE_MAX_AGE.total_seconds() / 3600),
                    upcoming_fixtures=len(upcoming), recent_review_upcoming_fixtures=recent,
                    schedule_freshness=freshness)

    def eligibility(self, key):
        self._verify_bound_snapshot()
        if self.mode == Mode.HISTORICAL_REFERENCE:
            return dict(canonical_fixture_key=key, snapshot_version=self.version, eligibility_status="UNAVAILABLE",
                        reason="HISTORICAL_ONLY", target=self.fixtures.get(key),
                        generated_at_utc=utc_text(self.forecast.eligibility.now()))
        return self.forecast.evaluate_forecast_eligibility(key, self.version)

    def preview(self, key):
        if self.mode == Mode.HISTORICAL_REFERENCE:
            eligibility = self.eligibility(key)
            return dict(status="UNAVAILABLE", eligibility=eligibility)
        self._verify_bound_snapshot()
        result = generate_forecast(key, self.version, eligibility=self.forecast.eligibility)
        if result["status"] == "GENERATED":
            candidate = result["forecast"]
            require(candidate["model_artifact_sha256"] == MODEL_SHA256 and candidate["history_database_sha256"] == self.digest,
                    "ARTIFACT_CORRUPT", "Forecast inputs no longer match the startup binding")
            # Generation returns a full candidate after applying eligibility. Avoid a second time-sensitive evaluation.
            return dict(status=candidate["eligibility_status"], preview=candidate)
        return self._action(result)

    def _published(self, record):
        fixture = self._require_fixture(record["canonical_fixture_key"])
        require(record["model_artifact_sha256"] == MODEL_SHA256, "LEDGER_CORRUPT", "Unexpected model in the ledger")
        return dict(record, home_team=fixture["home_team"], away_team=fixture["away_team"])

    def _action(self, result):
        if result["status"] == "FORECAST_ERROR":
            return dict(result, error=dict(code=result["error"], message="The verified forecast could not be generated"))
        if "forecast" in result:
            return dict(result, forecast=self._published(result["forecast"]))
        return result

    def publish(self, key):
        self._requires_forecasting()
        self._verify_bound_snapshot()
        require(sha256(MODEL_DIR / "laliga_lr_pipeline.joblib") == MODEL_SHA256
                and sha256(MODEL_DIR / "model_metadata.json") == MODEL_METADATA_SHA256,
                "ARTIFACT_CORRUPT", "Forecast artifact no longer matches the startup binding")
        return self._action(self.forecast.generate_forecast(key, self.version))

    def published(self, query):
        if self.mode == Mode.HISTORICAL_REFERENCE:
            return page([], query)
        # Traverse each checksum-validated chain once for the unfiltered ledger view.
        chains = self.forecast.ledger._records()
        rows = chains.get(query.fixture_key, []) if query.fixture_key else [
            record for chain in chains.values() for record in chain]
        rows = sorted(rows, key=lambda item: (item["generated_at_utc"], item["forecast_revision"], item["forecast_id"]),
                      reverse=True)
        result = page(rows, query)
        result["items"] = [self._published(row) for row in result["items"]]
        return result

    def get_published(self, forecast_id):
        self._requires_forecasting()
        return self._published(self.forecast.get_forecast(forecast_id))

    def compare(self, query):
        self._requires_forecasting()
        return dict(self.forecast.compare_forecasts(query.fixture_key, query.v1, query.v2),
                    v1=self.get_published(query.v1), v2=self.get_published(query.v2))

    def _history(self, team, season, before, limit):
        require(team in self.teams, "TEAM_NOT_FOUND", "Team is absent from this snapshot")
        require(season in self.seasons, "SEASON_NOT_FOUND", "Season is absent from this snapshot")
        return self._history_rows(team, season, before, limit)

    def _history_rows(self, team, season, before, limit):
        rows = self.store.query(
            """SELECT r.home_team, r.away_team, r.home_goals, r.away_goals, r.match_date, s.payload
                 FROM registry AS r LEFT JOIN statistics AS s
                   ON s.canonical_fixture_key=r.canonical_fixture_key AND s.team=?
                  AND r.statistics_status!='SOURCE_CONFLICT'
                WHERE r.season=? AND r.match_date<? AND r.match_status=?
                  AND (r.home_team=? OR r.away_team=?)
                ORDER BY r.match_date DESC, r.canonical_fixture_key DESC LIMIT ?""",
            (team, season, before, VERIFIED_COMPLETED, team, team, limit),
        )
        results = []
        for row in reversed(rows):
            home = row["home_team"] == team
            own, other = ("home", "away") if home else ("away", "home")
            match = dict(gf=row[own + "_goals"], ga=row[other + "_goals"], venue=own,
                         date=row["match_date"], opponent=row[other + "_team"])
            results.append((match, json.loads(row["payload"]) if row["payload"] else {}))
        return results

    @staticmethod
    def _trend(rows):
        return [dict(date=row["date"], venue=row["venue"], opponent=row["opponent"],
                     goals_for=row["gf"], goals_against=row["ga"], xg=stats.get("xg"),
                     xga=stats.get("xga"), source=stats.get("xg_source")) for row, stats in rows]

    def _present_history(self, team, season, rows, min_count=1):
        overall = history_summary(rows)
        status = "COMPLETE"
        if not rows:
            status = "ZERO_HISTORY"
        elif overall["missing_xg_fixtures"]:
            status = "INCOMPLETE_STATISTICS"
        elif len(rows) < min_count:
            status = "INSUFFICIENT_HISTORY"
        return dict(team=team, season=season, snapshot_version=self.version, mode=self.mode, status=status,
                    overall=overall, home=history_summary([entry for entry in rows if entry[0]["venue"] == "home"]),
                    away=history_summary([entry for entry in rows if entry[0]["venue"] == "away"]),
                    trend=self._trend(rows))

    def _history_cutoff(self):
        # The same date-only policy excludes today's outcomes in every forecasting mode.
        return self.forecast.eligibility.now().date().isoformat()

    def team_stats(self, team, season):
        self._verify_bound_snapshot()
        return self._present_history(team, season, self._history(team, season, self._history_cutoff(), 50))

    def match_analysis(self, query):
        self._verify_bound_snapshot()
        require(query.home != query.away, "INVALID_MATCHUP", "Choose two distinct teams")
        before = self._history_cutoff()
        n = int(query.window)
        home = self._history(query.home, query.season, before, n)
        away = self._history(query.away, query.season, before, n)
        h2h = [entry for entry in self._history_rows(query.home, query.season, before, 50)
               if entry[0]["opponent"] == query.away]
        return dict(snapshot_version=self.version, mode=self.mode, season=query.season, window=n,
                    as_of_exclusive=date.fromisoformat(before), home=self._present_history(query.home, query.season, home, n),
                    away=self._present_history(query.away, query.season, away, n), head_to_head=history_summary(h2h),
                    head_to_head_matches=self._trend(h2h))

    def _model_summary(self):
        metric_path = ROOT / "outputs/final_test/final_test_metrics.csv"
        phase7 = []
        with metric_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["model"] == "Linear Regression":
                    phase7.append(dict(label=row["test_split"], source="FBref", fixtures=int(row["n_matches"]),
                                       observations=int(row["n_observations"]), mae=float(row["mae"]), rmse=float(row["rmse"])))
        validation = json.loads((ROOT / "docs/PHASE_8_5_6_VALIDATION.json").read_text(encoding="utf-8"))
        require(validation["artifact_sha256"] == MODEL_SHA256 and validation["production_approved"] is False,
                "INVALID_EVALUATION_REFERENCE", "The validation report does not identify the frozen artifact")
        retrospective = []
        for name, row in validation["cohorts"].items():
            overall = row["metrics"]["overall"]
            retrospective.append(dict(label=name, source=row["label_source"], fixtures=row["scored_fixtures"],
                                      observations=row["scored_team_observations"], mae=overall["lr"]["mae"],
                                      rmse=overall["lr"]["rmse"], baseline_mae=overall["baseline"]["mae"]))
        return dict(self.metadata, phase7=phase7, retrospective=retrospective,
                    scientific_conclusion=validation["scientific_conclusion"],
                    evaluation_notice="Phase 7 FBref and Phase 8.5.6 retrospective cohorts use different periods and labels. "
                                      "Replay uses a strict date cutoff. Historical source availability and prospective accuracy are unverified.")
