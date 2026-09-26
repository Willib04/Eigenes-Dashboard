const STATUS_BY_AMPEL = { gruen: "good", gelb: "warning", rot: "critical" };
const LABEL_BY_AMPEL = { gruen: "Grün", gelb: "Gelb", rot: "Rot" };
const CSS_VAR_BY_STATUS = {
  good: "--status-good",
  warning: "--status-warning",
  critical: "--status-critical",
  muted: "--text-muted",
};

const METRIC_LABELS = {
  hrv: "HRV",
  resting_hr: "Ruhepuls",
  sleep: "Schlaf",
  respiration: "Atmung",
};

function statusOf(ampel) {
  return STATUS_BY_AMPEL[ampel] || "muted";
}

function labelOf(ampel) {
  return LABEL_BY_AMPEL[ampel] || "Keine Daten";
}

function fmtNum(value, digits = 1, unit = "") {
  if (value === null || value === undefined) return "keine Daten";
  const rounded = Number(value).toFixed(digits);
  return `${rounded}${unit}`;
}

// Kompakte Variante fuer enge Kacheln (Stat-Tiles) - "keine Daten" wuerde dort umbrechen.
function fmtNumShort(value, digits = 1) {
  if (value === null || value === undefined) return "–";
  return Number(value).toFixed(digits);
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function el(html) {
  const template = document.createElement("template");
  template.innerHTML = html.trim();
  return template.content.firstElementChild;
}

// --- Recovery-Ring ------------------------------------------------------

function renderRecoveryRing(report, config) {
  const score = report.recovery_score;
  const ampel = report.recovery_ampel;
  const status = statusOf(ampel);
  const radius = 60;
  const circumference = 2 * Math.PI * radius;
  const pct = score === null ? 0 : Math.max(0, Math.min(100, score)) / 100;
  const dash = circumference * pct;
  const color = status === "muted" ? cssVar("--text-muted") : cssVar(CSS_VAR_BY_STATUS[status]);

  const weights = config.recovery_weights || {};
  const weightsList = Object.entries(weights)
    .map(([k, v]) => `${METRIC_LABELS[k] || k} ${Math.round(v * 100)}%`)
    .join(", ");

  const g = report.recovery_grundlage || {};

  return el(`
    <div class="card recovery-card">
      <div class="card-header" style="width:100%">
        <span class="card-title">Recovery</span>
        <button class="info-btn" data-target="info-recovery" aria-expanded="false">i</button>
      </div>
      <div class="ring-wrap">
        <svg viewBox="0 0 148 148" width="148" height="148">
          <circle class="ring-track" cx="74" cy="74" r="${radius}"></circle>
          <circle class="ring-value" cx="74" cy="74" r="${radius}" stroke="${color}"
                  stroke-dasharray="${dash} ${circumference}"></circle>
        </svg>
        <div class="ring-center">
          <span class="ring-number">${score === null ? "–" : Math.round(score)}${score === null ? "" : "%"}</span>
          <span class="ring-unit">${score === null ? "keine Daten" : "von 100"}</span>
        </div>
      </div>
      <span class="status-pill">
        <span class="status-dot dot-${status}"></span>
        <span class="status-${status}">${labelOf(ampel)}</span>
      </span>
      <div id="info-recovery" class="info-panel" hidden>
        <p>Gewichtet aus HRV-, Ruhepuls-, Schlaf- und Atemfrequenz-Abweichung zur
        28-Tage-Baseline. Gewichtung: ${weightsList}. Ampel: grün ≥ ${config.recovery_green_min},
        gelb ${config.recovery_yellow_min}–${config.recovery_green_min - 1}, sonst rot.</p>
        <div class="info-row"><span class="info-label">HRV letzte Nacht</span>
          <span class="info-value">${fmtNum(g.hrv_ms, 0, " ms")} (Baseline ${fmtNum(g.hrv_baseline_ms, 0, " ms")})</span></div>
        <div class="info-row"><span class="info-label">Ruhepuls</span>
          <span class="info-value">${fmtNum(g.resting_hr, 0)} (Baseline ${fmtNum(g.resting_hr_baseline, 0)})</span></div>
        <div class="info-row"><span class="info-label">Schlaf</span>
          <span class="info-value">${fmtNum(g.schlaf_stunden, 2, " h")} (Bedarf ${fmtNum(g.schlafbedarf_stunden, 2, " h")})</span></div>
        <div class="info-row"><span class="info-label">Atemfrequenz</span>
          <span class="info-value">${fmtNum(g.atemfrequenz, 1, "/min")} (Baseline ${fmtNum(g.atemfrequenz_baseline, 1, "/min")})</span></div>
      </div>
    </div>
  `);
}

function renderRecoveryDetail(report, config) {
  const comps = report.recovery_components || {};
  const weights = config.recovery_weights || {};
  const rows = Object.keys(METRIC_LABELS)
    .map((key) => {
      const value = comps[key];
      const width = value === null || value === undefined ? 0 : Math.max(0, Math.min(100, value));
      const weightPct = weights[key] !== undefined ? ` (${Math.round(weights[key] * 100)}%)` : "";
      return `
        <div class="meter-row">
          <span class="meter-label">${METRIC_LABELS[key]}${weightPct}</span>
          <div class="meter-track"><div class="meter-fill" style="width:${width}%"></div></div>
          <span class="meter-value">${value === null || value === undefined ? "–" : Math.round(value)}</span>
        </div>`;
    })
    .join("");

  return el(`
    <div class="card">
      <div class="card-header">
        <span class="card-title">Recovery im Detail</span>
      </div>
      ${rows}
      <p class="muted" style="font-size:12px;margin-top:8px">0–100 je Teilbereich, 50 = auf deiner Baseline.</p>
    </div>
  `);
}

// --- Strain --------------------------------------------------------------

function renderStrainCard(report, config) {
  const strain = report.strain_heute;
  const max = config.strain_scale_max || 21;
  const widthPct = strain === null ? 0 : Math.max(0, Math.min(100, (strain / max) * 100));
  const korridor = report.empfehlung_heute && report.empfehlung_heute.strain_korridor;
  let corridorStyle = "display:none";
  if (korridor) {
    const left = (korridor[0] / max) * 100;
    const width = ((korridor[1] - korridor[0]) / max) * 100;
    corridorStyle = `left:${left}%;width:${width}%`;
  }

  return el(`
    <div class="card">
      <div class="card-header">
        <span class="card-title">Strain heute</span>
        <button class="info-btn" data-target="info-strain" aria-expanded="false">i</button>
      </div>
      <div class="strain-value-row">
        <span class="hero-number">${strain === null ? "–" : strain.toFixed(1)}<span class="muted" style="font-size:16px"> / ${max}</span></span>
        <span class="muted">TRIMP ${fmtNum(report.trimp_heute, 0)}</span>
      </div>
      <div class="strain-track">
        <div class="strain-corridor" style="${corridorStyle}"></div>
        <div class="strain-fill" style="width:${widthPct}%"></div>
      </div>
      <p class="muted" style="font-size:13px">Garmin Training Load: ${fmtNum(report.garmin_training_load_heute, 0)}</p>
      <div id="info-strain" class="info-panel" hidden>
        <p>TRIMP nach Banister aus Herzfrequenz und Dauer je Aktivität, logarithmisch
        auf eine 0–${max}-Skala abgebildet (WHOOP-ähnliches Konzept, eigene
        Kalibrierung). Der blaue Bereich zeigt den empfohlenen Strain-Korridor
        für heute.</p>
      </div>
    </div>
  `);
}

// --- Schlaf ----------------------------------------------------------------

function renderSleepCard(report) {
  const need = report.schlafbedarf_heute_nacht || {};
  return el(`
    <div class="card">
      <div class="card-header">
        <span class="card-title">Schlafbedarf heute Nacht</span>
        <button class="info-btn" data-target="info-sleep" aria-expanded="false">i</button>
      </div>
      <div class="bedtime-value">${report.empfohlene_zubettgehzeit || "–"}</div>
      <p class="muted">empfohlene Zubettgehzeit (${fmtNum(need.sleep_need_hours, 2, " h")} Schlaf)</p>
      <p class="muted" style="margin-top:14px;font-size:13px">
        Letzte Nacht: ${fmtNum(report.schlaf_letzte_nacht_stunden, 2, " h")}
        (Bedarf war ${fmtNum(report.schlafbedarf_letzte_nacht_stunden, 2, " h")})
      </p>
      <div id="info-sleep" class="info-panel" hidden>
        <div class="info-row"><span class="info-label">Grundbedarf</span><span class="info-value">${fmtNum(need.base_need_hours, 2, " h")}</span></div>
        <div class="info-row"><span class="info-label">+ Strain-Aufschlag</span><span class="info-value">${fmtNum(need.strain_surcharge_hours, 2, " h")}</span></div>
        <div class="info-row"><span class="info-label">+ Schlafschuld-Abbau</span><span class="info-value">${fmtNum(need.debt_repayment_hours, 2, " h")}</span></div>
        <div class="info-row"><span class="info-label">− Nickerchen</span><span class="info-value">${fmtNum(need.nap_hours, 2, " h")}</span></div>
        <p style="margin-top:8px">Nickerchen werden aktuell immer als 0 angenommen, da Garmin
        Connect keinen direkt abrufbaren Nap-Wert liefert.</p>
      </div>
    </div>
  `);
}

// --- Empfehlung --------------------------------------------------------

function renderRecommendationCard(report) {
  const rec = report.empfehlung_heute || {};
  const status = statusOf(report.recovery_ampel);
  const korridor = rec.strain_korridor;

  return el(`
    <div class="card card-span-2 recommendation-card status-${status}">
      <div class="card-header">
        <span class="card-title">Empfehlung heute</span>
      </div>
      <p class="recommendation-text">${rec.empfehlung || "Keine Empfehlung möglich."}</p>
      ${korridor ? `<p class="recommendation-range">Ziel-Strain-Korridor: ${korridor[0]}–${korridor[1]}</p>` : ""}
    </div>
  `);
}

// --- Trainingsbelastung ------------------------------------------------

function renderLoadCard(report) {
  const acwrNote = {
    warnung_zu_hoch: "Warnung: deutlich höher als gewohnt",
    hinweis_zu_niedrig: "Hinweis: eher niedrig",
    im_zielbereich: "im Zielbereich",
  }[report.acwr_flag] || "";

  return el(`
    <div class="card card-span-2">
      <div class="card-header">
        <span class="card-title">Trainingsbelastung</span>
        <button class="info-btn" data-target="info-load" aria-expanded="false">i</button>
      </div>
      <div class="stat-grid">
        <div class="stat-tile"><div class="value">${fmtNumShort(report.ctl, 1)}</div><div class="label">CTL (Fitness)</div></div>
        <div class="stat-tile"><div class="value">${fmtNumShort(report.atl, 1)}</div><div class="label">ATL (Ermüdung)</div></div>
        <div class="stat-tile"><div class="value">${fmtNumShort(report.tsb, 1)}</div><div class="label">TSB (Form)</div></div>
        <div class="stat-tile"><div class="value">${fmtNumShort(report.acwr, 2)}</div><div class="label">ACWR</div></div>
      </div>
      <p class="muted" style="font-size:13px;margin-top:10px">${acwrNote}</p>
      <div id="info-load" class="info-panel" hidden>
        <p><strong>CTL</strong> (Chronic Training Load, 42-Tage-Mittel) = Fitness.
        <strong>ATL</strong> (Acute Training Load, 7-Tage-Mittel) = Ermüdung.
        <strong>TSB</strong> = CTL − ATL = Form (positiv = frisch, negativ = müde).
        <strong>ACWR</strong> = Verhältnis akute (7T) zu chronische (28T) Belastung –
        Warnung über 1,5, Hinweis unter 0,8.</p>
      </div>
    </div>
  `);
}

// --- Warnbanner ----------------------------------------------------------

function renderWarningBanner() {
  return el(`
    <div class="warning-banner">
      <span class="icon">⚠️</span>
      <p>Deine HRV liegt seit mehreren Tagen unter deiner Baseline und dein Ruhepuls
      gleichzeitig darüber. Das <strong>kann</strong> auf beginnende Überlastung oder
      einen Infekt hindeuten – ist aber keine Diagnose. Beobachte es und erhole dich,
      falls du dich auch subjektiv nicht fit fühlst.</p>
    </div>
  `);
}

// --- Hilfsfunktionen fuer alle Seiten ---------------------------------------

function wireInfoButtons(root) {
  root.querySelectorAll(".info-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const panel = document.getElementById(btn.dataset.target);
      if (!panel) return;
      const isHidden = panel.hasAttribute("hidden");
      if (isHidden) {
        panel.removeAttribute("hidden");
      } else {
        panel.setAttribute("hidden", "");
      }
      btn.setAttribute("aria-expanded", String(isHidden));
    });
  });
}

