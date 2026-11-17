# Implementation Plan: cyberadapt-review2-integration

## Overview

Wire together the existing CyberAdapt crypto engine (`CyberAdapt_v1/cyberadapt_crypto.py`),
trust controller (`CyberAdapt_v1/cyberadapt_control.py`), and closed-loop platoon simulator
(`sim/sim.py`) into a presentation-ready system. The result is three top-level deliverables:
`sim/sim_integrated.py` (real ZK-TAT + H-PO on every V2X packet, plus the MA-ABSE-AR baseline
config), a live-streaming `dashboard/server.py`, and a zero-CDN single-page application
(`index.html` / `app.js` / `styles.css`).

---

## Tasks

- [ ] 1. Create import shims for the crypto and trust modules
  - [x] 1.1 Write `sim/crypto_gate.py`
    - Resolve `CyberAdapt_v1/` relative to repo root using `Path(__file__).resolve().parents[2]`
    - Insert the resolved path into `sys.path` and re-export `ZKTAT`, `HPO`, `RevocationBloomFilter`, `SMBP_TABLE_G`, `SMBP_TABLE_H` from `cyberadapt_crypto`
    - Add a module-level docstring identifying this as a shim
    - _Requirements: 2.1, 2.2_

  - [x] 1.2 Write `sim/trust_supervisor.py`
    - Use the same `Path(__file__).resolve().parents[2]` / `sys.path` approach as `crypto_gate.py`
    - Re-export `CyberAdaptTrustController` from `cyberadapt_control`
    - _Requirements: 3.1_

