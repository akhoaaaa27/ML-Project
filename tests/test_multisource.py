"""Offline synthetic mappings, chronology, coverage and frozen-artifact checks."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts.inference.build_fixture_features import build_fixture_features
from scripts.inference.model_artifact import load_trusted_pipeline
from scripts.multisource.acquire import discover
from scripts.multisource.features import build_features
from scripts.multisource.mapping import (checked_supplement, fixture_identity, mapped_fixture,
                                        reconcile_completion, team_name, understat_shots, validate_staging)
from scripts.multisource.run_audit import CURRENT_FIELDS, inspect_calendar, inspect_file, snapshot_rows
from scripts.prepare_training_features import FEATURES

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = dict(fixture_source="synthetic_results", xg_source="synthetic_xg", shots_source="synthetic_shots",
                  source_dataset_version="synthetic-v1", fetched_at="2026-11-22T00:00:00+00:00",
                  statistical_semantics="synthetic_research_only")


def fixture(day="2025-10-01", home="Barcelona", away="Real Madrid", season=2025, **changes):
    record = dict(date=day, home=home, away=away, home_goals=2, away_goals=1,
                  home_xg=1.85, away_xg=1.2, home_shots=16, away_shots=11,
                  home_shots_on_target=7, away_shots_on_target=4)
    record.update(changes)
    return mapped_fixture(record, CURRENT_FIELDS, season=season, provenance=PROVENANCE)


class MultiSourceTests(unittest.TestCase):
    def setUp(self):
        self.guard = patch("socket.socket.connect", side_effect=AssertionError("Offline tests only"))
        self.guard.start()
        self.addCleanup(self.guard.stop)

    def test_different_column_names_are_not_rejected(self):
        fields = dict(date="Date", home="HomeTeam", away="AwayTeam", home_gf="FTHG", away_gf="FTAG",
                      home_xg="Home_xG", away_xg="Away_xG", home_sh="HS", away_sh="AS", home_sot="HST", away_sot="AST")
        values = ["2025-10-01", "FC Barcelona", "Real Madrid", 2, 1, 1.85, 1.2, 16, 11, 7, 4]
        source = dict(zip(fields.values(), values))
        rows = mapped_fixture(source, fields, season=2025, provenance=PROVENANCE)
        self.assertEqual(rows, fixture())

    def test_home_away_and_derived_xga_ga(self):
        home, away = fixture()
        self.assertEqual((home["gf"], home["ga"], home["xg"], home["xga"], home["sh"], home["sot"]), (2,1,1.85,1.2,16,7))
        self.assertEqual((away["gf"], away["ga"], away["xg"], away["xga"], away["sh"], away["sot"]), (1,2,1.2,1.85,11,4))
        self.assertEqual((home["is_home"], away["is_home"]), (1,0))

    def test_team_aliases_are_explicit_and_accent_insensitive(self):
        for raw, canonical in [(" Atlético de Madrid ", "Atletico Madrid"), ("Deportivo Alavés", "Alaves"),
                               ("Celta de Vigo", "Celta Vigo"), ("Málaga", "Malaga"),
                               ("Deportivo A Coruña", "Deportivo La Coruna"), ("Real Oviedo", "Oviedo")]:
            self.assertEqual(team_name(raw), canonical)
        with self.assertRaisesRegex(ValueError, "Unknown"):
            team_name("unreviewed club")

    def test_season_is_start_year_and_invalid_dates_rejected(self):
        self.assertEqual(fixture_identity(2025,"2026-05-24","Barcelona","Real Madrid")[0],2025)
        for season, day in [(2025,"2027-01-01"),(2026,"2025-08-20"),(2025,"2025-02-30")]:
            with self.assertRaises(ValueError):fixture_identity(season,day,"Barcelona","Real Madrid")

    def test_missing_or_invalid_raw_values_are_not_imputed(self):
        for value in [None, np.nan, np.inf, -1, True]:
            with self.subTest(value=value), self.assertRaises(ValueError):fixture(home_xg=value)
        with self.assertRaises(ValueError):fixture(home_shots=1.5)
        with self.assertRaises(ValueError):fixture(home_shots=2,home_shots_on_target=3)

    def test_provenance_is_required_and_preserved(self):
        rows = fixture()
        for row in rows:
            for key, value in PROVENANCE.items():self.assertEqual(row[key],value)
        record = {value:0 for value in CURRENT_FIELDS.values()}
        for field in PROVENANCE:
            incomplete = dict(PROVENANCE);incomplete.pop(field)
            with self.assertRaisesRegex(ValueError,"provenance"):
                mapped_fixture(record,CURRENT_FIELDS,season=2025,provenance=incomplete)

    def test_duplicate_and_inconsistent_perspectives_rejected(self):
        rows = pd.DataFrame(fixture())
        validate_staging(rows)
        for data in [rows.iloc[:1],pd.concat([rows,rows]),rows.assign(xga=99)]:
            with self.assertRaises(ValueError):validate_staging(data)

    def test_same_fixture_on_different_dates_is_not_a_second_match(self):
        with self.assertRaises(ValueError):
            validate_staging(pd.DataFrame(fixture()+fixture(day="2025-10-02")))

    def test_supplement_matches_identity_not_provider_match_id(self):
        left = pd.DataFrame([dict(season=2025,date="2025-10-01",home="Barcelona",away="Real Madrid",provider_match_id="one",home_gf=2)])
        right = left.assign(provider_match_id="unrelated-id",home_sh=16)
        joined = checked_supplement(left,right)
        self.assertEqual(joined.home_sh.iloc[0],16)
        self.assertEqual(joined.provider_match_id_supplement.iloc[0],"unrelated-id")
        with self.assertRaisesRegex(ValueError,"conflict"):
            checked_supplement(left,right.assign(home_gf=3))
        with self.assertRaisesRegex(ValueError,"Date discrepancy"):
            checked_supplement(left,right.assign(date="2025-10-02"))
        self.assertTrue(checked_supplement(left,right.assign(away="Sevilla")).home_sh.isna().all())

    def test_shot_level_derivation_excludes_penalties_own_goals_and_post(self):
        rows = [dict(fixture_id=1,shot_id=i,side=side,result=outcome,situation=situation)
                for i,(side,outcome,situation) in enumerate([
                    ("h","Goal","OpenPlay"),("h","SavedShot","OpenPlay"),("h","ShotOnPost","OpenPlay"),
                    ("h","BlockedShot","OpenPlay"),("h","Goal","Penalty"),("h","SavedShot","Penalty"),
                    ("h","OwnGoal","OpenPlay"),("a","MissedShots","OpenPlay")])]
        result = understat_shots(pd.DataFrame(rows)).iloc[0]
        self.assertEqual((result.home_sh,result.home_sot,result.away_sh,result.away_sot),(4,2,1,0))
        for bad in [pd.DataFrame(rows).assign(result="unknown"),pd.DataFrame(rows+rows),
                    pd.DataFrame(rows[:-1]),pd.DataFrame(rows).assign(situation=None)]:
            with self.assertRaises(ValueError):understat_shots(bad)

    def test_zero_non_penalty_shots_are_derived_from_known_events(self):
        shots = pd.DataFrame([dict(fixture_id=1,shot_id=i,side=side,result="Goal",situation="Penalty")
                              for i,side in enumerate(["h","a"])])
        self.assertEqual(understat_shots(shots).home_sh.iloc[0],0)

    def test_stale_schedule_requires_independent_completion_and_does_not_fill_stats(self):
        current = pd.DataFrame([dict(date="2026-11-21",home="Barcelona",away="Real Madrid",status="unplayed",
                                     home_goals=np.nan,away_goals=np.nan,home_xg=np.nan)])
        self.assertFalse(reconcile_completion(current,[],season=2026).independently_completed.any())
        evidence = [dict(season=2026,date="2026-11-21",home="Barcelona",away="Real Madrid",home_gf=2,away_gf=1)]
        actual = reconcile_completion(current,evidence,season=2026)
        self.assertTrue(actual.independently_completed.all())
        self.assertTrue(actual.home_xg.isna().all())
        self.assertTrue(actual.home_goals.isna().all())
        for bad in [evidence+evidence,[dict(evidence[0],date="2026-11-20")]]:
            with self.assertRaises(ValueError):reconcile_completion(current,bad,season=2026)
        with self.assertRaisesRegex(ValueError,"score"):
            reconcile_completion(current.assign(status="full_time",home_goals=9,away_goals=9),evidence,season=2026)

    def test_calendar_coverage_does_not_treat_listed_fixtures_as_completed(self):
        calendar = pd.DataFrame([dict(date="2026-08-20",home="Barcelona",away="Real Madrid",status="unplayed"),
                                 dict(date="2027-01-20",home="Real Madrid",away="Barcelona",status="unplayed")])
        self.assertEqual(inspect_calendar(calendar,2026),dict(unique_fixtures=2,clubs=2,full_double_round_robin=True))
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            inspect_calendar(pd.concat([calendar,calendar]),2026)

    def test_shot_inventory_dates_derive_from_matching_fixture_file(self):
        with tempfile.TemporaryDirectory() as temp:
            shot_file = Path(temp)/"archive_2025_shots.csv"
            pd.DataFrame([dict(shot_id=1,fixture_id=7)]).to_csv(shot_file,index=False)
            pd.DataFrame([dict(fixture_id=7,date="2025-10-01",score="2-1")]).to_csv(
                shot_file.with_name("archive_2025_fixtures.csv"),index=False)
            metadata = inspect_file(shot_file,dict(url="https://synthetic.example/shots.csv",retrieved_at="2026-11-22T00:00:00Z"))
            self.assertEqual(metadata["earliest_date"],"2025-10-01")
            self.assertEqual(metadata["completed_fixtures"],1)
            self.assertEqual(metadata["date_basis"],"fixture_id_join_to_same_snapshot_fixture_export")

    def test_acquisition_only_follows_actual_allowed_download_links(self):
        html = '<a href="/history/la-liga/2025/shots.csv">shots</a><a href="https://untrusted.example/data.csv">bad</a>'
        self.assertEqual(discover("https://www.xgtables.io/understat-data/",html),["https://www.xgtables.io/history/la-liga/2025/shots.csv"])
        self.assertEqual(discover("https://www.xgtables.io/understat-data/","no download links"),[])

    def test_rolling_five_and_opponent_features(self):
        history = pd.DataFrame(sum((fixture(day=f"2025-10-{i:02d}",home_xg=i) for i in range(1,7)),[]))
        # Give repeated synthetic pairings distinct keys for independent prior fixtures.
        history["canonical_key"] = [f"synthetic-{i//2}" for i in range(len(history))]
        X,_ = build_features(history,"Barcelona","Real Madrid","2025-10-07",2025)
        self.assertEqual(tuple(X.columns),FEATURES)
        self.assertEqual(X.matches_seen.tolist(),[6.,6.])
        self.assertEqual(X.xg_avg5.iloc[0],4.)
        self.assertEqual(X.opponent_xg_avg5.iloc[1],4.)
        self.assertEqual(X.opponent_xga_avg5.iloc[1],1.2)
        self.assertEqual(X.short_history.tolist(),[0.,0.])

    def test_current_and_future_match_statistics_do_not_leak(self):
        before = pd.DataFrame(fixture())
        X,_ = build_features(before,"Barcelona","Real Madrid","2025-10-02",2025)
        future = pd.DataFrame(fixture(day="2025-10-02",home_xg=999)+fixture(day="2025-10-03",home_xg=999))
        altered = pd.concat([before,future],ignore_index=True)
        pd.testing.assert_frame_equal(X,build_features(altered,"Barcelona","Real Madrid","2025-10-02",2025)[0])

    def test_missing_completed_fixture_blocks_counts_even_outside_last_five(self):
        history = pd.DataFrame(fixture())
        expected = pd.concat([history,pd.DataFrame(fixture(day="2025-10-02",home="Barcelona",away="Sevilla"))])
        with self.assertRaisesRegex(ValueError,"Incomplete team history"):
            build_features(history,"Barcelona","Real Madrid","2025-10-03",2025,expected=expected)

    def test_consecutive_seasons_continue_and_gap_or_new_club_resets(self):
        history = pd.DataFrame(fixture(day="2024-05-01",season=2023))
        # Fixture key changes in a different season; carry consecutive stint.
        continued,_ = build_features(history,"Barcelona","Real Madrid","2024-08-20",2024)
        self.assertEqual(continued.matches_seen.tolist(),[1.,1.])
        reset,_ = build_features(history,"Barcelona","Real Madrid","2025-08-20",2025)
        self.assertEqual(reset.matches_seen.tolist(),[0.,0.])
        promoted,_ = build_features(history,"Málaga","Racing Santander","2026-08-20",2026)
        self.assertTrue(promoted.xg_avg5.isna().all())
        self.assertEqual(promoted.short_history.tolist(),[1.,1.])

    def test_research_features_equal_unchanged_production_builder(self):
        history = snapshot_rows()
        class ReadOnlyAdapter:
            def prior_team_records(self,team,season,before_date,exclude_key):
                return history.loc[history.team.eq(team)&history.season.le(season)&history.date.lt(before_date)]
        actual = build_fixture_features("Barcelona","Real Madrid","2025-09-30",2025,ReadOnlyAdapter()).X
        research,_ = build_features(history,"Barcelona","Real Madrid","2025-09-30",2025)
        pd.testing.assert_frame_equal(actual,research)

    def test_frozen_artifacts_and_existing_research_outputs_unchanged(self):
        path = ROOT/"outputs/provider_poc/reports/protected_files.json"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),"c3747965e7f5e86418236adfc6f2c8d0044e532c3a2fafeb987d2d2dde309cc3")
        for name, expected in json.loads(path.read_text(encoding="utf-8")).items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),expected,name)
        pipeline, metadata = load_trusted_pipeline()
        self.assertEqual(tuple(metadata["features"]),FEATURES)
        self.assertEqual(metadata["artifact_sha256"],"0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69")
        before = copy.deepcopy(pipeline.named_steps["preprocessing"].named_steps["median"].imputer_.statistics_)
        X,_ = build_features(snapshot_rows(),"Barcelona","Real Madrid","2025-09-30",2025)
        self.assertTrue(np.isfinite(pipeline.predict(X)).all())
        np.testing.assert_array_equal(before,pipeline.named_steps["preprocessing"].named_steps["median"].imputer_.statistics_)


if __name__ == "__main__":
    unittest.main()
