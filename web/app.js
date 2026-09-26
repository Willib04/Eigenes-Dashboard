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

// --- Hauptlogik ------------------------------------------------------------

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

async function loadDashboard() {
  const content = document.getElementById("content");
  const dateEl = document.getElementById("today-date");

  try {
    const [report, config] = await Promise.all([
      fetch("/api/report").then((r) => r.json()),
      fetch("/api/config").then((r) => r.json()),
    ]);

    const dateObj = new Date(report.date + "T00:00:00");
    dateEl.textContent = dateObj.toLocaleDateString("de-DE", {
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
  } catch (err) {
    content.innerHTML = `<p class="muted">Konnte keine Daten laden: ${err.message}. Läuft der Sync/Backfill schon?</p>`;
  }
}

loadDashboard();
