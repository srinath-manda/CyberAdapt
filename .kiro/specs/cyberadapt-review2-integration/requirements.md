# Requirements Document

## Introduction

CyberAdapt Review-2 Integration extends the existing CyberAdapt evaluation package to close the gap between the flag-based prototype and a demonstrably complete, presentation-ready system. The existing `sim.py` uses boolean flags to represent crypto decisions; `native/src/main.rs` holds the real Ristretto255 benchmarks; `cyberadapt_crypto.py` and `cyberadapt_control.py` hold working Python implementations of all six solutions. These assets exist in isolation. This feature wires them together into three deliverables:

1. **Integrated Crypto Simulator** (`sim/sim_integrated.py`) — `sim.py` extended to invoke real Python ZK-TAT prove/verify and H-PO compute/match on every 10 Hz V2X packet, including a new MA-ABSE-AR config (D1_ma_abse_ar) that exposes the insider-attack gap the base paper cannot close.
2. **Live Real-Time Dashboard** (extends `dashboard/`) — the existing static dashboard extended with Server-Sent Events (SSE), an animated 8-vehicle platoon view, real-time charts, a crypto gate log, and a side-by-side MA-ABSE-AR vs CyberAdapt comparison mode; all using Python stdlib only.
3. **Results Display** — scenario comparison tables and all Review-2 benchmark numbers drawn from `native_results.json` and `sim_results.json`.

The comparison paper is MA-ABSE-AR (Multi-Authority Attribute-Based Searchable Encryption with Attribute Revocation for IoV, IEEE TVT May 2026). CyberAdapt does not implement multi-authority ABSE; it addresses the layer MA-ABSE-AR leaves open — physical plausibility checking after a valid credential is verified.

---

## Glossary

- **Simulator**: The Python closed-loop platoon simulator, currently `sim/sim.py`, to be extended as `sim/sim_integrated.py`.
- **Integrated_Simulator**: The new `sim/sim_integrated.py` module that calls real Python crypto on every V2X packet.
- **ZK-TAT**: Zero-Knowledge Telemetry Authentication Token — a 128-byte token (C, e, s1, s2) based on a Pedersen commitment and Fiat-Shamir challenge, implemented in `cyberadapt_crypto.py`.
- **H-PO**: Hash-Based Policy Obfuscation — a 32-byte SHA-256 keyed tag: `SHA-256("HPO_SALT_V1" || attribute || shared_secret)`, implemented in `cyberadapt_crypto.py`.
- **SMBP**: Fixed-base ECC precomputation table T[i] = 2^i * G (256 entries), eliminating online doublings.
- **Bloom_Filter**: The 4 KiB, 4-probe, 32 768-bit revocation Bloom filter with P_FP ≈ 0.00123%.
- **Trust_Supervisor**: The Python `CyberAdaptTrustController` in `cyberadapt_control.py`, implementing Solutions 4–6 (anomaly fusion, shifted sigmoid w(S), actuator blending, dynamic headway).
- **Anomaly_Score**: The fused scalar S ∈ [0, 1] produced by combining jerk and Doppler radar residuals.
- **Trust_Weight**: The graded scalar w(S) ∈ [0.05, 1.00] produced by the calibrated shifted sigmoid with α=8, β=0.45.
- **Dynamic_Headway**: The time-gap h(t) = h_nom + (1 − w)(h_fail − h_nom), where h_nom=0.60 s, h_fail=1.60 s.
- **MA-ABSE-AR_Config**: The new defense configuration `D1_ma_abse_ar` — crypto gate only (ZK-TAT + H-PO pass → command executed directly), no physical plausibility checks.
- **CyberAdapt_Config**: Any of the existing configurations CA_full, CA_norevoke, or CA_fixedh.
- **Dashboard_Server**: The Python HTTP server in `dashboard/server.py`, extended with SSE endpoints, to be served on port 8765.
- **SSE_Stream**: An HTTP Server-Sent Events stream emitting JSON-encoded simulation state at 100 ms intervals.
- **Live_Run**: A simulation run executing step-by-step in a background thread while the Dashboard_Server streams its state to connected browser clients.
- **Crypto_Gate_Log**: A rolling log of the last 20 V2X packets showing ZK-TAT result, H-PO result, Bloom filter result, and per-packet latency.
- **Platoon_View**: The animated SVG/canvas rendering of 8 vehicles moving left-to-right, color-coded by Trust_Weight.
- **Comparison_Mode**: A dashboard view that runs MA-ABSE-AR_Config and CA_full simultaneously on the same scenario and seed, rendering both side-by-side.
- **Performance_Panel**: The dashboard section displaying SMBP, ZK-TAT, H-PO, and Bloom latency values loaded from `results/native_results.json`.
- **Scenario_Results_Table**: A table comparing MA-ABSE-AR_Config against CyberAdapt_Config across scenarios A1–A5, showing min_gap, collision count, mean_detection_delay, and mean_revocation_delay.
- **Packet**: A single V2X beacon transmitted by one vehicle and received by its follower at 10 Hz.
- **Insider_Attack**: An attack scenario (A1–A3) in which vehicle 2 holds a valid credential but transmits false telemetry. MA-ABSE-AR_Config cannot detect this; CA_full can.
- **Outsider_Attack**: Scenario A5, where the injected packet carries `cred=False`. Both MA-ABSE-AR_Config and CyberAdapt_Config reject it at the crypto gate.
- **Seed**: An integer in [1, 20] passed to `random.Random` to reproduce a deterministic simulation run.
- **Jerk_Limit**: The configurable J_LIM parameter (default 10.0 m/s³ in sim.py) used for the jerk plausibility check inside the trust loop.
- **native_results.json**: The file at `results/native_results.json` produced by `cargo run --release` in `native/`, containing Rust benchmark timings.
- **sim_results.json**: The file at `results/sim_results.json` produced by `sim/runpart.py`, containing per-seed per-variant per-scenario outcome dicts.

