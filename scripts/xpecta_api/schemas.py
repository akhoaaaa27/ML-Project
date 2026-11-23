"""Typed API inputs and the deliberately limited public output fields."""

from datetime import date, datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .settings import Mode

TeamId = Annotated[str, StringConstraints(min_length=1, max_length=60, pattern=r"^[\w .'-]+$")]
FixtureKey = Annotated[str, StringConstraints(min_length=25, max_length=160,
                     pattern=r"^research:laliga:[0-9]{4}:[\w .'-]+:[\w .'-]+$")]
ForecastId = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
SHA256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Season = Annotated[int, Field(ge=2019, le=2100)]
Count = Annotated[int, Field(ge=0)]
Xg = Annotated[float, Field(ge=0, allow_inf_nan=False)]
EligibilityStatus = Literal["READY", "EARLY_READY", "WAITING_DATA", "UNAVAILABLE"]
ObservedStatus = Literal["scheduled", "completed", "live", "postponed", "cancelled", "unverified"]
MatchStatus = Literal["VERIFIED_COMPLETED", "SCHEDULED", "SOURCE_CONFLICT", "UNVERIFIED"]
StatisticsStatus = Literal["COMPLETE_STATISTICS", "PENDING_UPDATE", "SOURCE_CONFLICT", "UNVERIFIED"]
HistoryStatus = Literal["COMPLETE", "INSUFFICIENT_HISTORY", "INCOMPLETE_STATISTICS", "ZERO_HISTORY"]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PageQuery(StrictInput):
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=25, ge=1, le=100)


class TeamQuery(PageQuery):
    season: Season | None = None


class FixtureQuery(TeamQuery):
    home: TeamId | None = None
    away: TeamId | None = None
    status: ObservedStatus | None = None
    upcoming: bool = False


class KeyQuery(StrictInput):
    fixture_key: FixtureKey


class ForecastQuery(PageQuery):
    fixture_key: FixtureKey | None = None


class CompareQuery(KeyQuery):
    v1: ForecastId
    v2: ForecastId


class TeamStatsQuery(StrictInput):
    team: TeamId
    season: Season


class AnalysisQuery(StrictInput):
    home: TeamId
    away: TeamId
    season: Season
    window: Literal["5", "10"] = "5"


class ForecastRequest(KeyQuery):
    model_config = ConfigDict(extra="forbid", strict=True)


class PreviewBinding(StrictInput):
    history_database_sha256: SHA256
    features_sha256: SHA256


class PublishRequest(ForecastRequest):
    expected: PreviewBinding | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class Live(BaseModel):
    status: Literal["ALIVE"] = "ALIVE"
    api_version: str


class Ready(BaseModel):
    status: Literal["READY", "UNAVAILABLE"]
    mode: Mode
    snapshot_version: str
    model_version: str | None = None
    reason: str | None = None
    frontend_available: bool
    production_approved: Literal[False] = False


class Team(BaseModel):
    id: TeamId
    name: str
    seasons: list[int]


class Fixture(BaseModel):
    canonical_fixture_key: FixtureKey
    season: Season
    home_team: TeamId
    away_team: TeamId
    match_date: date
    kickoff_utc: datetime | None
    observed_status: ObservedStatus
    match_status: MatchStatus
    statistics_status: StatisticsStatus
    snapshot_version: str
    verified_at: datetime


Item = TypeVar("Item")


class Page(BaseModel, Generic[Item]):
    items: list[Item]
    total: Count
    offset: Count
    limit: Count


class Bootstrap(BaseModel):
    api_version: str
    mode: Mode
    label: str
    snapshot_version: str
    model_version: str
    operator_writes_enabled: bool
    seasons: list[int]
    current_season: Season
    production_approved: Literal[False] = False


class ScheduleEvidence(BaseModel):
    acquired_at_utc: datetime
    expires_at_utc: datetime
    fixtures: Count
    status: Literal["VALID", "EXPIRED", "FUTURE"]


class DataStatus(BaseModel):
    mode: Mode
    snapshot_version: str
    database_sha256: str
    build_timestamp: datetime
    evaluated_at_utc: datetime
    latest_verified_completed_date: date | None
    schedule_max_age_hours: int
    upcoming_fixtures: Count
    recent_review_upcoming_fixtures: Count
    expired_review_upcoming_fixtures: Count
    missing_review_upcoming_fixtures: Count
    schedule_evidence: list[ScheduleEvidence]
    schedule_freshness: Literal["VERIFIED", "PARTIAL", "UNVERIFIED", "NO_UPCOMING", "HISTORICAL_ONLY"]
    registry_fixtures: Count
    verified_completed: Count
    complete_statistics: Count
    pending_statistics: Count
    conflicts: Count
    unverified: Count
    temporal_policy: str
    production_approved: Literal[False] = False


