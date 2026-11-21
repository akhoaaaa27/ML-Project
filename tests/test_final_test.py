"""Kiểm thử Phase 7 bằng dữ liệu Development/nhân tạo; không chấm điểm Test thật."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts.prepare_training_features import FEATURES, HISTORY_FEATURES, HistoryMedianImputer, load_dataset, prepare_features
from scripts.training.train_models import MODEL_NAMES, evaluate_predictions
from scripts.evaluation.bootstrap_analysis import match_losses, paired_bootstrap
from scripts.evaluation.error_analysis import prediction_table, summarize_errors, match_error_analysis, cross_model_errors
from scripts.evaluation import final_test as ft
from test_evaluation import SpyRegressor, predictions_fixture


def synthetic_parts():
    """Sao chép chỉ Development 2019; thay nhãn mùa/ngày cho kiểm thử cơ chế."""
    full = load_dataset()
    dev = full.loc[full.season.eq(2019)].copy()
    frames = []
    for year in range(2019, 2026):
        part = dev.copy() if year < 2024 else dev.loc[dev.match_id.isin(dev.match_id.unique()[-2:])].copy()
        part["season"] = year
        part["date"] = (pd.to_datetime(part.date) + pd.DateOffset(years=year-2019)).dt.strftime("%Y-%m-%d")
        part["match_id"] += (year-2019)*100000
        frames.append(part)
    return ft.partition_data(pd.concat(frames, ignore_index=True))


def bootstrap_fixture():
    frame = predictions_fixture()
    frame = frame.drop(columns="fold")
    frame.insert(0, "test_split", "main_final_test")
    return frame


class ProtocolTests(unittest.TestCase):
    def test_evaluate_requires_preexisting_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(ft, "fit_development", side_effect=AssertionError("Không được fit")):
                with self.assertRaisesRegex(ValueError, "prepare"):
                    ft.evaluate(Path(directory)/"absent.json")

    def test_prepare_does_not_score_and_reuses_exact_bytes(self):
        payload = {"features": list(FEATURES), "bootstrap": {"seed": 42}}
        with tempfile.TemporaryDirectory() as directory, patch.object(ft, "build_protocol", return_value=payload), \
                patch.object(ft, "evaluate_predictions", side_effect=AssertionError("Không được score")):
            path = Path(directory)/"protocol.json"
            ft.prepare_protocol(path)
            before = path.read_bytes()
            ft.prepare_protocol(path)
            self.assertEqual(before, path.read_bytes())
            self.assertEqual(ft.verify_protocol(path)[0], payload)

    def test_tampered_protocol_and_changed_sources_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ft, "build_protocol", return_value={"sha": "original"}):
            path = Path(directory)/"protocol.json"
            ft.prepare_protocol(path)
            path.write_text('{"sha":"changed"}', encoding="utf-8")
            before = path.read_bytes()
            with self.assertRaises(ValueError): ft.verify_protocol(path)
            with self.assertRaises(ValueError): ft.prepare_protocol(path)
            self.assertEqual(before, path.read_bytes())

    def test_selected_models_match_frozen_phase5(self):
        selected, models = ft.load_selected_models()
        for name, model in models.items():
            for key, value in selected["models"][name]["best_params"].items():
                self.assertEqual(model.get_params()[key], value)
        self.assertNotIn(ft.BASELINE, models)
        self.assertEqual(len(FEATURES), 13)
        self.assertNotIn("xg", FEATURES)


class FrozenTrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parts = synthetic_parts()

    def test_splits_are_disjoint_pairs_chronological(self):
        rows, matches = set(), set()
        end = None
        for split, part in self.parts.items():
            self.assertEqual(set(part.season), set(ft.SPLITS[split]))
            self.assertFalse(rows & set(part.index))
            self.assertFalse(matches & set(part.match_id))
            self.assertTrue(part.groupby("match_id").is_home.nunique().eq(2).all())
            if end is not None: self.assertLess(end, part.date.min())
            end = part.date.max()
            rows.update(part.index); matches.update(part.match_id)

    def test_overlap_broken_pair_and_dates_rejected(self):
        full = pd.concat(self.parts.values())
        with self.assertRaises(ValueError): ft.partition_data(full.iloc[1:])
        invalid = full.copy()
        invalid.loc[invalid.season.eq(2024), "date"] = "2018-01-01"
        with self.assertRaises(ValueError): ft.partition_data(invalid)
        invalid = full.copy()
        idx = invalid.index[invalid.season.eq(2024)][:2]
        invalid.loc[idx, "match_id"] = invalid.match_id.iloc[0]
        with self.assertRaises(ValueError): ft.partition_data(invalid)

    def test_four_fits_dev_only_same_objects_and_no_test_fitting(self):
        SpyRegressor.calls.clear()
        models = {n: SpyRegressor() for n in MODEL_NAMES if n != ft.BASELINE}
        fit_calls = []
        original = HistoryMedianImputer.fit
        def spy(instance, X, y=None):
            fit_calls.append(X.index.copy())
            return original(instance, X, y)
        with patch.object(HistoryMedianImputer, "fit", spy):
            fitted, audit = ft.fit_development(self.parts["development"], models)
        self.assertEqual(len(SpyRegressor.calls), 4)
        self.assertEqual(len(fit_calls), 4)
        for indices in fit_calls:
            self.assertTrue(indices.equals(self.parts["development"].index))
        medians = {n: p.named_steps["preprocessing"].named_steps["median"].imputer_.statistics_.copy() for n,p in fitted.items()}
        objects = {n: id(p) for n,p in fitted.items()}
        with patch.object(HistoryMedianImputer, "fit", side_effect=AssertionError("Test fit interdit")), \
                patch.object(SpyRegressor, "fit", side_effect=AssertionError("Test fit interdit")):
            for split in ("main_final_test", "supplemental_test"):
                pred, diagnostics = ft.infer_split(self.parts[split], split, fitted)
                self.assertEqual(len(pred), 5*len(self.parts[split]))
                repeat, _ = ft.infer_split(self.parts[split], split, fitted)
                pd.testing.assert_frame_equal(pred, repeat, check_exact=True)
                X, _, _ = prepare_features(self.parts[split])
                pre = fitted[ft.PRIMARY].named_steps["preprocessing"]
                np.testing.assert_array_equal(pred.loc[pred.model.eq(ft.BASELINE), "predicted_xg"], pre.transform(X).xg_avg5)
                shifted = X.copy()
                shifted.loc[:, list(HISTORY_FEATURES)] += 1e6
                shifted.iloc[0, shifted.columns.get_loc("xg_avg5")] = np.nan
                self.assertEqual(pre.transform(shifted).iloc[0].xg_avg5, audit[ft.PRIMARY]["medians"]["xg_avg5"])
        self.assertEqual(objects, {n: id(p) for n,p in fitted.items()})
        for n,p in fitted.items():
            np.testing.assert_array_equal(medians[n], p.named_steps["preprocessing"].named_steps["median"].imputer_.statistics_)

    def test_fit_test_seasons_rejected(self):
        with self.assertRaises(ValueError): ft.fit_development(self.parts["main_final_test"], {})

    def test_test_wrapper_does_not_weaken_development_guard(self):
        part = self.parts["main_final_test"]
        with self.assertRaises(ValueError): prediction_table(part, ft.PRIMARY, 3, part.xg, part.xg.to_numpy())
        with self.assertRaises(ValueError): ft.test_prediction_table(part, "supplemental_test", ft.PRIMARY, part.xg, part.xg.to_numpy())
        with self.assertRaises(ValueError): ft.test_prediction_table(part, "main_final_test", ft.PRIMARY, part.xg.iloc[::-1], part.xg.to_numpy())


class BootstrapAndErrorTests(unittest.TestCase):
    def test_match_means_preserve_home_away(self):
        pred = bootstrap_fixture()
        losses = match_losses(pred)
        for model in MODEL_NAMES:
            self.assertAlmostEqual(losses[model].mean(), pred.loc[pred.model.eq(model), "absolute_error"].mean())
        with self.assertRaises(ValueError): match_losses(pred.iloc[1:])
        with self.assertRaises(ValueError): match_losses(pd.concat([pred,pred.iloc[:1]]))

    def test_exact_sampling_multiplicity_delta_and_intervals(self):
        pred = bootstrap_fixture()
        summary, reps, audit = paired_bootstrap(pred, "main_final_test", ft.COMPARISONS, 2000, 42)
        losses = match_losses(pred)
        indices = np.random.default_rng(42).integers(0, 2, (2000, 2))
        self.assertTrue((indices[:,0] == indices[:,1]).any())
        for row in summary.itertuples():
            diff = losses[row.model_a].to_numpy()-losses[row.model_b].to_numpy()
            expected = diff[indices].mean(axis=1)
            actual = reps.loc[reps.comparison_id.eq(row.comparison_id), "delta_mae"].to_numpy()
            np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-15)
            np.testing.assert_allclose([row.ci_lower,row.ci_upper], np.quantile(expected,[.025,.975],method="linear"), atol=1e-15)
            self.assertAlmostEqual(row.observed_delta_mae, diff.mean())
        self.assertEqual(audit["sample_shape"], [2000,2])
        again = paired_bootstrap(pred, "main_final_test", ft.COMPARISONS, 2000, 42)
        pd.testing.assert_frame_equal(reps, again[1], check_exact=True)
        self.assertNotEqual(audit["sample_indices_sha256"], paired_bootstrap(pred,"main_final_test",ft.COMPARISONS,2000,43)[2]["sample_indices_sha256"])

    def test_mixed_splits_rejected(self):
        pred = bootstrap_fixture()
        pred.loc[0,"test_split"] = "supplemental_test"
        with self.assertRaises(ValueError): paired_bootstrap(pred,"main_final_test",ft.COMPARISONS)

    def test_generic_error_helpers_keep_original_outputs(self):
        pred = predictions_fixture()
        old, _ = summarize_errors(pred)
        new_pred = pred.rename(columns={"fold":"test_split"})
        new, _ = summarize_errors(new_pred, partition_column="test_split")
        pd.testing.assert_frame_equal(old.rename(columns={"folds":"test_splits"}),new)
        pd.testing.assert_frame_equal(match_error_analysis(pred).rename(columns={"fold":"test_split"}),
                                      match_error_analysis(new_pred,partition_column="test_split"))
        pd.testing.assert_frame_equal(cross_model_errors(pred).rename(columns={"fold":"test_split"}),
                                      cross_model_errors(new_pred,partition_column="test_split"))

    def test_clipping_residual_and_metrics(self):
        part = synthetic_parts()["main_final_test"]
        raw = np.array([-1.,0.,2.,3.])
        table = ft.test_prediction_table(part,"main_final_test",ft.PRIMARY,part.xg,raw)
        clipped = np.maximum(0,raw)
        np.testing.assert_array_equal(table.predicted_xg, clipped)
        np.testing.assert_array_equal(table.residual,clipped-part.xg.to_numpy())
        metrics,_ = evaluate_predictions(part.xg,raw)
        self.assertAlmostEqual(metrics["mae"],table.absolute_error.mean())
        self.assertAlmostEqual(metrics["rmse"],np.sqrt(table.squared_error.mean()))
        diag = ft.diagnostic_row(table,raw)
        self.assertEqual(diag["negative_raw_predictions"],1)
        self.assertEqual(diag["residual_std"],table.residual.std(ddof=0))


class TemporalAndExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev = load_dataset().loc[lambda f:f.season.eq(2019)].copy()

    def test_read_only_rolling_audit_and_prior_restoration(self):
        before = self.dev.copy(deep=True)
        audit = ft.temporal_audit(self.dev)
        self.assertEqual(audit["rolling_values_checked"],len(self.dev)*6)
        pd.testing.assert_frame_equal(self.dev,before,check_exact=True)
        X,y,restoration = prepare_features(self.dev)
        self.assertEqual(list(X.columns),list(FEATURES))
        self.assertEqual(int(X.isna().sum().sum()),restoration.restored_cells)
        self.assertTrue(X.index.equals(y.index))

    def test_current_future_and_same_day_ambiguity_stop(self):
        bad = self.dev.copy()
        bad.loc[bad.index[10],"xg_avg5"] += .01
        with self.assertRaisesRegex(ValueError,"Rolling sai"): ft.temporal_audit(bad)
        bad = self.dev.copy()
        team = bad.team.iloc[0]
        indices = bad.index[bad.team.eq(team)][:2]
        bad.loc[indices[1],"date"] = bad.loc[indices[0],"date"]
        with self.assertRaisesRegex(ValueError,"cùng đội/cùng ngày"): ft.temporal_audit(bad)

    def test_export_has_exact_schema_and_no_staging_leftovers(self):
        table = pd.DataFrame({"test_split":["main_final_test"],"value":[1.1234567890123457],"flag":[True]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            hashes = ft.export_tables({"sample.csv":table},path)
            self.assertEqual(hashes["sample.csv"],ft.sha256(path/"sample.csv"))
            self.assertEqual([p.name for p in path.iterdir()],["sample.csv"])
            pd.testing.assert_frame_equal(pd.read_csv(path/"sample.csv"),table)

    def test_synthetic_end_to_end_exports_figures_and_report(self):
        from scripts.evaluation.final_test_visualizations import generate_figures
        from scripts.evaluation.final_test_reporting import write_report
        protocol=ft.build_protocol()  # Kiểm tra toàn vẹn, không score Test thật.
        frames=[]; errors=[]; notes=[]; matches=[]; cross=[]; summaries=[]; replicates=[]; parts={}
        for split,year in [("main_final_test",2024),("supplemental_test",2025)]:
            pred=bootstrap_fixture()
            pred["test_split"]=split; pred["season"]=year; pred["raw_prediction"]=pred.predicted_xg
            frames.append(pred)
            source=pred.loc[pred.model.eq(ft.BASELINE)].copy().set_index("source_row")
            source["xg"]=source.actual_xg
            parts[split]=source
            error,_=ft.summarize_errors(pred,partition_column="test_split",scope=split)
            error.insert(0,"test_split",split); errors.append(error)
            notes.append(ft.notable_errors(pred)); matches.append(ft.match_error_analysis(pred,partition_column="test_split"))
            cross.append(ft.cross_model_errors(pred,partition_column="test_split"))
            summary,reps,_=ft.paired_bootstrap(pred,split,ft.COMPARISONS)
            summaries.append(summary); replicates.append(reps)
        predictions=pd.concat(frames,ignore_index=True)
        tables={name:pd.concat(items,ignore_index=True) for name,items in (
            ("final_test_error_analysis.csv",errors),("final_test_notable_errors.csv",notes),
            ("final_test_match_errors.csv",matches),("final_test_cross_model_errors.csv",cross),
            ("bootstrap_results.csv",summaries),("bootstrap_replicates.csv",replicates))}
        tables.update({"final_test_predictions.csv":predictions,"final_test_metrics.csv":ft.score_predictions(predictions,protocol),
            "final_test_diagnostics.csv":pd.DataFrame([ft.diagnostic_row(g,g.raw_prediction) for _,g in predictions.groupby(["test_split","model"],sort=False)])})
        training={n:dict(medians=dict.fromkeys(HISTORY_FEATURES,1.),estimator_fit_calls=1,imputer_fit_calls=1,n_fit_records=3800)
                  for n in MODEL_NAMES if n!=ft.BASELINE}
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            hashes=ft.export_tables(tables,output)
            with patch.object(ft,"OUTPUT_DIR",output):
                readback=ft.independent_readback(tables,parts,protocol)
            figures=generate_figures(tables,output/"figures")
            self.assertEqual(len(figures),7)
            manifest=dict(training=training,tests=dict(run=0,failures=0,errors=0,skipped=0,log="synthetic fixture"),
                evaluation_protocol_sha256="synthetic",dataset_sha256="synthetic",best_params_sha256="synthetic",
                readback=readback,csv_sha256=hashes,environment=dict(python="synthetic",packages={}),figures=figures)
            write_report(tables,protocol,manifest,output/"report.md")
            report=(output/"report.md").read_text(encoding="utf-8")
            self.assertEqual(report.count("\n## "),34)
            self.assertTrue(readback["bootstrap_replayed"])


if __name__ == "__main__": unittest.main()