---

## Requirements

### Requirement 1: MA-ABSE-AR Baseline Configuration

**User Story:** As a reviewer at CBIT Hyderabad, I want to see MA-ABSE-AR's exact behavior in the simulator so that I can verify CyberAdapt's improvement claim against a correctly modeled baseline.

#### Acceptance Criteria

1. THE Integrated_Simulator SHALL include a configuration named `D1_ma_abse_ar` in its `CFG` dict alongside the seven existing configurations.
2. WHEN the Integrated_Simulator processes a V2X Packet under `D1_ma_abse_ar`, THE Integrated_Simulator SHALL accept the Packet if and only if ZK-TAT verification passes and H-PO tag matching passes, with no additional physical plausibility checks.
3. WHEN an Insider_Attack scenario (A1_false_brake, A2_false_accel, A3_stealth_ramp) is run under `D1_ma_abse_ar`, THE Integrated_Simulator SHALL record `first_det=null` and `rev=null` for every seed, because a valid credential bypasses the crypto gate and no plausibility layer exists.
4. WHEN scenario A5_forged is run under `D1_ma_abse_ar`, THE Integrated_Simulator SHALL reject Outsider_Attack packets that carry `cred=False`, matching the behavior of the existing `D1_crypto` configuration.
5. THE Integrated_Simulator SHALL record per-packet ZK-TAT and H-PO latency in microseconds for every Packet processed under `D1_ma_abse_ar`, appended to a `crypto_latency` list in the run result dict.
6. FOR ALL seeds s ∈ [1, 20], running `D1_ma_abse_ar` on scenario L1_normal SHALL produce `collision=False` and `min_gap > 0`, confirming the baseline operates correctly under benign traffic.

---

### Requirement 2: Real Python Crypto on Every V2X Packet

**User Story:** As a reviewer, I want the simulator to invoke actual ZK-TAT prove/verify and H-PO compute/match on every V2X packet so that the measured crypto overhead is real, not estimated.

#### Acceptance Criteria

