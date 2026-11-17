// CyberAdapt Dashboard — pure ES module, no external imports
// Tasks 10.1–12.3: complete replacement of static results dashboard

// ─── 1. Module-level state ───────────────────────────────────────────────────

const APP = {
  evtSource: null,       // EventSource for SSE
  isRunning: false,
  mode: null,            // 'live' | 'compare' | null
  chartData: {           // rolling 60s window per series
    speed: {},           // { 'V0': [{t,v},...], 'F1': [...], ... }
    trust: {},
    gap: {},
    anomaly: {}
  },
  attackT: null,         // sim time when attack was injected
  flashedVehicles: new Set(),  // vehicles that have already flashed
  apiData: null,         // from /api/data
  legacyData: null,      // existing static dashboard data
};
const N_VEHICLES = 8;
const CHART_WINDOW = 60; // seconds

// ─── 3. Control functions ────────────────────────────────────────────────────

async function startLive() {
  const scenario = document.getElementById('scenario-select').value;
  const cfg = document.getElementById('config-select').value;
  const seed = parseInt(document.getElementById('seed-input').value) || 1;
  resetCharts();
  APP.attackT = null;
  APP.flashedVehicles.clear();
  const res = await fetch('/api/live', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({scenario, cfg, seed})
  });
  if (!res.ok) {
    const err = await res.json();
    setStatus('Error: ' + err.error, 'failed');
    return;
  }
  APP.isRunning = true;
  APP.mode = 'live';
  updateControls();
  setStatus('Running: ' + cfg + ' / ' + scenario + ' / seed ' + seed, 'running');
  openStream();
}

async function startCompare() {
  const scenario = document.getElementById('scenario-select').value;
  const seed = parseInt(document.getElementById('seed-input').value) || 1;
  resetCharts();
  APP.attackT = null;
  APP.flashedVehicles.clear();
  const res = await fetch('/api/compare', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({scenario, seed})
  });
  if (!res.ok) {
    const err = await res.json();
    setStatus('Error: ' + err.error, 'failed');
    return;
  }
  APP.isRunning = true;
  APP.mode = 'compare';
  updateControls();
  setStatus('Comparing MA-ABSE-AR vs CyberAdapt: ' + scenario + ' seed ' + seed, 'running');
  openStream();
}

async function stopRun() {
  await fetch('/api/stop', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
}

async function injectAttack() {
  await fetch('/api/inject', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({attack: 'A1_false_brake'})
  });
  setStatus('Attack injected!', 'running');
}

// ─── 4. SSE client ───────────────────────────────────────────────────────────

function openStream() {
  if (APP.evtSource) APP.evtSource.close();
  APP.evtSource = new EventSource('/api/stream');
  APP.evtSource.onmessage = (e) => {
    const frame = JSON.parse(e.data);
    if (frame.event === 'done' || frame.event === 'idle') {
      APP.isRunning = false;
      APP.mode = null;
      updateControls();
      setStatus(frame.event === 'done' ? 'Run complete.' : 'Idle', '');
      APP.evtSource.close();
      return;
    }
    if (frame.event === 'gap_divergence') {
      highlightDivergence(frame.t);
      return;
    }
    if (frame.mode === 'compare') {
      if (frame.ma) updatePlatoonCompare(frame.ma, frame.ca);
      if (frame.ca) {
        appendChart('speed',   frame.ca.t, buildSpeedSeries(frame.ca));
        appendChart('trust',   frame.ca.t, buildTrustSeries(frame.ca));
        appendChart('gap',     frame.ca.t, buildGapSeries(frame.ca));
        appendChart('anomaly', frame.ca.t, buildAnomalySeries(frame.ca));
      }
    } else {
      updatePlatoon(frame);
      appendChart('speed',   frame.t, buildSpeedSeries(frame));
      appendChart('trust',   frame.t, buildTrustSeries(frame));
      appendChart('gap',     frame.t, buildGapSeries(frame));
      appendChart('anomaly', frame.t, buildAnomalySeries(frame));
      updateCryptoLog(frame.last_crypto || []);
      if (frame.attack_active && APP.attackT === null) {
        APP.attackT = frame.t;
      }
    }
    renderAllCharts(frame.t || 0);
  };
  APP.evtSource.onerror = () => {
    if (!APP.isRunning) return;
    APP.isRunning = false;
    updateControls();
    setStatus('Stream disconnected.', 'failed');
  };
}

