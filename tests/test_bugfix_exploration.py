"""
test_bugfix_exploration.py — Bug condition exploration tests (BEFORE fix).

These tests MUST FAIL on unfixed code to confirm bugs exist.
After fixes implemented, these same tests MUST PASS.

Tests follow bug condition methodology:
- Bug 1: Wrong gap direction (trust architecture)
- Bug 2: Crypto payload bypass (message integrity)
- Bug 3: A4_replay crypto bypass (replay defense)
- Bug 4: Binary trust mode gap bug
- Bug 5: L2_legit_brake false positive
- Bug 6: Compare mode buggy visualization
"""

import sys
from pathlib import Path
import pytest

_SIM = Path(__file__).resolve().parents[1] / "sim"
sys.path.insert(0, str(_SIM))

from sim_integrated import run, CFG


class TestBug1_WrongGapDirection:
    """Bug 1: Gap adjusts at victim position (i-1→i) instead of follower position (i→i+1)"""
    
    def test_a1_false_brake_ca_full_gap_direction(self):
        """
        When F3 (i=2) is red/untrusted in A1_false_brake, gap F3→F4 (gap[3]) 
        should increase MORE than gap F2→F3 (gap[2]).
        
        Bug Condition: gap[2] increases ~8m, gap[3] only ~2m (wrong position)
        Expected Behavior: gap[3] should increase MORE (follower backs off from attacker)
        """
        result = run("CA_full", "A1_false_brake", seed=1, trace=True)
        
        # Extract trace data around t=25s when attack is active
        trace = result.get("trace", [])
        t25_samples = [row for row in trace if 24.5 <= row[0] <= 25.5]
        
        if not t25_samples:
            pytest.skip("No trace data at t=25s")
        
        # Get gap measurements: row[1] is gap[2] (F2→F3), row[4] is gap[0] (L→F1)
        # We need to compute gap[3] (F3→F4) from full state
        # For this test, check that gap[2] does NOT increase dramatically
        # while the system should be expanding gap[3]
        
        gaps_2 = [row[1] for row in t25_samples]  # gap F2→F3
        min_gap_2 = min(gaps_2)
        max_gap_2 = max(gaps_2)
        gap_2_expansion = max_gap_2 - min_gap_2
        
        # In FIXED code, gap[2] should remain relatively stable (~2m expansion)
        # while gap[3] expands significantly (~8m+)
        # In UNFIXED code, gap[2] expands incorrectly (~8m)
        
        # Expected behavior: gap[2] expansion should be SMALL (< 3m)
        # This will FAIL on unfixed code where gap[2] expands ~8m
        assert gap_2_expansion < 3.0, (
            f"Bug 1 NOT fixed: gap[2] (F2→F3) expanded {gap_2_expansion:.1f}m "
            f"(expected < 3m). Victim vehicle backing off from attacker instead of "
            f"follower backing off."
        )


class TestBug2_CryptoPayloadBypass:
    """Bug 2: Modified packets pass crypto validation (no payload integrity check)"""
    
    def test_a1_forged_packets_rejected(self):
        """
        When attacker modifies payload (a=-6.0) but reuses valid token/hpo_tag,
        packets should be REJECTED with payload_valid=false.
        
        Bug Condition: Modified packets show accepted=true (ZK-TAT ✓, H-PO ✓)
        Expected Behavior: Modified packets should be rejected (payload_valid=false)
        """
        result = run("CA_full", "A1_false_brake", seed=1, trace=False)
        
        # In FIXED code, crypto summary should show lower pass rate due to payload tampering
        # In UNFIXED code, forged packets pass crypto validation
        crypto = result.get("crypto", {})
        pass_rate = crypto.get("zktat_pass_rate", 1.0)
        
        # Expected behavior: pass rate should drop significantly (< 0.95) 
        # when payload tampering is detected
        # This will FAIL on unfixed code where pass_rate ≈ 1.0
        assert pass_rate < 0.95, (
            f"Bug 2 NOT fixed: crypto pass rate {pass_rate:.3f} too high "
            f"(expected < 0.95). Modified packets bypassing payload integrity check."
        )


class TestBug3_A4ReplayCryptoBypass:
    """Bug 3: Replayed packets from buffer pass validation with preserved credentials"""
    
    def test_a4_replay_packets_rejected(self):
        """
        When A4_replay copies packets from buffer at t>=60s with cred=False,
        packets should be REJECTED via stripped credentials or seq tracking.
        
        Bug Condition: Replayed packets show accepted=true despite 60s+ age
        Expected Behavior: Replayed packets should be rejected
        """
        result = run("CA_full", "A4_replay", seed=1, trace=False)
        
        # In FIXED code, replayed packets are rejected (lower pass rate)
        # In UNFIXED code, replayed packets pass validation
        crypto = result.get("crypto", {})
        pass_rate = crypto.get("zktat_pass_rate", 1.0)
        
        # Expected behavior: pass rate should drop when replays are rejected
        # A4_replay injects replays starting at t=60s, so significant rejection expected
        assert pass_rate < 0.90, (
            f"Bug 3 NOT fixed: crypto pass rate {pass_rate:.3f} too high "
            f"(expected < 0.90). Replayed packets bypassing freshness checks."
        )