1. THE Integrated_Simulator SHALL import and call `ZKTAT.prove` and `ZKTAT.verify` from `cyberadapt_v1/cyberadapt_crypto.py` (or an equivalent in-tree copy) for every Packet transmitted when crypto is enabled in the active configuration.
2. THE Integrated_Simulator SHALL import and call `HPO.compute_tag` and `HPO.match_policy` from `cyberadapt_v1/cyberadapt_crypto.py` (or an equivalent in-tree copy) for every Packet when crypto is enabled.
3. WHEN ZK-TAT verification fails for a Packet, THE Integrated_Simulator SHALL discard the Packet and record `zktat_fail=True` in that Packet's log entry.
4. WHEN H-PO tag matching fails for a Packet, THE Integrated_Simulator SHALL discard the Packet and record `hpo_fail=True` in that Packet's log entry.
5. THE Integrated_Simulator SHALL measure the wall-clock duration of each `ZKTAT.prove` call in microseconds and store it as `zktat_prove_us` in the Packet's log entry.
6. THE Integrated_Simulator SHALL measure the wall-clock duration of each `ZKTAT.verify` call in microseconds and store it as `zktat_verify_us` in the Packet's log entry.
7. THE Integrated_Simulator SHALL measure the wall-clock duration of each `HPO.compute_tag` + `HPO.match_policy` call pair in microseconds and store it as `hpo_us` in the Packet's log entry.
8. WHEN the Bloom_Filter is queried for a sender's credential during Packet processing, THE Integrated_Simulator SHALL measure the query duration in microseconds and store it as `bloom_us` in the Packet's log entry.
9. THE Integrated_Simulator SHALL output a JSON file at `results/sim_integrated_results.json` whose schema is a superset of `sim_results.json`, adding a `crypto_latency` key per run containing the per-packet log entries.
10. FOR ALL configurations where `gate=False` (i.e., D0_none), THE Integrated_Simulator SHALL skip ZK-TAT and H-PO calls entirely, keeping those run results identical to `sim.py` output for the same seed.

---

### Requirement 3: Trust Supervisor Integration

**User Story:** As a reviewer, I want the simulator to use the actual Trust_Supervisor implementation from `cyberadapt_control.py` so that the control loop reflects the documented equations exactly.

#### Acceptance Criteria

1. THE Integrated_Simulator SHALL import `CyberAdaptTrustController` from `cyberadapt_v1/cyberadapt_control.py` (or an equivalent in-tree copy) and instantiate one controller per simulation run.
2. WHEN the active configuration is `CA_full`, `CA_norevoke`, or `CA_fixedh`, THE Integrated_Simulator SHALL call `CyberAdaptTrustController.process_telemetry_step` for each follower vehicle at each 10 Hz beacon step to compute Trust_Weight and Dynamic_Headway.
3. THE Integrated_Simulator SHALL pass the Trust_Weight returned by `process_telemetry_step` to the CACC actuator blending formula `u = w·a_CACC + (1−w)·a_ACC` for the follower vehicle's command in the same timestep.
4. THE Integrated_Simulator SHALL use the Dynamic_Headway returned by `process_telemetry_step` as the target time gap `h` in the spacing policy `d_target = D0 + h·v` for that follower vehicle.
5. WHEN the Anomaly_Score S exceeds 0.5 for the first time on vehicle 3 during an attack scenario, THE Integrated_Simulator SHALL record `first_det = current_time − T_ATK` in the run result, matching the detection semantics of `sim.py`.
6. THE Integrated_Simulator SHALL preserve the headway slew-rate limiter of 0.25 s/s when transitioning between headway values produced by `process_telemetry_step`.

---

### Requirement 4: Output Schema and Backward Compatibility

**User Story:** As a developer, I want `sim_integrated_results.json` to be backward-compatible with the existing dashboard reader so that all existing dashboard views continue to work without modification.

#### Acceptance Criteria

1. THE Integrated_Simulator SHALL write results keyed as `"{scenario}|{variant}"` within a `"main"` dict, identical to the key structure in `sim_results.json`.
2. EVERY run result dict produced by the Integrated_Simulator SHALL contain the fields `min_gap`, `collision`, `vmin`, `peak_decel`, `peak_jerk`, `first_det`, `rev`, `minw`, `ever_w_lt_half`, and `mean_headway`, with the same semantics as `sim.py`.
3. THE Integrated_Simulator SHALL additionally include a `"crypto"` dict in each run result containing `mean_zktat_prove_us`, `mean_zktat_verify_us`, `mean_hpo_us`, `mean_bloom_us`, and `zktat_pass_rate` (fraction of packets that passed ZK-TAT verification).
4. WHEN the Dashboard_Server reads `sim_integrated_results.json`, THE Dashboard_Server SHALL produce `summarize_rows` output identical to what it produces from `sim_results.json` for the same scenario and variant, because the extra `"crypto"` key does not alter the existing aggregation fields.
5. IF `sim_integrated_results.json` does not exist, THEN THE Dashboard_Server SHALL fall back to loading `sim_results.json` without error, preserving all existing dashboard functionality.

