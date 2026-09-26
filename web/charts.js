// Wiederverwendbare, einfache SVG-Liniengrafik (kein Chart-Framework).
// Duenne Linien (2px, runde Enden), zurueckhaltende Gitterlinien, Legende
// bei mehreren Serien, Hover-Tooltip mit Fadenkreuz - eine Y-Achse pro Chart.

function formatShortDate(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
}

function buildLineChart(rows, seriesDefs, options = {}) {
  const width = options.width || 600;
  const height = options.height || 200;
  const paddingLeft = 36;
  const paddingBottom = 22;
  const paddingTop = 10;
  const paddingRight = 10;
  const plotWidth = width - paddingLeft - paddingRight;
  const plotHeight = height - paddingTop - paddingBottom;
  const valueFormatter = options.valueFormatter || ((v) => Math.round(v * 10) / 10);

  const allValues = [];
  for (const s of seriesDefs) {
    for (const row of rows) {
      const v = row[s.field];
      if (v !== null && v !== undefined) allValues.push(v);
    }
  }
  let min = allValues.length ? Math.min(...allValues) : 0;
  let max = allValues.length ? Math.max(...allValues) : 1;
  if (options.minZero) min = Math.min(min, 0);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const pad = (max - min) * 0.12;
  min -= pad;
  max += pad;

  const n = rows.length;
  const xFor = (i) => paddingLeft + (n <= 1 ? plotWidth / 2 : (i / (n - 1)) * plotWidth);
  const yFor = (v) => paddingTop + plotHeight - ((v - min) / (max - min)) * plotHeight;

  function pathFor(field) {
    let d = "";
    let drawing = false;
    rows.forEach((row, i) => {
      const v = row[field];
      if (v === null || v === undefined) {
        drawing = false;
        return;
      }
      const x = xFor(i);
      const y = yFor(v);
      d += (drawing ? " L " : " M ") + x.toFixed(1) + " " + y.toFixed(1);
      drawing = true;
    });
    return d;
  }

  const gridLines = [];
  const gridCount = 4;
  for (let i = 0; i <= gridCount; i++) {
    const v = min + ((max - min) * i) / gridCount;
    const y = yFor(v);
    gridLines.push(
      `<line x1="${paddingLeft}" y1="${y.toFixed(1)}" x2="${width - paddingRight}" y2="${y.toFixed(1)}" class="chart-grid"></line>`
    );
    gridLines.push(
      `<text x="${paddingLeft - 6}" y="${(y + 3).toFixed(1)}" class="chart-axis-label" text-anchor="end">${valueFormatter(v)}</text>`
    );
  }

  const xLabels = [];
  const labelCount = Math.min(5, n);
  for (let i = 0; i < labelCount; i++) {
    const idx = Math.round((i / Math.max(1, labelCount - 1)) * (n - 1));
    const x = xFor(idx);
    xLabels.push(
      `<text x="${x.toFixed(1)}" y="${height - 4}" class="chart-axis-label" text-anchor="middle">${formatShortDate(rows[idx].date)}</text>`
    );
  }

  const paths = seriesDefs
    .map((s) => {
      const d = pathFor(s.field);
      const dashArray = s.dashed ? ' stroke-dasharray="4 3"' : "";
      return `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"${dashArray}></path>`;
    })
    .join("");

  const svgId = "chart-" + Math.random().toString(36).slice(2, 9);

  const legend =
    seriesDefs.length > 1
      ? `<div class="chart-legend">${seriesDefs
          .map((s) => `<span class="legend-item"><span class="legend-swatch" style="background:${s.color}"></span>${s.label}</span>`)
          .join("")}</div>`
      : "";

  const html = `
    <div class="chart-wrap">
      <svg viewBox="0 0 ${width} ${height}" class="chart-svg" id="${svgId}" preserveAspectRatio="none">
        ${gridLines.join("")}
        ${paths}
        <g class="chart-hover" style="display:none">
          <line class="chart-crosshair" x1="0" x2="0" y1="${paddingTop}" y2="${paddingTop + plotHeight}"></line>
        </g>
        ${xLabels.join("")}
      </svg>
      <div class="chart-tooltip" style="display:none"></div>
    </div>
    ${legend}
  `;

  return { html, svgId, xFor, paddingLeft, plotWidth, n, valueFormatter };
}

function attachChartInteraction(chartMeta, rows, seriesDefs) {
  const svg = document.getElementById(chartMeta.svgId);
  if (!svg) return;
  const wrap = svg.closest(".chart-wrap");
  const tooltip = wrap.querySelector(".chart-tooltip");
  const hoverGroup = svg.querySelector(".chart-hover");
  const crosshair = svg.querySelector(".chart-crosshair");

  function handleMove(evt) {
    const rect = svg.getBoundingClientRect();
    const scale = svg.viewBox.baseVal.width / rect.width;
    const xInSvg = (evt.clientX - rect.left) * scale;
    const relative = (xInSvg - chartMeta.paddingLeft) / chartMeta.plotWidth;
    let idx = Math.round(relative * (chartMeta.n - 1));
    idx = Math.max(0, Math.min(chartMeta.n - 1, idx));

    const x = chartMeta.xFor(idx);
    crosshair.setAttribute("x1", x);
    crosshair.setAttribute("x2", x);
    hoverGroup.style.display = "block";

    const row = rows[idx];
    const lines = seriesDefs
      .map((s) => {
        const v = row[s.field];
        const formatted = v === null || v === undefined ? "keine Daten" : chartMeta.valueFormatter(v) + (s.unit || "");
        return `<div><span class="legend-swatch" style="background:${s.color}"></span>${s.label}: ${formatted}</div>`;
      })
      .join("");
    tooltip.innerHTML = `<div class="tooltip-date">${row.date}</div>${lines}`;
    tooltip.style.display = "block";

    const wrapRect = wrap.getBoundingClientRect();
    let left = evt.clientX - wrapRect.left + 12;
    if (left + 170 > wrapRect.width) left = evt.clientX - wrapRect.left - 172;
    tooltip.style.left = left + "px";
    tooltip.style.top = Math.max(0, evt.clientY - wrapRect.top - 50) + "px";
  }

  svg.addEventListener("mousemove", handleMove);
  svg.addEventListener("mouseleave", () => {
    hoverGroup.style.display = "none";
    tooltip.style.display = "none";
  });
}

// Baut die Grafik UND haengt die Interaktion an - Aufrufer muss das html
// erst ins DOM einfuegen, dann attach() aufrufen.
function lineChart(rows, seriesDefs, options = {}) {
  const meta = buildLineChart(rows, seriesDefs, options);
  return { html: meta.html, attach: () => attachChartInteraction(meta, rows, seriesDefs) };
}
