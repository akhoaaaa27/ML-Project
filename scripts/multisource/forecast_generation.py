"""Generate a forecast candidate through the existing frozen CompositePredictor."""

import math

from scripts.inference.common import InferenceError
from scripts.prepare_training_features import FEATURES
from .composite_inference import CompositePredictor
from .fixture_catalogue import fixture_catalogue
from .forecast_eligibility import FIXTURE_MAX_AGE, MODE, READY, ForecastEligibility, utc, utc_text
from .match_registry import require, semantic_hash

SCHEMA_VERSION = "1.0"
FEATURE_SCHEMA_VERSION = "1.0"
SOURCE_NOTICE = ("Research only. Mixed-provider statistics may differ from training definitions. "
                 "xG is expected total team goals, and predictive accuracy on these sources is unverified.")
PARITY_TOLERANCE = 1e-12


def feature_input(rows):
    require(len(rows) == 2 and all(set(row) == set(FEATURES) for row in rows),
            "FEATURE_SCHEMA_MISMATCH", "Exactly two ordered frozen-feature rows are required")
    result = dict(order=list(FEATURES), home=[rows[0][name] for name in FEATURES],
                  away=[rows[1][name] for name in FEATURES])
    require(all(v is None or type(v) in (float, int) and math.isfinite(v)
                for side in ("home", "away") for v in result[side]),
            "INVALID_NUMERIC", "Features must be finite or null")
    return result


def generate_forecast(canonical_fixture_key, snapshot_version, *, eligibility=None):
    engine = eligibility if eligibility is not None else ForecastEligibility()
    now = engine.now()
    store = engine.open(snapshot_version)
    return generate_bound_forecast(canonical_fixture_key, engine, store, fixture_catalogue(store), now)


def generate_bound_forecast(canonical_fixture_key, engine, store, rows, now):
    """Generate using an already validated snapshot and its fixture catalogue."""
    snapshot_version = store.manifest["version_id"]
    verdict = engine._evaluate(canonical_fixture_key, store, rows, now)
    if verdict["eligibility_status"] not in READY:
        return dict(status=verdict["eligibility_status"], eligibility=verdict)
    target = verdict["target"]
    cutoff = verdict["history_cutoff"]
    try:
        predictor = CompositePredictor(store)
        prediction = predictor.predict(target["home_team"], target["away_team"], target["match_date"],
                                       target["season"], prediction_cutoff=cutoff, mode=MODE)
        if prediction["status"] != "success":
            return dict(status="FORECAST_ERROR", eligibility=verdict, error=prediction["error"]["code"])
        features = feature_input(prediction["features"])
        require(prediction["history_cutoff"] == cutoff and prediction["composite_version"] == snapshot_version
                and prediction["production_approved"] is False and prediction["mode"] == MODE
                and prediction["artifact_sha256"] == predictor.metadata["artifact_sha256"],
                "INVALID_PREDICTION", "Prediction metadata disagrees with selected forecast")
        digest = store.verify_integrity()
        generated = engine.now()
        require(now <= generated < utc(target["kickoff_utc"])
                and generated.date() == now.date()
                and generated - utc(verdict["fixture_reviewed_at_utc"]) <= FIXTURE_MAX_AGE,
                "FORECAST_TIME_CHANGED", "Eligibility expired during generation; evaluate again")
    except InferenceError as exc:
        return dict(status="FORECAST_ERROR", eligibility=verdict, error=exc.code)
    candidate = {name:verdict[name] for name in ("dataset_kind", "generated_at_utc", "forecast_as_of_date",
                 "history_cutoff", "eligibility_policy_version", "eligibility_status", "canonical_fixture_key")}
    candidate["generated_at_utc"] = utc_text(generated)
    if engine.dataset_kind == "synthetic":
        candidate["demo_label"] = "SYNTHETIC_DEMO"
    candidate.update(schema_version=SCHEMA_VERSION, target_match_date=target["match_date"],
                     target_kickoff_utc=target["kickoff_utc"], target_semantics=prediction["target"],
                     history_snapshot_version=snapshot_version, history_database_sha256=digest,
                     model_version=predictor.metadata["model_version"], model_artifact_sha256=prediction["artifact_sha256"],
                     feature_schema_version=FEATURE_SCHEMA_VERSION, features=features,
                     features_sha256=semantic_hash(features), home_xg=prediction["home_xg"],
                     away_xg=prediction["away_xg"], raw_predictions=prediction["raw_predictions"],
                     history_provenance=prediction["history_provenance"],
                     history_windows={team:history["rolling_match_keys"] for team,history in prediction["history_summary"].items()},
                     fixture_reviewed_at_utc=verdict["fixture_reviewed_at_utc"],
                     inference_mode=MODE, production_approved=False,
                     source_semantics="mixed_provider_research", source_notice=SOURCE_NOTICE)
    return dict(status="GENERATED", forecast=candidate)
