# CRITICAL: Bugs 8, 9, 10 - Attack Scenarios Broken by Crypto Fix

## Overview
The Bug 2 payload MAC fix inadvertently BROKE all insider attack scenarios (A1_false_brake, A2_false_accel, A3_stealth_ramp, live inject). These attacks modify packet acceleration but don't recompute payload_mac, causing Stage 4 rejection. This defeats the purpose of testing trust-based defenses.

---

## Bug 8: A1/A2/A3 Insider Attacks Have Mismatched Payload MAC

### Affected Scenarios
- A1_false_brake (a=-6.0)
- A2_false_accel (a=3.0)
- A3_stealth_ramp (a=-min(3.0, 1.5*t))

### Location
**run() function - Lines 276-292**
**run_live() function - Lines 565-580**

### Current Buggy Code
```python
f = dict(pk)  # Copy legitimate packet with valid payload_mac
if scen == "A1_false_brake": f["a"] = -6.0  # Modify acceleration
elif scen == "A2_false_accel": f["a"] = 3.0
elif scen == "A3_stealth_ramp": f["a"] = -min(3.0, 1.5*tt)
# BUG: payload_mac still contains HMAC(ts|v|a_legitimate|seq)
# But packet now has a_forged, so MAC verification will FAIL!
```

### Impact
**CRITICAL**: Stage 4 payload integrity check REJECTS all insider attack packets because:
1. Original packet has `payload_mac` = HMAC("ts|v|a_legit|seq")
2. Attack modifies `f["a"]` to forged value
3. Crypto gate recomputes MAC = HMAC("ts|v|a_forged|seq")
4. MACs don't match → `payload_valid = False` → packet rejected
5. Attack packets NEVER reach trust supervisor, defeating trust testing!

### Expected Behavior
Insider attacks should simulate **COMPROMISED INSIDERS** who:
- Have access to crypto keys (_SHARED_SECRET)
- Can forge packets with VALID crypto credentials
- Bypass crypto layer but trigger TRUST anomaly detection
- Test whether trust system can detect behavioral anomalies despite valid crypto

### Required Fix
Recompute payload_mac after modifying acceleration:

```python
f = dict(pk)
if scen == "A1_false_brake": f["a"] = -6.0
elif scen == "A2_false_accel": f["a"] = 3.0
elif scen == "A3_stealth_ramp": f["a"] = -min(3.0, 1.5*tt)

# Insider attack: Recompute payload MAC with forged acceleration
# This simulates compromised insider with crypto key access
if scen in ("A1_false_brake", "A2_false_accel", "A3_stealth_ramp"):
    payload_str = f"{f['ts']}|{f['v']}|{f['a']}|{f['seq']}"
    payload_bytes = payload_str.encode('utf-8')
    f["payload_mac"] = hmac.new(_SHARED_SECRET, payload_bytes, hashlib.sha256).hexdigest()
```

---

## Bug 9: Live Inject Attack Has Mismatched Payload MAC

### Affected Feature
Live dashboard "Inject Attack" button

### Location
**run_live() function - Lines 583-587**

### Current Buggy Code
```python
if i == 2 and attack_active:
    f = dict(pk); f["a"] = -6.0  # Modify acceleration
    # BUG: payload_mac not recomputed, packet will be rejected!
    link[3] = [p for p in link[3] if not (p["ts"] == pk["ts"])] + (
        [dict(f, arr=t + rnd.uniform(0.010, 0.030))] if rnd.random() > 0.02 else []
    )
```

### Impact
**CRITICAL**: Dashboard "Inject Attack" button does NOTHING because all injected packets are rejected by Stage 4. Users see no attack response, defeating live demo purpose.

### Required Fix
```python
if i == 2 and attack_active:
    f = dict(pk); f["a"] = -6.0
    # Live inject: Recompute payload MAC with forged acceleration
    payload_str = f"{f['ts']}|{f['v']}|{f['a']}|{f['seq']}"
    payload_bytes = payload_str.encode('utf-8')
    f["payload_mac"] = hmac.new(_SHARED_SECRET, payload_bytes, hashlib.sha256).hexdigest()
    link[3] = [p for p in link[3] if not (p["ts"] == pk["ts"])] + (
        [dict(f, arr=t + rnd.uniform(0.010, 0.030))] if rnd.random() > 0.02 else []
    )
```

---

## Bug 10: Legitimate Insider vs Outsider Attack Semantics

### Design Issue
The current implementation conflates TWO DIFFERENT attack models:
1. **Insider attacks** (A1, A2, A3, live inject) - Compromised platoon member with valid credentials
2. **Outsider attacks** (A5_forged) - External attacker with NO credentials

### Current Broken Semantics
- Insider attacks have INVALID crypto (mismatched MAC) → Rejected at crypto layer
- Outsider attacks also have INVALID crypto (no credentials) → Also rejected at crypto layer
- **BOTH attack types fail crypto, so trust system is NEVER TESTED!**

