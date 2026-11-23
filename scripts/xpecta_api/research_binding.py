"""Validate the server-selected real snapshot against operator pins and V3 lineage."""

from scripts.inference.common import sha256
from scripts.multisource.fixture_catalogue import refresh_metadata
from scripts.multisource.match_registry import require
from scripts.multisource.revision_review import POLICY_VERSION

from .settings import REAL_MANIFEST_SHA256, REAL_SHA256, REAL_VERSION


def verify_pins(store, database_sha256, manifest_sha256):
    require(sha256(store.path) == database_sha256
            and sha256(store.path.with_name("manifest.json")) == manifest_sha256,
            "HISTORY_CORRUPT", "Snapshot and manifest must match the server pins")


def verify_real_snapshot(engine, store, settings):
    version = settings.snapshot_version
    expected = (REAL_SHA256, REAL_MANIFEST_SHA256) if version == REAL_VERSION else (
        settings.snapshot_sha256, settings.snapshot_manifest_sha256)
    verify_pins(store, *expected)
    visited = set()
    while version != REAL_VERSION:
        require(version not in visited, "INVALID_SNAPSHOT", "Snapshot lineage contains a cycle")
        visited.add(version)
        refresh = refresh_metadata(store)
        validation = store.manifest.get("inference_validation") or {}
        require(refresh and refresh["dataset_kind"] == "real" and refresh["policy_version"] == POLICY_VERSION
                and bool(refresh["changes"])
                and store.manifest["research_validation_status"] == "validated_registry_rolling_features_and_frozen_inference_parity"
                and validation.get("production_approved") is False
                and validation["targets"] == validation["success"] + validation["expected_blocked"] > 0
                and 0 <= max(validation["max_raw_parity_delta"], validation["max_clipped_parity_delta"]) <= 1e-12,
                "INVALID_SNAPSHOT", "Use a published and inference-validated real successor")
        parent = store.manifest["parent_version"]
        manual = {change["change_id"]: change for change in refresh["changes"] if change["decision"] == "MANUAL_REVIEW"}
        require(set(manual) == set(refresh["reviews"]) and all(
            row["review_decision"] == "APPROVE" and row["candidate_content_sha256"] == refresh["candidate_content_sha256"]
            and row["candidate_version"] == version and row["parent_version"] == parent
            and row["review_reason"].strip() and row["evidence_reference"].strip()
            and all(row.get(field) == value for field, value in manual[key].items())
            for key, row in refresh["reviews"].items()),
            "INVALID_SNAPSHOT", "Successor is missing candidate-bound review receipts")
        version = parent
        store = engine.open(version)
        require(sha256(store.path) == refresh["parent_sha256"],
                "HISTORY_CORRUPT", "Successor parent hash mismatch")
    verify_pins(store, REAL_SHA256, REAL_MANIFEST_SHA256)
    return expected