- [x] 2. Implement `sim/sim_integrated.py` — batch `run()` function
  - [x] 2.1 Define module-level constants, imports, and the `CFG` table
    - Copy all constants from `sim.py` (`DT`, `T`, `N`, `V0`, `D0`, `H_NOM`, `H_FAIL`, `KP`, `KD`, `KFF`, `TAU`, `A_MIN`, `A_MAX`, `JERK_LIM`, `DEFAULT_J_LIM`, `J_LIM`, `DV_LIM`, `KAPPA`, `RHO`, `ALPHA`, `BETA`, `W_MIN`, `SLEW`, `T_STALE`, `T_ATK`)
    - Import `ZKTAT`, `HPO`, `RevocationBloomFilter`, `SMBP_TABLE_G`, `SMBP_TABLE_H` from `crypto_gate`
    - Import `CyberAdaptTrustController` from `trust_supervisor`
    - Define `CFG` with all 7 existing configs (semantics unchanged) plus `D1_ma_abse_ar` as `dict(gate=True, trust=None, crypto=True)`
    - Define the `PacketLogEntry` dataclass with fields `t`, `src`, `zktat_pass`, `hpo_pass`, `bloom_hit`, `zktat_prove_us`, `zktat_verify_us`, `hpo_us`, `bloom_us`, `accepted`
    - _Requirements: 1.1, 2.1, 2.2_

  - [x] 2.2 Implement `w_of_S`, `leader_profile` helpers
    - Copy `w_of_S` and `leader_profile` from `sim.py` unchanged
    - _Requirements: 3.2, 3.3_

  - [x] 2.3 Implement the per-packet crypto pipeline inside `run()`
    - For each outbound V2X packet on crypto-enabled configs (`gate=True, crypto=True`): call `ZKTAT.prove(vid, epoch_ctx)` timed with `time.perf_counter_ns()` → `zktat_prove_us`; call `HPO.compute_tag(role_attribute, shared_platoon_secret)` and attach the 32-byte tag
    - For each received packet: query `bloom_filter.is_revoked(str(src_id))` → `bloom_us`; call `ZKTAT.verify(token, epoch_ctx)` → `zktat_verify_us`; call `HPO.match_policy(tag, role_attribute, shared_platoon_secret)` → `hpo_us`
    - Reject the packet (do not update `lastp`) if any check fails; set `zktat_pass`, `hpo_pass`, `bloom_hit` flags accordingly; append a `PacketLogEntry` to `crypto_latency`
    - Wrap each crypto call in `try/except Exception`; on exception treat as failure, log to `stderr` once per unique exception type per run
    - For `D0_none` (`gate=False`), skip all crypto calls so the run result is identical to `sim.py`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.10_

  - [x] 2.4 Integrate `CyberAdaptTrustController` for CA configs inside `run()`
    - Instantiate one `CyberAdaptTrustController` per `run()` call
    - For CA_full / CA_norevoke / CA_fixedh: call `controller.process_telemetry_step(veh_id, a_v2x, v_v2x, v_radar, a_acc_radar, v_actual, current_t, dt=0.1)` at every 10 Hz beacon step for each follower that received a packet
    - Use the returned `trust_weight_w` as `w[i]` and the returned `headway_h` as the target fed into the slew-rate limiter (preserve the 0.25 s/s SLEW cap from `sim.py`)
    - Preserve `first_det` recording semantics: set when S > 0.5 for vehicle 3 during an attack scenario
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 2.5 Build the return dict and write `results/sim_integrated_results.json`
    - Return dict must include all backward-compatible fields from `sim.py` (`min_gap`, `collision`, `vmin`, `peak_decel`, `peak_jerk`, `first_det`, `rev`, `minw`, `ever_w_lt_half`, `mean_headway`) plus a `crypto` sub-dict (`mean_zktat_prove_us`, `mean_zktat_verify_us`, `mean_hpo_us`, `mean_bloom_us`, `zktat_pass_rate`)
    - Write `results/sim_integrated_results.json` using the `{"main": {…}, "jsweep": {…}}` schema keyed as `"{scenario}|{variant}"`; zero/None values for crypto fields when `gate=False`
    - _Requirements: 1.5, 4.1, 4.2, 4.3_

  - [ ]* 2.6 Write property test: ZK-TAT round-trip identity (Property 1)
    - **Property 1: ZK-TAT round-trip identity**
    - `@given(vid=integers(1,7), ctx=text(min_size=1))` → assert `ZKTAT.verify(ZKTAT.prove(vid, ctx), ctx) == True`
    - Tag: `# Feature: cyberadapt-review2-integration, Property 1: ZK-TAT round-trip identity`
    - **Validates: Requirements 14.1**

  - [ ]* 2.7 Write property test: ZK-TAT wrong-context failure (Property 2)
    - **Property 2: ZK-TAT wrong-context failure**
    - `@given(vid=integers(1,7), ctx=text(min_size=1), wrong=text(min_size=1).filter(lambda s: s != ctx))` → assert verify returns `False`
    - Tag: `# Feature: cyberadapt-review2-integration, Property 2: ZK-TAT wrong-context failure`
    - **Validates: Requirements 14.2**

  - [ ]* 2.8 Write property test: H-PO round-trip identity (Property 4)
    - **Property 4: H-PO round-trip identity**
    - `@given(attr=text(min_size=1), sec=binary(min_size=1))` → assert `HPO.match_policy(HPO.compute_tag(attr, sec), attr, sec) == True`
    - Tag: `# Feature: cyberadapt-review2-integration, Property 4: H-PO round-trip identity`
    - **Validates: Requirements 14.5**

  - [ ]* 2.9 Write property test: H-PO key sensitivity (Property 5)
    - **Property 5: H-PO key sensitivity**
    - `@given(attr=text(min_size=1), s1=binary(min_size=1), s2=binary(min_size=1).filter(lambda b: b != s1))` → assert match returns `False`
    - Tag: `# Feature: cyberadapt-review2-integration, Property 5: H-PO key sensitivity`
    - **Validates: Requirements 14.6**

  - [ ]* 2.10 Write property test: Trust weight bounds (Property 6)
    - **Property 6: Trust weight bounds**
    - `@given(S=floats(0.0, 1.0, allow_nan=False))` → assert `0.05 <= CyberAdaptTrustController().compute_trust_weight(S) <= 1.0`
    - Tag: `# Feature: cyberadapt-review2-integration, Property 6: Trust weight bounds`
    - **Validates: Requirements 3.2, 3.3**

  - [ ]* 2.11 Write property test: Headway monotone in trust (Property 7)
    - **Property 7: Headway monotone in trust**
    - `@given(v=floats(0, 40, allow_nan=False), w1=floats(0,1, allow_nan=False), w2=floats(0,1, allow_nan=False))`, filter `w1 < w2` → assert `compute_dynamic_headway(v, w1)["headway_time_s"] >= compute_dynamic_headway(v, w2)["headway_time_s"]`
    - Tag: `# Feature: cyberadapt-review2-integration, Property 7: Headway monotone in trust`
    - **Validates: Requirements 3.4**

