"""Read-only source comparison and retrospective date-cutoff replay."""

from collections import Counter
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from scripts.prepare_training_features import FEATURES
from .composite_inference import CompositePredictor
from .mapping import fixture_identity, number, validate_staging
from .match_registry import COMPLETE_STATISTICS, GROUPS, SOURCE_CONFLICT, VERIFIED_COMPLETED, canonical_key, require
from .refresh_validation import archive_score

TRAINING_REFERENCE_END = "2025-09-30"
BOOTSTRAP_SEED = 856
BOOTSTRAP_RESAMPLES = 2000
QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)
EXPECTED_BLOCKS = {"REGISTRY_COVERAGE_UNVERIFIED", "MISSING_ROLLING_STATISTICS", "AMBIGUOUS_HISTORY"}


@dataclass(frozen=True)
class Cohort:
    name: str
    season: int
    label_source: str
    starts_after: str


COHORTS = (
    Cohort("B1", 2025, "Understat", TRAINING_REFERENCE_END),
    Cohort("B2", 2026, "Sportmonks", TRAINING_REFERENCE_END),
)


def finite_value(value):
    if value is None or pd.isna(value):
        return None
    return number(value, "observation")


def pair_overlap(reference, archives, *, shot_totals=None):
    """Match cross-provider fixtures by league season and directed teams, then verify date and score."""
    validate_staging(reference)
    indexed = {}
    for season, archive in sorted(archives.items()):
        require(archive.provider.eq("Understat").all() and archive.competition.eq("la-liga").all()
                and archive.season.eq(season).all() and archive.fixture_id.notna().all()
                and archive.fixture_id.is_unique and archive.understat_id.notna().all() and archive.understat_id.is_unique,
                "INVALID_OVERLAP_SOURCE", "Archive provider, scope or provider-ID uniqueness failed")
        for row in archive.to_dict("records"):
            _, day, home, away = fixture_identity(season,row["date"],row["home"],row["away"])
            key = canonical_key(season, home, away)
            require(key not in indexed, "DUPLICATE_OVERLAP", "Duplicate archive canonical fixture")
            indexed[key] = (row, day, archive_score(row["score"]))
    by_shot_id = {}
    if shot_totals is not None:
        require(shot_totals.fixture_id.is_unique, "DUPLICATE_SHOT_TOTALS", "Shot totals must be unique within the export")
        by_shot_id = shot_totals.set_index("fixture_id").to_dict("index")
    details = []
    for key, pair in reference.groupby("canonical_key", sort=True):
        home, away = pair.sort_values("is_home", ascending=False).to_dict("records")
        expected_key = canonical_key(home["season"], home["team"], away["team"])
        require(key == expected_key, "OVERLAP_IDENTITY_MISMATCH", "Reference key differs from its perspectives")
        matched = indexed.get(key)
        if matched is not None:
            row, day, score = matched
            require(day == home["date"] and score == (home["gf"], away["gf"]),
                    "OVERLAP_IDENTITY_MISMATCH", "Paired fixture date or final score disagrees")
        for side, ref in (("home", home), ("away", away)):
            item = dict(key=key, season=int(ref["season"]), perspective=side, matched=matched is not None,
                        fbref_xg=float(ref["xg"]), fbref_sh=int(ref["sh"]), fbref_sot=int(ref["sot"]),
                        external_xg=None, external_sh=None, external_sot=None, external_xg_missing_in_source=False)
            if matched is None:
                item.update(xg_exclusion="NO_MATCHED_IDENTITY", shot_exclusion="NO_MATCHED_IDENTITY")
            else:
                flag = row["totals_unreliable"]
                value = finite_value(row[side+"_xg"])
                item["external_xg_missing_in_source"] = value is None
                if pd.isna(flag) or flag not in (True, False):
                    item["xg_exclusion"] = "UNVERIFIED_XG_QUALITY"
                elif flag:
                    item["xg_exclusion"] = "PROVIDER_FLAGGED_UNRELIABLE"
                elif value is None:
                    item["xg_exclusion"] = "MISSING_EXTERNAL_XG"
                else:
                    item.update(external_xg=value, xg_exclusion=None)
                counts = by_shot_id.get(row["fixture_id"]) if item["season"] == 2025 else None
                if counts is None:
                    item["shot_exclusion"] = "NO_REVIEWED_SHOT_EVENT_COVERAGE"
                else:
                    item.update(external_sh=int(counts[side+"_sh"]), external_sot=int(counts[side+"_sot"]),
                                shot_exclusion=None)
            details.append(item)
    return details


