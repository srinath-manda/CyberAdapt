# Dashboard Trust & Crypto Validation Bugfix Design

## Overview

This design addresses six critical architectural bugs in the CyberAdapt platoon system across trust-based gap adjustment, cryptographic validation, replay defense, legitimate emergency detection, and visualization systems.

**Bugs Summary:**
1. **Wrong Gap Direction (Trust Architecture)**: Gap adjustment at victim position (i-1→i) instead of follower position (i→i+1) when vehicle i is untrusted
2. **Crypto Payload Bypass**: Modified packets pass validation because crypto validates identity/role only, not payload integrity
3. **A4_replay Crypto Bypass**: Replayed packets from buffer pass validation with preserved credentials despite cred=False flag
4. **Binary Trust Mode Gap Bug**: Binary trust (w ∈ {0,1}, 5s latch) exhibits same wrong gap direction as graded trust
5. **L2_legit_brake False Positive**: Legitimate leader emergency brake triggers false trust degradation across all followers
6. **Compare Mode Buggy Visualization**: Both D1 and CA show wrong gap behavior, obscuring differential trust mechanisms

**Comprehensive Fix Strategy:**
- Crypto Payload Binding: HMAC-SHA256 over "ts|v|a|seq", Stage 4 verification (Bugs 2,3)
- Trust Architecture Refactor: Propagate trust forward - vehicle i+1 uses w[i+1] to control gap i→i+1 (Bugs 1,4)
- Replay Defense: Strip credentials in A4_replay, track last_seq[src], bind seq in payload MAC (Bug 3)
- Legitimate Emergency Detection: Leader exemption OR platoon coordination detection OR time window aggregation (Bug 5)
- Dashboard Visualization Fix: Show vehicle i red based on w[i+1], highlight correct gaps (Bugs 1,6)

## Glossary

- **Bug_Condition_1-6 (C1-C6)**: Formal predicates identifying when each bug manifests
- **Property_1-6 (P1-P6)**: Correct behaviors for buggy inputs
- **Trust Weight w[i]**: Graded score [W_MIN,1.0] computed by vehicle i evaluating predecessor i-1
- **Binary Trust**: w[i] ∈ {0,1}, switches to 0 when z>=0.1, latches for viol_time[i]=5.0s
- **Payload MAC**: HMAC-SHA256 over "ts|v|a|seq" for tampering detection
- **Sequence Number seq**: Monotonic counter per vehicle for replay detection
- **last_seq[src]**: Per-vehicle tracking of last seen sequence number
- **rec_for_replay**: Recording buffer storing packets at t<60s for replay injection at t>=60s
- **J_LIM**: Jerk threshold for anomaly detection
- **Coordinated Platoon Event**: Multiple vehicles simultaneously exhibiting similar behavior

## Bug Details

### Bug Condition 1: Wrong Gap Adjustment Direction

Vehicle i detects anomalies from i-1, w[i] drops, h[i] increases. But increased headway affects d_t[i] = D0 + h[i]*v[i], controlling gap i-1→i. VICTIM vehicle i backs off from ATTACKER i-1, not attacker's follower.

**Formal Specification:**
```
FUNCTION isBugCondition1(sim_state, i)
  RETURN (i >= 2) AND (w[i] < 0.5) AND (packets_from(i-1) anomalous)
         AND (gap[i] increasing) AND (gap[i+1] NOT increasing faster)
END FUNCTION
```

**Root Cause**: w[i] and h[i] applied to vehicle i's OWN control, affecting gap i-1→i instead of gap i→i+1. Semantic confusion: w[i] means "trust weight HELD BY vehicle i" not "OF vehicle i".

### Bug Condition 2: Forged Packets Pass Crypto

Insider attacker modifies payload (a, v) but reuses valid token/hpo_tag. Crypto validates identity/role, NOT message integrity.

**Formal Specification:**
```
FUNCTION isBugCondition2(packet)
  RETURN (packet["a"] != original["a"]) AND (packet["token"] == original["token"])
         AND (_run_crypto_gate(packet) returns accepted=True)
END FUNCTION
```

**Root Cause**: _attach_crypto_to_packet() computes token/hpo_tag using ONLY sender identity and role, NO payload reference. No Stage 4 payload integrity check in _run_crypto_gate().

