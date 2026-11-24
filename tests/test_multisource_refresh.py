"""Offline generated fixtures only; no credentials, real source rows or network."""

import copy
from contextlib import closing
from datetime import date, timedelta
from itertools import permutations
import json
from pathlib import Path
import sqlite3
import tempfile
import shutil
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts.inference.common import InferenceError, ROOT, sha256
from scripts.inference.model_artifact import load_trusted_pipeline
from scripts.multisource.composite_history import CompositeHistory, RESEARCH_ROOT, publish_version
from scripts.multisource.composite_inference import CompositePredictor
from scripts.multisource.fixture_catalogue import FIELDS, checked_kickoff, data_status, fixture_catalogue
from scripts.multisource.forecast_eligibility import FIXTURE_MAX_AGE, ForecastEligibility, utc
from scripts.multisource.match_registry import semantic_hash
from scripts.multisource.refresh_composite import main, prepare, publish, review, status
from scripts.multisource.refresh_demo import complete, save_source, synthetic_parent
from scripts.multisource.refresh_validation import read_json, state
from scripts.xpecta_api.schedule_status import schedule_status


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base/"versions"; self.source = self.base/"source"; self.work = self.base/"candidates"
        self.network = patch("socket.socket.connect",side_effect=AssertionError("Network prohibited"))
        self.network.start(); self.addCleanup(self.network.stop)
        self.parent,self.records = synthetic_parent(self.root)
        self.parent_hash = sha256(self.parent.path)

    def prep(self, *, candidate="test", version=None, evidence=True, save=True, as_of="2026-11-22"):
        if save: save_source(self.source,self.records,evidence=evidence)
        return prepare(self.parent,candidate_id=candidate,candidate_version=version or candidate,source_directory=self.source,
                       workspace=self.work,as_of=as_of,dataset_kind="synthetic")

    def bundle(self, candidate="test"):
        return read_json(self.work/candidate/"candidate.json")

    def approve(self, candidate="test", decision="APPROVE"):
        for change in self.bundle(candidate)["changes"]:
            if change["decision"] == "MANUAL_REVIEW":
                review(self.work/candidate,change["change_id"],decision,"Explicit synthetic test review",
                       "synthetic://test-evidence",reviewed_at="2026-11-22T00:00:00Z")

    def published(self, candidate="test"):
        result = publish(self.work/candidate,root=self.root)
        return result,CompositeHistory(self.root/result["published_version"]/"laliga_composite.sqlite3",research_root=self.root)

    def test_local_no_change_no_credentials(self):
        with patch("scripts.multisource.refresh_composite.acquire") as download:
            result = self.prep()
            download.assert_not_called()
        self.assertEqual(result["PUBLISH_STATUS"],"NO_CHANGE")
        self.assertEqual(publish(self.work/"test",root=self.root)["PUBLISH_STATUS"],"NO_CHANGE")
        self.assertEqual(len(list(self.root.glob("*/manifest.json"))),1)

    def test_unchanged_kickoff_requires_matching_review_to_renew(self):
        row = self.records[3]
        row["kickoff_utc"] = row["date"] + "T19:00:00Z"
        self.prep(candidate="scheduled")
        self.approve("scheduled")
        _, self.parent = self.published("scheduled")
        self.assertEqual(self.prep(candidate="redownload", save=False)["PUBLISH_STATUS"], "NO_CHANGE")

        reviewed_at = row["date"] + "T09:00:00Z"
        review_path = self.source / "independent_schedule.json"
        match = dict(season=2026, date=row["date"], home=row["home"], away=row["away"],
                     status="scheduled", source_url="synthetic://official/schedule", kickoff_utc=row["kickoff_utc"])
        invalid = dict(match, kickoff_utc=row["date"] + "T20:00:00Z")
        review_path.write_text(json.dumps(dict(reviewed_at=reviewed_at, matches=[invalid])), encoding="utf-8")
        self.assertEqual(self.prep(candidate="mismatch", save=False)["error"], "SOURCE_CONFLICT")

        review_path.write_text(json.dumps(dict(reviewed_at=reviewed_at, matches=[match])), encoding="utf-8")
        self.assertEqual(self.prep(save=False)["AUTO_ACCEPTED"], 1)
        change, = self.bundle()["changes"]
        self.assertEqual(change["change_type"], ["SCHEDULE_REVERIFIED"])
        self.assertEqual(change["old_values"], change["new_values"])
        self.assertEqual(change["source_provenance"]["schedule_review"]["evidence_sha256"], sha256(review_path))
        _, successor = self.published()
        fixture = next(item for item in fixture_catalogue(successor)
                       if item["canonical_fixture_key"] == change["canonical_fixture_key"])
        engine = ForecastEligibility(synthetic_root=self.root, simulated_clock=lambda: reviewed_at)
        expires = utc(reviewed_at) + FIXTURE_MAX_AGE
        self.assertEqual(schedule_status(engine, successor, [fixture], expires)["recent_review_upcoming_fixtures"], 1)
        stale = schedule_status(engine, successor, [fixture], expires + timedelta(microseconds=1))
        self.assertEqual(stale["recent_review_upcoming_fixtures"], 0)

    def test_download_requires_explicit_opt_in_new_directory(self):
        with patch("scripts.multisource.refresh_composite.acquire",side_effect=ValueError("mocked acquisition")) as download:
            result = prepare(self.parent,candidate_id="download",candidate_version="download",workspace=self.work,
                             source_directory=self.source,download=True,as_of="2026-11-22")
            download.assert_called_once_with(self.work/"download/download")
        self.assertEqual(result["PUBLISH_STATUS"],"BLOCKED")
        self.assertFalse(self.source.exists())
        self.assertEqual(sha256(self.parent.path),self.parent_hash)

    def test_new_verified_completed_auto_accept_and_publish(self):
        complete(self.records[3]); result=self.prep()
        self.assertEqual(result["AUTO_ACCEPTED"],1)
        self.assertEqual(self.bundle()["changes"][0]["change_type"],["NEW_COMPLETED"])
        report,store=self.published()
        self.assertEqual(store.manifest["verified_completed"],self.parent.manifest["verified_completed"]+1)
        self.assertGreater(report["inference_validation"]["success"],0)

    def test_full_time_without_independent_evidence_blocked(self):
        complete(self.records[3]); self.assertEqual(self.prep(evidence=False)["error"],"UNVERIFIED_COMPLETION")

    def test_completed_missing_xg_pending_no_imputation(self):
        complete(self.records[3]); self.records[3]["home_xg"]=None
        result=self.prep(); self.assertEqual(result["PENDING_STATISTICS"],1)
        self.assertEqual(self.bundle()["changes"][0]["change_type"],["NEW_PENDING"])
        _,store=self.published()
        key=self.bundle()["changes"][0]["canonical_fixture_key"]
        self.assertIsNone(store.statistics_for(key,self.records[3]["home"])["xg"])

    def test_pending_statistics_resolved_auto_accept(self):
        self.parent,self.records=synthetic_parent(self.base/"pending",missing=(2026,0))
        self.root=self.base/"pending"; self.records[0]["home_xg"]=self.records[0]["away_xg"]=1.0
        result=self.prep(); self.assertEqual(result["AUTO_ACCEPTED"],1)
        self.assertEqual(self.bundle()["changes"][0]["change_type"],["PENDING_RESOLVED"])
        self.published()

    def test_unreliable_pending_requires_review(self):
        self.parent,self.records=synthetic_parent(self.base/"unreliable",missing=(2026,0),unreliable=True)
        self.root=self.base/"unreliable"; self.records[0]["home_xg"]=self.records[0]["away_xg"]=1.0
        result=self.prep(); self.assertEqual(result["MANUAL_REVIEW_REQUIRED"],1)
        with self.assertRaisesRegex(InferenceError,"unresolved"):publish(self.work/"test",root=self.root)

    def test_xg_correction_needs_approval(self):
        self.records[0]["home_xg"]+=0.25; result=self.prep()
        self.assertEqual(result["MANUAL_REVIEW_REQUIRED"],1)
        with self.assertRaises(InferenceError):publish(self.work/"test",root=self.root)
        self.approve(); self.published()

    def test_sh_sot_corrections_need_review(self):
        self.records[0]["home_shots"]=11; self.records[0]["home_shots_on_target"]=5
        self.assertEqual(self.prep()["MANUAL_REVIEW_REQUIRED"],1)

    def test_score_correction_manual_and_mirrored(self):
        self.records[0]["home_goals"]=3; self.assertEqual(self.prep()["MANUAL_REVIEW_REQUIRED"],1)
        self.assertIn("FINAL_SCORE_CORRECTION",self.bundle()["changes"][0]["change_type"])
        self.approve(); _,store=self.published()
        key=self.bundle()["changes"][0]["canonical_fixture_key"]
        self.assertEqual(store.statistics_for(key,self.records[0]["away"])["ga"],3)

    def test_independent_score_conflict_blocked(self):
        save_source(self.source,self.records)
        path=self.source/"independent_completed.json"; evidence=read_json(path)
        evidence["matches"][0]["home_gf"]=100; path.write_text(json.dumps(evidence),encoding="utf-8")
        self.assertEqual(self.prep(save=False)["error"],"SOURCE_CONFLICT")

    def test_schedule_date_revision_retains_stable_key(self):
        self.records[0]["date"]="2026-06-30"
        self.assertEqual(self.prep()["MANUAL_REVIEW_REQUIRED"],1)
        self.approve(); _,store=self.published()
        self.assertEqual(store.manifest["registry_fixtures"],self.parent.manifest["registry_fixtures"])
        self.assertEqual(self.bundle()["changes"][0]["old_values"]["match_date"],"2026-07-01")

    def test_kickoff_revision_manual_and_null_is_preserved(self):
        self.records[0]["kickoff_utc"]="2026-07-01T20:00:00Z"
        self.assertEqual(self.prep()["MANUAL_REVIEW_REQUIRED"],1)
        self.approve(); _,store=self.published()
        fixtures=fixture_catalogue(store)
        self.assertEqual(sum(r["kickoff_utc"] is not None for r in fixtures),1)

    def test_naive_or_wrong_date_kickoff_rejected(self):
        for value in ("2026-07-01T20:00:00","2026-07-02T00:00:00Z"):
            with self.assertRaises(InferenceError):checked_kickoff(value,"2026-07-01")
        self.assertEqual(checked_kickoff("2026-07-02T01:00:00+02:00","2026-07-01"),"2026-07-01T23:00:00Z")

    def test_duplicate_fixture_blocked(self):
        self.records.append(copy.deepcopy(self.records[0]))
        self.assertEqual(self.prep()["error"],"DUPLICATE_FIXTURE")

    def test_provider_id_reassignment_identity_conflict(self):
        self.records[0]["fixture_id"]=999999
        self.assertEqual(self.prep()["error"],"IDENTITY_CONFLICT")

    def test_home_away_swap_duplicate_or_identity_conflict(self):
        r=self.records[0];r["home"],r["away"]=r["away"],r["home"]
        self.assertIn(self.prep()["error"],{"IDENTITY_CONFLICT","SOURCE_CONFLICT"})

    def test_unknown_provider_blocked(self):
        self.records[0]["source"]="invented"
        self.assertEqual(self.prep()["error"],"SOURCE_CONFLICT")

    def test_own_manifest_hash_mismatch_blocks_parent_unchanged(self):
        save_source(self.source,self.records)
        with (self.source/"raw/synthetic_snapshot.json").open("a") as stream:stream.write(" ")
        self.assertEqual(self.prep(save=False)["error"],"SOURCE_VERSION_MISMATCH")
        self.assertEqual(sha256(self.parent.path),self.parent_hash)

    def test_new_valid_source_hash_is_normal(self):
        save_source(self.source,self.records);old=read_json(self.source/"acquisition_manifest.json")[0]["sha256"]
        complete(self.records[3]); self.prep()
        self.assertNotEqual(old,self.bundle()["source_hashes"]["raw/synthetic_snapshot.json"])
        self.published()

    def test_reviews_bound_to_exact_candidate_hash(self):
        self.records[0]["home_xg"]+=1; self.prep();self.approve()
        reviews=read_json(self.work/"test/reviews.json")
        self.assertEqual(next(iter(reviews.values()))["candidate_content_sha256"],semantic_hash(self.bundle()))
        self.assertEqual(status(self.work/"test")["REVIEW_STATUS"],"SATISFIED")

    def test_changed_source_after_approval_is_stale(self):
        self.records[0]["home_xg"]+=1;self.prep();self.approve()
        self.records[0]["home_xg"]+=1;save_source(self.source,self.records)
        with self.assertRaisesRegex(InferenceError,"changed"):publish(self.work/"test",root=self.root)
        self.assertEqual(status(self.work/"test")["PUBLISH_STATUS"],"BLOCKED")

    def test_tampered_receipt_is_stale_approval(self):
        self.records[0]["home_xg"]+=1;self.prep();self.approve()
        path=self.work/"test/reviews.json";reviews=read_json(path)
        next(iter(reviews.values()))["candidate_content_sha256"]="0"*64;path.write_text(json.dumps(reviews))
        with self.assertRaises(InferenceError) as caught:publish(self.work/"test",root=self.root)
        self.assertEqual(caught.exception.code,"STALE_APPROVAL")

    def test_rejected_or_unresolved_candidate_never_publishes_subset(self):
        self.records[0]["home_xg"]+=1;complete(self.records[3]);self.prep();self.approve(decision="REJECT")
        with self.assertRaises(InferenceError) as caught:publish(self.work/"test",root=self.root)
        self.assertEqual(caught.exception.code,"REVIEW_REJECTED")
        self.assertFalse((self.root/"test").exists())

    def test_partial_build_failure_rolls_back(self):
        complete(self.records[3]);self.prep()
        with self.assertRaisesRegex(ValueError,"integration failed"):
            publish(self.work/"test",root=self.root,validator=lambda *args:(_ for _ in ()).throw(ValueError("integration failed")))
        self.assertFalse((self.root/"test").exists())
        self.assertFalse(list(self.root.glob(".building-*")))
        self.assertEqual(sha256(self.parent.path),self.parent_hash)
        self.published()

    def test_parent_immutable_and_sqlite_integrity(self):
        complete(self.records[3]);self.prep();_,store=self.published()
        self.assertEqual(sha256(self.parent.path),self.parent_hash)
        with closing(sqlite3.connect(store.path.as_uri()+"?mode=ro",uri=True)) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(),[])

    def test_repeated_publish_idempotency(self):
        complete(self.records[3]);self.prep();self.published()
        self.assertEqual(publish(self.work/"test",root=self.root)["PUBLISH_STATUS"],"ALREADY_PUBLISHED")
        self.prep(candidate="repeat",version="another")
        self.assertEqual(publish(self.work/"repeat",root=self.root)["PUBLISH_STATUS"],"ALREADY_PUBLISHED")
        self.assertFalse((self.root/"another").exists())

    def test_metadata_only_change_no_publication(self):
        self.prep(); path=self.source/"acquisition_manifest.json"; entries=read_json(path)
        entries[0]["retrieved_at"]="2026-11-22T01:00:00Z";path.write_text(json.dumps(entries))
        self.assertEqual(self.prep(candidate="metadata",save=False)["CHANGES_FOUND"],0)
        self.assertEqual(publish(self.work/"metadata",root=self.root)["PUBLISH_STATUS"],"NO_CHANGE")

    def test_full_380_catalogue_and_381st_rejected(self):
        from scripts.inference.common import CANONICAL_TEAMS
        self.parent,self.records=synthetic_parent(self.base/"large",clubs=list(CANONICAL_TEAMS[:20]),prior=False,current_completed=0)
        self.root=self.base/"large"
        self.assertEqual(self.prep()["PUBLISH_STATUS"],"NO_CHANGE")
        catalogue=fixture_catalogue(self.parent)
        self.assertEqual(len(catalogue),380)
        self.assertEqual(len({r["canonical_fixture_key"] for r in catalogue}),380)
        self.records.append(copy.deepcopy(self.records[0]))
        self.assertEqual(self.prep(candidate="bad381")["PUBLISH_STATUS"],"BLOCKED")

    def test_missing_actual_last_five_blocks_without_skipping(self):
        parent,records=synthetic_parent(self.base/"inside",current_completed=0,missing=(2025,10))
        first=records[0];result=CompositePredictor(parent).predict(first["home"],first["away"],first["date"],2026)
        self.assertEqual(result["error"]["code"],"MISSING_ROLLING_STATISTICS")

    def test_missing_outside_last_five_counts_without_blocking(self):
        parent,records=synthetic_parent(self.base/"outside",current_completed=0,missing=(2025,0))
        first=records[0];result=CompositePredictor(parent).predict(first["home"],first["away"],first["date"],2026)
        self.assertEqual(result["status"],"success")
        for history in result["history_summary"].values():
            self.assertEqual(history["matches_seen"],6)
            self.assertEqual(len(history["rolling_match_keys"]),5)
            self.assertEqual(len(history["pending_outside_window"]),1)

    def test_target_and_future_excluded_temporal_policy(self):
        first=self.records[0];p=CompositePredictor(self.parent)
        built=p.construct(first["home"],first["away"],first["date"],2026)
        for summary in built.history.values():
            self.assertTrue(summary["last_date"] < first["date"])
        with self.assertRaises(InferenceError):p.construct(first["home"],first["away"],first["date"],2026,prediction_cutoff="2026-07-02")

    def test_future_completion_blocked(self):
        complete(self.records[3]); self.assertEqual(self.prep(as_of="2026-07-03")["error"],"FUTURE_COMPLETION")

    def test_equal_features_frozen_prediction_parity(self):
        complete(self.records[3]);self.prep();report,_=self.published()
        checks=report["inference_validation"]
        self.assertGreater(checks["unchanged_features"],0)
        self.assertLessEqual(max(checks["max_raw_parity_delta"],checks["max_clipped_parity_delta"]),1e-12)

    def test_legitimate_changed_history_changes_predictions(self):
        self.records[0]["home_xg"]+=1;self.prep();self.approve();report,store=self.published()
        self.assertGreater(report["inference_validation"]["changed_features"],0)
        target=self.records[1];args=(target["home"],target["away"],target["date"],2026)
        a=CompositePredictor(self.parent).predict(*args);b=CompositePredictor(store).predict(*args)
        self.assertEqual(a["status"],b["status"])
        self.assertNotEqual(a["features"],b["features"])
        self.assertFalse(np.array_equal(a["raw_predictions"],b["raw_predictions"]))

    def test_read_only_contract_and_production_disabled(self):
        complete(self.records[3]);self.prep();_,store=self.published()
        self.assertTrue(all(set(r)==set(FIELDS) for r in fixture_catalogue(store)))
        self.assertFalse(data_status(store)["production_approved"])
        with self.assertRaises(sqlite3.DatabaseError):store.query("DELETE FROM registry")
        r=self.records[0]
        denied=CompositePredictor(store).predict(r["home"],r["away"],r["date"],2026,mode="PRODUCTION_UPCOMING")
        self.assertEqual(denied["error"]["code"],"PRODUCTION_NOT_APPROVED")

    def test_frozen_artifacts_and_imputer_unchanged(self):
        protected=read_json(ROOT/"outputs/provider_poc/reports/protected_files.json")
        before,_=load_trusted_pipeline();complete(self.records[3]);self.prep();self.published();after,_=load_trusted_pipeline()
        first=before.named_steps["preprocessing"].named_steps["median"]
        second=after.named_steps["preprocessing"].named_steps["median"]
        self.assertEqual(first.n_samples_fit_,3800)
        self.assertEqual(first.n_samples_fit_,second.n_samples_fit_)
        np.testing.assert_array_equal(first.imputer_.statistics_,second.imputer_.statistics_)
        self.assertTrue(all(sha256(ROOT/name)==checksum for name,checksum in protected.items()))

    def test_no_raw_data_in_public_reports_or_tracked_paths(self):
        complete(self.records[3]);report=self.prep()
        self.assertNotIn("registry",report);self.assertNotIn("statistics",report)
        self.assertNotIn("source_directory",report)
        import subprocess
        tracked=subprocess.check_output(["git","ls-files"],cwd=ROOT).decode()
        self.assertNotIn("data/external/multisource/raw/",tracked)
        self.assertNotIn("data/history/research/",tracked)

    def test_negative_fractional_or_impossible_counts_blocked(self):
        for i,value in enumerate([-1,1.5,3]):
            self.records[0]["home_shots"]=value
            result=self.prep(candidate="bad_count_"+str(i))
            self.assertEqual(result["PUBLISH_STATUS"],"BLOCKED")

    def test_source_regressions_cannot_be_approved(self):
        self.records[0]["home_xg"]=None
        self.assertEqual(self.prep()["error"],"STATISTICS_REGRESSION")
        self.assertFalse((self.work/"test/candidate.json").exists())

    def test_candidate_payload_tampering_rejected(self):
        self.prep();path=self.work/"test/candidate.json";bundle=read_json(path)
        bundle["changes"].append({"decision":"AUTO_ACCEPT"});path.write_text(json.dumps(bundle))
        with self.assertRaises(InferenceError):publish(self.work/"test",root=self.root)

    def test_synthetic_cannot_enter_real_history_namespace(self):
        self.prep()
        with self.assertRaises(InferenceError):publish(self.work/"test",root=RESEARCH_ROOT)
        self.assertFalse((RESEARCH_ROOT/"test").exists())

    def test_manifest_path_traversal_and_duplicate_entries_blocked(self):
        save_source(self.source,self.records);path=self.source/"acquisition_manifest.json";items=read_json(path)
        path.write_text(json.dumps(items+items));self.assertEqual(self.prep(save=False)["error"],"INVALID_MANIFEST")
        items[0]["file"]="../source.json";path.write_text(json.dumps(items))
        self.assertEqual(self.prep(candidate="traversal",save=False)["error"],"INVALID_MANIFEST")

    def test_cli_status_and_export_contract(self):
        self.prep()
        with patch("builtins.print"):
            self.assertEqual(main(["status","--candidate",str(self.work/"test")]),0)
            self.assertEqual(main(["export","--database",str(self.parent.path),"--output",str(self.base/"export")]),0)
        status_record=read_json(self.base/"export/data-status.json")
        self.assertIn("build_timestamp",status_record)
        self.assertEqual(status_record["latest_verified_completed_date"],"2026-07-03")
        self.assertEqual(len(read_json(self.base/"export/fixtures.json")["fixtures"]),24)

    def test_pending_resolved_fully_revalidates_mirrors(self):
        self.parent,self.records=synthetic_parent(self.base/"mirrors",missing=(2026,0))
        self.root=self.base/"mirrors";complete(self.records[0],value=1.5);self.prep();_,store=self.published()
        key=self.bundle()["changes"][0]["canonical_fixture_key"]
        home=store.statistics_for(key,self.records[0]["home"]);away=store.statistics_for(key,self.records[0]["away"])
        self.assertEqual(home["xg"],away["xga"])
        self.assertEqual(home["xga"],away["xg"])

    def test_approval_cannot_bypass_invalid_new_statistics(self):
        self.records[0]["home_xg"]+=1;self.prep();self.approve()
        self.records[0]["home_shots_on_target"]=100;save_source(self.source,self.records)
        with self.assertRaises(InferenceError):publish(self.work/"test",root=self.root)
        self.assertEqual(sha256(self.parent.path),self.parent_hash)

    def test_same_team_completed_twice_on_date_is_blocked(self):
        self.records[1]["date"]=self.records[0]["date"]
        self.assertEqual(self.prep()["error"],"AMBIGUOUS_HISTORY")