---

### Requirement 5: SSE Live Simulation Stream

**User Story:** As a reviewer watching a live demo, I want the browser to receive real-time simulation state updates at 100 ms intervals so that the platoon view and charts animate smoothly.

#### Acceptance Criteria

1. THE Dashboard_Server SHALL expose a GET endpoint at `/api/stream` that returns `Content-Type: text/event-stream` and streams SSE frames while a Live_Run is in progress.
2. EACH SSE frame SHALL be a JSON object containing: `t` (simulation time in seconds), `x` (array of 8 vehicle positions in metres), `v` (array of 8 speeds in m/s), `w` (array of 8 Trust_Weight values), `S` (array of 8 Anomaly_Score values), `gap` (array of 7 inter-vehicle gaps in metres), `h` (array of 8 current Dynamic_Headway values in seconds), `last_crypto` (array of up to 7 Crypto_Gate_Log entries, one per follower link), and `cfg` (active configuration name).
3. THE Dashboard_Server SHALL emit one SSE frame every 100 ms of wall-clock time regardless of simulation speed, by sampling the latest available state from the background Live_Run thread.
4. WHEN a Live_Run completes or is cancelled, THE Dashboard_Server SHALL emit a final SSE frame with `{"event": "done", "cfg": "<name>"}` and then close the stream.
5. WHEN no Live_Run is in progress and a client connects to `/api/stream`, THE Dashboard_Server SHALL return an SSE frame with `{"event": "idle"}` and then close the stream.
6. THE Dashboard_Server SHALL allow at most one Live_Run at a time; if a second POST to `/api/live` arrives while one is running, THE Dashboard_Server SHALL return HTTP 409 with `{"error": "A live run is already in progress."}`.
7. THE Dashboard_Server SHALL accept a POST to `/api/live` with a JSON body `{"scenario": "<id>", "cfg": "<id>", "seed": <int>}` to start a Live_Run, returning HTTP 202 with the initial job snapshot.

---

### Requirement 6: Animated Platoon View

**User Story:** As a reviewer at a demo, I want to see the 8 vehicles animate in real time, color-coded by their trust weight, so that the effect of an attack on trust is immediately visible.

#### Acceptance Criteria

1. THE Platoon_View SHALL render 8 vehicle rectangles on an HTML canvas or SVG element, arranged left-to-right in platoon order (vehicle 0 at right, vehicle 7 at left), updating with every received SSE frame.
2. THE Platoon_View SHALL color each vehicle using a continuous gradient from green (Trust_Weight ≥ 0.9) through yellow (Trust_Weight = 0.5) to red (Trust_Weight ≤ 0.1), computed as `hsl(w × 120, 100%, 45%)` where `w` is the Trust_Weight.
3. THE Platoon_View SHALL display the numeric Trust_Weight to two decimal places beneath each vehicle rectangle.
4. THE Platoon_View SHALL show the inter-vehicle gap in metres between adjacent vehicle pairs, updated every SSE frame.
5. WHEN a vehicle's Trust_Weight drops below 0.5 for the first time in a run, THE Platoon_View SHALL briefly flash the vehicle red for 500 ms as a visual alert.
6. THE Platoon_View SHALL label vehicle 0 as "Leader" and vehicles 1–7 as "F1"–"F7".
7. WHEN a Live_Run is not active, THE Platoon_View SHALL display a static "Waiting for run..." placeholder with no animation.

---

### Requirement 7: Real-Time Charts

**User Story:** As a reviewer, I want real-time charts of speed, trust weight, inter-vehicle gap, and anomaly score so that I can observe the dynamics of an attack and CyberAdapt's response without post-processing.

#### Acceptance Criteria

