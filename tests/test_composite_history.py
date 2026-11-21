"""Offline synthetic registry, immutable database, Option B and LR integration."""

import copy
import hashlib
from itertools import permutations
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts.inference.build_fixture_features import build_fixture_features
from scripts.inference.common import HISTORY_PATH, InferenceError, ROOT
from scripts.inference.predict_fixture import FixturePredictor
from scripts.multisource.composite_features import build_composite_features
from scripts.multisource.composite_history import CompositeHistory, publish_version
from scripts.multisource.composite_inference import CompositePredictor
from scripts.multisource.match_registry import (COMPLETE_STATISTICS, PENDING_UPDATE, SOURCE_CONFLICT, UNVERIFIED,
                                               VERIFIED_COMPLETED, MatchRegistry, canonical_key, validate_catalogue)
from scripts.multisource.team_registry import resolve, stable_id
from scripts.prepare_training_features import FEATURES

STAMP="2026-11-22T00:00:00+00:00"
HASH="a"*64
CLUBS=["Barcelona","Real Madrid","Sevilla","Valencia"]


def observation(registry, *, home="Barcelona", away="Real Madrid", day="2025-08-01", season=2025,
                status="completed", verified=True, source="synthetic", version="synthetic-v1", goals=(2,1)):
    return registry.observe(season=season,match_date=day,home_team=home,away_team=away,observed_status=status,
                            evidence_verified=verified,home_goals=goals[0],away_goals=goals[1],verification_source=source,
                            source_version=version,verified_at=STAMP)


def pair_for(fixture, *, value=1.5):
    rows=[]
    for team,opponent,side,other,is_home in [(fixture["home_team"],fixture["away_team"],"home","away",1),
                                           (fixture["away_team"],fixture["home_team"],"away","home",0)]:
        rows.append(dict(canonical_key=fixture["canonical_fixture_key"],season=fixture["season"],date=fixture["match_date"],
                         team=team,opponent=opponent,is_home=is_home,gf=fixture[side+"_goals"],ga=fixture[other+"_goals"],
                         xg=value,xga=value,sh=10,sot=4,fixture_source="synthetic_results",xg_source="synthetic_xg",
                         shots_source="synthetic_shots",source_dataset_version="synthetic-v1",fetched_at=STAMP,
                         statistical_semantics="synthetic_reviewed_test_definition"))
    return rows


def scenario(*, prior=True, missing=None, current_completed=0, ambiguous=False, season_clubs=None):
    registry=MatchRegistry(); rows=[]; rosters={}
    season_clubs=season_clubs or ({2025:CLUBS,2026:CLUBS} if prior else {2026:CLUBS})
    for season,clubs in sorted(season_clubs.items()):
        rosters[season]=clubs
        for i,(home,away) in enumerate(permutations(clubs,2)):
            completed=season<2026 or i<current_completed
            day=f"{season}-08-{i+1:02d}"
            if ambiguous and season<2026 and i==1:day=f"{season}-08-01"
            key=observation(registry,home=home,away=away,day=day,season=season,
                            status="completed" if completed else "scheduled",verified=completed)
            if completed:
                pair=pair_for(registry.fixtures[key],value=float(i+1))
                if season==2025 and missing==i:
                    for row in pair:row["xg"]=row["xga"]=None
                rows.extend(pair)
    statistics={} if not rows else registry.attach_statistics(pd.DataFrame(rows))
    catalogues={s:validate_catalogue(registry,s,clubs,"synthetic_complete_calendar",HASH,STAMP) for s,clubs in rosters.items()}
    return registry,statistics,catalogues


class CompositeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/"versions"
        self.guard=patch("socket.socket.connect",side_effect=AssertionError("Offline tests only"));self.guard.start()
        self.addCleanup(self.guard.stop);self.addCleanup(self.tmp.cleanup)

    def store(self, args=None, version="v1", parent=None):
        registry,statistics,catalogues=args or scenario()
        return publish_version(registry,statistics,catalogues,version_id=version,input_hashes={"synthetic":HASH},root=self.root,parent=parent)

    def test_verified_completed_and_full_statistics_states(self):
        registry=MatchRegistry();key=observation(registry)
        self.assertEqual(registry.fixtures[key]["match_status"],VERIFIED_COMPLETED)
        self.assertEqual(registry.fixtures[key]["statistics_status"],PENDING_UPDATE)
        registry.attach_statistics(pd.DataFrame(pair_for(registry.fixtures[key])))
        self.assertEqual(registry.fixtures[key]["statistics_status"],COMPLETE_STATISTICS)

    def test_completed_with_missing_xg_is_pending_without_zero_fill(self):
        registry=MatchRegistry();key=observation(registry);rows=pair_for(registry.fixtures[key])
        for row in rows:row["xg"]=row["xga"]=None
        statistics=registry.attach_statistics(pd.DataFrame(rows))
        self.assertEqual(registry.fixtures[key]["statistics_status"],PENDING_UPDATE)
        self.assertIsNone(statistics[key][0]["xg"])

    def test_completed_with_missing_sh_or_sot_is_pending(self):
        for field in ["sh","sot"]:
            registry=MatchRegistry();key=observation(registry);rows=pair_for(registry.fixtures[key])
            rows[0][field]=None
            registry.attach_statistics(pd.DataFrame(rows))
            self.assertEqual(registry.fixtures[key]["statistics_status"],PENDING_UPDATE)

    def test_live_scheduled_postponed_are_not_completed(self):
        for status in ["live","scheduled","postponed","cancelled"]:
            registry=MatchRegistry();key=observation(registry,status=status)
            self.assertEqual(registry.fixtures[key]["match_status"],UNVERIFIED)
            self.assertIsNone(registry.fixtures[key]["home_goals"])

    def test_completed_label_without_verification_is_unverified(self):
        registry=MatchRegistry();key=observation(registry,verified=False)
        self.assertEqual(registry.fixtures[key]["match_status"],UNVERIFIED)

    def test_conflicting_final_scores_are_recorded(self):
        registry=MatchRegistry();key=observation(registry)
        observation(registry,source="second",goals=(1,1))
        self.assertEqual(registry.fixtures[key]["match_status"],SOURCE_CONFLICT)
        self.assertEqual(len(registry.conflicts),1)

    def test_date_conflict_uses_same_stable_identity(self):
        registry=MatchRegistry();key=observation(registry)
        observation(registry,source="second",day="2025-08-02")
        self.assertEqual(len(registry.fixtures),1)
        self.assertEqual(registry.fixtures[key]["match_status"],SOURCE_CONFLICT)

    def test_duplicate_source_fixture_rejected(self):
        registry=MatchRegistry();observation(registry)
        with self.assertRaisesRegex(InferenceError,"Duplicate"):observation(registry)

    def test_conflicting_statistics_are_not_selected_by_arrival(self):
        registry=MatchRegistry();key=observation(registry)
        registry.attach_statistics(pd.DataFrame(pair_for(registry.fixtures[key],value=1.5)))
        registry.attach_statistics(pd.DataFrame(pair_for(registry.fixtures[key],value=2.5)))
        self.assertEqual(registry.fixtures[key]["match_status"],VERIFIED_COMPLETED)
        self.assertEqual(registry.fixtures[key]["statistics_status"],SOURCE_CONFLICT)
        self.assertEqual(registry.statistics[key][0]["xg"],1.5)

    def test_missing_provenance_and_invalid_timestamp_rejected(self):
        registry=MatchRegistry();key=observation(registry);rows=pair_for(registry.fixtures[key])
        rows[0]["xg_source"]=""
        with self.assertRaises(InferenceError):registry.attach_statistics(pd.DataFrame(rows))
        with self.assertRaises(InferenceError):
            registry.observe(season=2025,match_date="2025-08-01",home_team="Barcelona",away_team="Sevilla",
                             observed_status="completed",home_goals=1,away_goals=0,evidence_verified=True,
                             verification_source="source",source_version="v1",verified_at="2026-11-22")

    def test_registry_coverage_is_not_inferred_from_rows(self):
        registry,statistics,catalogues=scenario()
        catalogues[2026]["calendar_verified"]=False
        with self.assertRaises(InferenceError):self.store((registry,statistics,catalogues))
        registry.fixtures.pop(next(key for key,row in registry.fixtures.items() if row["season"]==2026))
        with self.assertRaises(InferenceError):validate_catalogue(registry,2026,CLUBS,"source",HASH,STAMP)

    def test_old_missing_outside_last_five_does_not_reduce_matches_seen(self):
        store=self.store(scenario(missing=0))
        built=build_composite_features("Barcelona","Real Madrid","2026-08-01",2026,store)
        self.assertEqual(built.X.matches_seen.tolist(),[6.,6.])
        self.assertEqual(built.X.short_history.tolist(),[0.,0.])
        self.assertEqual(len(built.history["Barcelona"]["rolling_match_keys"]),5)
        self.assertEqual(len(built.history["Barcelona"]["pending_outside_window"]),1)

    def test_missing_inside_actual_window_is_never_skipped(self):
        store=self.store(scenario(missing=9))
        with self.assertRaises(InferenceError) as error:
            build_composite_features("Barcelona","Real Madrid","2026-08-01",2026,store)
        self.assertEqual(error.exception.code,"MISSING_ROLLING_STATISTICS")

    def test_short_history_uses_actual_one_to_four_matches(self):
        store=self.store(scenario(prior=False,current_completed=4))
        built=build_composite_features("Real Madrid","Sevilla","2026-08-05",2026,store)
        self.assertEqual(built.X.matches_seen.tolist(),[2.,1.])
        self.assertEqual(built.X.short_history.tolist(),[1.,1.])
        self.assertEqual(built.X.xg_avg5.iloc[0],2.5)

    def test_short_history_missing_one_of_its_matches_blocks(self):
        registry,statistics,catalogues=scenario(prior=False,current_completed=4)
        key=canonical_key(2026,"Barcelona","Real Madrid")
        registry.fixtures[key]["statistics_status"]=PENDING_UPDATE
        for row in statistics[key]:row["xg"]=row["xga"]=None
        store=self.store((registry,statistics,catalogues))
        with self.assertRaises(InferenceError):build_composite_features("Real Madrid","Sevilla","2026-08-05",2026,store)

    def test_verified_zero_history_preserves_nan_and_fitted_imputer(self):
        store=self.store(scenario(prior=False));predictor=CompositePredictor(store)
        before=predictor.pipeline.named_steps["preprocessing"].named_steps["median"].imputer_.statistics_.copy()
        result=predictor.predict("Barcelona","Real Madrid","2026-08-01",2026)
        self.assertEqual(result["status"],"success")
        self.assertIsNone(result["features"][0]["xg_avg5"])
        self.assertEqual(result["features"][0]["matches_seen"],0.)
        np.testing.assert_array_equal(before,predictor.pipeline.named_steps["preprocessing"].named_steps["median"].imputer_.statistics_)

    def test_unverified_zero_history_is_rejected(self):
        store=self.store(scenario(prior=False))
        with patch.object(store,"assert_coverage",side_effect=InferenceError("REGISTRY_COVERAGE_UNVERIFIED","No proof")):
            result=CompositePredictor(store).predict("Barcelona","Real Madrid","2026-08-01",2026)
        self.assertEqual(result["error"]["code"],"REGISTRY_COVERAGE_UNVERIFIED")

    def test_unknown_old_schedule_blocks_coverage_instead_of_guessing_completion(self):
        store=self.store(scenario(prior=False))
        with self.assertRaises(InferenceError) as error:store.assert_coverage("Barcelona",2026,"2026-08-02")
        self.assertEqual(error.exception.code,"REGISTRY_COVERAGE_UNVERIFIED")

    def test_consecutive_seasons_continue_and_absent_season_resets(self):
        clubs2025=["Barcelona","Real Madrid","Sevilla","Alaves"]
        current=["Valencia","Barcelona","Real Madrid","Sevilla"]
        store=self.store(scenario(season_clubs={2024:CLUBS,2025:clubs2025,2026:current}))
        built=build_composite_features("Valencia","Barcelona","2026-08-01",2026,store)
        self.assertEqual(built.X.matches_seen.tolist(),[0.,12.])
        self.assertEqual(built.history["Valencia"]["stint_start_season"],2026)

    def test_same_day_ambiguous_history_is_rejected(self):
        store=self.store(scenario(ambiguous=True))
        with self.assertRaises(InferenceError) as error:build_composite_features("Barcelona","Real Madrid","2026-08-01",2026,store)
        self.assertEqual(error.exception.code,"AMBIGUOUS_HISTORY")

    def test_current_future_outcomes_do_not_leak(self):
        first=self.store(scenario(),version="v1")
        second=self.store(scenario(current_completed=2),version="v2",parent=first)
        a=build_composite_features("Barcelona","Real Madrid","2026-08-01",2026,first).X
        b=build_composite_features("Barcelona","Real Madrid","2026-08-01",2026,second).X
        pd.testing.assert_frame_equal(a,b)

    def test_future_cutoff_and_wrong_fixture_date_are_rejected(self):
        predictor=CompositePredictor(self.store())
        self.assertEqual(predictor.predict("Barcelona","Real Madrid","2026-08-01",2026,prediction_cutoff="2026-08-02")["error"]["code"],"INVALID_CUTOFF")
        self.assertEqual(predictor.predict("Barcelona","Real Madrid","2026-08-02",2026)["error"]["code"],"INVALID_FIXTURE")

    def test_complete_history_parity_with_original_phase8_builder(self):
        registry,statistics,catalogues=scenario()
        store=self.store((registry,statistics,catalogues))
        rows=pd.DataFrame([r for pair in statistics.values() for r in pair])
        class Adapter:
            def prior_team_records(self,team,season,before_date,exclude_key):
                return rows.loc[rows.team.eq(team)&rows.season.le(season)&rows.date.lt(before_date)]
        original=build_fixture_features("Barcelona","Real Madrid","2026-08-01",2026,Adapter()).X
        actual=build_composite_features("Barcelona","Real Madrid","2026-08-01",2026,store).X
        pd.testing.assert_frame_equal(original,actual)
        self.assertEqual(tuple(actual.columns),FEATURES)
        self.assertEqual(actual.is_home.tolist(),[1.,0.])

    def test_pending_refresh_creates_new_version_and_retains_old_null(self):
        old=self.store(scenario(missing=0),version="v1");before=old.path.read_bytes()
        new=self.store(scenario(),version="v2",parent=old)
        self.assertEqual(old.path.read_bytes(),before)
        self.assertEqual(old.manifest["pending_statistics"],1)
        self.assertEqual(new.manifest["pending_statistics"],0)
        self.assertEqual(new.manifest["revision_counts"]["modified"],1)
        self.assertIsNone(old.statistics_for(canonical_key(2025,"Barcelona","Real Madrid"),"Barcelona")["xg"])

    def test_unchanged_snapshot_has_no_false_source_revisions(self):
        first=self.store(version="v1")
        second=self.store(version="v2",parent=first)
        self.assertEqual(second.manifest["revision_counts"],dict(added=0,modified=0,removed=0))

    def test_existing_version_cannot_be_overwritten_and_store_is_read_only(self):
        store=self.store();before=store.path.read_bytes()
        with self.assertRaises(InferenceError):self.store()
        with self.assertRaises(sqlite3.DatabaseError):store.query("DELETE FROM registry")
        self.assertEqual(store.path.read_bytes(),before)

    def test_read_only_queries_cannot_create_external_databases(self):
        store=self.store();outside=Path(self.tmp.name)/"must_not_exist.sqlite3"
        with self.assertRaises(sqlite3.DatabaseError):store.query("ATTACH DATABASE ? AS outside",(str(outside),))
        self.assertFalse(outside.exists())

    def test_failed_build_rolls_back_without_touching_previous_version(self):
        store=self.store(version="v1");before=store.path.read_bytes()
        with patch("scripts.multisource.composite_history.sqlite3.connect",side_effect=sqlite3.OperationalError("synthetic failure")):
            with self.assertRaises(sqlite3.OperationalError):self.store(version="v2",parent=None)
        self.assertEqual(store.path.read_bytes(),before)
        self.assertFalse((self.root/"v2").exists())
        self.assertFalse(list(self.root.glob(".building-*")))
        self.assertFalse((self.root/".publish.lock").exists())

    def test_failed_parity_validator_does_not_publish_a_version(self):
        old=self.store(version="v1");before=old.path.read_bytes()
        registry,statistics,catalogues=scenario()
        def failed(store):raise InferenceError("PARITY_FAILED","synthetic failure")
        with self.assertRaises(InferenceError):
            publish_version(registry,statistics,catalogues,version_id="v2",input_hashes={"test":HASH},root=self.root,validator=failed)
        self.assertFalse((self.root/"v2").exists())
        self.assertEqual(old.path.read_bytes(),before)

    def test_complete_flags_cannot_hide_missing_actual_statistics(self):
        registry,statistics,catalogues=scenario()
        key=canonical_key(2025,"Barcelona","Real Madrid")
        for row in statistics[key]:row["xg"]=row["xga"]=None
        with self.assertRaisesRegex(InferenceError,"completeness flags"):
            self.store((registry,statistics,catalogues))

    def test_unresolved_score_conflict_blocks_registry_counts(self):
        registry,statistics,catalogues=scenario()
        observation(registry,source="conflicting_source",goals=(3,3))
        catalogues[2025]=validate_catalogue(registry,2025,CLUBS,"synthetic_complete_calendar",HASH,STAMP)
        store=self.store((registry,statistics,catalogues))
        result=CompositePredictor(store).predict("Barcelona","Real Madrid","2026-08-01",2026)
        self.assertEqual(result["error"]["code"],"REGISTRY_COVERAGE_UNVERIFIED")

    def test_database_corruption_is_detected_before_inference(self):
        store=self.store();predictor=CompositePredictor(store)
        with store.path.open("ab") as stream:stream.write(b"corruption")
        self.assertEqual(predictor.predict("Barcelona","Real Madrid","2026-08-01",2026)["error"]["code"],"HISTORY_CORRUPT")

    def test_production_store_paths_and_path_traversal_are_blocked(self):
        with self.assertRaises(InferenceError):CompositeHistory(HISTORY_PATH)
        registry,statistics,catalogues=scenario()
        with self.assertRaises(InferenceError):
            publish_version(registry,statistics,catalogues,version_id="unsafe",input_hashes={"test":HASH},root=HISTORY_PATH.parent)
        with self.assertRaises(InferenceError):self.store(version="../escape")

    def test_research_does_not_bypass_production_gates(self):
        store=self.store()
        with self.assertRaises(InferenceError):FixturePredictor(store)
        result=CompositePredictor(store).predict("Barcelona","Real Madrid","2026-08-01",2026,mode="PRODUCTION_UPCOMING")
        self.assertEqual(result["error"]["code"],"PRODUCTION_NOT_APPROVED")
        self.assertFalse(store.manifest["production_approved"])

    def test_multisource_provenance_and_frozen_imputer_model(self):
        predictor=CompositePredictor(self.store())
        result=predictor.predict("Barcelona","Real Madrid","2026-08-01",2026)
        self.assertEqual(result["target"],"total_team_match_xg")
        self.assertEqual(result["artifact_sha256"],"0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69")
        self.assertEqual(result["home_team_id"],"barcelona")
        self.assertTrue(all(r["xg_source"]=="synthetic_xg" and r["shots_source"]=="synthetic_shots" for r in result["history_provenance"]))
        self.assertFalse(result["production_approved"])
        self.assertEqual(predictor.pipeline.named_steps["preprocessing"].named_steps["median"].n_samples_fit_,3800)

    def test_verified_research_aliases_preserve_existing_identities(self):
        for alias,canonical in [("Málaga CF","Malaga"),("R. Racing Club","Racing Santander"),("RC Deportivo","Deportivo La Coruna")]:
            self.assertEqual(resolve(alias),canonical)
        self.assertEqual(stable_id("FC Barcelona"),"barcelona")
        self.assertEqual(stable_id("RC Deportivo"),"deportivo-la-coruna")
        with self.assertRaises(ValueError):resolve("Racing unreviewed different club")

    def test_all_frozen_files_match_original_manifest(self):
        path=ROOT/"outputs/provider_poc/reports/protected_files.json"
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),"c3747965e7f5e86418236adfc6f2c8d0044e532c3a2fafeb987d2d2dde309cc3")
        for name,expected in json.loads(path.read_text(encoding="utf-8")).items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),expected,name)


if __name__=="__main__":unittest.main()