- [x] 3. Checkpoint — batch simulator complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement `sim/sim_integrated.py` — `run_live()` generator
  - [x] 4.1 Write the `run_live(cfgname, scen, seed, inject_flag, stop_flag)` generator
    - Signature: `def run_live(cfgname: str, scen: str, seed: int, inject_flag: threading.Event, stop_flag: threading.Event) -> Generator[dict, None, None]`
    - Yield one state dict per simulation step (every `DT = 0.01 s`) containing `t`, `x`, `v`, `w`, `S`, `gap`, `h`, `last_crypto`, `cfg`, `attack_active`
    - `last_crypto` is the latest slice of up to 7 `PacketLogEntry` dicts (one per follower link)
    - Check `stop_flag.is_set()` once per step and return early if set
    - Check `inject_flag.is_set()` to begin injecting A1-style false packets from vehicle 2 on the fly; set `attack_active = True` in all subsequent yielded frames
    - `gap` array has 7 elements (predecessor − follower − VL); `h` array has 8 elements (per-vehicle current headway)
    - _Requirements: 5.1, 5.2, 5.3, 10.3, 10.4_

  - [ ]* 4.2 Write property test: Run result schema completeness (Property 10)
    - **Property 10: Run result schema completeness**
    - `@given(scenario=sampled_from(SCENARIOS), variant=sampled_from(list(CFG.keys())), seed=integers(1,20))` → call `run(variant, scenario, seed)` and assert all required keys are present with correct types
    - Tag: `# Feature: cyberadapt-review2-integration, Property 10: Run result schema completeness`
    - **Validates: Requirements 4.2, 4.3**

  - [ ]* 4.3 Write property test: Crypto latency fields non-negative (Property 11)
    - **Property 11: Crypto latency fields non-negative**
    - `@given(seed=integers(1,5), scenario=sampled_from(["L1_normal","A1_false_brake"]))` on `D1_ma_abse_ar` → assert all `crypto_latency` entries have non-negative latency fields
    - Tag: `# Feature: cyberadapt-review2-integration, Property 11: Crypto latency fields non-negative`
    - **Validates: Requirements 2.5, 2.6, 2.7, 2.8**

  - [ ]* 4.4 Write property test: Gate=False configs skip crypto (Property 12, integration)
    - **Property 12: Gate=False configs skip crypto (integration)**
    - Use `unittest.mock.patch` to count calls to `ZKTAT.prove` and `HPO.compute_tag`; run `D0_none` on `L1_normal` with seed 1 and assert call count is 0; assert returned `min_gap` and `collision` match `sim.py` output for the same (scenario, seed)
    - Tag: `# Feature: cyberadapt-review2-integration, Property 12: Gate=False configs skip crypto`
    - **Validates: Requirements 2.10**

  - [ ]* 4.5 Write property test: MA-ABSE-AR insider-attack gap (Property 8)
    - **Property 8: MA-ABSE-AR insider-attack gap**
    - For all seeds in `[1, 20]` and all scenarios in `{A1_false_brake, A2_false_accel, A3_stealth_ramp}`, call `run("D1_ma_abse_ar", scenario, seed)` and assert `first_det is None` and `rev is None`
    - Tag: `# Feature: cyberadapt-review2-integration, Property 8: MA-ABSE-AR insider-attack gap`
    - **Validates: Requirements 1.3**

  - [ ]* 4.6 Write property test: Benign-traffic safety for all seeds (Property 9)
    - **Property 9: Benign-traffic safety for all seeds**
    - For all seeds in `[1, 20]`, call `run("D1_ma_abse_ar", "L1_normal", seed)` and assert `collision == False` and `min_gap > 0`
    - Tag: `# Feature: cyberadapt-review2-integration, Property 9: Benign-traffic safety`
    - **Validates: Requirements 1.6**

  - [ ]* 4.7 Write property test: Headway slew-rate limiter (Property 16)
    - **Property 16: Headway slew-rate limiter**
    - `@given(seed=integers(1,5))` on a trace-enabled `CA_full` run → extract consecutive headway values from the trace and assert `|h(t+DT) - h(t)| / DT <= 0.25` for every consecutive pair
    - Tag: `# Feature: cyberadapt-review2-integration, Property 16: Headway slew-rate limiter`
    - **Validates: Requirements 3.6**

