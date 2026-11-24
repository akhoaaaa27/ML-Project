"""Stage a reviewed Real Research snapshot and its selection for Git delivery."""

import argparse
import json
import os
import subprocess
import sys

from scripts.inference.common import InferenceError, ROOT, sha256
from scripts.multisource.forecast_eligibility import ForecastEligibility
from scripts.multisource.match_registry import require
from scripts.multisource.refresh_composite import write_json

from .research_binding import verify_real_snapshot
from .settings import REAL_VERSION, SHARED_SNAPSHOT, Settings


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def snapshot_files(store):
    manifest = store.path.with_name("manifest.json")
    require(not manifest.is_symlink(), "INVALID_SNAPSHOT", "Use the manifest in the published version directory")
    return store.path, manifest


def release_plan(version):
    require(version != REAL_VERSION, "INVALID_SNAPSHOT", "V3 is already shared as the baseline")
    engine = ForecastEligibility()
    store = engine.open(version)
    files = snapshot_files(store)
    selection = dict(snapshot_version=version, snapshot_sha256=sha256(files[0]),
                     snapshot_manifest_sha256=sha256(files[1]))
    verify_real_snapshot(engine, store, Settings(**selection))

    while store.manifest["version_id"] != REAL_VERSION:
        parent = store.manifest["parent_version"]
        store = engine.open(parent)
        for file in snapshot_files(store):
            path = file.relative_to(ROOT).as_posix()
            try:
                indexed = git("rev-parse", "--verify", f":{path}")
            except subprocess.CalledProcessError:
                indexed = ""
            require(indexed == git("hash-object", "--no-filters", "--", path),
                    "UNSHARED_PARENT", f"Share parent {parent} with its original bytes before sharing {version}")
    return selection, tuple(file.relative_to(ROOT).as_posix() for file in files)


def stage_release(version):
    lock_path = ForecastEligibility().root / ".refresh.lock"
    lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        selection, files = release_plan(version)
        configuration = SHARED_SNAPSHOT.relative_to(ROOT).as_posix()
        require(not SHARED_SNAPSHOT.is_symlink(), "INVALID_SNAPSHOT", "Use a regular shared configuration file")
        previous = SHARED_SNAPSHOT.read_bytes() if SHARED_SNAPSHOT.exists() else None
        write_json(SHARED_SNAPSHOT, selection)
        try:
            git("add", "--force", "--", *files, configuration)
        except (OSError, subprocess.CalledProcessError):
            if previous is None:
                SHARED_SNAPSHOT.unlink()
            else:
                SHARED_SNAPSHOT.write_bytes(previous)
            raise
        return selection
    finally:
        os.close(lock)
        lock_path.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Published snapshot whose data and embedded review may be shared")
    parser.add_argument("--check", action="store_true", help="Validate without staging files or changing the active version")
    args = parser.parse_args(argv)
    try:
        if args.check:
            selection, _ = release_plan(args.version)
        else:
            selection = stage_release(args.version)
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.strip() or "Git could not stage the snapshot", file=sys.stderr)
        return 1
    except (InferenceError, OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(dict(selection, status="VERIFIED" if args.check else "STAGED")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
