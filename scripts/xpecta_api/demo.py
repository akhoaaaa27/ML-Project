"""Prepare isolated Phase 8.5.5 scenarios for separate local API launches."""

import argparse
import json

from scripts.multisource.forecast_demo import historical_replay, refreshed_example
from scripts.multisource.forecast_examples import TARGET, UPDATE, synthetic_snapshot
from scripts.multisource.forecast_eligibility import ForecastEligibility

from .settings import Mode, Settings


def initialize_demo(directory):
    directory.mkdir(parents=True, exist_ok=False)
    history = directory / "history"
    initial = synthetic_snapshot(history, "initial")
    refreshed_example(directory, initial)
    updated = ForecastEligibility(synthetic_root=history, simulated_clock=lambda: UPDATE).open("updated")
    synthetic_snapshot(history, "same-features", completed=[*range(6), 7], now=UPDATE, parent=updated)
    synthetic_snapshot(history, "incomplete", completed=[*range(6), 7], pending={(2026, 7)}, now=UPDATE)
    return dict(target=TARGET, profiles=["initial", "updated", "same-features", "incomplete"],
                demo_label="SYNTHETIC DEMO", production_approved=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="defense")
    parser.add_argument("--historical-parity", action="store_true")
    options = parser.parse_args()
    settings = Settings(mode=Mode.SYNTHETIC_DEMO, snapshot_version="initial", demo_name=options.name)
    if options.historical_parity:
        report = historical_replay(settings.demo_root / "historical-parity")
    else:
        report = initialize_demo(settings.demo_root)
    print(json.dumps(report, indent=2))
