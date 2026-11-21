"""Validation, idempotency, provenance và rollback cho refresh offline."""

import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import numpy as np
import pandas as pd

from scripts.inference.common import InferenceError,fixture_key
from scripts.inference.data_refresh import CSVProvider,refresh_history,validate_completed_rows
from scripts.inference.history_store import HistoryStore,load_provider_policy
from inference_fixtures import MemoryProvider,completed_rows,rows_fixture,store_fixture


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.directory=Path(self.temp.name)
        self.path=self.directory/"history.sqlite3"
        self.frame=rows_fixture()

    def tearDown(self):self.temp.cleanup()

    def assert_code(self,code,call):
        with self.assertRaises(InferenceError) as found:call()
        self.assertEqual(found.exception.code,code)

    def test_valid_csv_ingestion_and_source_provenance(self):
        csv=self.directory/"history.csv";self.frame.to_csv(csv,index=False)
        result=refresh_history(CSVProvider(csv),self.path,manifest_dir=self.directory/"logs")
        self.assertEqual(result["inserted_matches"],14)
        self.assertEqual(result["source"]["kind"],"local_csv")
        self.assertFalse(result["model_retrained"])
        store=HistoryStore(self.path)
        record=json.loads(store.query("SELECT payload FROM matches LIMIT 1")[0]["payload"])
        for field in ["canonical_key","provider","provider_match_id","fetched_at","statistics_version","quality_status"]:
            self.assertIn(field,record)
        self.assertEqual(len(list((self.directory/"logs").glob("*.json"))),1)

    def test_idempotent_refresh_ignores_new_fetch_timestamp(self):
        refresh_history(MemoryProvider(self.frame),self.path)
        before=HistoryStore(self.path).query("SELECT * FROM matches ORDER BY canonical_key")
        self.frame["fetched_at"]="2026-11-22T00:00:00+00:00"
        result=refresh_history(MemoryProvider(self.frame),self.path)
        self.assertEqual(result["inserted_matches"],0)
        self.assertEqual(result["unchanged_matches"],14)
        self.assertEqual(before,HistoryStore(self.path).query("SELECT * FROM matches ORDER BY canonical_key"))

    def test_invalid_schema_and_unknown_column_rejected(self):
        self.assert_code("INVALID_SCHEMA",lambda:validate_completed_rows(self.frame.drop(columns="xg")))
        self.assert_code("INVALID_SCHEMA",lambda:validate_completed_rows(self.frame.assign(secret_unexpected="not_allowed")))

    def test_missing_xg_nan_and_empty_rejected(self):
        for value in [np.nan,""]:
            bad=self.frame.copy();bad["xg"]=bad.xg.astype(object);bad.loc[0,"xg"]=value
            self.assert_code("MISSING_STATISTICS",lambda:validate_completed_rows(bad))

    def test_invalid_negative_infinite_and_noninteger_numeric(self):
        for column,value in [("xg",-1),("xga",np.inf),("gf",.5),("sot",99),("is_home",2)]:
            bad=self.frame.copy();bad[column]=bad[column].astype(float);bad.loc[0,column]=value
            self.assert_code("INVALID_NUMERIC",lambda:validate_completed_rows(bad))

    def test_duplicate_and_missing_perspective_rejected(self):
        self.assert_code("DUPLICATE_FIXTURE",lambda:validate_completed_rows(pd.concat([self.frame,self.frame.iloc[:1]])))
        self.assert_code("INCOMPLETE_HISTORY",lambda:validate_completed_rows(self.frame.iloc[1:]))

    def test_pair_goals_xg_and_team_identity_consistency(self):
        for column,value,code in [("ga",5,"INCONSISTENT_PAIR"),("xga",5.,"INCONSISTENT_PAIR"),
                                  ("opponent","Getafe","INVALID_FIXTURE")]:
            bad=self.frame.copy();bad.loc[0,column]=value
            self.assert_code(code,lambda:validate_completed_rows(bad))

    def test_team_aliases_and_provider_id_not_legacy_id(self):
        rows=pd.DataFrame(completed_rows(home="Atletico Madrid",away="Alaves",provider_id="external-123"))
        rows.loc[0,"team"]="Atlético Madrid";rows.loc[1,"opponent"]="Atlético Madrid"
        records=validate_completed_rows(rows)
        self.assertEqual(records[0]["home_team"],"Atletico Madrid")
        self.assertEqual(records[0]["provider_match_id"],"external-123")
        self.assertTrue(records[0]["canonical_key"].startswith("laliga:2026:"))

    def test_new_provider_requires_separate_store_and_review(self):
        refresh_history(MemoryProvider(self.frame),self.path)
        changed=self.frame.copy();changed["provider"]="other_xg_model"
        self.assert_code("INCOMPATIBLE_PROVIDER",lambda:refresh_history(MemoryProvider(changed),self.path))
        store=HistoryStore(self.path)
        self.assert_code("UNSUPPORTED_PROVIDER",lambda:store.check_provider("upcoming"))
        bad_policy=self.directory/"policy.json";bad_policy.write_text('{"other":{"production_approved":true}}')
        self.assert_code("INCOMPATIBLE_PROVIDER",lambda:load_provider_policy(bad_policy))

    def test_changed_completed_outcome_or_version_needs_review(self):
        refresh_history(MemoryProvider(self.frame),self.path)
        for column in ["statistics_version","xg"]:
            bad=self.frame.copy()
            if column=="statistics_version":bad[column]="corrected-version"
            else:
                bad.loc[0,"xg"]=2.5;bad.loc[1,"xga"]=2.5
            self.assert_code("CORRECTION_REQUIRES_REVIEW",lambda:refresh_history(MemoryProvider(bad),self.path))
        self.assertEqual(HistoryStore(self.path).query("SELECT COUNT(*) n FROM matches")[0]["n"],14)

    def test_failure_after_partial_insert_rolls_back_all_new_fixtures(self):
        refresh_history(MemoryProvider(self.frame),self.path)
        before=HistoryStore(self.path).query("SELECT * FROM matches ORDER BY canonical_key")
        new=pd.DataFrame(completed_rows(home="Alaves",away="Eibar",day="2026-10-01",provider_id="000-new"))
        bad=self.frame.copy();bad.loc[0,"xg"]=9.;bad.loc[1,"xga"]=9.
        mixed=pd.concat([new,bad],ignore_index=True)
        self.assert_code("CORRECTION_REQUIRES_REVIEW",lambda:refresh_history(MemoryProvider(mixed),self.path,manifest_dir=self.directory/"logs"))
        after=HistoryStore(self.path).query("SELECT * FROM matches ORDER BY canonical_key")
        self.assertEqual(before,after)
        manifest=json.loads(next((self.directory/"logs").glob("*.json")).read_text(encoding="utf-8"))
        self.assertTrue(manifest["transaction_rolled_back"])
        self.assertEqual(manifest["inserted_matches"],0)

    def test_bad_coverage_rolls_back_schedule_and_history(self):
        bad=[dict(team="Barcelona",season=2026,stint_start_season=2026,provider="test_provider",
            verified_through="2026-11-20",eligible_match_keys=["missing:key"],verified_by="test",
            reviewed_at="2026-11-21T00:00:00+00:00")]
        self.assert_code("INCOMPLETE_HISTORY",lambda:refresh_history(MemoryProvider(self.frame),self.path,coverage=bad))
        self.assertEqual(HistoryStore(self.path).query("SELECT COUNT(*) n FROM matches")[0]["n"],0)

    def test_schedule_is_separate_from_completed_history(self):
        store=store_fixture(self.path,with_schedule=True,with_coverage=True)
        target=store.schedule_fixture("Real Madrid","Barcelona","2026-11-28",2026)
        self.assertEqual(target["provider_fixture_id"],"future-test-only")
        self.assertEqual(store.query("SELECT COUNT(*) n FROM matches")[0]["n"],14)
        self.assertEqual(store.coverage_for("Barcelona",2026)["verified_through"],"2026-11-20")

    def test_reject_noncompleted_or_unverified_records_and_naive_timestamp(self):
        for column,value,code in [("status","scheduled","INVALID_HISTORY"),("quality_status","unknown","INVALID_HISTORY"),
                                  ("fetched_at","2026-11-21T00:00:00","INVALID_SCHEMA")]:
            bad=self.frame.copy();bad[column]=value
            self.assert_code(code,lambda:validate_completed_rows(bad))


if __name__=="__main__":unittest.main()
