const prefix = kind => `xpecta.simulation.v1.${kind}.`;
const digest = value => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const text = value => typeof value === "string" && value.length > 0 && value.length <= 80;

export function validSimulation(row, kind) {
  return row?.dataset_kind === kind && row.production_approved === false &&
    text(row.home_team) && text(row.away_team) && row.home_team !== row.away_team &&
    Number.isInteger(row.season) && row.season >= 2019 &&
    /^\d{4}-\d{2}-\d{2}$/.test(row.history_cutoff) &&
    /Z$/.test(row.generated_at_utc) && Number.isFinite(Date.parse(row.generated_at_utc)) &&
    text(row.model_version) && text(row.history_snapshot_version) &&
    [row.home_xg, row.away_xg].every(value => Number.isFinite(value) && value >= 0) &&
    [row.history_database_sha256, row.model_artifact_sha256, row.features_sha256].every(digest);
}

export function saveSimulation(row, kind) {
  if (!validSimulation(row, kind)) throw new Error("The simulation result could not be verified.");
  const simulation_id = crypto.randomUUID();
  localStorage.setItem(prefix(kind) + simulation_id, JSON.stringify({...row, simulation_id, record_type: "CUSTOM_SIMULATION"}));
}

export function simulationHistory(kind) {
  const rows = [];
  let warning = "";
  try {
    for (const key of Object.keys(localStorage).filter(value => value.startsWith(prefix(kind)))) {
      let row;
      try { row = JSON.parse(localStorage.getItem(key)); } catch { /* A malformed entry is skipped. */ }
      const id = key.slice(prefix(kind).length);
      if (row?.simulation_id === id && /^[a-f0-9-]{36}$/.test(id) && validSimulation(row, kind)) {
        rows.push({...row, record_type: "CUSTOM_SIMULATION"});
      } else warning = "Some saved simulations could not be read.";
    }
  } catch {
    warning = "Local simulation history is unavailable.";
  }
  return {rows, warning};
}
