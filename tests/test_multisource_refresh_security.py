"""Regression counterexamples for PM854-F01--F04; generated data, offline."""

import copy
import json
import unittest

import pandas as pd

from scripts.inference.common import InferenceError, sha256
from scripts.multisource.composite_history import CompositeHistory, publish_version
from scripts.multisource.fixture_catalogue import fixture_catalogue
from scripts.multisource.refresh_composite import publish, review
from scripts.multisource.refresh_demo import complete
from scripts.multisource.refresh_validation import read_json, state
from tests import test_multisource_refresh as refresh_fixtures


class RefreshSecurityTests(unittest.TestCase):
    def setUp(self):
        # Compose the existing generator without inheriting/recounting its tests.
        self.case=refresh_fixtures.ProviderFormatTests("test_generated_csv_baseline_no_change")
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.parent_sha=sha256(self.case.parent.path)

    def mutate(self, filename, field, value, index=0):
        path=self.case.directory/"raw"/filename;frame=pd.read_csv(path)
        frame[field]=frame[field].astype(object)
        frame.loc[index,field]=value;frame.to_csv(path,index=False)

    def blocked(self, code=None):
        result=self.case.prepare()
        self.assertEqual(result["PUBLISH_STATUS"],"BLOCKED",result)
        if code:self.assertEqual(result["error"],code)
        self.assertFalse((self.case.base/"work/csv/candidate.json").exists())
        self.assertFalse((self.case.root/"csv").exists())
        self.assertEqual(sha256(self.case.parent.path),self.parent_sha)
        return result

    def bundle(self):return read_json(self.case.base/"work/csv/candidate.json")

    def approve_publish(self):
        for change in self.bundle()["changes"]:
            if change["decision"]=="MANUAL_REVIEW":
                review(self.case.base/"work/csv",change["change_id"],"APPROVE","Synthetic regression only","synthetic://proof")
        result=publish(self.case.base/"work/csv",root=self.case.root)
        self.assertEqual(result["PUBLISH_STATUS"],"PUBLISHED")
        return CompositeHistory(self.case.root/"csv/laliga_composite.sqlite3",research_root=self.case.root)

    def frozen_parent(self):
        registry,stats,catalogues,_=state(self.case.parent)
        key="research:laliga:2025:Barcelona:Real Madrid"
        for row in stats[key]:row["fixture_source"]="FBref_frozen_snapshot"
        self.case.parent=publish_version(registry,stats,catalogues,version_id="frozen_parent",
            input_hashes=self.case.parent.manifest["input_hashes"],root=self.case.root,parent=self.case.parent)
        self.parent_sha=sha256(self.case.parent.path)
        return key

    def new_completion(self, *, pending=False):
        path=self.case.directory/"raw/current_2026_fixtures.csv";frame=pd.read_csv(path)
        raw=frame.iloc[3].to_dict();complete(raw)
        if pending:raw["status"]="unplayed";raw["home_xg"]=raw["away_xg"]=None
        frame.loc[3]=raw;frame.to_csv(path,index=False)
        path=self.case.directory/"independent_completed.json";evidence=read_json(path)
        evidence["reviewed_at"]="2026-11-22T03:00:00Z"
        evidence["matches"].append(dict(season=2026,date=raw["date"],home=raw["home"],away=raw["away"],home_gf=2,away_gf=1))
        path.write_text(json.dumps(evidence),encoding="utf-8")
        return raw,path,evidence

    def test_f01_duplicate_archive_fixture_id_blocked(self):
        self.mutate("archive_2025_fixtures.csv","fixture_id",1001);self.blocked("IDENTITY_CONFLICT")

    def test_f01_duplicate_understat_id_blocked(self):
        self.mutate("archive_2025_fixtures.csv","understat_id",20001);self.blocked("IDENTITY_CONFLICT")

    def test_f01_fixture_id_reassigned_with_unique_ids_blocked(self):
        path=self.case.directory/"raw/archive_2025_fixtures.csv";frame=pd.read_csv(path)
        frame.loc[[0,1],"fixture_id"]=[1001,1000];frame.to_csv(path,index=False)
        self.blocked("IDENTITY_CONFLICT")

    def test_f01_understat_reassignment_cannot_be_no_change(self):
        self.mutate("archive_2025_fixtures.csv","understat_id",999999);self.blocked("IDENTITY_CONFLICT")

    def test_f01_wrong_fixture_shot_join_counterexample_blocked(self):
        self.mutate("archive_2025_fixtures.csv","fixture_id",1001)
        self.mutate("archive_2025_shots.csv","result","SavedShot",index=24)
        self.blocked("IDENTITY_CONFLICT")

    def test_f01_invalid_id_on_frozen_fbref_selection_blocked(self):
        self.frozen_parent();self.mutate("archive_2025_fixtures.csv","understat_id",999999)
        self.blocked("IDENTITY_CONFLICT")

    def test_f01_missing_zero_fractional_and_negative_ids_blocked(self):
        for field,value in [("fixture_id",None),("understat_id",0),("fixture_id",1.5),("understat_id",-1)]:
            with self.subTest(field=field,value=value):
                original=pd.read_csv(self.case.directory/"raw/archive_2025_fixtures.csv")
                self.mutate("archive_2025_fixtures.csv",field,value)
                # Separate workspace per case; the source itself remains a fresh candidate.
                result=self.case.prepare();self.assertEqual(result["PUBLISH_STATUS"],"BLOCKED")
                original.to_csv(self.case.directory/"raw/archive_2025_fixtures.csv",index=False)
                self.case.base=self.case.base/"next";self.case.base.mkdir()

    def test_f01_attested_baseline_mismatch_blocked(self):
        path=self.case.original/"raw/archive_2025_fixtures.csv"
        with path.open("a") as stream:stream.write("\n")
        self.blocked("BASELINE_SOURCE_REQUIRED")

    def test_f01_fractional_identity_cannot_round_to_attested_integer(self):
        self.mutate("archive_2025_fixtures.csv","fixture_id","1000.00000000000001")
        self.blocked("IDENTITY_CONFLICT")

    def test_f02_wrong_provider_blocked(self):
        self.mutate("archive_2025_shots.csv","provider","unreviewed_provider");self.blocked("SOURCE_CONFLICT")

    def test_f02_wrong_competition_blocked(self):
        self.mutate("archive_2025_shots.csv","competition","other-league");self.blocked("SOURCE_CONFLICT")

    def test_f02_wrong_season_blocked(self):
        self.mutate("archive_2025_shots.csv","season",2099);self.blocked("SOURCE_CONFLICT")

    def test_f02_unknown_fixture_reference_blocked(self):
        self.mutate("archive_2025_shots.csv","fixture_id",999999);self.blocked("IDENTITY_CONFLICT")

    def test_f02_cross_file_understat_id_mismatch_blocked(self):
        self.mutate("archive_2025_shots.csv","understat_id",20001);self.blocked("IDENTITY_CONFLICT")

    def test_f02_duplicate_shot_id_blocked(self):
        self.mutate("archive_2025_shots.csv","shot_id",2);self.blocked("IDENTITY_CONFLICT")

    def test_f02_invalid_shot_id_blocked(self):
        self.mutate("archive_2025_shots.csv","shot_id",0);self.blocked("IDENTITY_CONFLICT")

    def test_f02_missing_required_metadata_column_blocked(self):
        path=self.case.directory/"raw/archive_2025_shots.csv";frame=pd.read_csv(path)
        frame.drop(columns="understat_id").to_csv(path,index=False);self.blocked("INVALID_SCHEMA")

    def test_f02_complete_reviewed_schema_required(self):
        path=self.case.directory/"raw/archive_2025_shots.csv";frame=pd.read_csv(path)
        frame.drop(columns="last_action").to_csv(path,index=False);self.blocked("INVALID_SCHEMA")

    def test_f02_missing_identity_value_blocked(self):
        self.mutate("archive_2025_shots.csv","understat_id",None);self.blocked("IDENTITY_CONFLICT")

    def test_f02_invalid_scope_with_valid_correction_still_blocked(self):
        self.mutate("archive_2025_fixtures.csv","home_xg",1.25)
        self.mutate("archive_2025_shots.csv","provider","unreviewed_provider");self.blocked("SOURCE_CONFLICT")

    def test_f02_frozen_selection_shots_also_validated(self):
        self.frozen_parent();self.mutate("archive_2025_shots.csv","competition","other-league")
        self.blocked("SOURCE_CONFLICT")

    def test_f02_approval_cannot_override_changed_source_scope(self):
        self.mutate("archive_2025_fixtures.csv","home_xg",1.25)
        self.assertEqual(self.case.prepare()["MANUAL_REVIEW_REQUIRED"],1)
        change=self.bundle()["changes"][0];candidate=self.case.base/"work/csv"
        review(candidate,change["change_id"],"APPROVE","Synthetic regression only","synthetic://proof")
        self.mutate("archive_2025_shots.csv","provider","unreviewed_provider")
        self.case.update_manifest(self.case.directory)
        with self.assertRaises(InferenceError) as caught:publish(candidate,root=self.case.root)
        self.assertEqual(caught.exception.code,"SOURCE_CONFLICT")
        self.assertFalse((self.case.root/"csv").exists())

    def test_f03_new_completion_exact_evidence_tuple_and_separate_csv_provenance(self):
        raw,path,evidence=self.new_completion();result=self.case.prepare()
        self.assertEqual(result["AUTO_ACCEPTED"],1)
        key="research:laliga:2026:Real Madrid:Barcelona";row=self.bundle()["registry"][key]
        self.assertEqual((row["verification_source"],row["source_version"],row["verified_at"]),
            (evidence["source_url"],sha256(path),evidence["reviewed_at"]))
        csv_path=self.case.directory/"raw/current_2026_fixtures.csv"
        provenance=row["fixture_provenance"]
        self.assertEqual(provenance["fixture_source"],"Sportmonks")
        self.assertEqual(provenance["source_dataset_version"],"sha256:"+sha256(csv_path))
        self.assertEqual(provenance["provider_fixture_id"],str(raw["fixture_id"]))
        self.assertEqual(provenance["fetched_at"],"2026-11-22T00:00:00Z")
        review_provenance=self.bundle()["changes"][0]["source_provenance"]
        self.assertEqual((review_provenance["verification_source"],review_provenance["source_version"],
                          review_provenance["verified_at"]),
                         (row["verification_source"],row["source_version"],row["verified_at"]))
        self.assertEqual(review_provenance["fixture_provenance"],provenance)
        stats=self.bundle()["statistics"][key]
        self.assertTrue(all(r["source_dataset_version"]=="sha256:"+sha256(csv_path) for r in stats))
        self.assertTrue(all(r["fetched_at"]==provenance["fetched_at"] for r in stats))
        store=self.approve_publish()
        exported=next(r for r in fixture_catalogue(store) if r["canonical_fixture_key"]==key)
        self.assertEqual((exported["source_provider"],exported["source_version"],exported["verified_at"]),
                         (row["verification_source"],row["source_version"],row["verified_at"]))
        stored=json.loads(store.query("SELECT payload FROM registry WHERE canonical_fixture_key=?",(key,))[0]["payload"])
        self.assertEqual(stored["fixture_provenance"],provenance)

    def test_f03_pending_completion_keeps_evidence_tuple(self):
        _,path,evidence=self.new_completion(pending=True);result=self.case.prepare()
        self.assertEqual(result["PENDING_STATISTICS"],1)
        key="research:laliga:2026:Real Madrid:Barcelona";row=self.bundle()["registry"][key]
        self.assertEqual(row["statistics_status"],"PENDING_UPDATE")
        self.assertEqual(row["source_version"],sha256(path));self.assertEqual(row["verified_at"],evidence["reviewed_at"])
        self.assertTrue(all(r["xg"] is None for r in self.bundle()["statistics"][key]))
        self.approve_publish()

    def test_f03_stale_csv_preserves_previously_verified_completion_and_statistics(self):
        self.mutate("current_2026_fixtures.csv","status","unplayed")
        # Remove fresh independent evidence: the immutable parent is still proof.
        path=self.case.directory/"independent_completed.json";evidence=read_json(path)
        evidence["matches"]=evidence["matches"][1:];path.write_text(json.dumps(evidence))
        self.assertEqual(self.case.prepare()["PUBLISH_STATUS"],"NO_CHANGE")
        old=state(self.case.parent)[0].fixtures;new=self.bundle()["registry"]
        self.assertEqual(new,old)

    def test_f03_new_completion_missing_evidence_blocked(self):
        self.new_completion();path=self.case.directory/"independent_completed.json";evidence=read_json(path)
        evidence["matches"]=evidence["matches"][:-1];path.write_text(json.dumps(evidence))
        self.blocked("UNVERIFIED_COMPLETION")

    def test_f03_independent_score_conflict_blocked(self):
        _,path,evidence=self.new_completion();evidence["matches"][-1]["home_gf"]=99
        path.write_text(json.dumps(evidence));self.blocked("SOURCE_CONFLICT")

    def test_f04_three_component_score_blocked(self):
        self.mutate("archive_2025_fixtures.csv","score","2-1-99");self.blocked("INVALID_SCORE")

    def test_f04_malformed_variants_blocked(self):
        for i,value in enumerate(["2","2-","-1","1--2","abc","1.5-2",None,"NaN","inf-2"," 2-1","2 - 1","+2-1"]):
            with self.subTest(value=value):
                self.mutate("archive_2025_fixtures.csv","score",value)
                result=self.case.prepare();self.assertEqual(result["PUBLISH_STATUS"],"BLOCKED")
                self.assertEqual(result["error"],"INVALID_SCORE")
                self.case.base=self.case.base/str(i);self.case.base.mkdir()

    def test_f04_frozen_selected_malformed_score_blocked(self):
        self.frozen_parent();self.mutate("archive_2025_fixtures.csv","score","2-1-99")
        self.blocked("INVALID_SCORE")

    def test_control_unchanged_and_distinct_provider_id_namespaces(self):
        self.assertEqual(self.case.prepare()["PUBLISH_STATUS"],"NO_CHANGE")
        fixture=pd.read_csv(self.case.directory/"raw/archive_2025_fixtures.csv").iloc[0]
        self.assertNotEqual(fixture.fixture_id,fixture.understat_id)

    def test_control_valid_xg_correction_preserves_frozen_selection_and_publishes(self):
        key=self.frozen_parent();old=copy.deepcopy(state(self.case.parent)[1][key])
        self.mutate("archive_2025_fixtures.csv","home_xg",2.25,index=1)
        self.assertEqual(self.case.prepare()["MANUAL_REVIEW_REQUIRED"],1)
        store=self.approve_publish()
        for r in old:self.assertEqual(store.statistics_for(key,r["team"]),r)

    def test_control_integral_id_serialization_keeps_frozen_identity(self):
        self.frozen_parent();self.mutate("archive_2025_fixtures.csv","fixture_id",1000.0)
        self.assertEqual(self.case.prepare()["PUBLISH_STATUS"],"NO_CHANGE")

    def test_control_valid_shot_correction_requires_review_and_publishes(self):
        self.mutate("archive_2025_shots.csv","result","SavedShot",index=4)
        self.assertEqual(self.case.prepare()["MANUAL_REVIEW_REQUIRED"],1)
        store=self.approve_publish()
        self.assertEqual(store.statistics_for("research:laliga:2025:Barcelona:Real Madrid","Barcelona")["sot"],5)

    def test_control_zero_and_valid_score_corrections(self):
        self.mutate("archive_2025_fixtures.csv","score","0-0")
        self.assertEqual(self.case.prepare()["MANUAL_REVIEW_REQUIRED"],1)
        self.approve_publish()


if __name__=="__main__":unittest.main()