def distribution(values):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return dict(n=0, mean=None, std=None, quantiles={str(q):None for q in QUANTILES})
    return dict(n=len(values), mean=float(values.mean()), std=float(values.std(ddof=1)) if len(values)>1 else None,
                quantiles=dict(zip(map(str,QUANTILES), np.quantile(values,QUANTILES).tolist())))


def paired_statistics(rows, field):
    pairs = [(r["fbref_"+field], r["external_"+field]) for r in rows if r["external_"+field] is not None]
    a, b = np.asarray(pairs, dtype=float).reshape(-1,2).T
    delta = b-a
    rho = None
    if len(a)>1 and np.ptp(a)>0 and np.ptp(b)>0:
        rho = float(np.corrcoef(a,b)[0,1])
    reason = "xg_exclusion" if field == "xg" else "shot_exclusion"
    counts = Counter(r[reason] for r in rows if r["external_"+field] is None)
    return dict(direction=f"external_{field} - fbref_{field}", reference_observations=len(rows), paired=len(pairs),
                excluded=len(rows)-len(pairs), exclusions=dict(sorted(counts.items())),
                missing_observations=(sum(r["external_xg_missing_in_source"] for r in rows)
                                      if field=="xg" else counts["NO_REVIEWED_SHOT_EVENT_COVERAGE"]),
                fbref=distribution(a), external=distribution(b), signed_difference=distribution(delta),
                absolute_difference=distribution(abs(delta)), pearson_r=rho)


def error_metrics(actual, prediction):
    delta = np.asarray(prediction, dtype=float) - np.asarray(actual, dtype=float)
    if not len(delta):
        return dict(n=0, mae=None, rmse=None, mean_signed_residual=None, median_absolute_error=None)
    return dict(n=len(delta), mae=float(np.abs(delta).mean()), rmse=float(np.sqrt(np.mean(delta**2))),
                mean_signed_residual=float(delta.mean()), median_absolute_error=float(np.median(abs(delta))))


def summarize_scores(fixture_scores):
    def group(sides):
        rows = [row for pair in fixture_scores for row in pair if row["perspective"] in sides]
        actual = [row["actual"] for row in rows]
        lr = error_metrics(actual,[r["prediction"] for r in rows])
        baseline = error_metrics(actual,[r["baseline"] for r in rows])
        return dict(lr=lr, baseline=baseline, lr_minus_baseline_mae=lr["mae"]-baseline["mae"] if rows else None,
                    zero_history_count=sum(r["features"]["matches_seen"] == 0 for r in rows),
                    short_history_count_including_zero=sum(r["features"]["short_history"] == 1 for r in rows))

    paired = [np.mean([abs(row["prediction"]-row["actual"])-abs(row["baseline"]-row["actual"]) for row in pair])
              for pair in fixture_scores]
    interval = None
    if len(paired) >= 2:
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        draws = rng.integers(0,len(paired),size=(BOOTSTRAP_RESAMPLES,len(paired)))
        interval = np.quantile(np.asarray(paired)[draws].mean(axis=1),[0.025,0.975]).tolist()
    return dict(overall=group({"home","away"}), home=group({"home"}), away=group({"away"}),
                paired_fixture_bootstrap=dict(seed=BOOTSTRAP_SEED,resamples=BOOTSTRAP_RESAMPLES,
                                              interval_95_percentile=interval,fixtures=len(paired)))


def validate_target_labels(store, fixture, source):
    key = fixture["canonical_fixture_key"]
    day = fixture["match_date"]
    teams = (fixture["home_team"],fixture["away_team"])
    labels = [store.statistics_for(key,team) for team in teams]
    if not all(labels):
        return None, "MISSING_TARGET_STATISTICS"
    for index, label in enumerate(labels):
        require(label["canonical_key"] == key and label["season"] == fixture["season"]
                and label["date"] == day and label["team"] == teams[index]
                and label["opponent"] == teams[1-index] and label["is_home"] == 1-index
                and label["gf"] == fixture[("home_goals","away_goals")[index]]
                and label["ga"] == fixture[("away_goals","home_goals")[index]],
                "TARGET_IDENTITY_MISMATCH", "Target statistics do not match canonical date, sides and final score")
        require(all(isinstance(label.get(field),str) and label[field] for field in GROUPS),
                "TARGET_PROVENANCE_INVALID", "Target requires source and version provenance")
    if any(finite_value(label.get("xg")) is None for label in labels):
        return None, "MISSING_TARGET_XG"
    if any(finite_value(label.get(field)) is None for label in labels for field in ("xga","sh","sot")):
        return None, "INCOMPLETE_TARGET_STATISTICS"
    if any(label["xg_source"] != source for label in labels):
        return None, "TARGET_PROVIDER_MISMATCH"
    for index, label in enumerate(labels):
        require(finite_value(label["xga"]) == finite_value(labels[1-index]["xg"]),
                "TARGET_STATISTICS_INVALID", "Target xG/xGA perspectives disagree")
        require(number(label["sot"],"sot",integer=True) <= number(label["sh"],"shots",integer=True),
                "TARGET_STATISTICS_INVALID", "Target shot counts are inconsistent")
    return labels, None


