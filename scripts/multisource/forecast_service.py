"""Trusted Python handoff. Construct once in the application, pass only IDs to requests."""

from scripts.inference.common import sha256
from .fixture_catalogue import data_status, refresh_metadata
from .forecast_eligibility import POLICY_VERSION, ForecastEligibility
from .forecast_generation import generate_forecast
from .forecast_ledger import ForecastLedger
from .match_registry import require


class ForecastService:
    def __init__(self, *, synthetic_history=None, synthetic_ledger_base=None, simulated_clock=None):
        require((synthetic_history is None) == (synthetic_ledger_base is None),
                "INVALID_SCOPE", "Choose both isolated synthetic namespaces together")
        self.eligibility = ForecastEligibility(synthetic_root=synthetic_history,simulated_clock=simulated_clock)
        self.ledger = ForecastLedger(synthetic_base=synthetic_ledger_base)

    def list_eligible_fixtures(self, snapshot_version, *, season=None, include_unavailable=False):
        return self.eligibility.list_eligible_fixtures(snapshot_version,season=season,
                                                       include_unavailable=include_unavailable)

    def evaluate_forecast_eligibility(self, canonical_fixture_key, snapshot_version):
        return self.eligibility.evaluate_forecast_eligibility(canonical_fixture_key,snapshot_version)

    def _check_successor(self, previous, forecast):
        """Reject changing a published forecast to an older or unrelated history."""
        version = forecast["history_snapshot_version"]
        visited = set()
        store = self.eligibility.open(version)
        expected_hash = forecast["history_database_sha256"]
        while version not in visited:
            actual_hash = sha256(store.path)
            require(not expected_hash or actual_hash == expected_hash,
                    "SNAPSHOT_BINDING_MISMATCH", "Snapshot no longer matches its recorded binding")
            if version == previous["history_snapshot_version"]:
                require(actual_hash == previous["history_database_sha256"],
                        "SNAPSHOT_BINDING_MISMATCH", "Previous forecast snapshot binding changed")
                return
            visited.add(version)
            version = store.manifest["parent_version"]
            if version is None:
                break
            parent = self.eligibility.open(version)
            expected_hash = (refresh_metadata(store) or {}).get("parent_sha256")
            store = parent
        require(False,"STALE_FORECAST_SNAPSHOT","Use the same history or a verified successor")

    def generate_forecast(self, canonical_fixture_key, snapshot_version):
        chain = self.ledger.list_fixture_forecasts(canonical_fixture_key)
        previous = chain[-1] if chain else None
        result = generate_forecast(canonical_fixture_key,snapshot_version,eligibility=self.eligibility)
        if result["status"] != "GENERATED":
            return result
        forecast = result["forecast"]
        if previous:
            self._check_successor(previous,forecast)
        result = self.ledger.append(forecast,expected_previous_id=previous["forecast_id"] if previous else None)
        if result["status"] == "NO_CHANGE":
            result.update(evaluated_eligibility_status=forecast["eligibility_status"],
                          evaluated_snapshot_version=snapshot_version)
        return result

    def get_forecast(self, forecast_id):
        return self.ledger.get_forecast(forecast_id)

    def list_fixture_forecasts(self, canonical_fixture_key):
        return self.ledger.list_fixture_forecasts(canonical_fixture_key)

    def compare_forecasts(self, fixture_key, forecast_v1_id, forecast_v2_id):
        return self.ledger.compare_forecasts(fixture_key,forecast_v1_id,forecast_v2_id)

    def get_forecast_data_status(self, snapshot_version):
        result = data_status(self.eligibility.open(snapshot_version))
        result.update(dataset_kind=self.eligibility.dataset_kind, eligibility_policy_version=POLICY_VERSION)
        if self.eligibility.dataset_kind == "synthetic":
            result["demo_label"] = "SYNTHETIC_DEMO"
        return result
