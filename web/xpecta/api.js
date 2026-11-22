const root = "/api/v1";

export class ApiError extends Error {
  constructor(message, code) {
    super(message);
    this.code = code;
  }
}

const isObject = value => value !== null && typeof value === "object" && !Array.isArray(value);
const isPage = value => isObject(value) && Array.isArray(value.items) && Number.isInteger(value.total);
const hasKeys = (...keys) => value => isObject(value) && keys.every(key => Object.hasOwn(value, key));
const isForecast = value => hasKeys("canonical_fixture_key", "model_version", "history_cutoff")(value) &&
  [value.home_xg, value.away_xg].every(number => Number.isFinite(number) && number >= 0);
const isEligibility = value => hasKeys("eligibility_status", "reason")(value) &&
  ["READY", "EARLY_READY", "WAITING_DATA", "UNAVAILABLE"].includes(value.eligibility_status);
const isPreview = value => isObject(value) && (
  ["READY", "EARLY_READY"].includes(value.status) ? isForecast(value.preview) :
  ["WAITING_DATA", "UNAVAILABLE", "FORECAST_ERROR"].includes(value.status) && isEligibility(value.eligibility)
);

async function request(path, {query = {}, body, validate = isObject} = {}) {
  const params = new URLSearchParams(Object.entries(query).filter(([, value]) => value != null));
  const url = root + path + (params.size ? `?${params}` : "");
  const options = {credentials: "same-origin", signal: AbortSignal.timeout(12000)};
  if (body !== undefined) {
    Object.assign(options, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
  }
  let response, payload;
  try {
    response = await fetch(url, options);
    payload = await response.json();
  } catch {
    throw new ApiError("The local XPECTA service did not respond.", "LOCAL_API_UNAVAILABLE");
  }
  if (!response.ok) {
    throw new ApiError(payload?.error?.message || "XPECTA could not complete this request.",
      payload?.error?.code || "HTTP_ERROR");
  }
  if (!validate(payload)) throw new ApiError("XPECTA returned an unexpected response.", "INVALID_RESPONSE");
  return payload;
}

async function allPages(path, query = {}) {
  const items = [];
  const limit = 100;
  for (let offset = 0; ; offset += limit) {
    const page = await request(path, {query: {...query, offset, limit}, validate: isPage});
    items.push(...page.items);
    if (!page.items.length || items.length >= page.total) return items;
  }
}

export const api = {
  bootstrap: () => request("/bootstrap", {validate: hasKeys("mode", "seasons", "current_season", "snapshot_version")}),
  teams: () => allPages("/teams"),
  fixtures: query => allPages("/fixtures", query),
  dataStatus: () => request("/data-status", {validate: hasKeys("schedule_freshness", "verified_completed")}),
  preview: fixture_key => request("/forecasts/preview", {body: {fixture_key}, validate: isPreview}),
  history: () => allPages("/forecasts"),
  forecast: id => request(`/forecasts/${encodeURIComponent(id)}`, {validate: isForecast}),
  compare: query => request("/forecasts/compare", {query, validate: hasKeys("v1", "v2", "changed_features")}),
  teamStats: (team, season) => request("/historical/team-stats", {query: {team, season}, validate: hasKeys("overall", "trend", "status")}),
  analysis: query => request("/historical/match-analysis", {query, validate: hasKeys("home", "away", "head_to_head", "window")}),
  model: () => request("/model/summary", {validate: hasKeys("model", "features", "phase7", "retrospective")}),
};