1. THE Dashboard_Server SHALL serve a page section with four chart panels: (a) per-vehicle speed v(t), (b) per-vehicle Trust_Weight w(t), (c) inter-vehicle gap gap(t) for all 7 pairs, and (d) Anomaly_Score S(t) for vehicles 1–7.
2. EACH chart panel SHALL update at most every 100 ms with the latest SSE frame data, appending a new data point to a rolling 60-second time window.
3. THE Trust_Weight chart SHALL draw the Trust_Weight series for the attacked vehicle (vehicle 3) in a heavier line weight than the other series.
4. THE Anomaly_Score chart SHALL draw a horizontal reference line at S = 0.5 labeled "Detection threshold".
5. WHEN the attack begins at T_ATK (20 s into the simulation), THE charts SHALL mark the attack start with a vertical dashed line labeled "Attack t=20s".
6. THE charts SHALL be rendered using only browser-native APIs (Canvas 2D or SVG); no external charting libraries shall be loaded from CDNs.
7. WHEN a Live_Run completes, THE charts SHALL retain the final run's data and not reset until a new Live_Run starts.

---

### Requirement 8: Crypto Gate Log Panel

**User Story:** As a reviewer, I want to see the last 20 V2X packets with their ZK-TAT, H-PO, and Bloom results and latencies so that I can verify the crypto pipeline is operating correctly.

#### Acceptance Criteria

1. THE Dashboard_Server SHALL maintain a Crypto_Gate_Log of the last 20 Packet decisions in memory during a Live_Run, updated on every SSE frame.
2. EACH Crypto_Gate_Log entry SHALL contain: `t` (packet timestamp in seconds), `src` (sender vehicle index), `zktat_pass` (boolean), `hpo_pass` (boolean), `bloom_hit` (boolean), `zktat_us` (ZK-TAT verify latency in µs), `hpo_us` (H-PO latency in µs), `bloom_us` (Bloom query latency in µs), and `accepted` (boolean — true if the packet was admitted to the control loop).
3. THE Dashboard_Server SHALL include the Crypto_Gate_Log in every SSE frame under the key `last_crypto`.
4. THE dashboard page SHALL display the Crypto_Gate_Log as a scrollable table with columns matching each field in criterion 2.
5. WHEN `zktat_pass=False` or `hpo_pass=False` for an entry, THE dashboard SHALL highlight that row in red.
6. WHEN `bloom_hit=True` for an entry, THE dashboard SHALL highlight that row in orange to indicate a revocation match.

---

### Requirement 9: Side-by-Side Comparison Mode

**User Story:** As a reviewer, I want to run MA-ABSE-AR and CyberAdapt simultaneously on the same scenario and seed and see the results side-by-side so that the security gap is immediately visible.

#### Acceptance Criteria

1. THE Dashboard_Server SHALL accept a POST to `/api/compare` with a JSON body `{"scenario": "<id>", "seed": <int>}` to start a Comparison_Mode run.
2. WHEN a Comparison_Mode run starts, THE Integrated_Simulator SHALL execute `D1_ma_abse_ar` and `CA_full` in separate threads using the same scenario and seed, coordinated by wall-clock time so that both advance at the same simulation-time rate.
3. THE SSE_Stream SHALL emit paired frames containing state arrays for both configurations: keys `ma` and `ca` each holding the same sub-fields as a standard SSE frame (`t`, `x`, `v`, `w`, `S`, `gap`).
4. THE Platoon_View SHALL display two platoon strips stacked vertically: the top strip labeled "MA-ABSE-AR" and the bottom strip labeled "CyberAdapt (CA_full)".
5. WHEN both Comparison_Mode runs reach a point where the MA-ABSE-AR run has at least one gap ≤ 0 m (collision) while the CyberAdapt run gap remains > 2 m, THE Dashboard_Server SHALL emit an SSE event `{"event": "gap_divergence", "t": <time>}` to allow the dashboard to highlight the divergence.
6. WHEN a Comparison_Mode run completes, THE dashboard SHALL display a summary table showing final min_gap, collision flag, and mean Trust_Weight for each configuration.

---

### Requirement 10: Attack Injection Button

**User Story:** As a demo presenter, I want to trigger an A1_false_brake attack at any point during a live run so that I can demonstrate CyberAdapt's response interactively.

#### Acceptance Criteria