### Bug Condition 3: A4_replay Crypto Bypass

Replayed packets from rec_for_replay buffer (t>=60s) pass validation because dict copy preserves valid credentials from original transmission. cred=False doesn't remove them. No seq tracking.

**Formal Specification:**
```
FUNCTION isBugCondition3(packet)
  replay_packet := dict(old_packet_from_buffer, arr=t+0.035, cred=False, replay=True)
  RETURN (replay_packet contains token, hpo_tag, payload_mac from old_packet)
         AND (_run_crypto_gate(replay_packet) returns accepted=True)
         AND (no sequence number freshness check)
END FUNCTION
```

**Root Cause**: dict(old) copies ALL fields including credentials. cred=False is cosmetic. No last_seq[src] tracking. Timestamp freshness (0.2s) only catches immediate replays, not 60s+ replays.

### Bug Condition 4: Binary Trust Mode Gap Bug

Binary trust (D2_binary_hnom, D2b_binary_hfail) with w ∈ {0,1} and 5s viol_time latch exhibits same wrong gap direction. When z>=0.1, w[i]=0 for 5s, but gap i-1→i expands instead of i→i+1.

**Formal Specification:**
```
FUNCTION isBugCondition4(sim_state, i, cfg)
  RETURN (cfg.trust_mode == "binary") AND (z >= 0.1) AND (viol_time[i] > 0)
         AND (w[i] == 0) AND (gap[i] increasing) AND (gap[i+1] NOT increasing faster)
END FUNCTION
```

**Root Cause**: Binary mode uses same control law structure as graded trust. Bug 1's trust weight indexing mismatch applies identically to binary mode with viol_time latch.

### Bug Condition 5: L2_legit_brake Trust False Positive

Legitimate leader emergency brake (a=-6.0 for 1.8s at t=30s) triggers high jerk J > J_LIM across ALL followers. System detects anomaly, applies zJ penalty, drops trust weights, causing false positives.

**Formal Specification:**
```
FUNCTION isBugCondition5(scenario, i)
  leader_packet := packet with src=0, a=-6.0 (legitimate emergency)
  J := |leader_packet["a"] - previous_packet["a"]| / dt
  RETURN (scenario == "L2_legit_brake") AND (leader_packet.src == 0)
         AND (J > J_LIM) AND (w[i] < 0.5) AND (leader behavior legitimate)
END FUNCTION
```

**Root Cause**: Anomaly detection uses only local jerk/velocity/coherence metrics. Cannot distinguish legitimate leader-initiated emergency from isolated attacker. Uniform J_LIM threshold. No temporal aggregation.

### Bug Condition 6: Compare Mode Shows Both Configs Buggy

Side-by-side comparison (/api/compare) shows BOTH D1 (baseline) and CA (CyberAdapt) exhibiting wrong gap behavior because both use trust mechanisms affected by Bug 1.

**Formal Specification:**
```
FUNCTION isBugCondition6(compare_mode, configs)
  RETURN (compare_mode == true) AND (BOTH configs show gap adjustment at wrong position i-1→i)
         AND (visualization fails to differentiate reactive vs proactive mechanisms)
END FUNCTION
```

**Root Cause**: Both D1 (crypto-only trust) and CA (graded trust) apply trust weights in control law affected by Bug 1's architecture. Comparison visualization shows similar buggy behavior for both.

### Examples

**Bug 1**: A1_false_brake t=25s: F3 red, w[3]=0.2, gap F2→F3 increases ~8m, gap F3→F4 increases ~2m (wrong position)
**Bug 2**: A1_false_brake: Modified a=-6.0 passes crypto (ZK-TAT ✓, H-PO ✓, Accepted=true)
**Bug 3**: A4_replay t=65s: Packet from t=15s passes crypto despite 50s age and cred=False flag
**Bug 4**: D2_binary_hnom A1: z>=0.1, w[3]=0 for 5s, gap F2→F3 increases (wrong position, same as Bug 1)
**Bug 5**: L2_legit_brake t=30s: Leader brakes, ALL followers w[] drops <0.5 (false positives across platoon)
**Bug 6**: Compare D1 vs CA in A1: BOTH show gap F2→F3 expansion (obscures differential behavior)