function appendChartCard(content, title, chart, span = 2, note = "") {
  const card = el(`
    <div class="card card-span-${span}">
      <div class="card-header"><span class="card-title">${title}</span></div>
      ${chart.html}
      ${note ? `<p class="muted chart-note">${note}</p>` : ""}
    </div>
  `);
  content.appendChild(card);
  chart.attach();
  return card;
}

function buildSelector(current, options, onChange) {
  const container = document.createElement("div");
  container.className = "form-row";
  options.forEach((opt) => {
    const btn = document.createElement("button");
    btn.className = "btn btn-secondary btn-small";
    btn.textContent = opt.label;
    btn.style.opacity = opt.value === current ? "1" : "0.55";
    btn.addEventListener("click", () => onChange(opt.value));
    container.appendChild(btn);
  });
  return container;
}

function weekSelector(current, onChange) {
  return buildSelector(
    current,
    [
      { label: "4W", value: 4 },
      { label: "12W", value: 12 },
      { label: "26W", value: 26 },
      { label: "1J", value: 52 },
    ],
    onChange
  );
}

function daySelector(current, onChange) {
  return buildSelector(
    current,
    [
      { label: "7T", value: 7 },
      { label: "30T", value: 30 },
      { label: "90T", value: 90 },
      { label: "1J", value: 365 },
    ],
    onChange
  );
}

