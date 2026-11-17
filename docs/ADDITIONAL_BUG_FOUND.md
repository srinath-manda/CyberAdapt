# Additional Bug Found During Final Audit

## Bug 7: A5_forged Missing payload_mac Removal

### Description
The A5_forged outsider attack scenario removes `token`, `hpo_tag`, and `cred_id` from forged packets, but does NOT remove `payload_mac`. Since the Bug 2/3 fix added payload_mac to all legitimate packets, the A5_forged attack packet copied from the legitimate packet dict(pk) STILL CONTAINS the valid payload_mac from the original legitimate packet.

### Impact
**HIGH SEVERITY**: This allows A5_forged outsider attack packets to bypass Stage 4 payload integrity check in the crypto gate, defeating the purpose of the Bug 2 fix.

### Affected Code Locations

#### run() function - Line ~283
```python
elif scen == "A5_forged":
    f["a"] = -6.0; f["cred"] = False
    # Outsider forged packet: no token, cred=False
    f.pop("token", None); f.pop("hpo_tag", None); f.pop("cred_id", None)
    # BUG: Missing f.pop("payload_mac", None)
```

#### run_live() function - Line ~569
```python
elif scen == "A5_forged":
    f["a"] = -6.0; f["cred"] = False
    f.pop("token", None); f.pop("hpo_tag", None); f.pop("cred_id", None)
    # BUG: Missing f.pop("payload_mac", None)
```

### Root Cause
When the crypto payload MAC fix was added (Bug 2/3), the A5_forged attack injection code was not updated to also remove the new `payload_mac` field. The attack creates f = dict(pk), copying ALL fields from the legitimate packet including the valid payload_mac. Then it only removes token/hpo_tag/cred_id, leaving payload_mac intact.

### Expected Behavior
A5_forged outsider packets should have NO valid crypto credentials including payload_mac. The crypto gate should reject them due to missing or invalid payload_mac.

### Current Buggy Behavior
1. Legitimate packet created with valid payload_mac
2. A5_forged copies packet: f = dict(pk) (includes valid payload_mac)
3. Attack removes token, hpo_tag, cred_id but NOT payload_mac
4. Forged packet sent to vehicle F4 (i=3)
5. Crypto gate Stage 4 verifies payload_mac - it MATCHES because it's the legitimate MAC!
6. Packet accepted despite being an outsider attack with modified acceleration

### Fix Required

Add `f.pop("payload_mac", None)` to both locations:

**Location 1: run() function ~line 283**
```python
elif scen == "A5_forged":
    f["a"] = -6.0; f["cred"] = False
    # Outsider forged packet: no token, cred=False
    f.pop("token", None); f.pop("hpo_tag", None); f.pop("cred_id", None)
    f.pop("payload_mac", None)  # FIX: Remove payload MAC as well
```

**Location 2: run_live() function ~line 569**
```python
elif scen == "A5_forged":
    f["a"] = -6.0; f["cred"] = False
    f.pop("token", None); f.pop("hpo_tag", None); f.pop("cred_id", None)
    f.pop("payload_mac", None)  # FIX: Remove payload MAC as well
```

### Testing
After fix, run:
```bash
python -c "from sim.sim_integrated import run; res = run('CA_full', 'A5_forged', 1); print('Collision:', res['collision'])"
```

Expected: A5_forged packets should be rejected, platoon should avoid collision.

### Priority
**CRITICAL** - This undermines the entire payload integrity fix (Bug 2). Must be fixed before considering the bugfix complete.

---

## Summary of All 7 Bugs

1. ✅ **Bug 1**: Wrong Gap Direction - FIXED (dashboard visualization)
2. ✅ **Bug 2**: Crypto Payload Bypass - FIXED (payload MAC added)
3. ✅ **Bug 3**: A4_replay Crypto Bypass - FIXED (credentials stripped, seq tracking)
4. ✅ **Bug 4**: Binary Trust Gap Bug - FIXED (same as Bug 1)
5. ✅ **Bug 5**: L2_legit_brake False Positive - FIXED (leader exemption 2.5x threshold)
6. ✅ **Bug 6**: Compare Mode Bug - FIXED (dashboard visualization)
7. ❌ **Bug 7**: A5_forged Missing payload_mac Removal - **NOT FIXED YET**

## Action Required
Apply the 2-line fix to remove payload_mac from A5_forged injection in both run() and run_live().