- [x] 5. Checkpoint — simulator complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Extend `dashboard/server.py` with SSE infrastructure
  - [-] 6.1 Add shared live-run state and locking
    - Define `_job` dict with keys `status`, `mode`, `cfg`, `scenario`, `seed`, `attack_active`, `state_snapshot`, `crypto_log` (as `collections.deque(maxlen=20)`), `stop_flag`, `inject_flag`, `error`
    - Define `_job_lock = threading.Lock()` alongside the existing `STATE_LOCK`
    - Import `sim_integrated` from `sim/` (add `sim/` to `sys.path` using `Path(__file__).resolve().parent.parent / "sim"`)
    - _Requirements: 5.6, 8.1_

  - [-] 6.2 Implement the `/api/stream` SSE handler
    - Add a `GET /api/stream` branch inside `do_GET` that sets `Content-Type: text/event-stream`, `Cache-Control: no-cache`, and `X-Accel-Buffering: no` response headers; disable `send_bytes` path for SSE (write directly)
    - Implement the SSE loop: sleep 100 ms, acquire `_job_lock`, read `_job["state_snapshot"]`, release lock, format and flush `data: {...}\n\n`
    - When `_job["status"]` is `"completed"` or `"failed"`, emit `data: {"event":"done","cfg":"..."}\n\n` and exit the loop
    - When no run is active (`status == "idle"`), emit `data: {"event":"idle"}\n\n` and exit immediately
    - For comparison mode, emit paired frames with top-level key `"mode": "compare"` and sub-keys `"ma"` and `"ca"`; include gap-divergence detection (MA gap ≤ 0 m and CA gap > 2 m) emitting `{"event":"gap_divergence","t":<float>}` once
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 9.3, 9.5_

  - [ ]* 6.3 Write property test: SSE frame schema completeness (Property 13)
    - **Property 13: SSE frame schema completeness**
    - Build a synthetic state snapshot dict via a `make_state_snapshot` helper and assert the SSE frame builder returns a dict containing all required keys (`t`, `x`, `v`, `w`, `S`, `gap`, `h`, `attack_active`, `cfg`, `last_crypto`) with correct array lengths (8 for per-vehicle, 7 for gap)
    - Tag: `# Feature: cyberadapt-review2-integration, Property 13: SSE frame schema completeness`
    - **Validates: Requirements 5.2**

  - [ ]* 6.4 Write property test: Crypto gate log bounded size (Property 14)
    - **Property 14: Crypto gate log bounded size**
    - `@given(n=integers(1,100))` → append `n` entries to a `deque(maxlen=20)` and assert `len(deque) <= 20`
    - Tag: `# Feature: cyberadapt-review2-integration, Property 14: Crypto gate log bounded size`
    - **Validates: Requirements 8.1**

  - [ ]* 6.5 Write property test: Host header rejection (Property 15)
    - **Property 15: Host header rejection**
    - `@given(host=text().filter(lambda h: h not in {"127.0.0.1:8765","localhost:8765"}))` → assert `request_is_local()` returns `False` (or construct a minimal test request and assert the server responds 403)
    - Tag: `# Feature: cyberadapt-review2-integration, Property 15: Host header rejection`
    - **Validates: Requirements 15.1**

