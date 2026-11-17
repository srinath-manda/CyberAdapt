"""Quick test to validate bug fixes are working"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "sim"))

from sim_integrated import run

print("Testing Bug Fixes...")
print("=" * 60)

# Test Bug 2 & 3: Crypto fixes
print("\n1. Testing Bug 2 (Crypto Payload Bypass) with A1_false_brake...")
result = run("CA_full", "A1_false_brake", seed=1, trace=False)
crypto = result.get("crypto", {})
pass_rate = crypto.get("zktat_pass_rate", 1.0)
print(f"   Crypto pass rate: {pass_rate:.3f}")
if pass_rate < 0.95:
    print("   ✓ Bug 2 FIXED: Modified packets being rejected (pass rate < 0.95)")
else:
    print("   ✗ Bug 2 NOT fixed: Pass rate still too high")

# Test Bug 3: Replay defense
print("\n2. Testing Bug 3 (A4_replay Crypto Bypass)...")
result = run("CA_full", "A4_replay", seed=1, trace=False)
crypto = result.get("crypto", {})
pass_rate = crypto.get("zktat_pass_rate", 1.0)
print(f"   Crypto pass rate: {pass_rate:.3f}")
if pass_rate < 0.90:
    print("   ✓ Bug 3 FIXED: Replayed packets being rejected (pass rate < 0.90)")
else:
    print("   ✗ Bug 3 NOT fixed: Replays passing validation")

# Test Bug 5: Legitimate emergency
print("\n3. Testing Bug 5 (L2_legit_brake False Positive)...")
result = run("CA_full", "L2_legit_brake", seed=1, trace=False)
minw = result.get("minw", 1.0)
print(f"   Minimum trust weight: {minw:.3f}")
if minw >= 0.5:
    print("   ✓ Bug 5 FIXED: Trust maintained during legitimate emergency")
else:
    print("   ✗ Bug 5 NOT fixed: False positive trust degradation")

# Test Bug 1: Gap direction (requires trace analysis)
print("\n4. Testing Bug 1 (Wrong Gap Direction) with A1_false_brake...")
result = run("CA_full", "A1_false_brake", seed=1, trace=True)
trace = result.get("trace", [])
t25_samples = [row for row in trace if 24.5 <= row[0] <= 25.5]
if t25_samples:
    gaps_2 = [row[1] for row in t25_samples]  # gap F2→F3
    gap_2_expansion = max(gaps_2) - min(gaps_2)
    print(f"   Gap F2→F3 expansion: {gap_2_expansion:.1f}m")
    if gap_2_expansion < 3.0:
        print("   ✓ Bug 1 FIXED: Gap adjustment at correct follower position")
    else:
        print("   ✗ Bug 1 NOT fixed: Wrong gap position")
else:
    print("   ⚠ No trace data available for Bug 1 test")

# Test Bug 4: Binary trust mode
print("\n5. Testing Bug 4 (Binary Trust Mode Gap) with D2_binary_hnom...")
result = run("D2_binary_hnom", "A1_false_brake", seed=1, trace=True)
trace = result.get("trace", [])
t25_samples = [row for row in trace if 24.5 <= row[0] <= 25.5]
if t25_samples:
    gaps_2 = [row[1] for row in t25_samples]
    gap_2_expansion = max(gaps_2) - min(gaps_2)
    print(f"   Gap F2→F3 expansion: {gap_2_expansion:.1f}m")
    if gap_2_expansion < 3.0:
        print("   ✓ Bug 4 FIXED: Binary trust uses correct gap position")
    else:
        print("   ✗ Bug 4 NOT fixed: Binary mode has same bug")
else:
    print("   ⚠ No trace data available for Bug 4 test")

print("\n" + "=" * 60)
print("Fix validation complete!")
print("\nNote: Bug 6 (Compare Mode Visualization) requires dashboard testing")
print("Dashboard fix applied in app.js - vehicle coloring based on w[i+1]")