function pageHeader(content, title) {
  const header = el(`<div class="card card-span-2"><h2 class="page-title">${title}</h2></div>`);
  content.appendChild(header);
  return header;
}

// --- Seite: Heute ------------------------------------------------------

async function renderHeute(content) {
  const [report, config] = await Promise.all([
    fetch("/api/report").then((r) => r.json()),
    fetch("/api/config").then((r) => r.json()),
  ]);

  const dateObj = new Date(report.date + "T00:00:00");
  document.getElementById("today-date").textContent = dateObj.toLocaleDateString("de-DE", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });

  content.innerHTML = "";
  content.appendChild(renderRecoveryRing(report, config));
  content.appendChild(renderRecoveryDetail(report, config));
  content.appendChild(renderStrainCard(report, config));
  content.appendChild(renderSleepCard(report));
  content.appendChild(renderRecommendationCard(report));
  content.appendChild(renderLoadCard(report));
  if (report.warnsignal_ueberlastung) {
    content.appendChild(renderWarningBanner());
  }

  wireInfoButtons(content);
}

// --- Seite: Schlaf -----------------------------------------------------

function phaseBar(sleepRow) {
  if (!sleepRow || sleepRow.total_sleep_seconds == null) {
    return `<p class="muted">Keine Schlafdaten für die letzte Nacht.</p>`;
  }
  const phases = [
    { key: "deep_sleep_seconds", label: "Tief", color: "var(--accent)" },
    { key: "light_sleep_seconds", label: "Leicht", color: "var(--status-good)" },
    { key: "rem_sleep_seconds", label: "REM", color: "var(--status-warning)" },
    { key: "awake_seconds", label: "Wach", color: "var(--text-muted)" },
  ];
  const total = sleepRow.total_sleep_seconds + (sleepRow.awake_seconds || 0);
  const segments = phases
    .map((p) => {
      const seconds = sleepRow[p.key] || 0;
      const pct = total ? (seconds / total) * 100 : 0;
      return `<div style="width:${pct}%;background:${p.color}" title="${p.label}: ${(seconds / 60).toFixed(0)} min"></div>`;
    })
    .join("");
  const legend = phases
    .map((p) => {
      const seconds = sleepRow[p.key] || 0;
      const h = Math.floor(seconds / 3600);
      const m = Math.round((seconds % 3600) / 60);
      return `<span class="legend-item"><span class="legend-swatch" style="background:${p.color}"></span>${p.label}: ${h}h ${m}min</span>`;
    })
    .join("");
  return `
    <div style="display:flex;height:14px;border-radius:999px;overflow:hidden;margin-bottom:10px">${segments}</div>
    <div class="chart-legend">${legend}</div>
  `;
}