def replay_cohort(store, predictor, cohort):
    """For a complete target, construct and predict before fetching the target label values."""
    registry = store.query("SELECT * FROM registry ORDER BY season,match_date,canonical_fixture_key")
    by_key = {r["canonical_fixture_key"]:r for r in registry}
    fixtures = [r for r in registry if r["season"] == cohort.season]
    candidates = [r for r in fixtures if r["match_date"] > cohort.starts_after]
    outcomes, fixture_scores = [], []
    for row in candidates:
        key, day, home, away = (row[k] for k in ("canonical_fixture_key","match_date","home_team","away_team"))
        outcome = dict(key=key, match_date=day, status="EXCLUDED", reason=None)
        outcomes.append(outcome)
        require(key == canonical_key(cohort.season,home,away),"TARGET_IDENTITY_MISMATCH","Invalid registry key")
        if SOURCE_CONFLICT in (row["match_status"],row["statistics_status"]):
            outcome["reason"] = "SOURCE_CONFLICT"
        elif row["match_status"] != VERIFIED_COMPLETED:
            outcome["reason"] = "NOT_VERIFIED_COMPLETED"
        elif row["statistics_status"] != COMPLETE_STATISTICS:
            _, reason = validate_target_labels(store,row,cohort.label_source)
            outcome["reason"] = reason or "INCOMPLETE_TARGET_STATISTICS"
        else:
            prediction = predictor.predict(home,away,day,cohort.season,prediction_cutoff=day,mode="RESEARCH_INFERENCE")
            if prediction["status"] != "success":
                reason = prediction["error"]["code"]
                require(reason in EXPECTED_BLOCKS,"REPLAY_INFERENCE_ERROR",f"Unexpected frozen inference error: {reason}")
                outcome.update(status="BLOCKED",reason=reason)
                continue
            require(prediction["history_cutoff"] == day and not prediction["production_approved"]
                    and prediction["mode"] == "RESEARCH_INFERENCE"
                    and prediction["artifact_sha256"] == predictor.metadata["artifact_sha256"]
                    and [f["is_home"] for f in prediction["features"]] == [1,0],
                    "REPLAY_CONTRACT_INVALID", "Unexpected cutoff, model or perspective")
            require(all(p["canonical_fixture_key"] != key and p["canonical_fixture_key"] in by_key
                        and by_key[p["canonical_fixture_key"]]["match_date"] < day
                        and by_key[p["canonical_fixture_key"]]["match_status"] == VERIFIED_COMPLETED
                        for p in prediction["history_provenance"]),
                    "REPLAY_LEAKAGE", "A selected history row violates strict-before replay")
            labels, reason = validate_target_labels(store,row,cohort.label_source)
            if reason:
                outcome["reason"] = reason
                continue
            frame = pd.DataFrame(prediction["features"],columns=list(FEATURES),dtype=float)
            baseline = predictor.pipeline.named_steps["preprocessing"].transform(frame)["xg_avg5"].to_numpy()
            pair = []
            for i, side in enumerate(("home","away")):
                raw = prediction["raw_predictions"][i]
                clipped = prediction[side+"_xg"]
                require(math.isfinite(raw) and clipped == max(0,raw),"REPLAY_CONTRACT_INVALID","Clipping mismatch")
                pair.append(dict(key=key, perspective=side, actual=float(labels[i]["xg"]),
                                 label_provenance={k:labels[i][k] for k in GROUPS},
                                 prediction=clipped, raw_prediction=raw, baseline=number(baseline[i],"baseline"),
                                 features=prediction["features"][i],
                                 window=[p for p in prediction["history_provenance"] if p["team"] == labels[i]["team"]]))
            fixture_scores.append(pair)
            outcome["status"] = "SCORED"
    store.verify_integrity()
    return dict(cohort=cohort.name, season=cohort.season, label_source=cohort.label_source,
                catalogue_fixtures=len(fixtures), before_or_at_boundary=len(fixtures)-len(candidates),
                candidate_fixtures=len(candidates),
                verified_completed=sum(r["match_status"] == VERIFIED_COMPLETED for r in candidates),
                outcomes=outcomes, fixture_scores=fixture_scores)