- [ ] 7. Extend `dashboard/server.py` with live-run control endpoints
  - [-] 7.1 Implement `POST /api/live`
    - Validate JSON body: `scenario` must be in the 8 known scenario IDs (HTTP 400 otherwise), `cfg` must be in the known config list (HTTP 400), `seed` must be an integer in `[1, 20]` (HTTP 400)
    - Return HTTP 409 if `_job["status"] == "running"`
    - Spawn a daemon thread that calls `sim_integrated.run_live(cfg, scenario, seed, inject_flag, stop_flag)` and writes each yielded state dict to `_job["state_snapshot"]` under `_job_lock`; set `_job["status"]` to `"running"` before starting, `"completed"` on clean exit, `"failed"` on exception
    - Return HTTP 202 with the initial job snapshot
    - _Requirements: 5.6, 5.7, 15.3, 15.4, 15.5, 15.6_

  - [-] 7.2 Implement `POST /api/compare`
    - Validate JSON body: `scenario` and `seed` as above
    - Spawn two daemon threads, one for `D1_ma_abse_ar` and one for `CA_full`, each writing to `_job["state_snapshot"]["ma"]` and `_job["state_snapshot"]["ca"]` respectively under `_job_lock`; both share the same `stop_flag`
    - Return HTTP 202
    - _Requirements: 9.1, 9.2_

  - [-] 7.3 Implement `POST /api/inject` and `POST /api/stop`
    - `/api/inject`: validate body `{"attack": "A1_false_brake"}`; set `_job["inject_flag"]`; set `_job["attack_active"] = True`; return HTTP 200
    - `/api/stop`: set `_job["stop_flag"]`; return HTTP 200; the Live_Run thread must exit within 500 ms (enforced by checking the flag once per simulation step in `run_live`)
    - Add all four new paths (`/api/live`, `/api/compare`, `/api/inject`, `/api/stop`) to the `do_POST` dispatch in `DashboardHandler`
    - Add `GET /api/status` fast-path that reads `_job` under lock and returns within 200 ms
    - Extend `read_dashboard_data()` to try `sim_integrated_results.json` first, then fall back to `sim_results.json` on `(OSError, json.JSONDecodeError)`
    - _Requirements: 5.4, 5.6, 10.1, 10.2, 10.3, 13.7, 15.6, 15.7, 4.5_

- [~] 8. Checkpoint — backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Write `dashboard/index.html` and `dashboard/styles.css`
  - [x] 9.1 Write `dashboard/index.html` page structure
    - `#controls-bar`: scenario-select (8 options with human-readable labels), config-select (D0_none, D1_ma_abse_ar, D1_crypto, D2b_binary_hfail, CA_full), seed-input (number, default 1, min 1, max 20), `#btn-run-live`, `#btn-compare`, `#btn-stop` (hidden by default), `#btn-inject` (hidden by default, label "Inject A1 False Brake")
    - `#platoon-view`: `<canvas id="platoon-canvas">` with a sibling `<div id="platoon-overlay">` for the flash animation
    - `#charts`: four `<canvas>` elements — `chart-speed`, `chart-trust`, `chart-gap`, `chart-anomaly`
    - `#crypto-log`: `<table id="crypto-log-table">` with header columns: Time, Src, ZK-TAT, H-PO, Bloom, ZK-TAT µs, H-PO µs, Bloom µs, Accepted
    - `#performance-panel`: `<table id="perf-table">` with header columns: Operation, Mean µs, P95 µs
    - `#scenario-results`: `<table id="scenario-table">` with header columns: Scenario, MA min-gap, MA collisions, MA det-delay, CA min-gap, CA collisions, CA det-delay
    - Load `app.js` as `<script type="module" src="app.js"></script>`; no external CDN links
    - _Requirements: 6.1, 6.6, 6.7, 7.1, 8.4, 11.2, 12.1, 13.1, 13.2, 13.3_

  - [x] 9.2 Write `dashboard/styles.css`
    - Layout: flex column body; `#controls-bar` as a flex row with gap; `#charts` as a 2×2 CSS grid
    - Vehicle color: relies on inline `hsl(...)` set by JS; CSS class `.trust-flash` sets `outline: 3px solid red` and a 500 ms keyframe animation
    - Crypto log: row class `.zktat-fail` = red background; `.bloom-hit` = orange background
    - Scenario table: cell class `.collision-cell` = red background
    - Comparison mode: `#platoon-view` gains class `compare` → two stacked sub-strips labeled via `::before` pseudo-elements
    - _Requirements: 6.2, 6.5, 8.5, 8.6, 12.3_