async function renderSchlaf(content, weeks = 12) {
  const [trends, sleepLast, report] = await Promise.all([
    fetch(`/api/trends?weeks=${weeks}`).then((r) => r.json()),
    fetch(`/api/sleep`).then((r) => (r.ok ? r.json() : null)),
    fetch(`/api/report`).then((r) => r.json()),
  ]);

  content.innerHTML = "";
  const header = pageHeader(content, "Schlaf");
  header.appendChild(weekSelector(weeks, (w) => renderSchlaf(content, w)));

  const lastNightCard = el(`
    <div class="card card-span-2">
      <div class="card-header"><span class="card-title">Letzte Nacht</span></div>
      ${phaseBar(sleepLast)}
      <p class="muted" style="margin-top:8px">
        Gesamt: ${fmtNum(report.schlaf_letzte_nacht_stunden, 2, " h")} ·
        Zubettgehzeit heute empfohlen: ${report.empfohlene_zubettgehzeit || "–"}
      </p>
    </div>
  `);
  content.appendChild(lastNightCard);

  const durationChart = lineChart(
    trends.sleep_hours,
    [{ field: "value", label: "Schlafdauer", color: cssVar("--accent"), unit: " h" }],
    { valueFormatter: (v) => v.toFixed(1) }
  );
  appendChartCard(content, "Schlafdauer", durationChart);

  const scoreChart = lineChart(
    trends.sleep_score,
    [{ field: "value", label: "Schlafscore", color: cssVar("--status-good") }],
    { valueFormatter: (v) => Math.round(v) }
  );
  appendChartCard(content, "Schlafscore", scoreChart);

  const consistency = trends.sleep_consistency_minutes;
  const consistencyText =
    consistency === null
      ? "keine Daten (zu wenige Nächte mit erfasster Zubettgehzeit)"
      : `± ${Math.round(consistency)} Minuten Schwankung`;
  content.appendChild(
    el(`
      <div class="card">
        <div class="card-header"><span class="card-title">Schlafkonsistenz</span></div>
        <p class="recommendation-text">${consistencyText}</p>
        <p class="muted" style="font-size:12px;margin-top:8px">
          Standardabweichung deiner Zubettgehzeit über die letzten ${weeks} Wochen - niedriger ist konsistenter.
        </p>
      </div>
    `)
  );
}

// --- Seite: Erholung -----------------------------------------------------