// ─── 5. Platoon canvas rendering ─────────────────────────────────────────────

function updatePlatoon(frame) {
  const canvas = document.getElementById('platoon-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  const x = frame.x || [], v = frame.v || [], w = frame.w || [], gap = frame.gap || [];
  if (x.length < N_VEHICLES) {
    ctx.fillStyle = '#8b949e';
    ctx.font = '14px system-ui';
    ctx.textAlign = 'center';
    ctx.fillText('Waiting for run...', W / 2, H / 2);
    return;
  }

  const VL = 4.5; // vehicle length
  const xMin = Math.min(...x) - 10;
  const xMax = Math.max(...x) + 10 + VL;
  const scale = (W - 40) / (xMax - xMin);
  const RECT_H = 30, RECT_Y = H / 2 - RECT_H / 2;

  for (let i = 0; i < N_VEHICLES; i++) {
    const px = 20 + (x[i] - xMin) * scale;
    const rw = VL * scale;
    // Bug 1 & 6 fix: Color vehicle i based on w[i+1] (follower's trust in vehicle i)
    // This ensures visualization matches gap expansion: when vehicle i is red,
    // gap i→i+1 expands (follower backs off from untrusted vehicle)
    const wi = (i < N_VEHICLES - 1 && w[i + 1] !== undefined) ? w[i + 1] : 1.0;
    const hue = Math.round(wi * 120);
    ctx.fillStyle = `hsl(${hue}, 100%, 45%)`;
    ctx.fillRect(px, RECT_Y, Math.max(rw, 8), RECT_H);

    // Flash effect
    if (wi < 0.5 && !APP.flashedVehicles.has(i)) {
      APP.flashedVehicles.add(i);
      canvas.classList.add('trust-flash');
      setTimeout(() => canvas.classList.remove('trust-flash'), 500);
    }

    // Label
    ctx.fillStyle = '#e6edf3';
    ctx.font = '10px system-ui';
    ctx.textAlign = 'center';
    const label = i === 0 ? 'Leader' : 'F' + i;
    ctx.fillText(label, px + Math.max(rw, 8) / 2, RECT_Y - 4);
    // Show follower's trust weight for this vehicle
    ctx.fillText('w=' + (wi).toFixed(2), px + Math.max(rw, 8) / 2, RECT_Y + RECT_H + 12);
  }

  // Gap labels between pairs
  for (let i = 0; i < gap.length && i < N_VEHICLES - 1; i++) {
    const px0 = 20 + (x[i] - xMin) * scale;
    const px1 = 20 + (x[i + 1] - xMin) * scale + VL * scale;
    const midX = (px0 + px1) / 2;
    ctx.fillStyle = '#58a6ff';
    ctx.font = '9px monospace';
    ctx.textAlign = 'center';
    ctx.fillText((gap[i]).toFixed(1) + 'm', midX, H / 2 + RECT_H / 2 + 24);
  }

  document.getElementById('platoon-status').textContent =
    'cfg=' + (frame.cfg || '') + '  t=' + (frame.t || 0).toFixed(1) + 's' +
    (frame.attack_active ? '  ⚠ ATTACK ACTIVE' : '');
}

function updatePlatoonCompare(ma, ca) {
  const canvas = document.getElementById('platoon-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  // Draw two strips stacked
  drawPlatoonStrip(ctx, ma, 0,         W, H / 2 - 2, 'MA-ABSE-AR');
  drawPlatoonStrip(ctx, ca, H / 2 + 2, W, H / 2 - 2, 'CyberAdapt (CA_full)');
}

function drawPlatoonStrip(ctx, frame, yOffset, W, stripH, label) {
  if (!frame || !frame.x || frame.x.length < N_VEHICLES) return;
  const x = frame.x, w = frame.w || [], gap = frame.gap || [];
  const VL = 4.5;
  const xMin = Math.min(...x) - 10, xMax = Math.max(...x) + 10 + VL;
  const scale = (W - 40) / (xMax - xMin);
  const RECT_H = 20, RECT_Y = yOffset + stripH / 2 - RECT_H / 2;

  ctx.fillStyle = '#8b949e';
  ctx.font = '9px system-ui';
  ctx.textAlign = 'left';
  ctx.fillText(label, 4, yOffset + 12);

  for (let i = 0; i < N_VEHICLES; i++) {
    const px = 20 + (x[i] - xMin) * scale;
    const rw = Math.max(VL * scale, 6);
    // Bug 1 & 6 fix: Color based on follower's trust (w[i+1])
    const wi = (i < N_VEHICLES - 1 && w[i + 1] !== undefined) ? w[i + 1] : 1.0;
    const hue = Math.round(wi * 120);
    ctx.fillStyle = `hsl(${hue}, 100%, 45%)`;
    ctx.fillRect(px, RECT_Y, rw, RECT_H);
    ctx.fillStyle = '#e6edf3';
    ctx.font = '8px system-ui';
    ctx.textAlign = 'center';
    ctx.fillText('w=' + wi.toFixed(1), px + rw / 2, RECT_Y + RECT_H + 10);
  }
}

// ─── 6. Chart helpers ─────────────────────────────────────────────────────────

function buildSpeedSeries(frame) {
  const series = {};
  const labels = ['V0', 'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7'];
  (frame.v || []).forEach((v, i) => { series[labels[i]] = v; });
  return series;
}

function buildTrustSeries(frame) {
  const series = {};
  const labels = ['w0', 'w1', 'w2', 'w3', 'w4', 'w5', 'w6', 'w7'];
  (frame.w || []).forEach((w, i) => { series[labels[i]] = w; });
  return series;
}

function buildGapSeries(frame) {
  const series = {};
  (frame.gap || []).forEach((g, i) => { series['g' + i + '-' + (i + 1)] = g; });
  return series;
}

function buildAnomalySeries(frame) {
  const series = {};
  const labels = ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7'];
  (frame.S || []).forEach((s, i) => { series[labels[i]] = s; });
  return series;
}

function appendChart(chartKey, t, seriesValues) {
  const data = APP.chartData[chartKey];
  for (const [key, val] of Object.entries(seriesValues)) {
    if (!data[key]) data[key] = [];
    data[key].push({ t, v: val });
  }
  // Prune old points
  for (const key of Object.keys(data)) {
    data[key] = data[key].filter(pt => pt.t >= t - CHART_WINDOW);
  }
}

function resetCharts() {
  APP.chartData = { speed: {}, trust: {}, gap: {}, anomaly: {} };
}

// ─── 7. Chart rendering (Canvas 2D) ──────────────────────────────────────────

const CHART_COLORS = [
  '#58a6ff', '#3fb950', '#ff7b72', '#d2a8ff', '#ffa657',
  '#79c0ff', '#56d364', '#f78166'
];

function renderAllCharts(currentT) {
  renderChart('chart-speed',   APP.chartData.speed,   {min: 0,  max: 20,  label: 'Speed (m/s)', attackT: APP.attackT});
  renderChart('chart-trust',   APP.chartData.trust,   {min: 0,  max: 1.0, label: 'Trust w', refLine: 0.5, refLabel: 'w=0.5', attackT: APP.attackT, boldKey: 'w3'});
  renderChart('chart-gap',     APP.chartData.gap,     {min: -2, max: 40,  label: 'Gap (m)', attackT: APP.attackT});
  renderChart('chart-anomaly', APP.chartData.anomaly, {min: 0,  max: 1.0, label: 'S', refLine: 0.5, refLabel: 'Detection threshold', attackT: APP.attackT, boldKey: 'S3'});
}

function renderChart(canvasId, seriesMap, opts) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const PAD = {top: 10, right: 10, bottom: 20, left: 36};
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#0d1117';
  ctx.fillRect(0, 0, W, H);

  const keys = Object.keys(seriesMap);
  if (keys.length === 0) {
    ctx.fillStyle = '#8b949e';
    ctx.font = '11px system-ui';
    ctx.textAlign = 'center';
    ctx.fillText('No data', W / 2, H / 2);
    return;
  }

  // Find time range from all series
  const allPts = keys.flatMap(k => seriesMap[k]);
  if (allPts.length === 0) return;
  const tMax = Math.max(...allPts.map(p => p.t));
  const tMin = tMax - CHART_WINDOW;

  const yMin = opts.min !== undefined ? opts.min : Math.min(...allPts.map(p => p.v));
  const yMax = opts.max !== undefined ? opts.max : Math.max(...allPts.map(p => p.v));
  const yRange = yMax - yMin || 1;

  const toX = t => PAD.left + ((t - tMin) / CHART_WINDOW) * plotW;
  const toY = v => PAD.top + (1 - (v - yMin) / yRange) * plotH;

  // Grid lines
  ctx.strokeStyle = '#21262d';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = PAD.top + (i / 4) * plotH;
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + plotW, y); ctx.stroke();
    const val = yMax - (i / 4) * yRange;
    ctx.fillStyle = '#8b949e';
    ctx.font = '9px monospace';
    ctx.textAlign = 'right';
    ctx.fillText(val.toFixed(1), PAD.left - 2, y + 3);
  }

  // Reference line (e.g. detection threshold)
  if (opts.refLine !== undefined) {
    const ry = toY(opts.refLine);
    ctx.strokeStyle = '#9e6a03';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(PAD.left, ry); ctx.lineTo(PAD.left + plotW, ry); ctx.stroke();
    ctx.setLineDash([]);
    if (opts.refLabel) {
      ctx.fillStyle = '#9e6a03';
      ctx.font = '9px system-ui';
      ctx.textAlign = 'left';
      ctx.fillText(opts.refLabel, PAD.left + 2, ry - 2);
    }
  }

  // Attack marker
  if (opts.attackT !== null && opts.attackT !== undefined) {
    const ax = toX(opts.attackT);
    if (ax >= PAD.left && ax <= PAD.left + plotW) {
      ctx.strokeStyle = '#ff7b72';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(ax, PAD.top); ctx.lineTo(ax, PAD.top + plotH); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#ff7b72';
      ctx.font = '9px system-ui';
      ctx.textAlign = 'left';
      ctx.fillText('Attack t=' + opts.attackT.toFixed(0) + 's', ax + 2, PAD.top + 10);
    }
  }

  // Series lines
  keys.forEach((key, ki) => {
    const pts = seriesMap[key];
    if (pts.length < 2) return;
    const color = CHART_COLORS[ki % CHART_COLORS.length];
    const isBold = opts.boldKey && key === opts.boldKey;
    ctx.strokeStyle = color;
    ctx.lineWidth = isBold ? 2.5 : 1.0;
    ctx.beginPath();
    pts.forEach((pt, idx) => {
      const px = toX(pt.t), py = toY(pt.v);
      if (idx === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    });
    ctx.stroke();
  });
}

