"""Expose a verified Phase 7 cohort for the website's scientific charts."""

import csv
import json
from math import isclose, isfinite, sqrt
from statistics import mean

from scripts.inference.common import sha256
from scripts.multisource.match_registry import require


def main_test(directory, phase7):
    cohort = "main_final_test"
    manifest = json.loads((directory / "final_test_manifest.json").read_text(encoding="utf-8"))
    predictions = directory / "final_test_predictions.csv"
    metrics = directory / "final_test_metrics.csv"
    require(all(sha256(path) == manifest["csv_sha256"][path.name] for path in (metrics, predictions)),
            "INVALID_EVALUATION_REFERENCE", "Phase 7 evidence differs from its manifest")
    with metrics.open(encoding="utf-8", newline="") as handle:
        baseline = next(row for row in csv.DictReader(handle) if row["test_split"] == cohort
                        and row["model"] == "Historical Baseline")
    with predictions.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["test_split"] == cohort
                and row["model"] == "Linear Regression"]
    rows.sort(key=lambda row: (row["date"], int(row["match_id"]), -int(row["is_home"])))
    points = [dict(date=row["date"], team=row["team"], opponent=row["opponent"],
                   observed=float(row["actual_xg"]), predicted=float(row["predicted_xg"])) for row in rows]
    summary = next(row for row in phase7 if row["label"] == cohort)
    require(len(points) == summary["observations"] == int(baseline["n_observations"]) and
            len({row["source_row"] for row in rows}) == len(points) and
            all(isfinite(point[key]) and point[key] >= 0 for point in points for key in ("observed", "predicted")),
            "INVALID_EVALUATION_REFERENCE", "Main Final Test observations are invalid")
    errors = [point["observed"] - point["predicted"] for point in points]
    require(isclose(mean(map(abs, errors)), summary["mae"], abs_tol=1e-10) and
            isclose(sqrt(mean(error ** 2 for error in errors)), summary["rmse"], abs_tol=1e-10),
            "INVALID_EVALUATION_REFERENCE", "Main Final Test metrics do not match the chart inputs")
    return dict(main_test=dict(summary, baseline_mae=float(baseline["mae"])), main_observations=points)