- [ ] 10. Write `dashboard/app.js` — platoon canvas
  - [~] 10.1 Implement SSE client and state management
    - `startStream()` creates `new EventSource('/api/stream')` and assigns `evtSource.onmessage`
    - On each message: parse JSON; if `frame.event === 'done'` or `'idle'`, close stream and call `updateControlsIdle()`; if `frame.mode === 'compare'`, call `updatePlatoonCompare(frame.ma, frame.ca)` and `appendChartCompare(frame)`; otherwise call `updatePlatoon(frame)`, `appendChart(frame)`, `updateCryptoLog(frame.last_crypto)`, and `updateControlsRunning()`
    - If `frame.event === 'gap_divergence'`, call `highlightDivergence(frame.t)`
    - `updateControlsIdle()`: show Run/Compare, hide Stop/Inject
    - `updateControlsRunning()`: hide Run/Compare, show Stop; show Inject only when `frame.cfg` is `CA_full` or `D1_ma_abse_ar`
    - Wire button click handlers to `fetch('/api/live', ...)`, `fetch('/api/compare', ...)`, `fetch('/api/stop', ...)`, `fetch('/api/inject', ...)`
    - _Requirements: 13.4, 13.5, 13.6, 13.7, 10.1, 10.2_

  - [~] 10.2 Implement `updatePlatoon(frame)` on `#platoon-canvas`
    - Scale vehicle positions: linear map from `[min(x) − 10, max(x) + 10]` to `[0, canvasWidth]`
    - Draw 8 filled rectangles; fill color = `hsl(${Math.round(w * 120)}, 100%, 45%)`
    - Draw Trust_Weight labels (two decimal places) below each rectangle
    - Draw inter-vehicle gap in metres between adjacent pairs
    - Label vehicle 0 as "Leader"; vehicles 1–7 as "F1"–"F7"
    - When `w[i]` first drops below 0.5 in a run, toggle class `.trust-flash` on the overlay element for 500 ms
    - When no run is active, draw static "Waiting for run..." text centered on canvas
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [~] 10.3 Implement `updatePlatoonCompare(ma_frame, ca_frame)` for comparison mode
    - Draw two horizontally equivalent platoon strips stacked vertically in the same canvas
    - Label top strip "MA-ABSE-AR" and bottom strip "CyberAdapt (CA_full)" using `ctx.fillText`
    - Apply the same color and label rules as `updatePlatoon`
    - _Requirements: 9.4_

- [ ] 11. Write `dashboard/app.js` — real-time charts
  - [~] 11.1 Implement 60-second rolling-window chart rendering
    - Maintain four data arrays (one per chart): each is a map from series name → `[{t, v}, ...]`
    - On each SSE frame, append new points and prune points where `point.t < frame.t - 60`
    - For each chart, call `renderChart(canvasId, seriesMap, options)` using `ctx.beginPath()` / `ctx.lineTo()` only (no external library)
    - _Requirements: 7.1, 7.2, 7.6_

  - [~] 11.2 Implement chart series styling and reference lines
    - Trust chart: draw vehicle 3's series with `lineWidth = 2.5`; all others with `lineWidth = 1.0`
    - Anomaly chart: draw a horizontal dashed line at `S = 0.5` labeled "Detection threshold"
    - When `attack_active` transitions from `false` to `true`, record the current `t` and draw a vertical dashed line labeled `"Attack t=Xs"` on all four charts
    - _Requirements: 7.3, 7.4, 7.5_

  - [~] 11.3 Implement `appendChartCompare(frame)` for comparison mode
    - Overlay MA-ABSE-AR and CA_full speed/gap series on the same chart panels using distinct colors (e.g., `MA-*` series in red-hue, `CA-*` in green-hue)
    - Retain final run data until a new run starts
    - _Requirements: 7.7_

- [ ] 12. Write `dashboard/app.js` — crypto log, performance panel, scenario table
  - [~] 12.1 Implement `updateCryptoLog(entries)` for `#crypto-log-table`
    - Prepend new entries to the table body; trim to 20 rows
    - For rows where `zktat_pass === false` or `hpo_pass === false`, apply class `zktat-fail` (red highlight)
    - For rows where `bloom_hit === true`, apply class `bloom-hit` (orange highlight)
    - _Requirements: 8.2, 8.4, 8.5, 8.6_

  - [~] 12.2 Populate `#perf-table` from `/api/data`
    - On page load, call `fetch('/api/data')` and extract `data.native`
    - Populate rows for SMBP naive, SMBP precomp, Dalek variable-base, Dalek fixed-base, ZK-TAT prove, ZK-TAT verify, Cert verify, H-PO SHA-256, HMAC, Match-16, Bloom query
    - Display SMBP speedup as `(naive_us / smbp_w1_us).toFixed(1) + "x faster"`
    - Display ZK-TAT verify budget as `(zk_verify_us / 100000 * 100).toFixed(2) + "% of 100 ms V2X slot"`
    - Display Bloom query as `"Bloom query = 0.145 µs (< 0.001% of V2X slot)"`
    - Display ZK-TAT negative test count line from `native.neg_C` etc.
    - If `native` is null/empty, show "Native benchmark data unavailable — run cargo to regenerate" and display "—" in all numeric cells
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [~] 12.3 Populate `#scenario-table` from `/api/data`
    - Use `data.scenarios` to build one row per attack scenario (A1–A5) with two column groups: MA-ABSE-AR (D1_ma_abse_ar) and CA_full
    - Each cell: `mean_min_gap ± std_min_gap`, collision count, mean detection delay, mean revocation delay
    - Apply class `collision-cell` to any collision count cell that is > 0
    - Display "—" for detection/revocation delay when value is null
    - Add a footer row with summed collision count and mean min_gap across the five attack scenarios for each configuration
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