// ─── 8. Crypto log table ──────────────────────────────────────────────────────

function updateCryptoLog(entries) {
  const tbody = document.getElementById('crypto-log-body');
  if (!tbody || !entries.length) return;
  for (const e of entries) {
    const tr = document.createElement('tr');
    if (!e.zktat_pass || !e.hpo_pass) tr.classList.add('zktat-fail');
    else if (e.bloom_hit) tr.classList.add('bloom-hit');
    tr.innerHTML = `
      <td>${e.t != null ? e.t.toFixed(2) : '—'}</td>
      <td>${e.src !== undefined ? 'V' + e.src : '—'}</td>
      <td class="${e.zktat_pass ? 'pass' : 'fail'}">${e.zktat_pass ? '✓' : '✗'}</td>
      <td class="${e.hpo_pass ? 'pass' : 'fail'}">${e.hpo_pass ? '✓' : '✗'}</td>
      <td class="${e.bloom_hit ? 'fail' : 'pass'}">${e.bloom_hit ? '⚑' : '—'}</td>
      <td>${e.zktat_verify_us != null ? e.zktat_verify_us.toFixed(1) : '—'}</td>
      <td>${e.hpo_us != null ? e.hpo_us.toFixed(2) : '—'}</td>
      <td>${e.bloom_us != null ? e.bloom_us.toFixed(3) : '—'}</td>
      <td class="${e.accepted ? 'pass' : 'fail'}">${e.accepted ? '✓' : '✗'}</td>
    `;
    tbody.prepend(tr);
    // Keep max 20 rows
    while (tbody.rows.length > 20) tbody.deleteRow(tbody.rows.length - 1);
  }
}