class Eligibility(BaseModel):
    canonical_fixture_key: FixtureKey
    snapshot_version: str
    eligibility_status: EligibilityStatus
    reason: str | None
    target: Fixture | None = None
    history_cutoff: date | None = None
    fixture_reviewed_at_utc: datetime | None = None
    generated_at_utc: datetime
    intermediate_fixtures: list[FixtureKey] = Field(default_factory=list)
    production_approved: Literal[False] = False


class Candidate(BaseModel):
    canonical_fixture_key: FixtureKey
    history_snapshot_version: str
    history_database_sha256: str
    model_version: str
    model_artifact_sha256: str
    features_sha256: SHA256
    eligibility_status: Literal["READY", "EARLY_READY"]
    generated_at_utc: datetime
    history_cutoff: date
    home_xg: Xg
    away_xg: Xg
    source_notice: str
    source_semantics: str
    dataset_kind: Literal["real", "synthetic"]
    demo_label: Literal["SYNTHETIC_DEMO"] | None = None
    production_approved: Literal[False] = False


class PublishedForecast(Candidate):
    forecast_id: ForecastId
    forecast_revision: int
    forecast_stage: Literal["INITIAL", "UPDATED"]
    previous_forecast_id: ForecastId | None
    record_sha256: str
    home_team: TeamId
    away_team: TeamId
    target_match_date: date


class ForecastAction(BaseModel):
    status: Literal["READY", "EARLY_READY", "WAITING_DATA", "UNAVAILABLE", "PUBLISHED", "NO_CHANGE", "FORECAST_ERROR"]
    eligibility: Eligibility | None = None
    preview: Candidate | None = None
    forecast: PublishedForecast | None = None
    evaluated_eligibility_status: EligibilityStatus | None = None
    evaluated_snapshot_version: str | None = None
    error: ErrorDetail | None = None
    production_approved: Literal[False] = False


class ChangedFeature(BaseModel):
    feature: str
    before: tuple[float | None, float | None]
    after: tuple[float | None, float | None]


class Comparison(BaseModel):
    fixture_key: FixtureKey
    v1: PublishedForecast
    v2: PublishedForecast
    home_xg_delta: float
    away_xg_delta: float
    schedule_notice: str | None
    changed_features: list[ChangedFeature]
    unchanged_features: list[str]
    production_approved: Literal[False] = False


class HistoricalSummary(BaseModel):
    verified_fixtures: Count
    observed_xg_fixtures: Count
    missing_xg_fixtures: Count
    wins: Count
    draws: Count
    losses: Count
    goals_for: Count
    goals_against: Count
    mean_xg: Xg | None
    mean_xga: Xg | None
    xg_sources: dict[str, int]
    mean_shots: Xg | None
    mean_sot: Xg | None
    shots_sources: dict[str, int]
    clean_sheets: Count


class TrendPoint(BaseModel):
    date: date
    venue: Literal["home", "away"]
    opponent: TeamId
    goals_for: Count
    goals_against: Count
    xg: Xg | None
    xga: Xg | None
    source: str | None


class TeamStats(BaseModel):
    team: TeamId
    season: Season
    snapshot_version: str
    mode: Mode
    status: HistoryStatus
    overall: HistoricalSummary
    home: HistoricalSummary
    away: HistoricalSummary
    trend: list[TrendPoint]


class MatchAnalysis(BaseModel):
    snapshot_version: str
    mode: Mode
    season: Season
    window: int
    as_of_exclusive: date
    home: TeamStats
    away: TeamStats
    head_to_head: HistoricalSummary
    head_to_head_matches: list[TrendPoint]


class EvaluationMetric(BaseModel):
    label: str
    source: str
    period: str
    fixtures: Count
    observations: Count
    mae: Xg
    rmse: Xg
    baseline_mae: Xg | None = None


class ModelSummary(BaseModel):
    model: Literal["Linear Regression"]
    model_version: str
    artifact_sha256: str
    features: list[str]
    target_semantics: str
    clipping_policy: str
    training_start: date
    training_end: date
    training_observations: Count
    phase7: list[EvaluationMetric]
    retrospective: list[EvaluationMetric]
    scientific_conclusion: str
    evaluation_notice: str
    production_approved: Literal[False] = False
