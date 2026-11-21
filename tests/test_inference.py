"""Feature parity, replay offline và upcoming fail-safe; lịch 2026 trong fixtures là giả."""

from datetime import datetime,timezone
from contextlib import closing
import json
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from scripts.prepare_training_features import FEATURES,HistoryMedianImputer,ROOT
from scripts.inference.build_fixture_features import build_fixture_features
from scripts.inference.common import HISTORY_PATH,InferenceError,fixture_key
from scripts.inference.history_store import HistoryStore
from scripts.inference.data_refresh import refresh_history
from scripts.inference.predict_fixture import FixturePredictor,predict_fixture
from scripts.inference.verify_inference import verify_parity
from inference_fixtures import MemoryProvider,POLICY,completed_rows,store_fixture


class FixedDatetime(datetime):
    @classmethod
    def now(cls,tz=None):return cls(2026,11,21,12,0,0,tzinfo=timezone.utc)


class InferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot=HistoryStore()
        cls.predictor=FixturePredictor(cls.snapshot)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name)

    def tearDown(self):self.temp.cleanup()

    def upcoming(self,store,**kwargs):
        with patch("scripts.inference.predict_fixture.datetime",FixedDatetime):
            return FixturePredictor(store).predict("Real Madrid","Barcelona","2026-11-28",2026,mode="upcoming",**kwargs)

    def test_full_offline_feature_and_holdout_prediction_parity(self):
        with patch.object(socket.socket,"connect",side_effect=AssertionError("Không được dùng network")):
            audit=verify_parity(self.snapshot)
        self.assertEqual(audit["feature_rows"],4700)
        self.assertEqual(audit["holdout_prediction_rows"],900)
        self.assertLessEqual(audit["feature_max_absolute_delta"],5.1e-9)
        self.assertLessEqual(audit["prediction_max_absolute_delta"],1e-8)
        self.assertTrue(audit["protected_files_unchanged"])

    def test_zero_history_is_nan_then_frozen_median(self):
        fixture=self.snapshot.snapshot_fixture(1)
        built=build_fixture_features(fixture["home_team"],fixture["away_team"],fixture["date"],fixture["season"],self.snapshot)
        self.assertEqual(list(built.X.columns),list(FEATURES))
        self.assertTrue(built.X.matches_seen.eq(0).all())
        self.assertTrue(built.X.short_history.eq(1).all())
        self.assertTrue(built.X[["xg_avg5","opponent_xg_avg5"]].isna().all().all())
        processed=self.predictor.pipeline.named_steps["preprocessing"].transform(built.X)
        self.assertTrue(np.isfinite(processed.to_numpy()).all())
        self.assertEqual(processed.xg_avg5.iloc[0],self.predictor.metadata["imputation_statistics"]["xg_avg5"])

    def test_last_five_full_count_and_independent_opponent_alignment(self):
        store=store_fixture(self.directory/"history.sqlite3")
        built=build_fixture_features("Real Madrid","Barcelona","2026-11-28",2026,store)
        self.assertEqual(built.X.matches_seen.tolist(),[8.,7.])
        self.assertEqual(built.X.short_history.tolist(),[0.,0.])
        self.assertTrue(np.isclose(built.X.xg_avg5.iloc[1],np.mean([.8,1.,1.2,1.4,1.6])))
        np.testing.assert_array_equal(built.X.opponent_matches_seen,built.X.matches_seen.iloc[::-1].to_numpy())
        np.testing.assert_array_equal(built.X.opponent_xg_avg5,built.X.xg_avg5.iloc[::-1].to_numpy())
        self.assertEqual(built.X.is_home.tolist(),[1.,0.])
        self.assertNotEqual(built.X.shot_avg5.iloc[0],built.X.sot_avg5.iloc[0])

    def test_short_history_one_to_four(self):
        store=store_fixture(self.directory/"history.sqlite3")
        built=build_fixture_features("Real Madrid","Barcelona","2026-10-17",2026,store)
        self.assertEqual(built.X.matches_seen.tolist(),[3.,2.])
        self.assertEqual(built.X.short_history.tolist(),[1.,1.])
        self.assertFalse(built.X.isna().any().any())

    def test_home_away_symmetry(self):
        store=store_fixture(self.directory/"history.sqlite3")
        # Hai chiều fixture mùa sau chưa tồn tại: không loại một trận lịch sử đã đá.
        a=build_fixture_features("Real Madrid","Barcelona","2027-08-01",2027,store).X
        b=build_fixture_features("Barcelona","Real Madrid","2027-08-01",2027,store).X
        cols=[c for c in FEATURES if c!="is_home"]
        np.testing.assert_array_equal(a[cols].to_numpy(),b.iloc[::-1][cols].to_numpy())

    def test_season_gap_resets_stint_but_consecutive_seasons_continue(self):
        rows=completed_rows(day="2023-08-20",season=2023,provider_id="old")
        rows+=completed_rows(home="Barcelona",away="Valencia",day="2025-08-20",season=2025,provider_id="promoted")
        path=self.directory/"history.sqlite3"
        refresh_history(MemoryProvider(pd.DataFrame(rows)),path)
        store=HistoryStore(path,provider_policy=POLICY)
        zero=build_fixture_features("Barcelona","Real Madrid","2025-08-01",2025,store)
        self.assertEqual(zero.X.matches_seen.tolist(),[0.,0.])
        new=build_fixture_features("Barcelona","Real Madrid","2025-09-01",2025,store)
        self.assertEqual(new.X.matches_seen.tolist(),[1.,0.])
        continued=build_fixture_features("Barcelona","Real Madrid","2026-08-01",2026,store)
        self.assertEqual(continued.X.matches_seen.tolist(),[1.,0.])

    def test_strict_cutoff_same_day_excluded_and_no_timestamp_semantics_change(self):
        store=store_fixture(self.directory/"history.sqlite3")
        built=build_fixture_features("Real Madrid","Barcelona","2026-11-28",2026,store,prediction_cutoff="2026-10-15")
        self.assertEqual(built.X.matches_seen.tolist(),[2.,1.])
        for audit in built.history.values():
            self.assertLess(audit["last_date"],"2026-10-15")
        with self.assertRaises(InferenceError):build_fixture_features("Real Madrid","Barcelona","2026-11-28",2026,store,temporal_policy="kickoff")
        with self.assertRaises(InferenceError):build_fixture_features("Real Madrid","Barcelona","2026-11-28",2026,store,prediction_cutoff="2026-12-01")

    def test_current_and_future_outcomes_cannot_change_replay(self):
        path=self.directory/"history.sqlite3";shutil.copyfile(HISTORY_PATH,path)
        store=HistoryStore(path)
        predictor=FixturePredictor(store)
        a=predictor.predict("Athletic Club","Getafe","2024-08-15",2024)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("UPDATE team_records SET xg=99999,xga=99999,gf=999,ga=999,sh=999,sot=999 WHERE date>=?",("2024-08-15",))
        b=predictor.predict("Athletic Club","Getafe","2024-08-15",2024)
        self.assertEqual((a["home_xg"],a["away_xg"]),(b["home_xg"],b["away_xg"]))
        self.assertNotIn("actual_xg",b)

    def test_no_fit_or_fit_transform_inside_prediction(self):
        imputer=self.predictor.pipeline.named_steps["preprocessing"].named_steps["median"]
        before=imputer.imputer_.statistics_.copy()
        with patch.object(LinearRegression,"fit",side_effect=AssertionError("fit interdit")),patch.object(HistoryMedianImputer,"fit",side_effect=AssertionError("fit interdit")),patch.object(HistoryMedianImputer,"fit_transform",side_effect=AssertionError("fit_transform interdit")):
            result=self.predictor.predict("Athletic Club","Getafe","2024-08-15",2024)
        self.assertEqual(result["status"],"success")
        np.testing.assert_array_equal(before,imputer.imputer_.statistics_)

    def test_prediction_clipping_and_home_away_alignment(self):
        with patch.object(self.predictor.pipeline,"predict",return_value=np.array([-1.,1.25])):
            result=self.predictor.predict("Athletic Club","Getafe","2024-08-15",2024)
        self.assertEqual(result["home_xg"],0.)
        self.assertEqual(result["away_xg"],1.25)
        self.assertTrue(result["clipping_applied"])
        with patch.object(self.predictor.pipeline,"predict",return_value=np.array([np.inf,1.])):
            result=self.predictor.predict("Athletic Club","Getafe","2024-08-15",2024)
        self.assertEqual(result["error"]["code"],"INVALID_NUMERIC")

    def test_request_errors_are_structured(self):
        cases=[("unknown","Getafe","2024-08-15",2024,"UNKNOWN_TEAM"),
            ("Getafe","Getafe","2024-08-15",2024,"DUPLICATE_TEAM"),
            ("Athletic Club","Getafe","2024-02-30",2024,"INVALID_DATE"),
            ("Athletic Club","Getafe","2024-08-15",2022,"INVALID_SEASON"),
            ("Athletic Club","Getafe","2024-08-16",2024,"INVALID_FIXTURE")]
        for home,away,day,season,code in cases:
            result=self.predictor.predict(home,away,day,season)
            self.assertEqual(result["status"],"error")
            self.assertEqual(result["error"]["code"],code)

    def test_upcoming_stale_snapshot_fails_explicitly(self):
        result=self.upcoming(self.snapshot)
        self.assertEqual(result["status"],"error")
        self.assertEqual(result["error"]["code"],"STALE_DATA")
        self.assertNotIn("home_xg",result)

    def test_upcoming_old_cutoff_cannot_bypass_freshness(self):
        result=self.upcoming(self.snapshot,prediction_cutoff="2025-09-30")
        self.assertEqual(result["error"]["code"],"INVALID_CUTOFF")

    def test_upcoming_global_latest_does_not_hide_stale_team(self):
        from inference_fixtures import rows_fixture
        rows=rows_fixture()
        rows=rows.loc[~rows.provider_match_id.str.startswith("barca-")|rows.provider_match_id.eq("barca-0")].copy()
        rows.loc[rows.provider_match_id.eq("barca-0"),"date"]="2026-09-01"
        path=self.directory/"history.sqlite3"
        refresh_history(MemoryProvider(rows),path)
        result=self.upcoming(HistoryStore(path,provider_policy=POLICY))
        self.assertEqual(result["error"]["code"],"STALE_DATA")
        self.assertEqual(result["error"]["details"]["team"],"Barcelona")

    def test_upcoming_unresolved_previous_fixture_blocks_prediction(self):
        path=self.directory/"history.sqlite3";store=store_fixture(path,with_schedule=True,with_coverage=True)
        pending=dict(provider="test_provider",provider_fixture_id="postponed-test-only",home_team="Barcelona",away_team="Eibar",
            date="2026-11-22",season=2026,status="postponed",quality_status="verified",verified_by="synthetic_test_only",
            fetched_at="2026-11-21T00:00:00+00:00",canonical_key=fixture_key(2026,"Barcelona","Eibar"))
        with closing(sqlite3.connect(path)) as connection,connection:
            connection.execute("INSERT INTO schedule VALUES (?,?,?)",(pending["canonical_key"],"test_provider",json.dumps(pending)))
        self.assertEqual(self.upcoming(store)["error"]["code"],"COVERAGE_UNVERIFIED")

    def test_old_schedule_verification_cannot_claim_current_schedule(self):
        path=self.directory/"history.sqlite3";store=store_fixture(path,with_schedule=True,with_coverage=True)
        row=store.query("SELECT canonical_key,payload FROM schedule")[0]
        value=json.loads(row["payload"]);value["fetched_at"]="2026-10-01T00:00:00+00:00"
        with closing(sqlite3.connect(path)) as connection,connection:
            connection.execute("UPDATE schedule SET payload=? WHERE canonical_key=?",(json.dumps(value),row["canonical_key"]))
        self.assertEqual(self.upcoming(store)["error"]["code"],"FIXTURE_UNVERIFIED")

    def test_old_coverage_review_cannot_claim_current_completeness(self):
        path=self.directory/"history.sqlite3";store=store_fixture(path,with_schedule=True,with_coverage=True)
        value=store.coverage_for("Barcelona",2026);value["reviewed_at"]="2026-10-01T00:00:00+00:00"
        with closing(sqlite3.connect(path)) as connection,connection:
            connection.execute("UPDATE coverage SET payload=? WHERE team=?",(json.dumps(value),"Barcelona"))
        self.assertEqual(self.upcoming(store)["error"]["code"],"COVERAGE_UNVERIFIED")

    def test_upcoming_without_schedule_is_unverified(self):
        result=self.upcoming(store_fixture(self.directory/"history.sqlite3"))
        self.assertEqual(result["error"]["code"],"FIXTURE_UNVERIFIED")

    def test_upcoming_requires_per_team_coverage(self):
        store=store_fixture(self.directory/"history.sqlite3",with_schedule=True)
        self.assertEqual(self.upcoming(store)["error"]["code"],"COVERAGE_UNVERIFIED")

    def test_upcoming_verified_synthetic_success_schema(self):
        store=store_fixture(self.directory/"history.sqlite3",with_schedule=True,with_coverage=True)
        result=self.upcoming(store)
        self.assertEqual(result["status"],"success")
        for field in ["home_xg","away_xg","model_version","data_status","history_cutoff","history_provenance","artifact_sha256"]:
            self.assertIn(field,result)
        self.assertEqual(result["schedule_status"],"verified_scheduled")
        self.assertEqual(result["history_cutoff"],"2026-11-21")

    def test_missing_completed_coverage_match_and_incomplete_stint_fail(self):
        path=self.directory/"history.sqlite3";store=store_fixture(path,with_schedule=True,with_coverage=True)
        with closing(sqlite3.connect(path)) as connection, connection:
            key=fixture_key(2026,"Barcelona","Real Madrid")
            connection.execute("DELETE FROM team_records WHERE canonical_key=?",(key,))
        self.assertEqual(self.upcoming(store)["error"]["code"],"INCOMPLETE_HISTORY")

    def test_cli_and_python_inference_agree_and_no_network_required(self):
        python_result=predict_fixture("Athletic Club","Getafe","2024-08-15",2024,self.snapshot)
        result=subprocess.run([sys.executable,"-m","scripts.inference.predict_fixture","replay","--match-id","1901"],
            cwd=ROOT,capture_output=True,text=True,encoding="utf-8",check=True)
        self.assertEqual(python_result,json.loads(result.stdout))

    def test_read_only_inference_does_not_change_history_or_model(self):
        from scripts.inference.common import MODEL_DIR,sha256
        paths=[HISTORY_PATH,MODEL_DIR/"laliga_lr_pipeline.joblib",MODEL_DIR/"model_metadata.json"]
        before=[sha256(path) for path in paths]
        self.predictor.predict("Athletic Club","Getafe","2024-08-15",2024)
        self.assertEqual(before,[sha256(path) for path in paths])


if __name__=="__main__":unittest.main()
