"""Kiểm thử artifact production đã export; không train production lần hai."""

import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import joblib
import numpy as np
from sklearn.linear_model import LinearRegression

from scripts.prepare_training_features import FEATURES,HISTORY_FEATURES,HistoryMedianImputer,ROOT,load_dataset,prepare_features
from scripts.inference.common import MODEL_DIR,InferenceError,sha256
from scripts.inference.export_final_pipeline import export_pipeline
from scripts.inference.model_artifact import load_trusted_pipeline


class ModelExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline,cls.metadata=load_trusted_pipeline()

    def test_exact_training_params_and_feature_schema(self):
        m=self.metadata
        self.assertEqual(m["training_seasons"],[2019,2020,2021,2022,2023])
        self.assertEqual(m["training_observations"],3800)
        self.assertEqual(m["training_matches"],1900)
        self.assertEqual(m["features"],list(FEATURES))
        self.assertEqual(m["estimator_fit_calls"],1)
        self.assertEqual(m["imputer_fit_calls"],1)
        selected=json.loads((ROOT/"outputs/tuning/best_params.json").read_text(encoding="utf-8"))["models"]["Linear Regression"]
        self.assertEqual(m["effective_estimator_parameters"],dict(selected["fixed_parameters"],**selected["best_params"]))
        self.assertEqual(m["parameter_file_sha256"],sha256(ROOT/"outputs/tuning/best_params.json"))

    def test_development_medians_coefficients_and_intercept_retained(self):
        full=load_dataset()
        dev=full.loc[full.season.isin(self.metadata["training_seasons"])]
        X,_,_=prepare_features(dev)
        imputer=self.pipeline.named_steps["preprocessing"].named_steps["median"]
        np.testing.assert_array_equal(imputer.imputer_.statistics_,X[list(HISTORY_FEATURES)].median().to_numpy())
        self.assertEqual(imputer.n_samples_fit_,3800)
        model=self.pipeline.named_steps["model"]
        np.testing.assert_array_equal(model.coef_,self.metadata["coefficients"])
        self.assertEqual(float(model.intercept_),self.metadata["intercept"])
        phase7=json.loads((ROOT/"outputs/final_test/final_test_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(self.metadata["imputation_statistics"],phase7["training"]["Linear Regression"]["medians"])

    def test_no_overwrite_or_retrain_when_artifact_exists(self):
        before=sha256(MODEL_DIR/"laliga_lr_pipeline.joblib")
        with patch.object(LinearRegression,"fit",side_effect=AssertionError("Không được fit lại")),patch.object(HistoryMedianImputer,"fit",side_effect=AssertionError("Không được fit lại")):
            with self.assertRaisesRegex(InferenceError,"không ghi đè"):export_pipeline()
        self.assertEqual(before,sha256(MODEL_DIR/"laliga_lr_pipeline.joblib"))

    def test_export_fit_routing_is_once_and_development_only(self):
        from scripts.inference.export_final_pipeline import train_production_pipeline
        # Thay fit bằng spy: kiểm tra routing mà không train production lần hai.
        with patch("scripts.training.tune_models.build_pipeline",return_value=self.pipeline), \
                patch.object(self.pipeline,"fit",return_value=self.pipeline) as spy:
            _,metadata,X=train_production_pipeline()
        self.assertEqual(spy.call_count,1)
        fitted_X,fitted_y=spy.call_args.args
        full=load_dataset()
        self.assertEqual(set(full.loc[fitted_X.index,"season"]),{2019,2020,2021,2022,2023})
        self.assertEqual(len(fitted_X),3800)
        self.assertTrue(fitted_X.index.equals(fitted_y.index))
        self.assertEqual(list(X.columns),list(FEATURES))

    def test_serialization_reload_predictions_exact_and_deterministic(self):
        full=load_dataset().loc[lambda f:f.season.eq(2019)]
        X,_,_=prepare_features(full)
        a,b=io.BytesIO(),io.BytesIO()
        joblib.dump(self.pipeline,a,compress=3,protocol=5);joblib.dump(self.pipeline,b,compress=3,protocol=5)
        self.assertEqual(a.getvalue(),b.getvalue())
        # Buffer được tạo từ object trusted ngay trong test, không phải upload.
        loaded=joblib.load(io.BytesIO(a.getvalue()))
        np.testing.assert_array_equal(self.pipeline.predict(X),loaded.predict(X))

    def test_clean_process_import_and_reload(self):
        result=subprocess.run([sys.executable,"-c","from scripts.inference.model_artifact import load_trusted_pipeline; p,m=load_trusted_pipeline(); print(m['training_observations']); print(p.named_steps['model'].coef_.tolist())"],
                              cwd=ROOT,capture_output=True,text=True,encoding="utf-8",check=True)
        self.assertEqual(result.stdout.splitlines()[0],"3800")
        self.assertEqual(json.loads(result.stdout.splitlines()[1]),self.metadata["coefficients"])

    def test_missing_and_untrusted_paths_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(InferenceError) as found:load_trusted_pipeline(directory)
            self.assertEqual(found.exception.code,"UNTRUSTED_ARTIFACT")
            with self.assertRaises(InferenceError) as found:load_trusted_pipeline(directory,trusted_directory=directory)
            self.assertEqual(found.exception.code,"ARTIFACT_MISSING")

    def test_corrupt_artifact_hash_rejected_before_joblib_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            shutil.copyfile(MODEL_DIR/"model_metadata.json",path/"model_metadata.json")
            (path/"laliga_lr_pipeline.joblib").write_bytes(b"untrusted-corrupt-content")
            with patch.object(joblib,"load",side_effect=AssertionError("Không được deserialize")):
                with self.assertRaises(InferenceError) as found:load_trusted_pipeline(path,trusted_directory=path)
            self.assertEqual(found.exception.code,"ARTIFACT_CORRUPT")

    def test_environment_mismatch_rejected_before_deserialization(self):
        with patch("scripts.inference.model_artifact.versions",return_value={"python":"incompatible"}),patch.object(joblib,"load",side_effect=AssertionError("Không được deserialize")):
            with self.assertRaises(InferenceError) as found:load_trusted_pipeline()
        self.assertEqual(found.exception.code,"ENVIRONMENT_INCOMPATIBLE")

    def test_all_frozen_files_unchanged(self):
        frozen=json.loads((ROOT/"outputs/inference/protected_files.json").read_text(encoding="utf-8"))
        for name,digest in frozen.items():self.assertEqual(sha256(ROOT/name),digest,name)


if __name__=="__main__":unittest.main()