## Expected Behavior

### All Bugs Expected Behavior Summary

1. Gap i→i+1 SHALL increase when vehicle i untrusted (Bug 1 fix)
2. Modified packets SHALL be rejected with payload_valid=false (Bug 2 fix)
3. Replayed packets SHALL be rejected via stripped credentials or seq tracking (Bug 3 fix)
4. Binary trust mode SHALL use correct gap position i→i+1 (Bug 4 fix)
5. Legitimate leader emergency SHALL NOT trigger false positives (Bug 5 fix)
6. Compare mode SHALL show differential behavior at correct positions (Bug 6 fix)

## Hypothesized Root Cause

**Bug 1**: Trust weight indexing mismatch - w[i] applied to vehicle i's own control affecting gap i-1→i
**Bug 2**: No payload binding in crypto attachment. No Stage 4 integrity check
**Bug 3**: dict copy preserves credentials. cred=False cosmetic. No seq tracking
**Bug 4**: Binary mode uses same control law structure as graded trust. Inherits Bug 1
**Bug 5**: No contextual awareness in anomaly detection. Uniform thresholds
**Bug 6**: Both D1 and CA affected by Bug 1. Visualization doesn't distinguish trust mechanisms

## Correctness Properties

Property 1: Bug Condition 1 - Correct Gap Adjustment Direction

_For any_ simulation state where vehicle i (i >= 2) has low trust weight (w[i] < 0.5) due to anomalies from predecessor i-1, the fixed control law SHALL cause gap i→i+1 to increase (follower i+1 SHALL back off from untrusted vehicle i), NOT gap i-1→i.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Bug Condition 2 - Forged Packets Rejected

_For any_ V2X packet where payload fields (a, v) modified but crypto credentials reused from legitimate packet, the fixed crypto gate SHALL detect tampering and reject with accepted=false.

**Validates: Requirements 2.5, 2.6, 2.7, 2.8**

Property 3: Bug Condition 3 - Replay Packets Detected

_For any_ V2X packet in A4_replay replayed from rec_for_replay buffer (t>=60s), the fixed system SHALL detect replay via (1) stripped credentials failing validation OR (2) sequence freshness check rejecting seq <= last_seq[src].

**Validates: Requirements 2.9, 2.10, 2.11, 2.12, 2.13**

Property 4: Bug Condition 4 - Binary Trust Correct Gap

_For any_ configuration running binary trust mode (D2_binary_hnom, D2b_binary_hfail) where vehicle i triggers binary violation (z >= 0.1, w[i]=0), the fixed control law SHALL cause gap i→i+1 to increase, NOT gap i-1→i.

**Validates: Requirements 2.14, 2.15, 2.16, 2.17**

Property 5: Bug Condition 5 - Legitimate Emergency No False Positive

_For any_ L2_legit_brake scenario where leader (src=0) initiates legitimate emergency brake (a=-6.0 for 1.8s at t=30s), the fixed anomaly detection SHALL maintain high trust in leader (w[i] ≈ 1.0 for followers) by exempting leader from jerk penalty OR detecting coordinated platoon event OR using time window aggregation.

**Validates: Requirements 2.18, 2.19, 2.20, 2.21, 2.22**

Property 6: Bug Condition 6 - Compare Mode Correct Differential Visualization

_For any_ comparison run (/api/compare) with D1 vs CA, the fixed dashboard SHALL show differential gap behavior: D1 (reactive-only at correct position i→i+1) vs CA (proactive+reactive at correct position i→i+1), with annotations distinguishing trust mechanisms.

**Validates: Requirements 2.23, 2.24, 2.25, 2.26, 2.27**

Property 7: Preservation - All Unchanged Behaviors

_For any_ non-buggy inputs (scenarios without attacks or with legitimate behaviors), the fixed system SHALL preserve existing behaviors: self-protection layer, baseline performance, legitimate packet acceptance, outsider attack rejection, bloom revocation, timestamp freshness.

**Validates: Requirements 3.1-3.10**

## Fix Implementation

### Changes Required

**File**: e:\\final_proj_implementation\\CyberAdapt_Final\\sim\\sim_integrated.py

#### Change Category 1: Add Payload MAC to Crypto Attachment (Bug 2 Fix)