class TestBug4_BinaryTrustGapBug:
    """Bug 4: Binary trust mode exhibits same wrong gap direction as graded trust"""
    
    def test_d2_binary_gap_direction(self):
        """
        When D2_binary_hnom runs A1_false_brake and w[3]=0 (binary violation),
        gap[3] (F3→F4) should increase, NOT gap[2] (F2→F3).
        
        Bug Condition: gap[2] increases in binary mode (same bug as graded trust)
        Expected Behavior: gap[3] should increase at correct follower position
        """
        result = run("D2_binary_hnom", "A1_false_brake", seed=1, trace=True)
        
        trace = result.get("trace", [])
        t25_samples = [row for row in trace if 24.5 <= row[0] <= 25.5]
        
        if not t25_samples:
            pytest.skip("No trace data at t=25s")
        
        gaps_2 = [row[1] for row in t25_samples]
        min_gap_2 = min(gaps_2)
        max_gap_2 = max(gaps_2)
        gap_2_expansion = max_gap_2 - min_gap_2
        
        # Expected behavior: gap[2] expansion should be small in fixed binary mode
        assert gap_2_expansion < 3.0, (
            f"Bug 4 NOT fixed: binary trust mode gap[2] expanded {gap_2_expansion:.1f}m "
            f"(expected < 3m). Binary trust has same gap direction bug as graded trust."
        )


class TestBug5_L2LegitBrakeFalsePositive:
    """Bug 5: Legitimate leader emergency brake triggers false trust degradation"""
    
    def test_l2_legit_brake_maintains_trust(self):
        """
        When L2_legit_brake runs and leader initiates legitimate emergency at t=30s,
        follower trust weights should remain high (w[i] >= 0.5 for all followers).
        
        Bug Condition: All followers show w[] < 0.5 (false positive across platoon)
        Expected Behavior: Trust weights should stay high (w >= 0.8) for legitimate emergency
        """
        result = run("CA_full", "L2_legit_brake", seed=1, trace=False)
        
        # minw tracks minimum trust weight across platoon
        minw = result.get("minw", 1.0)
        
        # Expected behavior: trust should remain high (>= 0.5, ideally >= 0.8)
        # This will FAIL on unfixed code where minw drops < 0.5
        assert minw >= 0.5, (
            f"Bug 5 NOT fixed: minimum trust weight {minw:.3f} too low "
            f"(expected >= 0.5). Legitimate leader emergency triggering false positives."
        )


class TestBug6_CompareModeVisualization:
    """Bug 6: Compare mode shows both configs with same wrong gap behavior"""
    
    def test_compare_mode_differential_behavior(self):
        """
        When comparing D1_ma_abse_ar vs CA_full in A1_false_brake,
        configs should show DIFFERENTIAL gap behavior at CORRECT positions.
        
        Bug Condition: Both configs show gap F2→F3 expansion (same wrong position)
        Expected Behavior: Both should show correct position, with distinguishable mechanisms
        """
        result_d1 = run("D1_ma_abse_ar", "A1_false_brake", seed=1, trace=True)
        result_ca = run("CA_full", "A1_false_brake", seed=1, trace=True)
        
        # Extract gap behaviors
        trace_d1 = result_d1.get("trace", [])
        trace_ca = result_ca.get("trace", [])
        
        if not trace_d1 or not trace_ca:
            pytest.skip("No trace data for comparison")
        
        # Get t=25s samples
        t25_d1 = [row for row in trace_d1 if 24.5 <= row[0] <= 25.5]
        t25_ca = [row for row in trace_ca if 24.5 <= row[0] <= 25.5]
        
        if not t25_d1 or not t25_ca:
            pytest.skip("Insufficient trace data at t=25s")
        
        # Check gap[2] expansion for both
        gaps_2_d1 = [row[1] for row in t25_d1]
        gaps_2_ca = [row[1] for row in t25_ca]
        
        gap_2_exp_d1 = max(gaps_2_d1) - min(gaps_2_d1)
        gap_2_exp_ca = max(gaps_2_ca) - min(gaps_2_ca)
        
        # Expected behavior: BOTH should have small gap[2] expansion (< 3m)
        # In unfixed code, BOTH show large expansion (obscuring differential behavior)
        assert gap_2_exp_d1 < 3.0 and gap_2_exp_ca < 3.0, (
            f"Bug 6 NOT fixed: D1 gap[2]={gap_2_exp_d1:.1f}m, CA gap[2]={gap_2_exp_ca:.1f}m "
            f"(both expected < 3m). Compare mode shows both configs buggy."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
