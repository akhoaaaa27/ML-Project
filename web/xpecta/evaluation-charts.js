export function evaluationCharts(points, format, escape) {
  const labels = point => `${point.date} · ${point.team} vs ${point.opponent}`;
  const hover = (point, suffix) => {
    const tip = escape(`${labels(point)} · ${suffix}`);
    return `data-tip="${tip}"><title>${tip}</title>`;
  };
  const svg = (width, height, label, contents) =>
    `<svg class="chart-svg evaluation-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${label}">${contents}</svg>`;
  const plotSize = 318;
  const left = 58;
  const top = 16;
  const bottom = top + plotSize;
  const right = left + plotSize;
  const max = Math.ceil(Math.max(1, ...points.flatMap(row => [row.observed, row.predicted])));
  const x = value => left + value * plotSize / max;
  const y = value => bottom - value * plotSize / max;
  const tick = value => Number.isInteger(value) ? value : value.toFixed(1);
  const grid = Array.from({length: 6}, (_, i) => {
    const value = max * i / 5;
    return `<path class="evaluation-grid" d="M${left} ${y(value)} H${right} M${x(value)} ${top} V${bottom}"/>
      <text x="${left - 10}" y="${y(value) + 4}" text-anchor="end">${tick(value)}</text>
      <text x="${x(value)}" y="${bottom + 18}" text-anchor="middle">${tick(value)}</text>`;
  }).join("");
  const scatter = svg(398, 381, "Observed versus predicted team xG", `${grid}
    <line class="evaluation-reference" x1="${left}" x2="${right}" y1="${bottom}" y2="${top}"/>
    ${points.map(row => `<circle class="evaluation-point" cx="${x(row.observed)}" cy="${y(row.predicted)}" r="3.1"
      ${hover(row, `Observed ${format(row.observed)} xG · Predicted ${format(row.predicted)} xG`)}</circle>`).join("")}
    <text x="${left + plotSize / 2}" y="373" text-anchor="middle">Observed xG</text>
    <text x="15" y="${top + plotSize / 2}" text-anchor="middle" transform="rotate(-90 15 ${top + plotSize / 2})">Predicted xG</text>`);

  const sample = points.filter((_, i) => i % 9 === 0);
  const residualOf = row => row.observed - row.predicted;
  const bound = Math.ceil(Math.max(1, ...points.map(row => Math.abs(residualOf(row)))));
  const residualWidth = 318;
  const zero = (top + bottom) / 2;
  const scale = value => zero - value * plotSize / (2 * bound);
  const barWidth = residualWidth / sample.length;
  const residualGrid = [bound, bound / 2, 0, -bound / 2, -bound].map(value =>
    `<path class="${value === 0 ? "evaluation-reference" : "evaluation-grid"}" d="M${left} ${scale(value)} H${right}"/>
    <text x="${left - 10}" y="${scale(value) + 4}" text-anchor="end">${tick(value)}</text>`).join("");
  const residual = svg(398, 381, "Residuals, observed minus predicted xG", `${residualGrid}
    ${sample.map((row, i) => {
      const delta = residualOf(row);
      const position = scale(delta);
      return `<rect class="evaluation-bar ${delta < 0 ? "negative" : ""}" x="${left + i * barWidth}"
        y="${Math.min(position, zero)}" width="${barWidth * .83}" height="${Math.max(.6, Math.abs(position - zero))}"
        ${hover(row, `Residual ${format(delta)} xG`)}</rect>`;
    }).join("")}
    <text x="${left}" y="${bottom + 18}">1</text><text x="${right}" y="${bottom + 18}" text-anchor="end">${sample.length}</text>
    <text x="${left + residualWidth / 2}" y="373" text-anchor="middle">Chronological sample</text>
    <text x="15" y="${zero}" text-anchor="middle" transform="rotate(-90 15 ${zero})">Observed − predicted (xG)</text>`);
  return {scatter, residual, sampleSize: sample.length};
}
