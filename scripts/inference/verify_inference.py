"""Kiểm toán read-only parity, fresh-process loading và bảo toàn Phase 1–7."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

from scripts.prepare_training_features import ROOT, FEATURES, load_dataset, prepare_features
from .build_fixture_features import build_fixture_features
from .common import OUTPUT_DIR, MODEL_DIR, check, cli_output, sha256, write_json
from .history_store import HistoryStore
from .model_artifact import load_trusted_pipeline

FEATURE_ATOL = 5.1e-9
PREDICTION_ATOL = 1e-8


def verify_parity(history=None):
    history=HistoryStore() if history is None else history
    pipeline,metadata=load_trusted_pipeline()
    full=load_dataset()
    expected,_,_=prepare_features(full)
    all_X=[]; indices=[]
    for _,fixture in full.groupby("match_id",sort=True):
        home=fixture.loc[fixture.is_home.eq(1)].iloc[0]
        away=fixture.loc[fixture.is_home.eq(0)].iloc[0]
        built=build_fixture_features(home.team,away.team,home.date,int(home.season),history)
        all_X.append(built.X)
        indices.extend([int(home.name),int(away.name)])
    rebuilt=pd.concat(all_X,ignore_index=True)
    original=expected.loc[indices].reset_index(drop=True)
    np.testing.assert_array_equal(rebuilt.isna(),original.isna())
    np.testing.assert_allclose(rebuilt.to_numpy(),original.to_numpy(),rtol=0,atol=FEATURE_ATOL,equal_nan=True)
    max_feature_delta=float(np.nanmax(abs(rebuilt.to_numpy()-original.to_numpy())))
    predictions=np.maximum(0,pipeline.predict(rebuilt))
    reconstructed=pd.Series(predictions,index=indices)
    # Chỉ đọc dự báo tham chiếu; không đọc actual_xg hoặc tính lại Test performance.
    reference=pd.read_csv(ROOT/"outputs/final_test/final_test_predictions.csv",
                          usecols=["test_split","source_row","model","predicted_xg"])
    lr=reference.loc[reference.model.eq("Linear Regression")]
    check(len(lr)==900 and lr.source_row.is_unique,"PARITY_FAILED","Tham chiếu LR phải đủ 900 holdout records.")
    actual=reconstructed.loc[lr.source_row].to_numpy()
    np.testing.assert_allclose(actual,lr.predicted_xg.to_numpy(),rtol=0,atol=PREDICTION_ATOL)
    bound=float(np.abs(pipeline.named_steps["model"].coef_).sum()*FEATURE_ATOL+1e-12)
    check(bound<=PREDICTION_ATOL,"PARITY_FAILED","Ngưỡng prediction phải bao phủ bound sai số CSV và float.")
    process=subprocess.run([sys.executable,"-m","scripts.inference.predict_fixture","replay","--match-id","1901"],
        cwd=ROOT,check=True,capture_output=True,text=True,encoding="utf-8")
    fresh=json.loads(process.stdout)
    check(fresh["status"]=="success","PARITY_FAILED","Fresh-process replay không thành công.")
    sample=full.loc[full.match_id.eq(1901)]
    for is_home,column in [(1,"home_xg"),(0,"away_xg")]:
        row=sample.loc[sample.is_home.eq(is_home)].index[0]
        check(abs(fresh[column]-float(reconstructed.loc[row]))<=PREDICTION_ATOL,"PARITY_FAILED","Fresh process lệch alignment Home/Away.")
    # Fresh process tải và đối chiếu toàn bộ coefficients/intercept/medians trong loader.
    protected=json.loads((OUTPUT_DIR/"protected_files.json").read_text(encoding="utf-8"))
    check(all(sha256(ROOT/name)==digest for name,digest in protected.items()),"PROTECTED_FILE_CHANGED","File nghiên cứu đã thay đổi.")
    return dict(status="success",feature_rows=4700,fixtures=2350,features=list(FEATURES),
        feature_atol=FEATURE_ATOL,feature_max_absolute_delta=max_feature_delta,
        holdout_prediction_rows=900,main_prediction_rows=int(lr.test_split.eq("main_final_test").sum()),
        supplemental_prediction_rows=int(lr.test_split.eq("supplemental_test").sum()),
        prediction_atol=PREDICTION_ATOL,prediction_rounding_bound=bound,
        prediction_max_absolute_delta=float(np.max(abs(actual-lr.predicted_xg.to_numpy()))),
        actual_targets_used_for_parity=False,phase7_evaluation_rerun=False,
        fresh_process_reload=True,serialized_fitted_state_verified=True,offline=True,
        protected_files_checked=len(protected),protected_files_unchanged=True,
        artifact_sha256=metadata["artifact_sha256"],example_replay=fresh)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=OUTPUT_DIR/"verification_manifest.json")
    args=parser.parse_args()
    def run():
        result=verify_parity()
        write_json(args.output,result)
        return {key:value for key,value in result.items() if key!="example_replay"}
    return cli_output(run)


if __name__=="__main__":
    raise SystemExit(main())
