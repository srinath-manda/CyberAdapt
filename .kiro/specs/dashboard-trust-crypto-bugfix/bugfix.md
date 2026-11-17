# Dashboard Trust & Crypto Validation Bugfix Requirements Document

## Introduction

The CyberAdapt live dashboard exhibits six critical architectural bugs across trust-based gap adjustment, cryptographic validation, and visualization systems that together undermine platoon safety. These bugs affect multiple configurations and attack scenarios, requiring comprehensive fixes to restore correct defensive behavior.

**Bug 1 - Wrong Gap Direction (Trust Architecture)**: When vehicle F3 is detected as untrustworthy (shown red in dashboard), the gap F2→F3 increases instead of F3→F4, meaning the victim backs off from the attacker rather than the attacker's follower backing off. This affects ALL trust-enabled configurations (D2_binary_hnom, D2b_binary_hfail, CA_full, CA_norevoke, CA_fixedh) across scenarios A1_false_brake, A2_false_accel, A3_stealth_ramp, and live inject.

**Bug 2 - Crypto Payload Bypass (Message Integrity)**: Modified attack packets with altered acceleration (a=-6.0) pass crypto validation (ZK-TAT ✓, H-PO ✓, Accepted=true) because tokens validate sender identity/role only without cryptographic binding to message payload (ts, v, a fields). Affects crypto-enabled configs (D1_ma_abse_ar, CA_full, CA_norevoke, CA_fixedh).

**Bug 3 - A4_replay Crypto Bypass**: Replayed packets from recorded buffer pass crypto validation because they contain VALID crypto credentials from original transmission. Setting cred=False doesn't remove existing credentials. Affects all crypto-enabled configurations in A4_replay scenario (t>=60s).

**Bug 4 - Binary Trust Mode Gap Bug**: Binary trust mode (w=0 or w=1 with 5s latch) exhibits the same wrong gap direction as graded trust. When vehicle i triggers binary trust violation (z >= 0.1), vehicle i backs off instead of vehicle i+1. Affects D2_binary_hnom and D2b_binary_hfail configurations.

**Bug 5 - L2_legit_brake Trust False Positive**: Legitimate emergency braking by leader (a=-6.0 for 1.8s at t=30s) triggers high jerk anomaly detection across ALL followers, causing false positive trust degradation. System cannot distinguish coordinated platoon emergency response from individual attacker behavior. Affects all trust-enabled configurations in L2_legit_brake scenario.

**Bug 6 - Compare Mode Shows Both Configs Buggy**: Side-by-side comparison (/api/compare endpoint) shows BOTH configurations exhibit wrong gap behavior because trust bugs affect both baseline (D1 with crypto-only trust) and CyberAdapt (CA with graded trust). Visualization fails to differentiate reactive-only vs proactive+reactive gap adjustment mechanisms.

These bugs interact systematically: Bug 2 allows payload tampering to bypass crypto validation, Bug 1 causes defensive gaps at wrong positions, Bug 3 enables replay attacks to circumvent freshness checks, Bug 4 extends wrong-gap behavior to binary trust mode, Bug 5 causes false positives during legitimate emergencies, and Bug 6 obscures correct system behavior in comparisons.

## Bug Analysis

### Current Behavior (Defect)

#### Bug 1: Wrong Gap Direction (Trust Architecture)

1.1 WHEN vehicle F3 (position i=2) is the attacker and transmits malicious packets to F4 THEN the dashboard shows F3 as red (untrusted) BUT the gap F2→F3 increases instead of F3→F4

1.2 WHEN trust weight `w[i]` drops at vehicle i due to anomalies from predecessor i-1 THEN vehicle i increases its own gap to i-1, causing the victim vehicle to back off from the attacker rather than the attacker's follower backing off

1.3 WHEN vehicle F3 broadcasts malicious data to F4 THEN `w[4]` stays high because F3's outgoing packets to F4 appear legitimate in consistency checks, so F4 does not back off from the red vehicle

1.4 WHEN configurations D2_binary_hnom, D2b_binary_hfail, CA_full, CA_norevoke, CA_fixedh run scenarios A1_false_brake, A2_false_accel, A3_stealth_ramp, or live inject THEN gap adjustments occur at victim position (i-1→i) instead of follower position (i→i+1)

