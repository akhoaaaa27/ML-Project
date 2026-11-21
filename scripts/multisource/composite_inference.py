"""Research-only frozen LR inference; production upcoming is explicitly disabled."""

import argparse
import json

import numpy as np
from threadpoolctl import threadpool_limits

from scripts.inference.common import InferenceError, MODEL_DIR, sha256
from scripts.inference.model_artifact import load_trusted_pipeline
from .composite_features import build_composite_features
from .composite_history import CompositeHistory
from .match_registry import require
from .team_registry import resolve, stable_id


class CompositePredictor:
    def __init__(self, history):
        require(isinstance(history,CompositeHistory), "INVALID_HISTORY", "Validated CompositeHistory required")
        self.history = history
        self.pipeline,self.metadata = load_trusted_pipeline()

    def construct(self, home, away, day, season, *, prediction_cutoff=None):
        self.history.verify_integrity()
        return build_composite_features(home,away,day,season,self.history,prediction_cutoff=prediction_cutoff)

    def predict(self, home, away, day, season, *, prediction_cutoff=None, mode="RESEARCH_INFERENCE"):
        try:
            require(mode == "RESEARCH_INFERENCE", "PRODUCTION_NOT_APPROVED", "Composite production upcoming is not approved")
            built = self.construct(home,away,day,season,prediction_cutoff=prediction_cutoff)
            require(sha256(MODEL_DIR/"laliga_lr_pipeline.joblib") == self.metadata["artifact_sha256"],
                    "ARTIFACT_CORRUPT", "Frozen artifact changed")
            with threadpool_limits(limits=1):
                raw = np.asarray(self.pipeline.predict(built.X),dtype=float)
            require(raw.shape == (2,) and np.isfinite(raw).all(), "INVALID_NUMERIC", "Invalid frozen prediction")
            result = dict(status="success",mode=mode,production_approved=False,
                          home_team=resolve(home),away_team=resolve(away),home_team_id=stable_id(home),away_team_id=stable_id(away),
                          match_date=day,season=season,history_cutoff=built.cutoff,
                          home_xg=float(max(0,raw[0])),away_xg=float(max(0,raw[1])),
                          raw_predictions=raw.tolist(),clipping_applied=bool((raw<0).any()),
                          model="Linear Regression",target="total_team_match_xg",artifact_sha256=self.metadata["artifact_sha256"],
                          composite_version=self.history.manifest["version_id"],
                          logical_provider=self.history.manifest["logical_provider"],
                          data_quality_status="research_registry_coverage_and_rolling_statistics_validated",
                          source_semantics="mixed_xg_models_and_shot_definitions_not_production_approved",
                          temporal_policy="date_only_strict_before_cutoff_not_as_of_vintage",
                          features=built.X.where(built.X.notna(),None).to_dict("records"),
                          history_summary=built.history,history_provenance=built.provenance)
            # Ensure a JSON-safe representation of legitimate zero-history NaN.
            result["features"] = [{k:None if isinstance(v,float) and np.isnan(v) else v for k,v in row.items()}
                                  for row in result["features"]]
            return result
        except InferenceError as exc:
            return exc.result(mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database",required=True)
    parser.add_argument("--home",required=True)
    parser.add_argument("--away",required=True)
    parser.add_argument("--date",required=True)
    parser.add_argument("--season",required=True,type=int)
    parser.add_argument("--cutoff")
    parser.add_argument("--mode",default="RESEARCH_INFERENCE")
    args = parser.parse_args()
    try:
        predictor = CompositePredictor(CompositeHistory(args.database))
        result = predictor.predict(args.home,args.away,args.date,args.season,prediction_cutoff=args.cutoff,mode=args.mode)
    except InferenceError as exc:
        result = exc.result("RESEARCH_INFERENCE")
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