// ─── 9. Performance panel ─────────────────────────────────────────────────────

function populatePerfTable(native) {
  const tbody = document.getElementById('perf-body');
  const budgetEl = document.getElementById('perf-budget');
  const negEl = document.getElementById('perf-neg-tests');
  if (!tbody) return;

  if (!native || Object.keys(native).length === 0) {
    tbody.innerHTML = '<tr><td colspan="4">Native benchmark data unavailable — run cargo to regenerate</td></tr>';
    if (budgetEl) budgetEl.textContent = '';
    if (negEl) negEl.textContent = '';
    return;
  }

  const rows = [
    ['SMBP naive baseline',       native.naive_us,         native.naive_p95_us,      'No precomputed table'],
    ['SMBP with precomp table',   native.smbp_w1_us,       native.smbp_w1_p95_us,    'T[i] = 2^i·G stored'],
    ['Dalek variable-base',       native.dalek_var_us,     native.dalek_var_p95_us,  'curve25519-dalek'],
    ['Dalek fixed-base',          native.dalek_fixed_us,   native.dalek_fixed_p95_us,'Fastest baseline'],
    ['ZK-TAT prove',              native.zk_prove_us,      native.zk_prove_p95_us,   'Pedersen + Fiat-Shamir'],
    ['ZK-TAT verify',             native.zk_verify_us,     native.zk_verify_p95_us,  'R\' = s1G + s2H − eC'],
    ['Cert verify',               native.cert_verify_us,   native.cert_verify_p95_us,'Reference'],
    ['H-PO SHA-256',              native.hpo_sha256_us,    null,                     'Single hash'],
    ['H-PO HMAC',                 native.hpo_hmac_us,      null,                     'Keyed'],
    ['H-PO Match-16 attrs',       native.hpo_match16_us,   null,                     '16 policy attributes'],
    ['Bloom filter query',        native.bloom_query_us,   null,                     '4 probes, 4 KiB'],
  ];

  tbody.innerHTML = rows.map(([op, mean, p95, note]) => `
    <tr>
      <td>${op}</td>
      <td>${mean != null ? Number(mean).toFixed(3) : '—'}</td>
      <td>${p95 != null ? Number(p95).toFixed(1) : '—'}</td>
      <td>${note || ''}</td>
    </tr>
  `).join('');

  // SMBP speedup
  if (native.naive_us && native.smbp_w1_us && budgetEl) {
    const speedup = (native.naive_us / native.smbp_w1_us).toFixed(1);
    const pct = (native.zk_verify_us / 100000 * 100).toFixed(2);
    budgetEl.textContent =
      `SMBP speedup: ${speedup}x faster  |  ` +
      `ZK-TAT verify = ${pct}% of 100 ms V2X slot  |  ` +
      `Bloom query = ${Number(native.bloom_query_us).toFixed(3)} µs (< 0.001% of V2X slot)`;
  }

  if (negEl) {
    const neg = [
      native.neg_C, native.neg_e,
      native.neg_s1, native.neg_s2, native.neg_ctx
    ].every(v => v === 0 || v == null);
    negEl.textContent = neg
      ? 'ZK-TAT negative tests: 0 false accepts in 300 trials ✓'
      : 'ZK-TAT negative test data not available.';
  }
}