#### Bug 2: Crypto Payload Bypass (Message Integrity)

1.5 WHEN an attacker modifies the acceleration field `a` in a legitimate packet (A1_false_brake: `f["a"] = -6.0`) and preserves the original `token`, `hpo_tag`, and `cred_id` THEN crypto validation shows ZK-TAT ✓, H-PO ✓, Bloom hit = false, Accepted = true

1.6 WHEN `_run_crypto_gate()` validates a packet in Stages 2-3 (ZK-TAT verify, H-PO match) THEN it only validates sender identity and role attributes BUT does NOT verify message payload integrity (acceleration, velocity values)

1.7 WHEN insider attacks (A1_false_brake, A2_false_accel, A3_stealth_ramp, live inject) copy legitimate packets, modify payload, but reuse valid crypto credentials THEN the packets pass all crypto gates and propagate downstream unchecked

1.8 WHEN configurations D1_ma_abse_ar, CA_full, CA_norevoke, CA_fixedh run attack scenarios THEN forged packets with modified payloads pass crypto validation despite tampering

#### Bug 3: A4_replay Crypto Bypass

1.9 WHEN A4_replay scenario executes at t>=60s AND packets are copied from rec_for_replay buffer THEN the copied packets contain valid token, hpo_tag, and payload_mac from original transmission time

1.10 WHEN replay injection code (lines 249-253) sets `cred=False` on replayed packet THEN the existing crypto credentials (token, hpo_tag, payload_mac) in the copied dict are NOT removed

1.11 WHEN `_run_crypto_gate()` processes replayed packet THEN it validates the original valid credentials and accepts the packet (Accepted=true) despite being a replay from 60+ seconds ago

1.12 WHEN timestamp freshness check (0.2s window) runs on replayed packet THEN it only catches replays within 0.2s, NOT replays from recording buffer 60+ seconds old

1.13 WHEN no sequence number tracking exists per vehicle source THEN the system cannot detect that replayed packet has seq number already seen 60+ seconds ago

#### Bug 4: Binary Trust Mode Gap Bug

1.14 WHEN configuration D2_binary_hnom or D2b_binary_hfail runs (binary trust mode w=0 or w=1) THEN the system exhibits same wrong gap direction as graded trust mode

1.15 WHEN vehicle i detects anomaly z >= 0.1 from predecessor i-1 in binary mode THEN vehicle i triggers viol_time[i] latch and sets w[i]=0 for 5 seconds

1.16 WHEN w[i]=0 due to binary violation latch THEN vehicle i increases its own headway h[i], causing gap i-1→i to expand instead of gap i→i+1

1.17 WHEN binary trust violation clears (z < 0.1) and 5s latch expires THEN w[i] resets to 1.0 but gap adjustment already occurred at wrong position

#### Bug 5: L2_legit_brake Trust False Positive

1.18 WHEN L2_legit_brake scenario executes at t=30s AND leader initiates legitimate emergency brake (a=-15.0 for 0.4s then a=-6.0 for 1.4s) THEN ALL followers receive legitimate deceleration packets

1.19 WHEN follower vehicle i computes jerk J = |a_new - a_old| / dt from legitimate emergency brake packets THEN J exceeds J_LIM threshold, triggering zJ penalty

1.20 WHEN jerk penalty zJ accumulates in anomaly score S[i] THEN trust weight w[i] drops below 0.5, marking leader as "untrusted" despite legitimate behavior

1.21 WHEN anomaly detection uses only local jerk/velocity/coherence metrics THEN the system cannot distinguish legitimate coordinated platoon emergency from isolated attacker behavior

1.22 WHEN all followers simultaneously experience high jerk from leader's emergency brake THEN trust degradation propagates through entire platoon, causing false positive detections across all trust-enabled configurations

#### Bug 6: Compare Mode Shows Both Configs Buggy

1.23 WHEN /api/compare endpoint runs side-by-side comparison (typically D1_ma_abse_ar vs CA_full) THEN BOTH configurations show wrong gap adjustment direction because both use trust mechanisms affected by Bug 1