**Function**: _attach_crypto_to_packet() (lines 169-187)

**Changes**: Import hmac/hashlib, serialize payload, compute HMAC-SHA256, attach payload_mac field

#### Change Category 2: Add Payload Integrity Check to Crypto Gate (Bug 2 Fix)

**Function**: _run_crypto_gate() (lines 133-166)

**Changes**: Extract fields, reconstruct payload, verify MAC in Stage 4, update acceptance logic, add payload_valid to PacketLogEntry

#### Change Category 3: Strip Credentials in A4_replay (Bug 3 Fix)

**Location**: Lines 249-253

**Changes**: Replace dict(old) with explicit field copying, exclude token/hpo_tag/payload_mac/cred_id

#### Change Category 4: Add Sequence Number Tracking (Bug 3 Fix)

**Function**: _run_crypto_gate()

**Changes**: Add last_seq dict, check seq freshness before Stage 4, add replay_detected to PacketLogEntry

#### Change Category 5: Redesign Trust Weight Application (Bug 1 & 4 Fix)

**Function**: Control loop (lines 447-477)

**Changes**: Keep anomaly detection unchanged, propagate trust forward so vehicle i+1 uses w[i+1] to affect gap i→i+1

#### Change Category 6: Legitimate Emergency Detection (Bug 5 Fix)

**Function**: Anomaly detection loop (lines 393-426)

**Changes**: Implement leader exemption (higher J_LIM for src=0) AND time window aggregation (persistent anomalies only)

#### Change Category 7: Update Dashboard Visualization (Bug 1 & 6 Fix)

**File**: e:\\final_proj_implementation\\CyberAdapt_Final\\dashboard\\app.js

**Changes**: Use w[i+1] for vehicle i coloring, highlight gap i→i+1 when vehicle i red, add compare mode annotations

#### Change Category 8: Update PacketLogEntry Dataclass (Bug 2 & 3 Fix)

**Location**: Line 125-135

**Changes**: Add payload_valid and replay_detected bool fields, update dashboard crypto log

## Testing Strategy

### Validation Approach

1. **Exploratory Bug Condition Checking**: Surface counterexamples on UNFIXED code confirming all 6 bugs
2. **Fix Checking**: Verify FIXED code produces correct behavior for buggy inputs
3. **Preservation Checking**: Verify unchanged behaviors remain intact

### Exploratory Tests (UNFIXED Code)

- Bug 1: A1_false_brake CA_full t=25s: Expect gap[2] increases ~8m, gap[3] ~2m
- Bug 2: A1_false_brake CA_full: Expect modified packets show accepted=true
- Bug 3: A4_replay CA_full t=65s: Expect replayed packets show accepted=true
- Bug 4: D2_binary_hnom A1: Expect gap[2] increases when w[3]=0
- Bug 5: L2_legit_brake CA_full t=32s: Expect w[] drops <0.5 for followers
- Bug 6: Compare D1 vs CA in A1: Expect both show gap F2→F3 expansion

### Fix Checking Tests (FIXED Code)

- Bug 1: Verify gap F3→F4 increases when F3 red, not gap F2→F3
- Bug 2: Verify forged packets rejected with payload_valid=false
- Bug 3: Verify replayed packets rejected via stripped credentials or seq tracking
- Bug 4: Verify gap i→i+1 expands in binary mode
- Bug 5: Verify trust weights maintained for legitimate leader emergency
- Bug 6: Verify differential gap behavior at correct positions

### Preservation Tests (FIXED Code)

- L1_normal: Verify baseline performance identical to original
- Legitimate packets: Verify accepted=true with valid payload_mac
- A5_forged: Verify outsider packets rejected
- Revoked cred_id: Verify bloom_hit=true, accepted=false
- Timestamp freshness: Verify rejection outside 0.2s window
- Self-protection: Verify vehicle i still increases gap to i-1 IN ADDITION to vehicle i+1 backing off

### Unit, Property-Based, and Integration Tests

- Crypto MAC computation/verification with valid/modified payloads
- Sequence number tracking with in-order/out-of-order/replayed values
- Trust weight propagation in control loop
- Legitimate emergency detection with leader packets
- Dashboard vehicle coloring and gap visualization
- Full simulations (A1, A4, L2) with all fixes integrated
