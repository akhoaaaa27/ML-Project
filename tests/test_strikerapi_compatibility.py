"""Audit source differences, offline planning, mock workflow và preservation."""

import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts.inference.common import ROOT
from scripts.inference.data_refresh import refresh_history
from scripts.inference.history_store import HistoryStore
from scripts.data_provider.compatibility_audit import compare_sample,run_poc
from scripts.data_provider.normalize_strikerapi import normalize_game
from scripts.data_provider.sample_selector import select_reference,expanded_plan,discovery_params
from scripts.data_provider.strikerapi_client import POCError,StrikerAPIClient,POC_DIR
from strikerapi_fixtures import REFERENCE,TEST_CREDENTIAL,game_fixture,listing_fixture,mock_response,session_fixture,shot_fixture


def fbref_fixture():
    return pd.DataFrame(dict(match_id=[99,99],season=[2023,2023],date=["2023-10-28"]*2,
        team=["Barcelona","Real Madrid"],opponent=["Real Madrid","Barcelona"],is_home=[1,0],
        gf=[1,2],ga=[2,1],xg=[1.2,1.4],xga=[1.4,1.2],sh=[3,4],sot=[2,3]))


class StrikerAPICompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)

    def tearDown(self):self.tmp.cleanup()

    def normalized(self):
        table,_=normalize_game(game_fixture(),REFERENCE,provider_game_id="synthetic-game",fetched_at="2026-11-21T00:00:00+00:00")
        return table

    def test_compatibility_metrics_are_source_differences_not_prediction_mae(self):
        rows,summary=compare_sample(self.normalized(),REFERENCE,fbref_fixture())
        np.testing.assert_allclose(rows.xg_difference,[-.2,.1],atol=1e-15)
        self.assertAlmostEqual(summary["xg_mean_absolute_difference"],.15)
        self.assertAlmostEqual(summary["xg_mean_signed_difference"],-.05)
        self.assertAlmostEqual(summary["xg_max_absolute_difference"],.2)
        self.assertEqual(summary["goals_exact_agreement_rate"],1.)
        self.assertEqual(summary["shots_exact_agreement_rate"],.5)
        self.assertEqual(summary["shots_on_target_exact_agreement_rate"],.5)
        self.assertFalse(summary["population_compatibility_established"])
        self.assertTrue(summary["metric_is_source_difference_not_model_prediction_mae"])

    def test_wrong_identity_duplicate_or_missing_row_rejected(self):
        for mode in ["identity","duplicate","missing"]:
            table=self.normalized()
            if mode=="identity":table["date"]="2023-10-29"
            elif mode=="duplicate":table=pd.concat([table,table.iloc[:1]])
            else:table=table.iloc[:1]
            with self.assertRaises(ValueError):compare_sample(table,REFERENCE,fbref_fixture())

    def test_one_development_match_and_expanded_plan_deterministic(self):
        reference=select_reference()
        self.assertEqual(reference["season"],2023)
        self.assertEqual(reference["local_match_id"],1521)
        self.assertEqual(discovery_params(reference)["league"],"laliga")
        one,two=expanded_plan(),expanded_plan()
        pd.testing.assert_frame_equal(one,two)
        self.assertEqual(len(one),24);self.assertTrue(one.season.between(2019,2023).all())
        self.assertEqual(one.xg_range.nunique(),3);self.assertEqual(one.season.nunique(),5)
        self.assertFalse(one.local_match_id.duplicated().any())

    def test_dry_run_full_workflow_has_zero_network_and_cost(self):
        with patch("requests.Session.get",side_effect=AssertionError("Network interdit")),patch("requests.Session.post",side_effect=AssertionError("Credits interdit")):
            report=run_poc(output_dir=self.path)
        self.assertEqual(report["status"],"dry_run")
        self.assertEqual(report["billable_posts_this_run"],0)
        self.assertEqual(report["cumulative_conservative_reserved_credits"],0)
        self.assertEqual([step["cumulative_estimated_max"] for step in report["plan"]],[2,7,17])
        self.assertFalse(report["real_sample_collected"])

    def test_mocked_full_flow_skips_unnecessary_shot_map_and_reuses_cache(self):
        (self.path/".env").write_text("STRIKERAPI_API_KEY="+TEST_CREDENTIAL)
        session=session_fixture();session.post.side_effect=[mock_response({"data":listing_fixture()}),mock_response({"data":game_fixture()})]
        def client_factory(**kwargs):return StrikerAPIClient(**kwargs,root=self.path,session=session,logger=lambda event:None)
        with patch.dict(os.environ,{"STRIKERAPI_API_KEY":TEST_CREDENTIAL}),patch("scripts.data_provider.compatibility_audit.load_dataset",return_value=fbref_fixture()), \
                patch("scripts.data_provider.compatibility_audit.StrikerAPIClient",side_effect=client_factory):
            report=run_poc(execute=True,output_dir=self.path/"out")
            again=run_poc(execute=True,max_credits=0,output_dir=self.path/"out")
        self.assertEqual(session.post.call_count,2)
        self.assertEqual(report["cumulative_conservative_reserved_credits"],7)
        self.assertEqual(again["billable_posts_this_run"],0)
        self.assertEqual(len(list((self.path/"out/comparisons").glob("*.csv"))),1)
        self.assertFalse(report["production_approved"])

    def test_mocked_fallback_cost_is_exactly_17_and_shot_map_is_conditional(self):
        game=game_fixture();game["team_stats"][0]["xg"]=None
        session=session_fixture();session.post.side_effect=[mock_response({"data":listing_fixture()}),mock_response({"data":game}),mock_response({"data":shot_fixture()})]
        def factory(**kwargs):return StrikerAPIClient(**kwargs,root=self.path,session=session,logger=lambda event:None)
        with patch.dict(os.environ,{"STRIKERAPI_API_KEY":TEST_CREDENTIAL}),patch("scripts.data_provider.compatibility_audit.load_dataset",return_value=fbref_fixture()), \
                patch("scripts.data_provider.compatibility_audit.StrikerAPIClient",side_effect=factory):
            report=run_poc(execute=True,output_dir=self.path/"out")
        self.assertEqual(report["cumulative_conservative_reserved_credits"],17)
        self.assertEqual(session.post.call_count,3)
        self.assertEqual(report["normalization"]["xg_source"],"raw_shot_aggregation_both_teams")

    def test_incomplete_sample_does_not_export_import_ready_csv(self):
        game=game_fixture();game["team_stats"][0]["shots_on_target"]=None
        session=session_fixture();session.post.side_effect=[mock_response({"data":listing_fixture()}),mock_response({"data":game})]
        def factory(**kwargs):return StrikerAPIClient(**kwargs,root=self.path,session=session,logger=lambda event:None)
        with patch.dict(os.environ,{"STRIKERAPI_API_KEY":TEST_CREDENTIAL}),patch("scripts.data_provider.compatibility_audit.load_dataset",return_value=fbref_fixture()), \
                patch("scripts.data_provider.compatibility_audit.StrikerAPIClient",side_effect=factory):
            report=run_poc(execute=True,output_dir=self.path/"out")
        self.assertEqual(report["status"],"sample_incomplete")
        self.assertEqual(session.post.call_count,2)
        self.assertFalse(list((self.path/"out/samples").glob("*_team_matches.csv")))

    def test_valid_adapter_can_import_to_temporary_separate_staging(self):
        table=self.normalized()
        class SampleProvider:
            def fetch_completed(self):return table.copy()
            def source_identity(self):return dict(kind="synthetic_unit_test_only")
        path=self.path/"strikerapi_staging.sqlite3"
        result=refresh_history(SampleProvider(),path)
        self.assertEqual(result["inserted_matches"],1)
        store=HistoryStore(path)
        self.assertEqual(store.provider(),"strikerapi")
        with self.assertRaises(ValueError):store.check_provider("upcoming")

    def test_all_frozen_phase8_files_remain_byte_identical(self):
        hashes=json.loads((POC_DIR/"reports/protected_files.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(hashes),107)
        for name,expected in hashes.items():self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),expected,name)

    def test_gitignore_protects_private_data_but_not_example_or_summary(self):
        for name in [".env","outputs/provider_poc/raw/response.json","outputs/provider_poc/logs/debug.log","outputs/provider_poc/staging/test.sqlite3"]:
            self.assertEqual(subprocess.run(["git","check-ignore","-q","--",name],cwd=ROOT).returncode,0,name)
        for name in [".env.example","outputs/provider_poc/reports/poc_summary.json"]:
            self.assertNotEqual(subprocess.run(["git","check-ignore","-q","--",name],cwd=ROOT).returncode,0,name)


if __name__=="__main__":unittest.main()