1.24 WHEN D1_ma_abse_ar (baseline) runs with crypto-only trust via anomaly detection THEN it exhibits wrong gap direction at victim position i-1→i

1.25 WHEN CA_full (CyberAdapt) runs with graded trust THEN it also exhibits wrong gap direction at same position due to shared trust architecture bug

1.26 WHEN dashboard compare visualization displays gap evolution for both configs THEN it shows similar buggy behavior for both, obscuring the intended difference between reactive-only (D1) and proactive+reactive (CA) gap adjustment

1.27 WHEN compare mode should highlight differential trust mechanisms THEN it fails to distinguish because underlying trust architecture bug affects both configurations identically

### Expected Behavior (Correct)

#### Bug 1 Fix: Correct Gap Direction (Trust Architecture)

2.1 WHEN vehicle F3 (position i=2) is detected as untrustworthy (shown red in dashboard) THEN the system SHALL cause gap F3→F4 to increase, meaning F4 (the follower) SHALL increase distance from untrusted F3

2.2 WHEN a vehicle i is identified as an attacker or has low trust weight THEN its immediate follower (vehicle i+1) SHALL detect the threat through anomaly metrics and reduce `w[i+1]`, triggering increased headway affecting gap i→i+1

2.3 WHEN the dashboard visualizes a vehicle as red (untrusted) THEN the gap adjustment behavior SHALL match the visualization: the follower of that red vehicle SHALL back off, highlighting gap i→i+1

2.4 WHEN trust weight w[i] is computed by vehicle i evaluating predecessor i-1 THEN the trust effect SHALL propagate forward: vehicle i+1 SHALL use this trust evaluation when computing its gap control to vehicle i

#### Bug 2 Fix: Crypto Payload Binding (Message Integrity)

2.5 WHEN an attacker modifies any payload field (acceleration `a`, velocity `v`) in a packet THEN crypto validation SHALL detect tampering and reject the packet with validation failure status

2.6 WHEN `_run_crypto_gate()` validates a packet's token and H-PO tag THEN it SHALL verify the token is cryptographically bound to message content (acceleration, velocity, timestamp), not just sender identity

2.7 WHEN insider attacks attempt to forge data by reusing valid credentials with modified payloads THEN the crypto gate SHALL reject these packets (Accepted = false) and log them as tampering attempts

2.8 WHEN `_attach_crypto_to_packet()` generates credentials THEN it SHALL compute HMAC-SHA256 over serialized payload "ts|v|a|seq" and attach payload_mac field for integrity verification

#### Bug 3 Fix: Replay Attack Defense

2.9 WHEN A4_replay scenario copies packets from rec_for_replay buffer THEN the replay injection code SHALL strip all crypto credentials (token, hpo_tag, payload_mac) before reinjection

2.10 WHEN crypto gate receives packet THEN it SHALL track last_seq[src] per vehicle source and reject packets with seq <= last_seq[src] (replay detection via sequence freshness)

2.11 WHEN payload MAC is computed THEN it SHALL include seq field in binding: "ts|v|a|seq" preventing attacker from incrementing seq on replayed packet to bypass freshness check

2.12 WHEN hard gate validates packet THEN it SHALL check sequence number freshness BEFORE crypto gate, enabling early rejection of replayed packets

2.13 WHEN sequence number tracking detects seq <= last_seq[src] THEN packet SHALL be rejected with replay_detected flag in PacketLogEntry

#### Bug 4 Fix: Binary Trust Mode Correct Gap

2.14 WHEN configuration D2_binary_hnom or D2b_binary_hfail runs in binary trust mode THEN the trust architecture fix (Bug 1) SHALL apply identically: gap i→i+1 expands when vehicle i is untrusted

2.15 WHEN vehicle i detects anomaly z >= 0.1 from predecessor i-1 in binary mode THEN vehicle i SHALL trigger viol_time[i] latch, but the gap effect SHALL apply at follower position i→i+1

2.16 WHEN binary trust violation latch sets w[i]=0 for 5 seconds THEN vehicle i+1 SHALL increase its headway affecting gap i→i+1, not vehicle i affecting gap i-1→i