async function renderErholung(content, weeks = 12) {
  const [recoveryHistory, trends] = await Promise.all([
    fetch(`/api/recovery_history?weeks=${weeks}`).then((r) => r.json()),
    fetch(`/api/trends?weeks=${weeks}`).then((r) => r.json()),
  ]);

  content.innerHTML = "";
  const header = pageHeader(content, "Erholung");
  header.appendChild(weekSelector(weeks, (w) => renderErholung(content, w)));

  const recoveryChart = lineChart(
    recoveryHistory,
    [{ field: "recovery_score", label: "Recovery", color: cssVar("--accent") }],
    { valueFormatter: (v) => Math.round(v) }
  );
  appendChartCard(content, "Recovery-Score", recoveryChart);

  const hrvChart = lineChart(
    trends.hrv,
    [
      { field: "value", label: "HRV", color: cssVar("--accent"), unit: " ms" },
      { field: "baseline", label: "Baseline", color: cssVar("--text-muted"), dashed: true, unit: " ms" },
    ],
    { valueFormatter: (v) => Math.round(v) }
  );
  appendChartCard(content, "HRV", hrvChart);

  const rhrChart = lineChart(
    trends.resting_hr,
    [
      { field: "value", label: "Ruhepuls", color: cssVar("--status-critical") },
      { field: "baseline", label: "Baseline", color: cssVar("--text-muted"), dashed: true },
    ],
    { valueFormatter: (v) => Math.round(v) }
  );
  appendChartCard(content, "Ruhepuls", rhrChart);

  const bbChart = lineChart(
    trends.body_battery_max,
    [{ field: "value", label: "Body Battery (Tageshöchstwert)", color: cssVar("--status-good") }],
    { valueFormatter: (v) => Math.round(v) }
  );
  appendChartCard(content, "Body Battery", bbChart);

  const stressChart = lineChart(
    trends.stress_avg,
    [{ field: "value", label: "Stress (Ø)", color: cssVar("--status-warning") }],
    { valueFormatter: (v) => Math.round(v) }
  );
  appendChartCard(content, "Stress", stressChart);
}

// --- Seite: Belastung ----------------------------------------------------

async function renderBelastung(content, days = 90) {
  const history = await fetch(`/api/history?days=${days}`).then((r) => r.json());

  content.innerHTML = "";
  const header = pageHeader(content, "Belastung");
  header.appendChild(daySelector(days, (d) => renderBelastung(content, d)));

  const ctlAtlChart = lineChart(
    history,
    [
      { field: "ctl", label: "CTL (Fitness)", color: cssVar("--accent") },
      { field: "atl", label: "ATL (Ermüdung)", color: cssVar("--status-warning") },
    ],
    { valueFormatter: (v) => Math.round(v) }
  );
  appendChartCard(content, "CTL / ATL", ctlAtlChart);

  const tsbChart = lineChart(
    history,
    [{ field: "tsb", label: "TSB (Form)", color: cssVar("--status-good") }],
    { valueFormatter: (v) => Math.round(v) }
  );
  appendChartCard(content, "TSB (Form)", tsbChart, 2, "Positiv = frisch, negativ = müde.");

  const strainChart = lineChart(
    history,
    [{ field: "strain", label: "Strain", color: cssVar("--accent") }],
    { valueFormatter: (v) => v.toFixed(1), minZero: true }
  );
  appendChartCard(content, "Täglicher Strain", strainChart);

  const acwrChart = lineChart(
    history,
    [{ field: "acwr", label: "ACWR", color: cssVar("--status-critical") }],
    { valueFormatter: (v) => v.toFixed(2) }
  );
  appendChartCard(content, "ACWR (akut:chronisch)", acwrChart, 2, "Warnung > 1,5, Hinweis < 0,8.");
}

// --- Seite: Trends -------------------------------------------------------