1. THE dashboard page SHALL provide a button labeled "Inject A1 False Brake" that is enabled only while a Live_Run is active on `CA_full` or `D1_ma_abse_ar`.
2. WHEN the button is clicked, THE dashboard SHALL POST to `/api/inject` with body `{"attack": "A1_false_brake"}`.
3. WHEN THE Dashboard_Server receives POST `/api/inject`, THE Dashboard_Server SHALL signal the active Live_Run to begin injecting A1_false_brake attack packets from vehicle 2 immediately from the current simulation time.
4. THE SSE_Stream SHALL include `"attack_active": true` in all subsequent frames after injection until the Live_Run ends.
5. WHEN the attack is injected under `CA_full`, THE Trust_Weight chart SHALL show w(S) for vehicle 3 dropping from near 1.0 toward w_min = 0.05 within 3 seconds of simulated time, confirming detection.
6. WHEN the attack is injected under `D1_ma_abse_ar`, THE Trust_Weight chart SHALL remain at w = 1.0 for vehicle 3 for the entire run, confirming the insider-attack gap.

---

### Requirement 11: Performance Panel

**User Story:** As a reviewer, I want to see the SMBP, ZK-TAT, H-PO, and Bloom benchmark numbers from the Rust prototype on the dashboard so that I can cite them during the Review-2 presentation.

#### Acceptance Criteria

1. THE Dashboard_Server SHALL load `results/native_results.json` at startup and expose its contents at the existing `/api/data` endpoint under the key `"native"` (this key already exists; the requirement is that it always contains the latest file contents).
2. THE dashboard page SHALL display a Performance_Panel section with a table containing the following rows, populated from `native_results.json`: SMBP naive baseline (88.063 µs / P95: 97.8 µs), SMBP with precomp table (29.125 µs / P95: 32.0 µs), Dalek variable-base (42.471 µs / P95: 47.7 µs), Dalek fixed-base (19.129 µs / P95: 21.7 µs), ZK-TAT prove (106.183 µs / P95: 114.1 µs), ZK-TAT verify (84.127 µs / P95: 93.0 µs), Cert verify (69.646 µs / P95: 78.4 µs), H-PO SHA-256 (0.216 µs), HMAC (0.358 µs), Match-16 (5.17 µs), Bloom query (0.145 µs).
3. THE Performance_Panel SHALL display the SMBP speedup ratio, computed as `naive_us / smbp_w1_us` from `native_results.json`, formatted as "X.Xx faster".
4. THE Performance_Panel SHALL display the ZK-TAT verify budget as a percentage of a 10 Hz beacon interval (100 000 µs), formatted as "ZK-TAT verify = X.X% of 100 ms V2X slot".
5. THE Performance_Panel SHALL display the Bloom query latency as "Bloom query = 0.145 µs (< 0.001% of V2X slot)".
6. THE Performance_Panel SHALL display `neg_C=0, neg_e=0, neg_s1=0, neg_s2=0, neg_ctx=0` as "ZK-TAT negative tests: 0 false accepts in 300 trials", confirming security correctness.
7. WHEN `native_results.json` cannot be read, THE Performance_Panel SHALL display "Native benchmark data unavailable — run cargo to regenerate" and all numeric cells SHALL show "—".

---

### Requirement 12: Scenario Results Table

**User Story:** As a reviewer, I want a table comparing MA-ABSE-AR against CyberAdapt across all attack scenarios so that I can present the gap in a single view.

#### Acceptance Criteria

1. THE dashboard page SHALL include a Scenario_Results_Table with one row per scenario (A1–A5) and two column groups: "MA-ABSE-AR (D1_ma_abse_ar)" and "CyberAdapt (CA_full)".
2. EACH row SHALL display: scenario label, min_gap (mean ± std over 20 seeds), collision count out of 20 seeds, mean detection delay (seconds), and mean revocation delay (seconds).
3. WHEN collision count > 0 for a cell, THE Scenario_Results_Table SHALL color that cell red.
4. WHEN mean detection delay is null (no detections), THE Scenario_Results_Table SHALL display "—" for detection and revocation delay cells.
5. THE Scenario_Results_Table SHALL load data from `sim_integrated_results.json` if present, otherwise from `sim_results.json`, using the existing `summarize_rows` function.
6. THE Scenario_Results_Table SHALL include a footer row showing the mean min_gap and total collision count summed across all five attack scenarios for each configuration.