class ProviderFormatTests(unittest.TestCase):
    """Generated CSVs exercise the same adapter used with private real exports."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.network=patch("socket.socket.connect",side_effect=AssertionError("No network"));self.network.start();self.addCleanup(self.network.stop)
        seed,records=synthetic_parent(self.base/"seed")
        self.original=self.base/"original";self.directory=self.base/"candidate";self.root=self.base/"versions"
        (self.original/"raw").mkdir(parents=True)
        for r in records:r.update(source="Sportmonks",team_xg_source="Sportmonks")
        pd.DataFrame(records).to_csv(self.original/"raw/current_2026_fixtures.csv",index=False)
        clubs=["Barcelona","Real Madrid","Sevilla","Valencia"]
        for season in range(2019,2026):
            fixtures=[];shots=[]
            for i,(home,away) in enumerate(permutations(clubs,2)):
                fixtures.append(dict(provider="Understat",competition="la-liga",season=season,fixture_id=1000+i,understat_id=20000+i,
                    date=(date(season,7,1)+timedelta(days=i)).isoformat(),home=home,away=away,score="2-1",
                    home_xg=float(i+1),away_xg=float(i+1),totals_unreliable=False,
                    home_published_xg=float(i+1),away_published_xg=float(i+1),home_win_probability=0.5,
                    draw_probability=0.25,away_win_probability=0.25,xg_note=None,result_note=None))
                for side in ("h","a"):
                    for j in range(10):shots.append(dict(provider="Understat",competition="la-liga",season=season,
                        fixture_id=1000+i,understat_id=20000+i,shot_id=1+20*i+10*int(side=="a")+j,side=side,
                        result="SavedShot" if j<4 else "MissedShots",situation="OpenPlay",minute=j,player_id=123,
                        player="Synthetic player",x=0.8,y=0.5,understat_xg=0.1,shot_type="RightFoot",
                        assisted_by=None,last_action=None))
            pd.DataFrame(fixtures).to_csv(self.original/f"raw/archive_{season}_fixtures.csv",index=False)
            if season==2025:pd.DataFrame(shots).to_csv(self.original/"raw/archive_2025_shots.csv",index=False)
        save_source(self.base/"evidence",records)
        independent=read_json(self.base/"evidence/independent_completed.json")
        independent["source_url"]="https://www.laliga.com/en-GB/laliga-easports/results"
        (self.original/"independent_completed.json").write_text(json.dumps(independent))
        self.update_manifest(self.original)
        registry,stats,catalogues,_=state(seed)
        # These are distinct provider namespaces, as in the reviewed real export.
        for row in list(registry.fixtures.values())+registry.evidence:
            if row.get("season")==2025:
                row["provider_fixture_id"]=str(20000+int(row["provider_fixture_id"])-1000)
        hashes={"raw/"+e["file"]:e["sha256"] for e in read_json(self.original/"acquisition_manifest.json")}
        self.parent=publish_version(registry,stats,catalogues,version_id="generated_csv_parent",input_hashes=hashes,root=self.root)
        shutil.copytree(self.original,self.directory)
        self.local=patch("scripts.multisource.refresh_validation.LOCAL",self.original);self.local.start();self.addCleanup(self.local.stop)

    def update_manifest(self,directory):
        entries=[]
        for path in sorted((directory/"raw").glob("*.csv")):
            if path.name.startswith("current"):
                url="https://www.xgtables.io/data/v1/la-liga/2026/fixtures.csv"
            else:
                pieces=path.stem.split("_");url=f"https://www.xgtables.io/history/la-liga/{pieces[1]}/{pieces[2]}.csv"
            entries.append(dict(file=path.name,status=200,url=url,retrieved_at="2026-11-22T00:00:00Z",sha256=sha256(path),bytes=path.stat().st_size))
        (directory/"acquisition_manifest.json").write_text(json.dumps(entries))

    def prepare(self):
        self.update_manifest(self.directory)
        return prepare(self.parent,candidate_id="csv",candidate_version="csv",source_directory=self.directory,
                       workspace=self.base/"work",as_of="2026-11-22")

    def alter(self,filename,field,value,index=0):
        path=self.directory/"raw"/filename;frame=pd.read_csv(path);frame.loc[index,field]=value;frame.to_csv(path,index=False)

    def test_generated_csv_baseline_no_change(self):
        self.assertEqual(self.prepare()["PUBLISH_STATUS"],"NO_CHANGE")

    def test_current_csv_new_completion(self):
        path=self.directory/"raw/current_2026_fixtures.csv";frame=pd.read_csv(path)
        raw=frame.iloc[3].to_dict();complete(raw);frame.loc[3]=raw;frame.to_csv(path,index=False)
        evidence=read_json(self.directory/"independent_completed.json")
        evidence["matches"].append(dict(season=2026,date=raw["date"],home=raw["home"],away=raw["away"],home_gf=2,away_gf=1))
        (self.directory/"independent_completed.json").write_text(json.dumps(evidence))
        self.assertEqual(self.prepare()["AUTO_ACCEPTED"],1)
        self.assertEqual(publish(self.base/"work/csv",root=self.root)["PUBLISH_STATUS"],"PUBLISHED")

    def test_archive_xg_correction_manual(self):
        self.alter("archive_2025_fixtures.csv","home_xg",1.25)
        self.assertEqual(self.prepare()["MANUAL_REVIEW_REQUIRED"],1)
        bundle=read_json(self.base/"work/csv/candidate.json")
        change=bundle["changes"][0]
        self.assertIn("STATISTICS_CORRECTION",change["change_type"])
        review(self.base/"work/csv",change["change_id"],"APPROVE","Synthetic CSV correction","synthetic://proof")
        self.assertEqual(publish(self.base/"work/csv",root=self.root)["PUBLISH_STATUS"],"PUBLISHED")

    def test_archive_shot_event_correction_manual(self):
        self.alter("archive_2025_shots.csv","result","SavedShot",index=4)
        self.assertEqual(self.prepare()["MANUAL_REVIEW_REQUIRED"],1)

    def test_archive_missing_side_rejected(self):
        path=self.directory/"raw/archive_2025_shots.csv";frame=pd.read_csv(path)
        frame=frame.loc[~(frame.fixture_id.eq(1000)&frame.side.eq("a"))];frame.to_csv(path,index=False)
        self.assertEqual(self.prepare()["PUBLISH_STATUS"],"BLOCKED")

    def test_older_archive_revision_outside_supported_scope(self):
        self.alter("archive_2024_fixtures.csv","home_xg",1.25)
        self.assertEqual(self.prepare()["error"],"FROZEN_SOURCE_SCOPE")

    def test_current_unreviewed_xg_provider_blocked(self):
        self.alter("current_2026_fixtures.csv","team_xg_source","invented")
        self.assertEqual(self.prepare()["error"],"SOURCE_CONFLICT")

    def test_current_schema_loss_blocked(self):
        path=self.directory/"raw/current_2026_fixtures.csv";frame=pd.read_csv(path)
        frame.drop(columns="away_shots").to_csv(path,index=False)
        self.assertEqual(self.prepare()["error"],"INVALID_SCHEMA")

    def test_current_fixture_count_loss_blocked(self):
        path=self.directory/"raw/current_2026_fixtures.csv";frame=pd.read_csv(path)
        frame.iloc[:-1].to_csv(path,index=False)
        self.assertEqual(self.prepare()["error"],"REGISTRY_COVERAGE_UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
