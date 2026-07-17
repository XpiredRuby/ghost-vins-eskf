(() => {
  "use strict";

  const DATA_URL = "data/GHOST_INTERACTIVE_SHOWCASE_DATA.json";
  const REPLAY_URL = "data/GHOST_HARDWARE_REPLAY_20260716.json";

  const COLORS = {
    measured: "#58d6e7",
    synthetic: "#f3b763",
    verification: "#76a9ff",
    failure: "#ff7f86",
    green: "#6fd8a8",
    purple: "#b9a0ff",
    cv: "#9fb1c4",
    imm: "#58d6e7",
    mh: "#f3b763",
    measurement: "#f1f6fb",
    grid: "rgba(157, 183, 207, 0.14)",
    paper: "#08131f",
    plot: "#08131f",
    text: "#dce8f2",
    muted: "#879bb0",
  };

  const PLOT_CONFIG = {
    responsive: true,
    displaylogo: false,
    scrollZoom: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
  };

  const state = {
    data: null,
    replay: null,
    replayTime: 0,
    playing: false,
    speed: 1,
    animationFrame: null,
    previousFrameTime: null,
    activeStage: 0,
    activeOcclusionScenario: "short_hide",
    activeResponseScenario: "lateral_motion",
    faultFilter: "",
    faultSort: "fault",
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatNumber(value, digits = 4) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "Not retained";
    const number = Number(value);
    if (Number.isInteger(number)) return number.toLocaleString();
    return number.toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: digits,
    });
  }

  function formatMeters(value, digits = 4) {
    return value === null || value === undefined ? "Not retained" : `${formatNumber(value, digits)} m`;
  }

  function formatMilliseconds(value, digits = 4) {
    return value === null || value === undefined ? "Not retained" : `${formatNumber(value, digits)} ms`;
  }

  function formatSeconds(value, digits = 4) {
    return value === null || value === undefined ? "Not retained" : `${formatNumber(value, digits)} s`;
  }

  function badgeClass(dataClass) {
    const key = String(dataClass || "").toUpperCase();
    if (key === "MEASURED_HARDWARE") return "measured";
    if (key === "SYNTHETIC_SOFTWARE") return "synthetic";
    if (key === "VERIFICATION") return "verification";
    if (key === "MIXED_EVIDENCE") return "mixed";
    return "verification";
  }

  function badgeLabel(dataClass) {
    const labels = {
      MEASURED_HARDWARE: "Measured hardware",
      SYNTHETIC_SOFTWARE: "Synthetic software",
      VERIFICATION: "Verification",
      MIXED_EVIDENCE: "Mixed evidence",
    };
    return labels[dataClass] || String(dataClass || "Evidence").replaceAll("_", " ");
  }

  function evidenceBadge(dataClass, extra = "") {
    return `<span class="evidence-badge ${badgeClass(dataClass)}">${escapeHtml(extra || badgeLabel(dataClass))}</span>`;
  }

  function plotLayout(overrides = {}) {
    return {
      paper_bgcolor: COLORS.paper,
      plot_bgcolor: COLORS.plot,
      font: { color: COLORS.text, family: "Inter, system-ui, sans-serif", size: 11 },
      margin: { l: 62, r: 24, t: 35, b: 58 },
      hoverlabel: { bgcolor: "#102236", bordercolor: "rgba(255,255,255,.22)", font: { color: "#fff" } },
      legend: { orientation: "h", y: 1.12, x: 0, font: { size: 10 } },
      xaxis: { gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, automargin: true },
      yaxis: { gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, automargin: true },
      ...overrides,
    };
  }

  function requirePlotly() {
    if (!window.Plotly) throw new Error("Plotly.js did not load.");
    return window.Plotly;
  }

  async function loadJson(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
    return response.json();
  }

  function renderHero() {
    const container = $("#hero-metrics");
    container.innerHTML = state.data.hero_metrics.map((metric) => {
      const isFailure = metric.status === "NOT_MET";
      const badge = isFailure
        ? `<span class="evidence-badge failure">Requirement not met</span>`
        : evidenceBadge(metric.badge);
      return `
        <article class="metric-card ${isFailure ? "status-not-met" : ""}">
          <div class="metric-top">${badge}<span class="evidence-badge ${isFailure ? "failure" : "verification"}">${escapeHtml(metric.status.replaceAll("_", " "))}</span></div>
          <strong class="metric-value">${escapeHtml(metric.display)}</strong>
          <p>${escapeHtml(metric.label)}</p>
          <small>${escapeHtml(metric.sample_basis)} · ${escapeHtml(metric.source)}</small>
        </article>`;
    }).join("");
  }

  function renderMission() {
    const mission = state.data.mission;
    $("#mission-stats").innerHTML = [
      [mission.obstacle_occlusion_count, "simulated obstacle occlusions"],
      [mission.reacquisition_count, "simulated reacquisitions"],
      [`${formatNumber(mission.observer_distance_traveled_m, 4)} m`, "observer distance traveled"],
      [mission.collision_count, "reported collisions"],
      [mission.out_of_bounds_count, "out-of-bounds events"],
      [`${formatNumber(mission.elapsed_s, 4)} s`, "mission elapsed time"],
    ].map(([value, label]) => `<div><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`).join("");
  }

  function renderArchitecture() {
    const stages = state.data.system_stages;
    const rail = $("#stage-rail");
    rail.innerHTML = stages.map((stage, index) => `
      <button class="stage-button" id="stage-tab-${escapeHtml(stage.id)}" type="button" role="tab"
        aria-selected="${index === state.activeStage}" aria-controls="stage-detail" tabindex="${index === state.activeStage ? 0 : -1}" data-stage-index="${index}">
        <span class="stage-number">${escapeHtml(stage.number)}</span>
        <strong>${escapeHtml(stage.name)}</strong>
        <small>${escapeHtml(stage.summary)}</small>
      </button>`).join("");

    $$(".stage-button", rail).forEach((button) => {
      button.addEventListener("click", () => selectStage(Number(button.dataset.stageIndex)));
      button.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        let next = state.activeStage;
        if (event.key === "ArrowRight") next = (state.activeStage + 1) % stages.length;
        if (event.key === "ArrowLeft") next = (state.activeStage - 1 + stages.length) % stages.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = stages.length - 1;
        selectStage(next, true);
      });
    });
    selectStage(0);
    $("#imu-status").textContent = state.data.imu_status.statement;
  }

  function detailList(title, values) {
    return `<div><strong>${escapeHtml(title)}</strong><ul>${values.map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul></div>`;
  }

  function selectStage(index, focus = false) {
    state.activeStage = index;
    const stage = state.data.system_stages[index];
    $$(".stage-button").forEach((button, buttonIndex) => {
      button.setAttribute("aria-selected", String(buttonIndex === index));
      button.tabIndex = buttonIndex === index ? 0 : -1;
    });
    const active = $$(".stage-button")[index];
    if (focus && active) active.focus();
    $("#stage-detail").innerHTML = `
      ${evidenceBadge(stage.badge)}
      <h3>${escapeHtml(stage.number)} · ${escapeHtml(stage.name)}</h3>
      <p>${escapeHtml(stage.summary)}</p>
      <div class="stage-detail-grid">
        ${detailList("Inputs", stage.inputs)}
        ${detailList("Outputs", stage.outputs)}
        ${detailList("Failure modes", stage.failure_modes)}
      </div>
      <p class="stage-evidence"><strong>Evidence:</strong> ${stage.evidence.map(escapeHtml).join(" · ")}</p>`;
  }

  // No smoothing or interpolation: cursor readouts use the latest actual sample at or before the selected time.
  function latestAtOrBefore(rows, time) {
    let low = 0;
    let high = rows.length - 1;
    let result = null;
    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      if (rows[mid].t_s <= time) {
        result = rows[mid];
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }
    return result;
  }

  function buildEventShapes(events) {
    const colorMap = {
      OCCLUSION_START: COLORS.failure,
      REACQUIRED: COLORS.green,
      RESET: COLORS.failure,
      TARGET_LOCK: COLORS.measured,
      TRACKER_INITIALIZED: COLORS.verification,
    };
    return events
      .filter((event) => colorMap[event.event])
      .map((event) => ({
        type: "line", xref: "x", yref: "paper", x0: event.t_s, x1: event.t_s, y0: 0, y1: 1,
        line: { color: colorMap[event.event], width: event.event === "RESET" ? 2 : 1, dash: "dot" },
      }));
  }

  function renderReplay() {
    const replay = state.replay;
    const scrubber = $("#replay-scrubber");
    scrubber.min = 0;
    scrubber.max = replay.duration_s;
    scrubber.step = 0.01;
    scrubber.value = 0;

    $("#replay-provenance-summary").textContent = `${replay.measurements.length} recorded vision samples · ${replay.imm_estimates.length} IMM records · ${replay.mh_estimates.length} GHOST-MH records`;
    $("#replay-provenance").innerHTML = Object.values(replay.provenance).map((source) => `
      <div class="hash-row"><strong>${escapeHtml(source.logical_name)}</strong><code>${escapeHtml(source.sha256)}</code><span>${Number(source.size_bytes).toLocaleString()} bytes</span></div>`).join("");

    $("#replay-play").addEventListener("click", toggleReplay);
    $("#replay-reset").addEventListener("click", () => {
      stopReplay();
      setReplayTime(0);
    });
    scrubber.addEventListener("input", () => {
      stopReplay();
      setReplayTime(Number(scrubber.value));
    });
    $("#replay-speed").addEventListener("change", (event) => {
      state.speed = Number(event.target.value);
    });

    renderReplayCharts();
    setReplayTime(0);
  }

  function renderReplayCharts() {
    const Plotly = requirePlotly();
    const replay = state.replay;
    const measurement = replay.measurements;
    const imm = replay.imm_estimates;
    const mh = replay.mh_estimates;

    const xyTraces = [
      {
        x: measurement.map((row) => row.x_m), y: measurement.map((row) => row.y_m),
        mode: "markers", name: "Recorded measurement", marker: { size: 4, color: COLORS.measurement, opacity: 0.55 },
        customdata: measurement.map((row) => row.t_s), hovertemplate: "Measured<br>x=%{x:.5f} m<br>y=%{y:.5f} m<br>t=%{customdata:.3f} s<extra></extra>",
      },
      {
        x: imm.map((row) => row.x_m), y: imm.map((row) => row.y_m),
        mode: "lines+markers", name: "Formal IMM — recorded subset", line: { color: COLORS.imm, width: 1.5 }, marker: { size: 3 },
        customdata: imm.map((row) => row.t_s), hovertemplate: "IMM recorded sample<br>x=%{x:.5f} m<br>y=%{y:.5f} m<br>t=%{customdata:.3f} s<extra></extra>",
      },
      {
        x: mh.map((row) => row.x_m), y: mh.map((row) => row.y_m),
        mode: "lines+markers", name: "GHOST-MH — recorded subset", line: { color: COLORS.mh, width: 1.5 }, marker: { size: 3 },
        customdata: mh.map((row) => row.t_s), hovertemplate: "GHOST-MH recorded sample<br>x=%{x:.5f} m<br>y=%{y:.5f} m<br>t=%{customdata:.3f} s<extra></extra>",
      },
      { x: [null], y: [null], mode: "markers", name: "Current measurement", marker: { size: 13, color: COLORS.measurement, line: { color: "#08131f", width: 2 } }, hoverinfo: "skip", showlegend: false },
      { x: [null], y: [null], mode: "markers", name: "Current IMM", marker: { size: 12, color: COLORS.imm, symbol: "diamond", line: { color: "#08131f", width: 2 } }, hoverinfo: "skip", showlegend: false },
      { x: [null], y: [null], mode: "markers", name: "Current MH", marker: { size: 12, color: COLORS.mh, symbol: "square", line: { color: "#08131f", width: 2 } }, hoverinfo: "skip", showlegend: false },
    ];
    Plotly.newPlot("replay-xy-chart", xyTraces, plotLayout({
      margin: { l: 66, r: 22, t: 48, b: 62 },
      xaxis: { title: "Camera-frame X (m)", gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, automargin: true },
      yaxis: { title: "Camera-frame Y (m)", gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, automargin: true, scaleanchor: "x", scaleratio: 1 },
      legend: { orientation: "h", y: 1.13, x: 0, font: { size: 10 } },
      uirevision: "replay-xy",
    }), PLOT_CONFIG);

    const eventShapes = buildEventShapes(replay.events);
    const timeTraces = [
      {
        x: measurement.map((row) => row.t_s), y: measurement.map((row) => row.x_m),
        mode: "markers", name: "Recorded measurement X", marker: { size: 4, color: COLORS.measurement, opacity: 0.62 },
        hovertemplate: "Measured X=%{y:.5f} m<br>t=%{x:.3f} s<extra></extra>",
      },
      {
        x: imm.map((row) => row.t_s), y: imm.map((row) => row.x_m),
        mode: "lines+markers", name: "Formal IMM X — recorded subset", line: { color: COLORS.imm, width: 1.5 }, marker: { size: 2.5 },
        hovertemplate: "IMM X=%{y:.5f} m<br>t=%{x:.3f} s<extra></extra>",
      },
      {
        x: mh.map((row) => row.t_s), y: mh.map((row) => row.x_m),
        mode: "lines+markers", name: "GHOST-MH X — recorded subset", line: { color: COLORS.mh, width: 1.5 }, marker: { size: 2.5 },
        hovertemplate: "MH X=%{y:.5f} m<br>t=%{x:.3f} s<extra></extra>",
      },
    ];
    Plotly.newPlot("replay-time-chart", timeTraces, plotLayout({
      shapes: [...eventShapes, { type: "line", xref: "x", yref: "paper", x0: 0, x1: 0, y0: 0, y1: 1, line: { color: COLORS.verification, width: 2 } }],
      xaxis: { title: "Replay time (s)", range: [0, replay.duration_s], gridcolor: COLORS.grid, zerolinecolor: COLORS.grid },
      yaxis: { title: "Camera-frame X (m)", gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, automargin: true },
      legend: { orientation: "h", y: 1.13, x: 0, font: { size: 10 } },
      uirevision: "replay-time",
    }), PLOT_CONFIG);
  }

  function describePoint(point, cursorTime) {
    if (!point) return "No recorded sample yet";
    const age = cursorTime - point.t_s;
    return `x ${formatNumber(point.x_m, 5)} m · y ${formatNumber(point.y_m, 5)} m · sample age ${formatNumber(age, 3)} s`;
  }

  function setReplayTime(time) {
    const replay = state.replay;
    state.replayTime = Math.max(0, Math.min(Number(time), replay.duration_s));
    $("#replay-scrubber").value = state.replayTime;
    $("#replay-time").textContent = `${state.replayTime.toFixed(3)} s`;

    const measurement = latestAtOrBefore(replay.measurements, state.replayTime);
    const imm = latestAtOrBefore(replay.imm_estimates, state.replayTime);
    const mh = latestAtOrBefore(replay.mh_estimates, state.replayTime);
    const status = latestAtOrBefore(replay.status_changes, state.replayTime);
    const event = latestAtOrBefore(replay.events, state.replayTime);

    $("#replay-measurement").textContent = describePoint(measurement, state.replayTime);
    $("#replay-imm").textContent = describePoint(imm, state.replayTime);
    $("#replay-mh").textContent = describePoint(mh, state.replayTime);
    $("#replay-state").textContent = status ? status.state.replaceAll("_", " ") : "NO STATE YET";
    $("#replay-visibility").textContent = mh ? (mh.visible ? "Visible in tracker record" : "Not visible in tracker record") : "No tracker record yet";
    $("#replay-event").textContent = event ? `${event.event}: ${event.message || ""}` : "No event yet";

    if (window.Plotly && $("#replay-xy-chart").data) {
      window.Plotly.restyle("replay-xy-chart", { x: [[measurement?.x_m ?? null]], y: [[measurement?.y_m ?? null]] }, [3]);
      window.Plotly.restyle("replay-xy-chart", { x: [[imm?.x_m ?? null]], y: [[imm?.y_m ?? null]] }, [4]);
      window.Plotly.restyle("replay-xy-chart", { x: [[mh?.x_m ?? null]], y: [[mh?.y_m ?? null]] }, [5]);
      const shapes = buildEventShapes(replay.events);
      shapes.push({ type: "line", xref: "x", yref: "paper", x0: state.replayTime, x1: state.replayTime, y0: 0, y1: 1, line: { color: COLORS.verification, width: 2 } });
      window.Plotly.relayout("replay-time-chart", { shapes });
    }
  }

  function replayFrame(timestamp) {
    if (!state.playing) return;
    if (state.previousFrameTime === null) state.previousFrameTime = timestamp;
    const elapsed = (timestamp - state.previousFrameTime) / 1000;
    state.previousFrameTime = timestamp;
    const next = state.replayTime + elapsed * state.speed;
    if (next >= state.replay.duration_s) {
      setReplayTime(state.replay.duration_s);
      stopReplay();
      return;
    }
    setReplayTime(next);
    state.animationFrame = requestAnimationFrame(replayFrame);
  }

  function toggleReplay() {
    if (state.playing) {
      stopReplay();
      return;
    }
    if (state.replayTime >= state.replay.duration_s) setReplayTime(0);
    state.playing = true;
    state.previousFrameTime = null;
    $("#replay-play").textContent = "Pause";
    state.animationFrame = requestAnimationFrame(replayFrame);
  }

  function stopReplay() {
    state.playing = false;
    state.previousFrameTime = null;
    $("#replay-play").textContent = "Play";
    if (state.animationFrame) cancelAnimationFrame(state.animationFrame);
    state.animationFrame = null;
  }

  function renderEstimatorComparison() {
    const comparison = state.data.estimator_comparison;
    const estimators = comparison.estimators;
    $("#estimator-cards").innerHTML = estimators.map((estimator) => `
      <article class="estimator-card">
        ${evidenceBadge("SYNTHETIC_SOFTWARE", "Synthetic N=24")}
        <h3>${escapeHtml(estimator.name)}</h3>
        <p>${escapeHtml(estimator.observation)}</p>
        <div class="estimator-metrics">
          <div><span>Overall RMSE</span><strong>${formatMeters(estimator.overall_rmse_m, 5)}</strong></div>
          <div><span>Hidden RMSE</span><strong>${formatMeters(estimator.hidden_rmse_m, 5)}</strong></div>
          <div><span>p99 runtime</span><strong>${formatMilliseconds(estimator.p99_runtime_ms, 4)}</strong></div>
          <div><span>Max runtime</span><strong>${formatMilliseconds(estimator.max_runtime_ms, 4)}</strong></div>
          <div><span>Reacquisition time</span><strong class="metric-unavailable">Not retained symmetrically</strong></div>
          <div><span>Reset count</span><strong class="metric-unavailable">Not retained symmetrically</strong></div>
        </div>
      </article>`).join("");

    const Plotly = requirePlotly();
    const names = estimators.map((row) => row.name);
    Plotly.newPlot("estimator-rmse-chart", [
      { x: names, y: estimators.map((row) => row.overall_rmse_m), name: "Overall RMSE", type: "bar", marker: { color: COLORS.verification }, hovertemplate: "%{x}<br>Overall RMSE=%{y:.5f} m<extra></extra>" },
      { x: names, y: estimators.map((row) => row.hidden_rmse_m), name: "Hidden-period RMSE", type: "bar", marker: { color: COLORS.failure }, hovertemplate: "%{x}<br>Hidden RMSE=%{y:.5f} m<extra></extra>" },
    ], plotLayout({
      barmode: "group",
      xaxis: { gridcolor: COLORS.grid, automargin: true },
      yaxis: { title: "Position RMSE (m)", rangemode: "tozero", gridcolor: COLORS.grid, zerolinecolor: COLORS.grid },
    }), PLOT_CONFIG);

    Plotly.newPlot("estimator-runtime-chart", [
      { x: names, y: estimators.map((row) => row.p99_runtime_ms), name: "p99", type: "bar", marker: { color: COLORS.measured }, hovertemplate: "%{x}<br>p99=%{y:.4f} ms<extra></extra>" },
      { x: names, y: estimators.map((row) => row.max_runtime_ms), name: "Maximum", type: "bar", marker: { color: COLORS.synthetic }, hovertemplate: "%{x}<br>Max=%{y:.4f} ms<extra></extra>" },
    ], plotLayout({
      barmode: "group",
      xaxis: { gridcolor: COLORS.grid, automargin: true },
      yaxis: { title: "Execution time (ms)", rangemode: "tozero", gridcolor: COLORS.grid, zerolinecolor: COLORS.grid },
    }), PLOT_CONFIG);
  }

  const SCENARIO_LABELS = {
    short_hide: "Short hide",
    long_hide: "Long hide",
    lateral_motion: "Lateral motion",
    range_change: "Range change",
  };

  function metricLabel(key) {
    return key.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function flattenMetrics(metrics) {
    const rows = [];
    Object.entries(metrics).forEach(([key, value]) => {
      if (key.endsWith("_unavailable_reason")) return;
      if (value && typeof value === "object" && !Array.isArray(value)) {
        Object.entries(value).forEach(([subKey, subValue]) => rows.push([`${metricLabel(key)} · ${metricLabel(subKey)}`, subValue]));
      } else if (Array.isArray(value)) {
        rows.push([metricLabel(key), value.map((item) => formatNumber(item, 4)).join(", ")]);
      } else {
        rows.push([metricLabel(key), value]);
      }
    });
    return rows;
  }

  function formatScenarioMetric(label, value) {
    if (value === null || value === undefined) return "Not retained";
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (typeof value === "number") {
      if (/sample|count/i.test(label)) return formatNumber(value, 0);
      if (/duration|time/i.test(label)) return formatSeconds(value, 4);
      if (/error|drift|delta|baseline|hold/i.test(label)) return formatMeters(value, 5);
      return formatNumber(value, 4);
    }
    return String(value);
  }

  function renderScenarioGroup(config) {
    const scenarios = state.data[config.dataKey];
    const selector = $(config.selector);
    const activeKey = state[config.stateKey];
    selector.innerHTML = Object.keys(scenarios).map((key) => `
      <button class="scenario-button" type="button" role="tab" aria-selected="${key === activeKey}"
        tabindex="${key === activeKey ? 0 : -1}" data-scenario="${escapeHtml(key)}" data-group="${escapeHtml(config.group)}">${escapeHtml(SCENARIO_LABELS[key] || key)}</button>`).join("");
    $$(".scenario-button", selector).forEach((button) => {
      button.addEventListener("click", () => selectScenarioGroup(config, button.dataset.scenario));
      button.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const keys = Object.keys(scenarios);
        const current = keys.indexOf(state[config.stateKey]);
        let next = current;
        if (event.key === "ArrowRight") next = (current + 1) % keys.length;
        if (event.key === "ArrowLeft") next = (current - 1 + keys.length) % keys.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = keys.length - 1;
        selectScenarioGroup(config, keys[next], true);
      });
    });
    selectScenarioGroup(config, activeKey);
  }

  function selectScenarioGroup(config, key, focus = false) {
    state[config.stateKey] = key;
    $$(".scenario-button", $(config.selector)).forEach((button) => {
      const selected = button.dataset.scenario === key;
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
      if (selected && focus) button.focus();
    });
    const scenario = state.data[config.dataKey][key];
    $(config.badge).innerHTML = evidenceBadge(scenario.badge);
    $(config.title).textContent = scenario.title;
    $(config.basis).textContent = `${scenario.sample_basis} · ${scenario.source}`;
    $(config.conclusion).textContent = scenario.conclusion;
    $(config.metrics).innerHTML = flattenMetrics(scenario.metrics).map(([label, value]) => `
      <div class="scenario-metric"><span>${escapeHtml(label)}</span><strong class="${value === null ? "metric-unavailable" : ""}">${escapeHtml(formatScenarioMetric(label, value))}</strong></div>`).join("");
    renderScenarioChart(config.chart, key, scenario);
  }

  function renderScenarioChart(chartId, key, scenario) {
    const Plotly = requirePlotly();
    const metrics = scenario.metrics;
    let traces = [];
    let layout = plotLayout({ yaxis: { rangemode: "tozero", gridcolor: COLORS.grid, zerolinecolor: COLORS.grid } });

    if (key === "short_hide") {
      const errors = metrics.first_frame_errors_m;
      traces = [{
        x: ["Constant velocity", "GHOST-MH top 1", "Last-seen hold"],
        y: [errors.constant_velocity, errors.ghost_mh_top1, errors.last_seen_hold],
        type: "bar",
        marker: { color: [COLORS.cv, COLORS.mh, COLORS.green] },
        hovertemplate: "%{x}<br>Error=%{y:.5f} m<extra></extra>",
      }];
      layout.yaxis = { title: "First-reacquisition proxy error (m)", rangemode: "tozero", gridcolor: COLORS.grid, zerolinecolor: COLORS.grid };
    } else if (key === "long_hide") {
      traces = [{
        x: metrics.occlusion_durations_s.map((_, index) => `Simulated occlusion ${index + 1}`),
        y: metrics.occlusion_durations_s,
        type: "bar", marker: { color: COLORS.synthetic },
        hovertemplate: "%{x}<br>Duration=%{y:.4f} s<extra></extra>",
      }];
      layout.yaxis = { title: "Occlusion duration (s)", rangemode: "tozero", gridcolor: COLORS.grid, zerolinecolor: COLORS.grid };
    } else if (key === "lateral_motion") {
      traces = [{
        x: ["Center baseline", "Hold left", "Hold right"],
        y: [metrics.baseline_y_m, metrics.left_hold_y_m, metrics.right_hold_y_m],
        type: "bar", marker: { color: [COLORS.verification, COLORS.measured, COLORS.failure] },
        hovertemplate: "%{x}<br>Camera-frame Y=%{y:.5f} m<extra></extra>",
      }];
      layout.yaxis = { title: "Camera-frame Y (m)", gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, zerolinewidth: 2 };
    } else if (key === "range_change") {
      traces = [{
        x: ["Closer focused retest", "Farther focused run"],
        y: [metrics.closer_delta_x_m, metrics.farther_delta_x_m],
        type: "bar", marker: { color: [COLORS.measured, COLORS.verification] },
        customdata: [metrics.closer_valid_samples, metrics.farther_valid_samples],
        hovertemplate: "%{x}<br>Delta X=%{y:.5f} m<br>Recorded pose samples=%{customdata}<extra></extra>",
      }];
      layout.yaxis = { title: "Delta camera-frame X (m)", gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, zerolinewidth: 2 };
    }
    Plotly.react(chartId, traces, layout, PLOT_CONFIG);
  }

  function renderScenarioSelectors() {
    renderScenarioGroup({
      group: "occlusion", dataKey: "occlusion_scenarios", stateKey: "activeOcclusionScenario",
      selector: "#occlusion-selector", badge: "#occlusion-badge", title: "#occlusion-scenario-title",
      basis: "#occlusion-basis", conclusion: "#occlusion-conclusion", metrics: "#occlusion-metrics", chart: "occlusion-chart",
    });
    renderScenarioGroup({
      group: "response", dataKey: "response_scenarios", stateKey: "activeResponseScenario",
      selector: "#response-selector", badge: "#response-badge", title: "#response-scenario-title",
      basis: "#response-basis", conclusion: "#response-conclusion", metrics: "#response-metrics", chart: "response-chart",
    });
  }

  function renderHardware() {
    const hardware = state.data.hardware;
    const specs = [
      ["Edge computer", hardware.raspberry_pi_model, hardware.machine],
      ["Operating system", hardware.os, hardware.kernel],
      ["Middleware", `ROS 2 ${hardware.ros_distro}`, "rmw_fastrtps_cpp in runtime campaign"],
      ["Vision sensor", hardware.camera, hardware.camera_interface],
      ["Target", `${hardware.tag_family} · ID ${hardware.tag_id}`, `${hardware.tag_size_m} m nominal size`],
      ["Camera calibration", `${formatNumber(hardware.calibration_rms_reprojection_error_px, 5)} px RMS`, "Reprojection error; not absolute target accuracy"],
      ["Camera pose rate", `${formatNumber(hardware.camera_pose_hz, 2)} Hz`, "Preserved live hardware bag"],
      ["IMM output rate", `${formatNumber(hardware.imm_output_hz, 2)} Hz`, "Preserved live hardware bag"],
      ["GHOST-MH output rate", `${formatNumber(hardware.mh_output_hz, 2)} Hz`, "Preserved live hardware bag"],
      ["Environment-level process RSS", `${formatNumber(hardware.max_process_rss_mb, 4)} MB`, "Top-level environment summary"],
      ["Largest estimator-benchmark RSS", `${formatNumber(hardware.max_estimator_benchmark_rss_mb, 4)} MB`, "Maximum across the four retained estimator benchmark blocks"],
      ["Maximum temperature", `${formatNumber(hardware.max_temperature_c, 4)} °C`, "Retained runtime campaign"],
      ["Throttling status", hardware.throttled_status_final, "No throttling flag reported"],
    ];
    $("#hardware-spec-grid").innerHTML = specs.map(([label, value, note]) => `
      <article class="hardware-spec"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`).join("");
  }

  function getFilteredFaults() {
    let faults = [...state.data.fault_testing.faults];
    const query = state.faultFilter.trim().toLowerCase();
    if (query) faults = faults.filter((row) => row.fault.toLowerCase().includes(query));
    if (state.faultSort === "fault") faults.sort((a, b) => a.fault.localeCompare(b.fault));
    if (state.faultSort === "recovery-asc") faults.sort((a, b) => a.recovery_time_s - b.recovery_time_s || a.fault.localeCompare(b.fault));
    if (state.faultSort === "recovery-desc") faults.sort((a, b) => b.recovery_time_s - a.recovery_time_s || a.fault.localeCompare(b.fault));
    return faults;
  }

  function renderFaults() {
    const faultTesting = state.data.fault_testing;
    $("#fault-pass-definition").textContent = faultTesting.pass_definition;
    $("#fault-metric-boundary").textContent = faultTesting.metric_interpretation;
    $("#fault-group-summary").textContent = `${faultTesting.unique_rmse_profile_count} exact RMSE profiles and ${faultTesting.unique_recovery_time_count} exact recovery-time values appear across ${faultTesting.fault_count} cases · source stream: ${faultTesting.source_stream}`;
    $("#fault-filter").addEventListener("input", (event) => {
      state.faultFilter = event.target.value;
      updateFaultDisplay();
    });
    $("#fault-sort").addEventListener("change", (event) => {
      state.faultSort = event.target.value;
      updateFaultDisplay();
    });
    updateFaultDisplay();
  }

  function updateFaultDisplay() {
    const faults = getFilteredFaults();
    $("#fault-table-body").innerHTML = faults.map((row) => `
      <tr>
        <td><strong>${escapeHtml(row.fault.replaceAll("_", " "))}</strong></td>
        <td class="${row.detected ? "table-pass" : "table-fail"}">${row.detected ? "Yes" : "No"}</td>
        <td class="${row.isolated ? "table-pass" : "table-fail"}">${row.isolated ? "Yes" : "No"}</td>
        <td class="${row.recovery_ok ? "table-pass" : "table-fail"}">${row.recovery_ok ? "Yes" : "No"}</td>
        <td>${formatSeconds(row.recovery_time_s, 4)}</td>
        <td>${formatMeters(row.position_error_rmse_m.cv_kalman, 5)}</td>
        <td>${formatMeters(row.position_error_rmse_m.formal_imm, 5)}</td>
        <td>${formatMeters(row.position_error_rmse_m.ghost_mh, 5)}</td>
      </tr>`).join("");

    const Plotly = requirePlotly();
    Plotly.react("fault-recovery-chart", [{
      x: faults.map((row) => row.recovery_time_s),
      y: faults.map((row) => row.fault.replaceAll("_", " ")),
      type: "bar", orientation: "h", marker: { color: COLORS.synthetic },
      customdata: faults.map((row) => row.detected_at_s),
      hovertemplate: "%{y}<br>Recovery=%{x:.4f} s<br>Detected at=%{customdata:.3f} s<extra></extra>",
    }], plotLayout({
      margin: { l: 170, r: 25, t: 35, b: 55 },
      xaxis: { title: "Recovery time (s)", rangemode: "tozero", gridcolor: COLORS.grid, zerolinecolor: COLORS.grid },
      yaxis: { autorange: "reversed", gridcolor: COLORS.grid, automargin: true },
      showlegend: false,
    }), PLOT_CONFIG);
  }

  function renderRuntime() {
    const runtime = state.data.runtime;
    const requirements = runtime.requirements;
    $("#rt002-interpretation").textContent = runtime.rt002_interpretation;
    $("#deadline-anomaly-interpretation").textContent = runtime.deadline_anomaly_interpretation;
    $("#reporting-check-interpretation").textContent = runtime.reporting_check_interpretation;
    $("#deadline-row-summary").textContent = `${runtime.deadline_rows_met} of ${runtime.deadline_rows_total} measured maximum-execution rows met the deadline; ${runtime.deadline_rows_not_met} did not.`;
    const cards = [
      {
        id: "RT-001", title: "Source-to-receipt latency", row: requirements["RT-001"],
        details: [
          ["Observed p95", `${formatNumber(requirements["RT-001"].p95_ms, 4)} ms`],
          ["p95 limit", `${formatNumber(requirements["RT-001"].limits_ms.p95, 3)} ms`],
          ["Observed p99", `${formatNumber(requirements["RT-001"].p99_ms, 4)} ms`],
          ["p99 limit", `${formatNumber(requirements["RT-001"].limits_ms.p99, 3)} ms`],
          ["Samples", formatNumber(requirements["RT-001"].sample_count, 0)],
        ],
      },
      {
        id: "RT-002", title: "Publication rate and deadline", row: requirements["RT-002"],
        details: [
          ["Observed rate", `${formatNumber(requirements["RT-002"].publication_rate_hz, 4)} Hz`],
          ["Minimum rate", `${formatNumber(requirements["RT-002"].limits.minimum_rate_hz, 3)} Hz`],
          ["Deadline miss fraction", formatNumber(requirements["RT-002"].deadline_miss_fraction, 4)],
          ["Allowed miss fraction", formatNumber(requirements["RT-002"].limits.maximum_deadline_miss_fraction, 4)],
          ["Intervals", formatNumber(requirements["RT-002"].interarrival_ms.count, 0)],
        ],
      },
      {
        id: "RT-003", title: "Resource and thermal evidence", row: requirements["RT-003"],
        details: [
          ["Thermal samples", formatNumber(requirements["RT-003"].thermal_sample_count, 0)],
          ["Throttling clear", requirements["RT-003"].throttling_clear ? "Yes" : "No"],
          ["Max temperature", `${formatNumber(state.data.hardware.max_temperature_c, 4)} °C`],
          ["Final flag", runtime.environment.throttled_status_final],
        ],
      },
    ];
    $("#runtime-requirements").innerHTML = cards.map((card) => `
      <article class="requirement-card ${card.row.passed ? "passed" : "failed"}">
        <div class="requirement-head"><span class="evidence-badge measured">Measured hardware</span><span class="evidence-badge ${card.row.passed ? "verification" : "failure"}">${card.row.passed ? "Passed" : "Not met"}</span></div>
        <h3>${escapeHtml(card.id)} · ${escapeHtml(card.title)}</h3>
        <p>${escapeHtml(card.row.summary)}</p>
        <div class="requirement-details">${card.details.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}</div>
      </article>`).join("");

    $("#runtime-passed").innerHTML = runtime.what_passed.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    $("#runtime-failed").innerHTML = runtime.what_did_not_pass.map((item) => `<li>${escapeHtml(item)}</li>`).join("");

    const rows = runtime.estimator_deadline.rows;
    const labels = rows.map((row) => `${row.implementation === "python_reference" ? "PY" : "C++"} ${row.estimator.toUpperCase()} · stress ${row.stress_workers}`);
    const Plotly = requirePlotly();
    Plotly.newPlot("runtime-deadline-chart", [
      {
        x: rows.map((row) => Number(row.p99_execution_us) / 1000), y: labels,
        type: "bar", orientation: "h", name: "p99", marker: { color: COLORS.measured },
        hovertemplate: "%{y}<br>p99=%{x:.4f} ms<extra></extra>",
      },
      {
        x: rows.map((row) => Number(row.max_execution_us) / 1000), y: labels,
        type: "bar", orientation: "h", name: "Maximum", marker: { color: rows.map((row) => row.max_below_deadline ? COLORS.synthetic : COLORS.failure) },
        hovertemplate: "%{y}<br>Maximum=%{x:.4f} ms<extra></extra>",
      },
    ], plotLayout({
      barmode: "group",
      margin: { l: 170, r: 26, t: 40, b: 58 },
      shapes: [{ type: "line", xref: "x", yref: "paper", x0: runtime.estimator_deadline.deadline_ms, x1: runtime.estimator_deadline.deadline_ms, y0: 0, y1: 1, line: { color: COLORS.failure, width: 2, dash: "dash" } }],
      annotations: [{ x: runtime.estimator_deadline.deadline_ms, y: 1.04, xref: "x", yref: "paper", text: "33.333 ms deadline", showarrow: false, font: { color: COLORS.failure, size: 10 } }],
      xaxis: { title: "Execution time (ms)", rangemode: "tozero", gridcolor: COLORS.grid, zerolinecolor: COLORS.grid },
      yaxis: { autorange: "reversed", automargin: true, gridcolor: COLORS.grid },
    }), PLOT_CONFIG);
  }

  function renderLimitations() {
    $("#limitations-grid").innerHTML = state.data.limitations.map((item) => `<article class="limitation-card">${escapeHtml(item)}</article>`).join("");
  }

  function renderEvidence() {
    $("#download-grid").innerHTML = state.data.downloads.map((item) => `
      <a class="download-card" href="${escapeHtml(item.path)}"><strong>${escapeHtml(item.label)}</strong><code>${escapeHtml(item.path)}</code></a>`).join("");
    $("#evidence-map-body").innerHTML = Object.entries(state.data.evidence_map).map(([claim, files]) => `
      <tr><td><code>${escapeHtml(claim)}</code></td><td>${files.map((file) => `<a href="${escapeHtml(file)}">${escapeHtml(file)}</a>`).join(" · ")}</td></tr>`).join("");
  }

  function runBrowserSmokeInteractions() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("smoke") !== "1") return;

    const scrubber = $("#replay-scrubber");
    scrubber.value = String(Number(scrubber.max) * 0.5);
    scrubber.dispatchEvent(new Event("input", { bubbles: true }));

    const rangeButton = $$('#response-selector .scenario-button').find((button) => button.dataset.scenario === "range_change");
    if (rangeButton) rangeButton.click();

    const sort = $("#fault-sort");
    sort.value = "recovery-desc";
    sort.dispatchEvent(new Event("change", { bubbles: true }));

    document.documentElement.dataset.smokeReplayMeasurement = $("#replay-measurement").textContent;
    document.documentElement.dataset.smokeReplayTime = String(state.replayTime);
    document.documentElement.dataset.smokeScenario = state.activeResponseScenario;
    document.documentElement.dataset.smokeFaultFirst = $("#fault-table-body tr strong")?.textContent || "";
    document.documentElement.dataset.smokeComplete = "true";
  }

  function setupNavigation() {
    const toggle = $("#nav-toggle");
    const nav = $("#primary-nav");
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
    });
    $$("a", nav).forEach((link) => link.addEventListener("click", () => {
      nav.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    }));
  }

  function showLoadError(error) {
    console.error(error);
    const panel = $("#load-error");
    panel.hidden = false;
    document.documentElement.dataset.showcaseError = error instanceof Error ? error.message : String(error);
    const detail = document.createElement("code");
    detail.textContent = error instanceof Error ? error.message : String(error);
    panel.appendChild(detail);
  }

  async function init() {
    setupNavigation();
    try {
      [state.data, state.replay] = await Promise.all([loadJson(DATA_URL), loadJson(REPLAY_URL)]);
      renderHero();
      renderMission();
      renderArchitecture();
      renderReplay();
      renderEstimatorComparison();
      renderScenarioSelectors();
      renderHardware();
      renderFaults();
      renderRuntime();
      renderLimitations();
      renderEvidence();
      document.documentElement.dataset.showcaseReady = "true";
      document.documentElement.dataset.heroMetrics = String(document.querySelectorAll("#hero-metrics .metric-card").length);
      document.documentElement.dataset.stageButtons = String(document.querySelectorAll(".stage-button").length);
      document.documentElement.dataset.estimatorCards = String(document.querySelectorAll(".estimator-card").length);
      document.documentElement.dataset.faultRows = String(document.querySelectorAll("#fault-table-body tr").length);
      runBrowserSmokeInteractions();
    } catch (error) {
      showLoadError(error);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