- [~] 13. Checkpoint — frontend complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Write `tests/test_sim_integrated.py` — structural / example-based tests
  - [~] 14.1 Write structural unit tests
    - Assert `D1_ma_abse_ar` key exists in `sim_integrated.CFG` with `gate=True, trust=None, crypto=True`
    - Assert outsider packets (`cred=False`) are rejected under `D1_ma_abse_ar` in A5_forged (run seed 1 and check that every `PacketLogEntry` for a `cred=False` source has `accepted=False`)
    - Assert `process_telemetry_step` call count matches expected beacon count under CA_full (use `unittest.mock.patch` on the controller method; a 100 s run at 10 Hz with 7 followers = 7,000 expected calls)
    - Assert per-packet log entries contain all required keys under a short run (10 s)
    - Assert `sim_integrated_results.json` schema matches expected structure after a minimal run
    - _Requirements: 1.2, 1.4, 2.3, 2.4, 2.9, 4.1, 4.2, 4.3_

  - [~] 14.2 Write integration test: ZK-TAT forgery (Property 3)
    - Use a fixed pair of vehicle IDs `vid1=1, vid2=2`; prove with `vid1`, then manually mutate the token's `s2` to simulate a forgery and assert verify returns `False`
    - Also test that substituting a different `C` (from a prove on `vid2`) fails verify on `vid1`'s context
    - Tag: `# Feature: cyberadapt-review2-integration, Property 3: ZK-TAT soundness under forgery`
    - **Validates: Requirements 14.3**

  - [~] 14.3 Write integration test: SSE timing
    - Start a live run via POST `/api/live` using an in-process `ThreadingHTTPServer` test instance; connect a client to `/api/stream`; collect 10 frames; assert mean inter-frame interval is in `[50 ms, 200 ms]`
    - _Requirements: 5.3_

- [~] 15. Final checkpoint — full system
  - Ensure all tests pass (including all property-based tests with `--hypothesis-seed=0`), ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; core behavior is fully implemented without them
- Each task references specific requirements for traceability
- Checkpoints at tasks 3, 5, 8, and 13 provide incremental validation gates
- Property tests use `hypothesis` (`pip install hypothesis`); run via `python -m pytest tests/test_sim_integrated.py`
- The existing `tests/test_sim.py` and `tests/test_dashboard.py` suites must continue passing — `sim_integrated.py` is a strict superset and `server.py` extensions are additive
- File paths are all relative to `e:\final_proj_implementation\CyberAdapt_Final\`
- `sim/sim.py`, `sim/runpart.py`, `sim/report.py`, `sim/gen.py` are **unchanged**

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "9.1", "9.2"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["2.3", "2.4"] },
    { "id": 3, "tasks": ["2.5"] },
    { "id": 4, "tasks": ["2.6", "2.7", "2.8", "2.9", "2.10", "2.11", "4.1"] },
    { "id": 5, "tasks": ["4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "6.1"] },
    { "id": 6, "tasks": ["6.2", "7.1"] },
    { "id": 7, "tasks": ["6.3", "6.4", "6.5", "7.2", "7.3"] },
    { "id": 8, "tasks": ["10.1"] },
    { "id": 9, "tasks": ["10.2", "10.3", "11.1"] },
    { "id": 10, "tasks": ["11.2", "11.3", "12.1"] },
    { "id": 11, "tasks": ["12.2", "12.3"] },
    { "id": 12, "tasks": ["14.1", "14.2", "14.3"] }
  ]
}
```