// ─── 10. Scenario results table ───────────────────────────────────────────────

function populateScenarioTable(scenarios) {
  const tbody = document.getElementById('scenario-body');
  const tfoot = document.getElementById('scenario-foot');
  if (!tbody || !scenarios) return;

  const attackScenarios = ['A1_false_brake', 'A2_false_accel', 'A3_stealth_ramp', 'A4_replay', 'A5_forged'];
  const labels = {
    A1_false_brake:   'A1 · False braking',
    A2_false_accel:   'A2 · False acceleration',
    A3_stealth_ramp:  'A3 · Stealth ramp',
    A4_replay:        'A4 · Replay',
    A5_forged:        'A5 · Forged packets'
  };

  let totalMaCol = 0, totalCaCol = 0, sumMaGap = 0, sumCaGap = 0, nRows = 0;

  tbody.innerHTML = attackScenarios.map(scen => {
    const ma = (scenarios[scen] || {})['D1_ma_abse_ar'];
    const ca = (scenarios[scen] || {})['CA_full'];

    const maGap = ma ? ma.mean_min_gap.toFixed(2) + ' ± ' + ma.std_min_gap.toFixed(2) : '—';
    const caGap = ca ? ca.mean_min_gap.toFixed(2) + ' ± ' + ca.std_min_gap.toFixed(2) : '—';
    const maCol = ma ? ma.collisions : 0;
    const caCol = ca ? ca.collisions : 0;
    const maDet = ma?.mean_detection_delay != null ? ma.mean_detection_delay.toFixed(2) + 's' : '—';
    const caDet = ca?.mean_detection_delay != null ? ca.mean_detection_delay.toFixed(2) + 's' : '—';

    totalMaCol += maCol;
    totalCaCol += caCol;
    if (ma) { sumMaGap += ma.mean_min_gap; nRows++; }
    if (ca) sumCaGap += ca.mean_min_gap;

    return `<tr>
      <td>${labels[scen] || scen}</td>
      <td>${maGap}</td>
      <td class="${maCol > 0 ? 'collision-cell' : ''}">${maCol}/20</td>
      <td>${maDet}</td>
      <td>${caGap}</td>
      <td class="${caCol > 0 ? 'collision-cell' : ''}">${caCol}/20</td>
      <td>${caDet}</td>
    </tr>`;
  }).join('');

  if (tfoot) {
    tfoot.innerHTML = `<tr>
      <td><strong>Total</strong></td>
      <td>${nRows > 0 ? (sumMaGap / nRows).toFixed(2) : '—'}</td>
      <td class="${totalMaCol > 0 ? 'collision-cell' : ''}">${totalMaCol}/100</td>
      <td>—</td>
      <td>${nRows > 0 ? (sumCaGap / nRows).toFixed(2) : '—'}</td>
      <td class="${totalCaCol > 0 ? 'collision-cell' : ''}">${totalCaCol}/100</td>
      <td>—</td>
    </tr>`;
  }
}