async function renderTrends(content, weeks = 12) {
  const [trends, racePrediction] = await Promise.all([
    fetch(`/api/trends?weeks=${weeks}`).then((r) => r.json()),
    fetch(`/api/race_predictions/latest`).then((r) => (r.ok ? r.json() : null)),
  ]);

  content.innerHTML = "";
  const header = pageHeader(content, "Trends");
  header.appendChild(weekSelector(weeks, (w) => renderTrends(content, w)));

  if (trends.vo2max_running.length > 0) {
    const vo2Chart = lineChart(
      trends.vo2max_running,
      [{ field: "value", label: "VO2max", color: cssVar("--accent") }],
      { valueFormatter: (v) => v.toFixed(1) }
    );
    appendChartCard(content, "VO2max (Laufen)", vo2Chart, 2, "Nur Tage mit neuer Garmin-Messung, dazwischen linear verbunden.");
  } else {
    content.appendChild(
      el(`<div class="card card-span-2"><div class="card-header"><span class="card-title">VO2max</span></div><p class="muted">Keine VO2max-Daten im gewählten Zeitraum.</p></div>`)
    );
  }

  if (racePrediction) {
    const fmtTime = (seconds) => {
      if (seconds === null || seconds === undefined) return "keine Daten";
      const m = Math.floor(seconds / 60);
      const s = Math.round(seconds % 60);
      return `${m}:${String(s).padStart(2, "0")}`;
    };
    content.appendChild(
      el(`
        <div class="card card-span-2">
          <div class="card-header"><span class="card-title">Wettkampfprognosen (Garmin, Stand ${racePrediction.date})</span></div>
          <div class="stat-grid">
            <div class="stat-tile"><div class="value">${fmtTime(racePrediction.time_5k_seconds)}</div><div class="label">5 km</div></div>
            <div class="stat-tile"><div class="value">${fmtTime(racePrediction.time_10k_seconds)}</div><div class="label">10 km</div></div>
            <div class="stat-tile"><div class="value">${fmtTime(racePrediction.time_half_marathon_seconds)}</div><div class="label">Halbmarathon</div></div>
            <div class="stat-tile"><div class="value">${fmtTime(racePrediction.time_marathon_seconds)}</div><div class="label">Marathon</div></div>
          </div>
        </div>
      `)
    );
  }

  const consistency = trends.sleep_consistency_minutes;
  content.appendChild(
    el(`
      <div class="card">
        <div class="card-header"><span class="card-title">Schlafkonsistenz</span></div>
        <p class="recommendation-text">${consistency === null ? "keine Daten" : `± ${Math.round(consistency)} Minuten`}</p>
      </div>
    `)
  );
}

// --- Seite: Aktivitäten --------------------------------------------------