---

### Requirement 13: Scenario Selector and Controls

**User Story:** As a demo presenter, I want a dropdown to select any of the 8 scenarios and launch a live run with one click so that I can quickly switch between scenarios during the presentation.

#### Acceptance Criteria

1. THE dashboard page SHALL provide a scenario selector dropdown containing all 8 scenario IDs with their human-readable labels (e.g., "A1 · False braking").
2. THE dashboard page SHALL provide a configuration selector dropdown containing at least: D0_none, D1_ma_abse_ar, D1_crypto, D2b_binary_hfail, CA_full.
3. THE dashboard page SHALL provide a seed input (integer, default 1, range 1–20).
4. WHEN the "Run Live" button is clicked, THE dashboard SHALL POST to `/api/live` with the selected scenario, configuration, and seed.
5. WHEN the "Compare" button is clicked, THE dashboard SHALL POST to `/api/compare` with the selected scenario and seed.
6. WHEN a Live_Run is in progress, THE dashboard SHALL disable the "Run Live" and "Compare" buttons and show a "Stop" button.
7. WHEN the "Stop" button is clicked, THE dashboard SHALL POST to `/api/stop` and THE Dashboard_Server SHALL terminate the active Live_Run thread within 500 ms.

---

### Requirement 14: Cryptographic Correctness — ZK-TAT Round Trip

**User Story:** As a developer, I want to verify that the ZK-TAT implementation preserves the prove-then-verify identity so that forged tokens are detected reliably.

#### Acceptance Criteria

1. THE Integrated_Simulator SHALL verify that for all vehicle IDs vid ∈ [1, 7] and all context strings generated during a run, `ZKTAT.verify(ZKTAT.prove(vid, ctx), ctx)` returns `True`.
2. THE Integrated_Simulator SHALL verify that `ZKTAT.verify(token, wrong_ctx)` returns `False` when `wrong_ctx ≠ ctx`.
3. THE Integrated_Simulator SHALL verify that a token generated by one vehicle ID vid1 fails verification when checked against a different vehicle ID vid2, confirming zero identity leakage.
4. FOR ALL Packets in scenario A5_forged, THE Integrated_Simulator SHALL record `zktat_pass=False` for every injected outsider packet (those with `cred=False`), because the outsider cannot produce a valid token for vehicle 2's credential.
5. THE H-PO tag computed by `HPO.compute_tag(attribute, secret)` SHALL match `HPO.match_policy(tag, attribute, secret)` for the same inputs (round-trip identity).
6. THE H-PO tag computed with one secret SHALL fail `HPO.match_policy` when checked with a different secret, confirming key sensitivity.

---

### Requirement 15: Dashboard Server Security and Reliability

**User Story:** As a local user, I want the dashboard to remain local-only, refuse unrecognized routes, and not crash on malformed input so that the demo environment is stable.

#### Acceptance Criteria

1. THE Dashboard_Server SHALL bind only to `127.0.0.1:8765` and SHALL reject requests whose `Host` header does not match `127.0.0.1:8765` or `localhost:8765` with HTTP 403.
2. THE Dashboard_Server SHALL use Python's `http.server` and `threading` modules from the standard library only; no third-party HTTP frameworks SHALL be imported.
3. WHEN a POST body to `/api/live` or `/api/compare` contains a scenario ID not in the list of 8 known scenarios, THE Dashboard_Server SHALL return HTTP 400 with `{"error": "Unknown scenario ID."}`.
4. WHEN a POST body to `/api/live` contains a configuration ID not in the known configuration list, THE Dashboard_Server SHALL return HTTP 400 with `{"error": "Unknown configuration ID."}`.
5. WHEN a POST body to `/api/live` contains a seed outside [1, 20], THE Dashboard_Server SHALL return HTTP 400 with `{"error": "Seed must be an integer between 1 and 20."}`.
6. IF an unhandled exception occurs in a Live_Run background thread, THEN THE Dashboard_Server SHALL catch the exception, set the job status to `"failed"`, and continue serving other requests without crashing.
7. THE Dashboard_Server SHALL respond to GET `/api/status` within 200 ms even while a Live_Run is in progress, by reading the shared state under a threading lock.