### Correct Semantics
**Insider Attacks (Compromised Member):**
- Assumption: Attacker is platoon member F3 (vehicle i=2)
- Attacker has FULL ACCESS to crypto keys (_SHARED_SECRET)
- Attacker can forge packets with VALID crypto (token, hpo_tag, payload_mac all correct)
- Crypto layer ACCEPTS packets (zktat_pass=True, hpo_pass=True, payload_valid=True)
- Trust layer DETECTS anomalies (high jerk, velocity mismatch, coherence violations)
- Result: Trust weight w[3] drops, triggers adaptive gap, isolation, potential revocation

**Outsider Attacks (External Attacker):**
- Assumption: Attacker is NOT a platoon member, has NO crypto keys
- Attacker cannot generate valid crypto credentials
- Crypto layer REJECTS packets immediately (no token, no hpo_tag, no payload_mac)
- Trust layer NEVER REACHED because crypto rejection happens first
- Result: Packets dropped silently at crypto gate Stage 1-4

### Testing Strategy
The two attack models test DIFFERENT security layers:
- **Insider attacks test TRUST SYSTEM** - Can trust anomaly detection catch compromised insiders?
- **Outsider attacks test CRYPTO SYSTEM** - Can crypto validation block external attackers?

---

## Summary of Required Fixes

### Fix Locations

**1. run() function - Lines 276-292**
```python
if i == 2 and t >= T_ATK and scen in ("A1_false_brake", "A2_false_accel",
                                        "A3_stealth_ramp", "A5_forged"):
    f = dict(pk)
    tt = t - T_ATK
    if scen == "A1_false_brake": f["a"] = -6.0
    elif scen == "A2_false_accel": f["a"] = 3.0
    elif scen == "A3_stealth_ramp": f["a"] = -min(3.0, 1.5*tt)
    elif scen == "A5_forged":
        f["a"] = -6.0; f["cred"] = False
        f.pop("token", None); f.pop("hpo_tag", None); f.pop("cred_id", None)
        f.pop("payload_mac", None)
    
    # Insider attacks: Recompute payload MAC (compromised insider with key access)
    if scen in ("A1_false_brake", "A2_false_accel", "A3_stealth_ramp"):
        payload_str = f"{f['ts']}|{f['v']}|{f['a']}|{f['seq']}"
        payload_bytes = payload_str.encode('utf-8')
        f["payload_mac"] = hmac.new(_SHARED_SECRET, payload_bytes, hashlib.sha256).hexdigest()
    
    if scen == "A5_forged":
        link[3].append(dict(f, arr=t + 0.035))
    else:
        link[3] = [p for p in link[3] if not (p["ts"] == pk["ts"])] + (
            [dict(f, arr=t + rnd.uniform(0.010, 0.030))] if rnd.random() > 0.02 else []
        )
```

**2. run_live() function - Lines 565-580 (same fix)**

**3. run_live() function - Lines 583-587 (live inject)**
```python
if i == 2 and attack_active:
    f = dict(pk); f["a"] = -6.0
    # Live inject: Recompute payload MAC
    payload_str = f"{f['ts']}|{f['v']}|{f['a']}|{f['seq']}"
    payload_bytes = payload_str.encode('utf-8')
    f["payload_mac"] = hmac.new(_SHARED_SECRET, payload_bytes, hashlib.sha256).hexdigest()
    link[3] = [p for p in link[3] if not (p["ts"] == pk["ts"])] + (
        [dict(f, arr=t + rnd.uniform(0.010, 0.030))] if rnd.random() > 0.02 else []
    )
```

---

## Testing After Fix

### Validation Steps
```bash
# 1. Test A1_false_brake - Should trigger trust degradation, NOT crypto rejection
python -c "from sim.sim_integrated import run; res = run('CA_full', 'A1_false_brake', 1); print('Min trust:', res['minw'])"
# Expected: minw < 0.5 (trust detected attack)

# 2. Test A5_forged - Should trigger crypto rejection
python -c "from sim.sim_integrated import run; res = run('CA_full', 'A5_forged', 1); print('Collision:', res['collision'])"
# Expected: collision=False (crypto blocked outsider)

# 3. Test live dashboard inject
START_DASHBOARD.bat
# Click "Inject Attack", verify F3 goes red, gap F3→F4 expands, crypto log shows "Accepted=true"
```

### Expected Crypto Log Behavior
**A1_false_brake (insider):**
- ZK-TAT: ✓ (green)
- H-PO: ✓ (green)
- Bloom hit: false
- Payload valid: ✓ (green, because MAC was recomputed)
- **Accepted: true** (crypto passes, trust detects anomaly later)

**A5_forged (outsider):**
- ZK-TAT: ✗ (red, no token)
- H-PO: ✗ (red, no hpo_tag)
- Bloom hit: false
- Payload valid: ✗ (red, no payload_mac)
- **Accepted: false** (crypto blocks immediately)

---

## Priority
**BLOCKING** - These bugs make the entire system untestable. All insider attack scenarios are broken. Must fix before ANY validation or demo.

---

## Root Cause Analysis
The Bug 2 payload integrity fix was designed to detect tampering by outsiders, but it didn't account for the **insider threat model** where attackers have crypto key access. The attack injection code needs to distinguish:
- Insider attacks → Recompute crypto credentials with forged data
- Outsider attacks → Remove all crypto credentials

This is the CORRECT security model: crypto blocks outsiders, trust detects compromised insiders.