function formatDuration(seconds) {
  if (!seconds) return "–";
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}min` : `${m} min`;
}

function formatPace(minPerKm) {
  if (!minPerKm) return "–";
  const m = Math.floor(minPerKm);
  const s = Math.round((minPerKm - m) * 60);
  return `${m}:${String(s).padStart(2, "0")} min/km`;
}

async function renderAktivitaeten(content, days = 30) {
  const activities = await fetch(`/api/activities?days=${days}`).then((r) => r.json());

  content.innerHTML = "";
  const header = pageHeader(content, "Aktivitäten");
  header.appendChild(daySelector(days, (d) => renderAktivitaeten(content, d)));

  if (activities.length === 0) {
    content.appendChild(el(`<div class="card card-span-2"><p class="muted">Keine Aktivitäten im gewählten Zeitraum.</p></div>`));
    return;
  }

  const rows = activities
    .map((a) => {
      const distanceKm = a.distance_m ? (a.distance_m / 1000).toFixed(2) + " km" : "";
      return `
        <div class="list-row">
          <div class="list-row-main">
            <span class="list-row-title">${a.name || a.activity_type || "Aktivität"}</span>
            <span class="muted">${a.date} · ${a.activity_type || ""}</span>
          </div>
          <div style="text-align:right">
            <div>${formatDuration(a.duration_seconds)} ${distanceKm ? "· " + distanceKm : ""}</div>
            <div class="muted">
              ${a.avg_pace_min_per_km ? formatPace(a.avg_pace_min_per_km) + " · " : ""}
              ${a.avg_hr ? "Ø " + Math.round(a.avg_hr) + " bpm" : ""}
              ${a.training_load ? " · Load " + Math.round(a.training_load) : ""}
            </div>
          </div>
        </div>`;
    })
    .join("");

  content.appendChild(el(`<div class="card card-span-2">${rows}</div>`));
}

// --- Seite: Trainingsplan --------------------------------------------------

const PHASE_LABELS = {
  schaerfung: "Schärfung",
  entlastung: "Entlastung",
  taper: "Taper",
};

const WORKOUT_TYPE_LABELS = {
  easy: "Locker",
  tempo: "Tempo",
  intervals: "Intervalle",
  long: "Lang",
  strength: "Kraft",
  rest: "Ruhe",
  race: "Wettkampf",
};

function workoutStatusBadge(status) {
  const map = { erledigt: "erledigt", verpasst: "verpasst", heute: "heute", geplant: "geplant" };
  const cls = map[status] || "geplant";
  return `<span class="badge badge-${cls}">${status}</span>`;
}

async function sendWorkoutToGarmin(workoutId, button) {
  const confirmed = window.confirm(
    "Diesen Workout jetzt an Garmin Connect senden?\n\n" +
      "Hinweis: Diese Funktion wurde nicht gegen einen echten Garmin-Account getestet. " +
      "Prüfe danach in der Garmin-Connect-App, ob der Workout korrekt ankommt."
  );
  if (!confirmed) return;

  button.disabled = true;
  button.textContent = "Sende …";
  try {
    const res = await fetch(`/api/plan/workouts/${workoutId}/send-to-garmin`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Unbekannter Fehler");
    button.textContent = "Gesendet ✓";
  } catch (err) {
    alert("Senden fehlgeschlagen: " + err.message);
    button.disabled = false;
    button.textContent = "An Garmin senden";
  }
}

async function renderTrainingsplanForm(content, planConfig) {
  content.innerHTML = "";
  pageHeader(content, "Trainingsplan");

  const goalMinutes = Math.floor(planConfig.goal_time_seconds / 60);
  const goalSeconds = planConfig.goal_time_seconds % 60;

  const formCard = el(`
    <div class="card card-span-2">
      <div class="card-header"><span class="card-title">Noch kein aktiver Plan</span></div>
      <p class="muted">Erstelle einen periodisierten Plan für dein Ziel. Die Werte kannst du vor dem
      Erstellen anpassen, dauerhaft in <code>app/plan_config.py</code>.</p>
      <div class="form-row">
        <label>Wochen <input type="number" id="plan-weeks" value="${planConfig.goal_weeks}" min="2" max="8" /></label>
        <label>Distanz (m) <input type="number" id="plan-distance" value="${planConfig.goal_distance_m}" /></label>
        <label>Zielzeit (min:sek) <input type="text" id="plan-time" value="${goalMinutes}:${String(Math.round(goalSeconds)).padStart(2, "0")}" /></label>
      </div>
      <button class="btn" id="generate-plan-btn">Plan erstellen</button>
    </div>
  `);
  content.appendChild(formCard);

  formCard.querySelector("#generate-plan-btn").addEventListener("click", async () => {
    const weeks = parseInt(document.getElementById("plan-weeks").value, 10);
    const distance = parseFloat(document.getElementById("plan-distance").value);
    const timeParts = document.getElementById("plan-time").value.split(":").map(Number);
    const timeSeconds = timeParts.length === 2 ? timeParts[0] * 60 + timeParts[1] : planConfig.goal_time_seconds;

    await fetch("/api/plan/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal_weeks: weeks, goal_distance_m: distance, goal_time_seconds: timeSeconds }),
    });
    renderTrainingsplan(content);
  });
}

async function renderTrainingsplan(content) {
  const [planData, planConfig] = await Promise.all([
    fetch("/api/plan").then((r) => r.json()),
    fetch("/api/plan_config").then((r) => r.json()),
  ]);

  if (!planData.plan) {
    await renderTrainingsplanForm(content, planConfig);
    return;
  }

  content.innerHTML = "";
  const header = pageHeader(content, "Trainingsplan");
  const regenBtn = document.createElement("button");
  regenBtn.className = "btn btn-secondary btn-small";
  regenBtn.textContent = "Plan neu erstellen";
  regenBtn.addEventListener("click", async () => {
    if (!window.confirm("Neuen Plan erstellen? Der aktuelle Plan bleibt in der Historie, ist aber nicht mehr aktiv.")) return;
    await fetch("/api/plan/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    renderTrainingsplan(content);
  });
  header.appendChild(regenBtn);

  const goalDate = new Date(planData.plan.goal_date + "T00:00:00").toLocaleDateString("de-DE");
  const goalMinutes = Math.floor(planData.plan.goal_time_seconds / 60);
  content.appendChild(
    el(`
      <div class="card card-span-2">
        <p class="muted">
          Ziel: ${(planData.plan.goal_distance_m / 1000).toFixed(1)} km in unter ${goalMinutes} Minuten,
          Wettkampf/Zeitfahren am ${goalDate}.
        </p>
      </div>
    `)
  );

  const byWeek = new Map();
  for (const w of planData.workouts) {
    if (!byWeek.has(w.week_number)) byWeek.set(w.week_number, []);
    byWeek.get(w.week_number).push(w);
  }
  const fulfillmentByWeek = new Map(planData.weekly_fulfillment.map((f) => [f.week_number, f]));

  const listCard = el(`<div class="card card-span-2"></div>`);
  content.appendChild(listCard);

  for (const [weekNumber, workouts] of [...byWeek.entries()].sort((a, b) => a[0] - b[0])) {
    const fulfillment = fulfillmentByWeek.get(weekNumber);
    const quoteText = fulfillment && fulfillment.quote_prozent !== null
      ? `${fulfillment.erledigt}/${fulfillment.geplant} erledigt (${fulfillment.quote_prozent}%)`
      : "";
    listCard.appendChild(
      el(`<div class="week-header"><span class="section-title">Woche ${weekNumber + 1} · ${PHASE_LABELS[workouts[0].phase] || workouts[0].phase}</span><span class="muted">${quoteText}</span></div>`)
    );

    for (const w of workouts) {
      const row = el(`
        <div class="list-row">
          <div class="list-row-main">
            <span class="list-row-title">${w.date} · ${WORKOUT_TYPE_LABELS[w.workout_type] || w.workout_type}: ${w.title}</span>
            <span class="muted">${w.description}</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            ${workoutStatusBadge(w.status)}
            ${w.workout_type !== "rest" ? `<button class="btn btn-secondary btn-small" data-workout-id="${w.id}">${w.sent_to_garmin_at ? "Erneut senden" : "An Garmin senden"}</button>` : ""}
          </div>
        </div>
      `);
      listCard.appendChild(row);
      const sendBtn = row.querySelector("button[data-workout-id]");
      if (sendBtn) {
        sendBtn.addEventListener("click", () => sendWorkoutToGarmin(w.id, sendBtn, content));
      }
    }
  }
}

// --- Seite: Chat -----------------------------------------------------------

async function renderChat(content) {
  const status = await fetch("/api/chat/status").then((r) => r.json());

  content.innerHTML = "";
  pageHeader(content, "Chat");

  if (!status.konfiguriert) {
    content.appendChild(
      el(`
        <div class="card card-span-2">
          <p class="muted">Kein <code>ANTHROPIC_API_KEY</code> in der <code>.env</code> hinterlegt.
          Trag deinen Claude-API-Key ein und starte das Dashboard neu, um den Chat zu nutzen.</p>
        </div>
      `)
    );
    return;
  }

  const chatCard = el(`
    <div class="card card-span-2">
      <div class="chat-log" id="chat-log"></div>
      <div class="chat-input-row">
        <input type="text" id="chat-input" placeholder="z.B. 'Ich bin Dienstag krank, verschieb die Einheit'" />
        <button class="btn" id="chat-send">Senden</button>
      </div>
    </div>
  `);
  content.appendChild(chatCard);

  const log = chatCard.querySelector("#chat-log");
  const input = chatCard.querySelector("#chat-input");
  const sendBtn = chatCard.querySelector("#chat-send");

  function addBubble(text, who) {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble chat-bubble-${who}`;
    bubble.textContent = text;
    log.appendChild(bubble);
    log.scrollTop = log.scrollHeight;
    return bubble;
  }

  function addProposal(vorschlag) {
    const items = vorschlag
      .map((c) => {
        if (c.aktion === "verschieben") return `<li>Workout #${c.workout_id} verschieben auf ${c.neues_datum}</li>`;
        if (c.aktion === "loeschen") return `<li>Workout #${c.workout_id} streichen</li>`;
        return `<li>Workout #${c.workout_id} ändern${c.neuer_typ ? " zu " + c.neuer_typ : ""}</li>`;
      })
      .join("");
    const card = document.createElement("div");
    card.className = "proposal-card";
    card.innerHTML = `<strong>Vorgeschlagene Änderungen:</strong><ul>${items}</ul><button class="btn btn-small">Übernehmen</button>`;
    log.appendChild(card);
    log.scrollTop = log.scrollHeight;

    card.querySelector("button").addEventListener("click", async () => {
      card.querySelector("button").disabled = true;
      try {
        const res = await fetch("/api/chat/apply", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ aenderungen: vorschlag }),
        });
        if (!res.ok) throw new Error((await res.json()).detail || "Fehler");
        card.innerHTML = "<em>Übernommen ✓</em>";
      } catch (err) {
        alert("Konnte Änderungen nicht übernehmen: " + err.message);
      }
    });
  }

  async function send() {
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    addBubble(message, "user");
    sendBtn.disabled = true;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Fehler");
      addBubble(data.antwort, "coach");
      if (data.vorschlag) addProposal(data.vorschlag);
    } catch (err) {
      addBubble("Fehler: " + err.message, "coach");
    } finally {
      sendBtn.disabled = false;
    }
  }

  sendBtn.addEventListener("click", send);
  input.addEventListener("keydown", (evt) => {
    if (evt.key === "Enter") send();
  });
}

// --- Router ------------------------------------------------------------

const ROUTES = {
  heute: renderHeute,
  schlaf: renderSchlaf,
  erholung: renderErholung,
  belastung: renderBelastung,
  trainingsplan: renderTrainingsplan,
  aktivitaeten: renderAktivitaeten,
  trends: renderTrends,
  chat: renderChat,
};

function setActiveTab(tabName) {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("tab-active", btn.dataset.tab === tabName);
  });
}

async function navigate(tabName) {
  if (!ROUTES[tabName]) tabName = "heute";
  setActiveTab(tabName);
  const content = document.getElementById("content");
  content.innerHTML = '<p class="muted">Lade …</p>';
  try {
    await ROUTES[tabName](content);
  } catch (err) {
    content.innerHTML = `<p class="muted">Fehler beim Laden: ${err.message}</p>`;
  }
}

document.getElementById("tabs").addEventListener("click", (evt) => {
  const btn = evt.target.closest(".tab");
  if (!btn) return;
  window.location.hash = btn.dataset.tab;
});

window.addEventListener("hashchange", () => {
  navigate(window.location.hash.slice(1));
});

navigate(window.location.hash ? window.location.hash.slice(1) : "heute");
