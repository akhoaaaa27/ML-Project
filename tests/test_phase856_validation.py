"""Synthetic checks only. These fixtures cannot supply real-data error evidence."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts.inference.common import InferenceError, MODEL_DIR, sha256
from scripts.multisource.composite_history import publish_version
from scripts.multisource.composite_inference import CompositePredictor
from scripts.multisource.forecast_examples import synthetic_snapshot
from scripts.multisource.phase856_reporting import summarize_cohort
from scripts.multisource.phase856_validation import COHORTS, Cohort, error_metrics, pair_overlap, paired_statistics, replay_cohort, summarize_scores
from scripts.multisource.refresh_validation import state


KEY = "research:laliga:2025:Barcelona:Real Madrid"


def paired_input():
    home=dict(season=2025,date="2025-08-01",team="Barcelona",opponent="Real Madrid",is_home=1,
              gf=2,ga=1,xg=1.3,xga=0.6,sh=10,sot=3,canonical_key=KEY)
    away=dict(home,team="Real Madrid",opponent="Barcelona",is_home=0,gf=1,ga=2,xg=0.6,xga=1.3,sh=5,sot=2)
    archive = pd.DataFrame([dict(provider="Understat",competition="la-liga",season=2025,date="2025-08-01",
        home="Barcelona",away="Real Madrid",fixture_id=9087,understat_id=192,score="2-1",
        home_xg=1.8,away_xg=0.4,totals_unreliable=False)])
    return pd.DataFrame([away,home]), {2025:archive}


class OverlapTests(unittest.TestCase):
    def test_identity_and_home_away_paired_without_shared_provider_id(self):
        ref,archives=paired_input()
        rows=pair_overlap(ref,archives)
        self.assertTrue(all(row["matched"] for row in rows))
        self.assertEqual([(r["perspective"],r["external_xg"]) for r in rows],[("home",1.8),("away",0.4)])

    def test_duplicate_archive_identity_is_rejected(self):
        ref,archives=paired_input()
        original=archives[2025]
        archives[2025]=pd.concat([original,original.assign(fixture_id=9088,understat_id=193)])
        with self.assertRaises(InferenceError) as error:pair_overlap(ref,archives)
        self.assertEqual(error.exception.code,"DUPLICATE_OVERLAP")

    def test_date_and_score_mismatch_are_rejected(self):
        for field,value in (("date","2025-08-02"),("score","1-2")):
            with self.subTest(field=field):
                ref,archives=paired_input()
                archives[2025].loc[0,field]=value
                with self.assertRaises(InferenceError) as error:pair_overlap(ref,archives)
                self.assertEqual(error.exception.code,"OVERLAP_IDENTITY_MISMATCH")

    def test_signed_provider_difference_and_distribution(self):
        results=paired_statistics(pair_overlap(*paired_input()),"xg")
        self.assertEqual(results["paired"],2)
        self.assertAlmostEqual(results["signed_difference"]["mean"],0.15)
        self.assertAlmostEqual(results["absolute_difference"]["mean"],0.35)
        self.assertAlmostEqual(results["absolute_difference"]["quantiles"]["0.5"],0.35)
        self.assertAlmostEqual(results["pearson_r"],1)

    def test_missing_shots_are_never_created_and_available_counts_are_paired(self):
        ref,archives=paired_input()
        missing=paired_statistics(pair_overlap(ref,archives),"sh")
        self.assertEqual(missing["exclusions"],{"NO_REVIEWED_SHOT_EVENT_COVERAGE":2})
        self.assertIsNone(missing["signed_difference"]["mean"])
        counts=pd.DataFrame([dict(fixture_id=9087,home_sh=8,away_sh=6,home_sot=3,away_sot=1)])
        paired=paired_statistics(pair_overlap(ref,archives,shot_totals=counts),"sh")
        self.assertEqual(paired["paired"],2)
        self.assertEqual(paired["signed_difference"]["mean"],-0.5)

    def test_missing_label_and_provider_flag_have_separate_counts(self):
        ref,archives=paired_input()
        archives[2025].loc[0,"away_xg"]=np.nan
        result=paired_statistics(pair_overlap(ref,archives),"xg")
        self.assertEqual(result["exclusions"],{"MISSING_EXTERNAL_XG":1})
        self.assertEqual(result["missing_observations"],1)
        archives[2025].loc[0,"totals_unreliable"]=True
        flagged=paired_statistics(pair_overlap(ref,archives),"xg")
        self.assertEqual(flagged["exclusions"],{"PROVIDER_FLAGGED_UNRELIABLE":2})
        self.assertEqual(flagged["missing_observations"],1)


class ReplayTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.parent=synthetic_snapshot(self.root,"parent",pending={(2026,5)})
        self.cohort=Cohort("only_synthetic",2026,"synthetic","2025-09-30")
        self.predictor=CompositePredictor(self.parent)

    def evaluate(self, store=None, cohort=None):
        return replay_cohort(store or self.parent,CompositePredictor(store) if store else self.predictor,cohort or self.cohort)

    def test_completed_selection_and_missing_target_xg_denominator(self):
        report=summarize_cohort(self.evaluate())
        self.assertEqual((report["candidate_fixtures"],report["verified_completed"]),(12,6))
        self.assertEqual(report["exclusions"]["EXCLUDED"],{"MISSING_TARGET_XG":1,"NOT_VERIFIED_COMPLETED":6})
        self.assertEqual(report["scored_team_observations"],10)

    def test_history_cutoff_and_correct_target_side_alignment(self):
        report=self.evaluate()
        dates={r["canonical_fixture_key"]:r["match_date"] for r in self.parent.query("SELECT * FROM registry")}
        for pair in report["fixture_scores"]:
            self.assertEqual([r["features"]["is_home"] for r in pair],[1,0])
            self.assertEqual([r["perspective"] for r in pair],["home","away"])
            for row in pair:
                self.assertTrue(all(dates[p["canonical_fixture_key"]]<dates[row["key"]] for p in row["window"]))

    def test_target_label_change_does_not_change_target_prediction_or_features(self):
        original=self.evaluate()
        key=original["fixture_scores"][0][0]["key"]
        registry,stats,catalogues,_=state(self.parent)
        for row in stats[key]:
            row["xg"]+=2;row["xga"]+=2
        changed=publish_version(registry,stats,catalogues,version_id="labels",input_hashes={"synthetic":"1"*64},
                                root=self.root,parent=self.parent,identity_review={"dataset_kind":"synthetic"})
        pair1=next(p for p in original["fixture_scores"] if p[0]["key"]==key)
        pair2=next(p for p in self.evaluate(changed)["fixture_scores"] if p[0]["key"]==key)
        for a,b in zip(pair1,pair2):
            self.assertNotEqual(a["actual"],b["actual"])
            self.assertEqual((a["features"],a["raw_prediction"],a["baseline"]),(b["features"],b["raw_prediction"],b["baseline"]))

    def test_pending_actual_last_five_blocks_downstream_result(self):
        snapshot=synthetic_snapshot(self.root,"pending",pending={(2026,0)})
        report=summarize_cohort(self.evaluate(snapshot))
        self.assertGreater(report["exclusions"]["BLOCKED"]["MISSING_ROLLING_STATISTICS"],0)
        self.assertEqual(report["exclusions"]["EXCLUDED"]["MISSING_TARGET_XG"],1)

    def test_b1_and_b2_metrics_use_separate_targets_and_provenance(self):
        registry,stats,catalogues,_=state(self.parent)
        for records in stats.values():
            for row in records:
                row["xg_source"]="Understat" if row["season"]==2025 else "Sportmonks"
        store=publish_version(registry,stats,catalogues,version_id="label_sources",input_hashes={"synthetic":"2"*64},
                              root=self.root,identity_review={"dataset_kind":"synthetic"})
        a,b=[summarize_cohort(self.evaluate(store,cohort)) for cohort in COHORTS]
        self.assertEqual((a["label_source"],b["label_source"]),("Understat","Sportmonks"))
        self.assertEqual((a["scored_team_observations"],b["scored_team_observations"]),(24,10))
        self.assertNotEqual(a["metrics"]["overall"]["lr"]["mae"],b["metrics"]["overall"]["lr"]["mae"])

    def test_baseline_reuses_frozen_transform_and_pairs_exactly_same_rows(self):
        detail=self.evaluate()
        for pair in detail["fixture_scores"]:
            x=pd.DataFrame([r["features"] for r in pair],dtype=float)
            expected=self.predictor.pipeline.named_steps["preprocessing"].transform(x)["xg_avg5"].tolist()
            self.assertEqual([r["baseline"] for r in pair],expected)
        metrics=summarize_scores(detail["fixture_scores"])["overall"]
        self.assertEqual(metrics["lr"]["n"],metrics["baseline"]["n"])
        self.assertAlmostEqual(metrics["lr_minus_baseline_mae"],metrics["lr"]["mae"]-metrics["baseline"]["mae"])

    def test_summary_is_deterministic_and_residual_has_correct_sign(self):
        detail=self.evaluate()
        self.assertEqual(summarize_cohort(detail),summarize_cohort(detail))
        metrics=error_metrics([1,3],[2,1])
        self.assertEqual(metrics["mean_signed_residual"],-0.5)
        self.assertEqual(metrics["mae"],1.5)
        self.assertAlmostEqual(metrics["rmse"],np.sqrt(2.5))

    def test_phase_856_keeps_snapshot_and_fitted_artifact_read_only(self):
        paths=(self.parent.path,MODEL_DIR/"laliga_lr_pipeline.joblib",MODEL_DIR/"model_metadata.json")
        before=[sha256(p) for p in paths]
        with patch.object(self.predictor.pipeline,"fit",side_effect=AssertionError("retraining forbidden")):
            self.evaluate()
        self.assertEqual([sha256(p) for p in paths],before)


if __name__=="__main__":
    unittest.main()