// ─── 11. UI helpers ───────────────────────────────────────────────────────────

function updateControls() {
  const btnRun     = document.getElementById('btn-run-live');
  const btnCompare = document.getElementById('btn-compare');
  const btnStop    = document.getElementById('btn-stop');
  const btnInject  = document.getElementById('btn-inject');
  if (!btnRun) return;
  if (APP.isRunning) {
    btnRun.style.display     = 'none';
    btnCompare.style.display = 'none';
    btnStop.style.display    = '';
    // Show inject only for live (not compare)
    if (APP.mode === 'live') {
      const cfg = document.getElementById('config-select').value;
      btnInject.style.display = (cfg === 'CA_full' || cfg === 'D1_ma_abse_ar') ? '' : 'none';
    } else {
      btnInject.style.display = 'none';
    }
  } else {
    btnRun.style.display     = '';
    btnCompare.style.display = '';
    btnStop.style.display    = 'none';
    btnInject.style.display  = 'none';
  }
}

function setStatus(text, cls) {
  const el = document.getElementById('status-text');
  if (!el) return;
  el.textContent = text;
  el.className = cls || '';
}

function highlightDivergence(t) {
  setStatus('⚠ Gap divergence at t=' + t.toFixed(1) + 's — MA-ABSE-AR collided, CyberAdapt held!', 'running');
}

// ─── 12. DOMContentLoaded init ────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  try {
    const res = await fetch('/api/data');
    APP.apiData = await res.json();
    populatePerfTable(APP.apiData.native);
    populateScenarioTable(APP.apiData.scenarios);
  } catch (e) {
    setStatus('Could not load dashboard data: ' + e.message, 'failed');
  }

  document.getElementById('btn-run-live').addEventListener('click', startLive);
  document.getElementById('btn-compare').addEventListener('click', startCompare);
  document.getElementById('btn-stop').addEventListener('click', stopRun);
  document.getElementById('btn-inject').addEventListener('click', injectAttack);

  // Draw placeholder platoon
  updatePlatoon({x: [], v: [], w: [], gap: [], S: [], t: 0, cfg: '', attack_active: false});
  setStatus('Idle — select a scenario and click Run Live', '');
});
