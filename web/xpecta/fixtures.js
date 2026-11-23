const PAGE_SIZE = 12;

const normalize = value => value.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim().replace(/\s+/g, " ");
const kickoff = row => Date.parse(row.kickoff_utc);
const dateKey = time => new Date(time).toISOString().slice(0, 10);

export function fixturePage(rows, filters, requestedPage, evaluatedAt) {
  const now = Date.parse(evaluatedAt);
  const day = dateKey(now);
  const query = normalize(filters.search || "");
  const invalidRange = Boolean(filters.start && filters.end && filters.start > filters.end);
  const matches = invalidRange ? [] : rows.filter(row => {
    const at = kickoff(row);
    if (filters.status === "upcoming") {
      if (row.observed_status !== "scheduled" || row.match_date < day || (Number.isFinite(at) && at <= now)) return false;
    } else if (filters.status && row.observed_status !== filters.status) return false;
    if (filters.team && ![row.home_team, row.away_team].includes(filters.team)) return false;
    if (query && ![row.home_team, row.away_team].some(team => normalize(team).includes(query))) return false;
    if (filters.start || filters.end) {
      if (!Number.isFinite(at)) return false;
      const kickoffDay = dateKey(at);
      if ((filters.start && kickoffDay < filters.start) || (filters.end && kickoffDay > filters.end)) return false;
    }
    return true;
  }).sort((a, b) => {
    const first = kickoff(a), second = kickoff(b);
    if (Number.isFinite(first) && Number.isFinite(second) && first !== second) return first - second;
    if (Number.isFinite(first) !== Number.isFinite(second)) return Number.isFinite(first) ? -1 : 1;
    return a.canonical_fixture_key < b.canonical_fixture_key ? -1 : Number(a.canonical_fixture_key > b.canonical_fixture_key);
  });
  const total = matches.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.max(1, Math.min(requestedPage, pages));
  const start = (page - 1) * PAGE_SIZE;
  return {items: matches.slice(start, start + PAGE_SIZE), total, page, pages,
    first: total ? start + 1 : 0, last: Math.min(start + PAGE_SIZE, total), invalidRange};
}
