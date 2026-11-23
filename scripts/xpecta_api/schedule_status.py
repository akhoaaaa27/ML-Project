"""Summarize fixture evidence without scoring forecasts or substituting build time."""

from collections import Counter
import json

from scripts.multisource.forecast_eligibility import FIXTURE_MAX_AGE, utc_text


def schedule_status(engine, store, upcoming, now):
    catalogues = {row["season"]: json.loads(row["payload"]) for row in store.query("SELECT season, payload FROM catalogues")}
    evidence = Counter()
    for row in upcoming:
        catalogue = catalogues.get(row["season"])
        if catalogue and row["kickoff_utc"]:
            acquired = engine._schedule_evidence(store, row, catalogue)
            if acquired is not None:
                evidence[acquired] += 1
    groups = [
        dict(acquired_at_utc=utc_text(acquired), expires_at_utc=utc_text(acquired + FIXTURE_MAX_AGE),
             fixtures=count, status=("FUTURE" if acquired > now else
                                     "EXPIRED" if now - acquired > FIXTURE_MAX_AGE else "VALID"))
        for acquired, count in sorted(evidence.items())
    ]
    recent = sum(row["fixtures"] for row in groups if row["status"] == "VALID")
    return dict(schedule_evidence=groups, recent_review_upcoming_fixtures=recent,
                expired_review_upcoming_fixtures=sum(row["fixtures"] for row in groups if row["status"] == "EXPIRED"),
                missing_review_upcoming_fixtures=len(upcoming) - sum(evidence.values()))