2.17 WHEN binary trust mode switches between w=0 and w=1 with latch logic THEN gap adjustments SHALL occur at correct follower position consistently across all trust level transitions

#### Bug 5 Fix: Legitimate Emergency Detection

2.18 WHEN L2_legit_brake scenario executes AND leader (src=0) initiates legitimate emergency brake THEN follower anomaly detection SHALL exempt leader from jerk penalty OR use higher J_LIM threshold for leader packets

2.19 WHEN multiple consecutive vehicles (i-2, i-1, i) all report similar high deceleration simultaneously THEN the system SHALL classify this as coordinated platoon maneuver, NOT individual attack, avoiding false positive trust degradation

2.20 WHEN anomaly metrics exceed thresholds transiently (<1.0s window) THEN the system SHALL NOT trigger trust degradation, allowing legitimate emergency responses to complete without false positives

2.21 WHEN leader initiates emergency brake with high jerk THEN followers SHALL maintain high trust in leader (w ≈ 1.0) while still responding to emergency via radar-based control and emergency braking logic

2.22 WHEN legitimate emergency scenarios (L2_legit_brake) run across all trust-enabled configurations THEN false positive rate SHALL be zero or near-zero, distinguishing from attack scenarios (A1, A2, A3)

#### Bug 6 Fix: Compare Mode Correct Visualization

2.23 WHEN /api/compare endpoint runs side-by-side comparison THEN the dashboard SHALL correctly show differential gap behavior: D1 (baseline) with reactive-only gaps vs CA (CyberAdapt) with proactive+reactive gaps at correct follower positions

2.24 WHEN D1_ma_abse_ar (baseline) runs THEN it SHALL show gap adjustment at correct position i→i+1 based on its crypto-only trust mechanism

2.25 WHEN CA_full (CyberAdapt) runs THEN it SHALL show gap adjustment at correct position i→i+1 based on its graded trust mechanism, with clearer proactive response compared to D1

2.26 WHEN compare visualization displays gap evolution THEN it SHALL annotate differences: D1 (reactive anomaly detection only) vs CA (proactive trust + reactive anomaly), highlighting correct defensive behavior in both

2.27 WHEN dashboard shows vehicle health status in compare mode THEN vehicle i SHALL be colored red based on w[i+1] (follower's evaluation), ensuring consistency between vehicle color and gap expansion position

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a vehicle i detects anomalies in packets FROM its predecessor i-1 THEN the system SHALL CONTINUE TO allow vehicle i to locally increase its own gap to i-1 (existing self-protection layer, preserved as additional safety)

3.2 WHEN no attacks are present and all vehicles have high trust weights THEN the system SHALL CONTINUE TO maintain nominal gaps and headways as in baseline (min_gap ≥ 8m, mean_headway ≈ 0.6s)

3.3 WHEN vehicles compute control based on radar, last packet, and trust weights THEN the system SHALL CONTINUE TO use existing control law (KP, KD, KFF gains, jerk limits, emergency braking)

3.4 WHEN legitimate packets with unmodified payload and valid credentials are received THEN the system SHALL CONTINUE TO accept them with ZK-TAT ✓, H-PO ✓, Accepted = true

3.5 WHEN outsider forged packets (A5_forged) with `cred=False` and no token arrive THEN the system SHALL CONTINUE TO reject them as currently implemented

3.6 WHEN Bloom revocation checks (Stage 1) run THEN they SHALL CONTINUE TO reject packets from revoked credential IDs regardless of token validity

3.7 WHEN crypto latency measurements (prove_us, verify_us, hpo_us, bloom_us) are collected THEN the system SHALL CONTINUE TO log these in PacketLogEntry for performance analysis

3.8 WHEN timestamp freshness check runs within 0.2s window THEN it SHALL CONTINUE TO reject packets with timestamps outside window (preserved for near-term freshness, enhanced by sequence number check for long-term replay defense)

3.9 WHEN legitimate scenario L1_normal runs with no attacks THEN system SHALL CONTINUE TO produce baseline performance metrics identical to original implementation

3.10 WHEN A5_forged (outsider attack) runs THEN crypto gate SHALL CONTINUE TO reject packets with cred=False and missing credentials, maintaining existing outsider defense
