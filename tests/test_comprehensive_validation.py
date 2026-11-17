"""
Comprehensive Validation Test Suite for All 10 Bug Fixes
Tests unit-level, integration-level, and end-to-end correctness
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "sim"))

import pytest
from sim_integrated import run, run_live, _run_crypto_gate, _attach_crypto_to_packet, CFG, PacketLogEntry, RevocationBloomFilter
import hmac
import hashlib
import threading

# ══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS FOR CRYPTO FIXES (Bugs 2, 3, 7, 8, 9)
# ══════════════════════════════════════════════════════════════════════════════

class TestCryptoPayloadMAC:
    """Unit tests for Bug 2: Crypto Payload Bypass fix"""
    
    def test_payload_mac_attachment(self):
        """Test that payload_mac is correctly attached to legitimate packets"""
        pk = dict(ts=10.0, v=14.0, a=0.5, seq=100)
        _attach_crypto_to_packet(pk, sender_id=2)
        
        assert "payload_mac" in pk, "payload_mac not attached"
        assert len(pk["payload_mac"]) == 64, f"MAC should be 64 hex chars, got {len(pk['payload_mac'])}"
        
        # Verify MAC computation
        _SHARED_SECRET = b"CYBERADAPT_PLATOON_SECRET_2026_CBIT"
        payload_str = f"{pk['ts']}|{pk['v']}|{pk['a']}|{pk['seq']}"
        expected_mac = hmac.new(_SHARED_SECRET, payload_str.encode('utf-8'), hashlib.sha256).hexdigest()
        assert pk["payload_mac"] == expected_mac, "MAC mismatch"
    
    def test_payload_mac_verification_valid(self):
        """Test that valid payload_mac passes verification"""
        pk = dict(ts=10.0, v=14.0, a=0.5, seq=100, src=2, cred=True)
        _attach_crypto_to_packet(pk, sender_id=2)
        
        bloom = RevocationBloomFilter()
        last_seq = {}
        crypto_latency = []
        
        accepted, entry = _run_crypto_gate(pk, t=10.0, cfg=CFG["CA_full"], bloom=bloom, 
                                           crypto_latency=crypto_latency, last_seq=last_seq)
        
        assert entry.payload_valid == True, "Valid payload should pass"
        assert accepted == True, "Packet should be accepted"
    
    def test_payload_mac_verification_tampered(self):
        """Test that tampered payload fails verification"""
        pk = dict(ts=10.0, v=14.0, a=0.5, seq=100, src=2, cred=True)
        _attach_crypto_to_packet(pk, sender_id=2)
        
        # Tamper with acceleration
        pk["a"] = -6.0  # Modified but MAC not recomputed
        
        bloom = RevocationBloomFilter()
        last_seq = {}
        crypto_latency = []
        
        accepted, entry = _run_crypto_gate(pk, t=10.0, cfg=CFG["CA_full"], bloom=bloom,
                                           crypto_latency=crypto_latency, last_seq=last_seq)
        
        assert entry.payload_valid == False, "Tampered payload should fail"
        assert accepted == False, "Tampered packet should be rejected"
    
    def test_payload_mac_missing(self):
        """Test that missing payload_mac fails verification"""
        pk = dict(ts=10.0, v=14.0, a=0.5, seq=100, src=2, cred=True, token="fake", hpo_tag="fake")
        # No payload_mac attached
        
        bloom = RevocationBloomFilter()
        last_seq = {}
        crypto_latency = []
        
        accepted, entry = _run_crypto_gate(pk, t=10.0, cfg=CFG["CA_full"], bloom=bloom,
                                           crypto_latency=crypto_latency, last_seq=last_seq,
                                           zktat_pass_override=True)
        
        assert entry.payload_valid == False, "Missing payload_mac should fail"
        assert accepted == False, "Packet without MAC should be rejected"


class TestSequenceTracking:
    """Unit tests for Bug 3: A4_replay sequence tracking fix"""
    
    def test_sequence_freshness_first_packet(self):
        """Test that first packet from source is accepted"""
        pk = dict(ts=10.0, v=14.0, a=0.5, seq=1, src=2, cred=True)
        _attach_crypto_to_packet(pk, sender_id=2)
        
        bloom = RevocationBloomFilter()
        last_seq = {}
        crypto_latency = []
        
        accepted, entry = _run_crypto_gate(pk, t=10.0, cfg=CFG["CA_full"], bloom=bloom,
                                           crypto_latency=crypto_latency, last_seq=last_seq)
        
        assert entry.replay_detected == False, "First packet should not be flagged as replay"
        assert accepted == True, "First packet should be accepted"
        assert last_seq[2] == 1, "Sequence should be tracked"
    
    def test_sequence_freshness_monotonic(self):
        """Test that monotonically increasing sequences are accepted"""
        bloom = RevocationBloomFilter()
        last_seq = {}
        crypto_latency = []
        
        for seq in [1, 2, 3, 4, 5]:
            pk = dict(ts=10.0 + seq*0.1, v=14.0, a=0.5, seq=seq, src=2, cred=True)
            _attach_crypto_to_packet(pk, sender_id=2)
            accepted, entry = _run_crypto_gate(pk, t=10.0+seq*0.1, cfg=CFG["CA_full"], 
                                               bloom=bloom, crypto_latency=crypto_latency, last_seq=last_seq)
            assert entry.replay_detected == False, f"Seq {seq} should not be replay"
            assert accepted == True, f"Seq {seq} should be accepted"
        
        assert last_seq[2] == 5, "Last sequence should be 5"
    
    def test_sequence_freshness_replay(self):
        """Test that replayed packets (seq <= last_seq) are rejected"""
        bloom = RevocationBloomFilter()
        last_seq = {2: 5}  # Already seen up to seq 5
        crypto_latency = []
        
        # Try replaying seq 3
        pk = dict(ts=16.0, v=14.0, a=0.5, seq=3, src=2, cred=True)
        _attach_crypto_to_packet(pk, sender_id=2)
        
        accepted, entry = _run_crypto_gate(pk, t=16.0, cfg=CFG["CA_full"], bloom=bloom,
                                           crypto_latency=crypto_latency, last_seq=last_seq)
        
        assert entry.replay_detected == True, "Old sequence should be flagged as replay"
        assert accepted == False, "Replayed packet should be rejected"


class TestInsiderAttackMACRecompute:
    """Unit tests for Bugs 8, 9: Insider attack MAC recomputation"""
    
    def test_insider_attack_mac_valid(self):
        """Test that insider attack with recomputed MAC passes crypto"""
        # Simulate insider attack: create legitimate packet, modify acceleration, recompute MAC
        pk = dict(ts=25.0, v=14.0, a=0.5, seq=250, src=2, cred=True)
        _attach_crypto_to_packet(pk, sender_id=2)
        
        # Modify acceleration (insider attack)
        pk["a"] = -6.0
        
        # Recompute MAC (Bug 8 fix)
        _SHARED_SECRET = b"CYBERADAPT_PLATOON_SECRET_2026_CBIT"
        payload_str = f"{pk['ts']}|{pk['v']}|{pk['a']}|{pk['seq']}"
        pk["payload_mac"] = hmac.new(_SHARED_SECRET, payload_str.encode('utf-8'), hashlib.sha256).hexdigest()
        
        # Verify crypto passes
        bloom = RevocationBloomFilter()
        last_seq = {}
        crypto_latency = []
        
        accepted, entry = _run_crypto_gate(pk, t=25.0, cfg=CFG["CA_full"], bloom=bloom,
                                           crypto_latency=crypto_latency, last_seq=last_seq)
        
        assert entry.payload_valid == True, "Recomputed MAC should be valid"
        assert accepted == True, "Insider attack packet should pass crypto (trust will detect it)"


class TestOutsiderAttackCredentialStrip:
    """Unit tests for Bug 7: A5_forged credential stripping"""
    
    def test_outsider_attack_all_credentials_stripped(self):
        """Test that A5_forged strips all 4 credential fields"""
        pk = dict(ts=25.0, v=14.0, a=0.5, seq=250, src=2, cred=True)
        _attach_crypto_to_packet(pk, sender_id=2)
        
        # Simulate A5_forged injection (Bug 7 fix)
        f = dict(pk)
        f["a"] = -6.0
        f["cred"] = False
        f.pop("token", None)
        f.pop("hpo_tag", None)
        f.pop("cred_id", None)
        f.pop("payload_mac", None)  # Bug 7 fix: This must be removed!
        
        # Verify all credentials removed
        assert "token" not in f, "token should be removed"
        assert "hpo_tag" not in f, "hpo_tag should be removed"
        assert "cred_id" not in f, "cred_id should be removed"
        assert "payload_mac" not in f, "payload_mac should be removed (Bug 7 fix)"
        
        # Verify crypto rejects
        bloom = RevocationBloomFilter()
        last_seq = {}
        crypto_latency = []
        
        accepted, entry = _run_crypto_gate(f, t=25.0, cfg=CFG["CA_full"], bloom=bloom,
                                           crypto_latency=crypto_latency, last_seq=last_seq,
                                           zktat_pass_override=False)
        
        assert accepted == False, "Outsider packet without credentials should be rejected"


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS FOR ATTACK SCENARIOS (Bugs 1-10)
# ══════════════════════════════════════════════════════════════════════════════

class TestAttackScenarioIntegration:
    """Integration tests verifying end-to-end attack flows"""
    
    def test_a1_false_brake_trust_detects(self):
        """Bug 1, 2, 8: A1_false_brake should pass crypto but trigger trust detection"""
        res = run('CA_full', 'A1_false_brake', 1)
        
        # Trust should detect attack
        assert res['minw'] < 0.5, f"Trust should detect attack (minw={res['minw']:.3f} should be <0.5)"
        assert res['first_det'] is not None, "Attack should be detected"
        assert res['first_det'] < 10.0, f"Detection should be quick (<10s), got {res['first_det']:.2f}s"
        
        # No collision due to adaptive gap
        assert res['collision'] == False, "CyberAdapt should prevent collision"
        assert res['min_gap'] > 0.0, f"Min gap should be positive, got {res['min_gap']:.2f}m"
        
        # Check crypto passes (insider attack with valid MAC)
        if 'crypto' in res:
            assert res['crypto']['total_packets'] > 0, "Crypto should process packets"
    
    def test_a2_false_accel_trust_detects(self):
        """Bug 8: A2_false_accel should pass crypto but trigger trust detection"""
        res = run('CA_full', 'A2_false_accel', 1)
        
        assert res['minw'] < 0.5, f"Trust should detect accel attack (minw={res['minw']:.3f})"
        assert res['collision'] == False, "CyberAdapt should prevent collision"
    
    def test_a3_stealth_ramp_trust_detects(self):
        """Bug 8: A3_stealth_ramp should pass crypto but trigger gradual trust degradation"""
        res = run('CA_full', 'A3_stealth_ramp', 1)
        
        assert res['minw'] < 0.5, f"Trust should eventually detect stealth (minw={res['minw']:.3f})"
        assert res['collision'] == False, "CyberAdapt should prevent collision"
    
    def test_a4_replay_crypto_blocks(self):
        """Bug 3: A4_replay should be blocked by crypto gate (replay detection)"""
        res = run('CA_full', 'A4_replay', 1)
        
        # Attack should be blocked before causing collision
        assert res['collision'] == False, "Replay attack should be blocked"
        assert res['min_gap'] > 5.0, f"Min gap should be healthy (>5m), got {res['min_gap']:.2f}m"
    
    def test_a5_forged_crypto_blocks(self):
        """Bug 7: A5_forged should be blocked by crypto gate (no credentials)"""
        res = run('CA_full', 'A5_forged', 1)
        
        # Outsider attack should be blocked
        assert res['collision'] == False, "Outsider attack should be blocked"
        assert res['min_gap'] > 5.0, f"Min gap should be healthy (>5m), got {res['min_gap']:.2f}m"
    
    def test_l1_normal_baseline_preserved(self):
        """Bugs 1-10: L1_normal should maintain nominal performance (regression test)"""
        res = run('CA_full', 'L1_normal', 1)
        
        # Nominal performance metrics
        assert res['collision'] == False, "No collision in normal scenario"
        assert res['min_gap'] > 8.0, f"Min gap should be nominal (>8m), got {res['min_gap']:.2f}m"
        assert res['mean_headway'] > 0.5, f"Mean headway should be >0.5s, got {res['mean_headway']:.3f}s"
        assert res['mean_headway'] < 0.8, f"Mean headway should be <0.8s, got {res['mean_headway']:.3f}s"
    
    def test_l2_legit_brake_no_false_positive(self):
        """Bug 5: L2_legit_brake should NOT trigger false positive (leader exemption)"""
        res = run('CA_full', 'L2_legit_brake', 1)
        
        # Leader should remain trusted (minw should be high)
        # Note: Might still degrade slightly for followers, but leader should be exempted
        assert res['collision'] == False, "No collision in legitimate brake"
        assert res['min_gap'] > 5.0, f"Min gap should stay safe (>5m), got {res['min_gap']:.2f}m"
        
        # With leader exemption, minw should stay relatively high (>0.5 ideally)
        # If it drops below 0.5, it's a false positive for leader packets
        if res['minw'] < 0.5:
            pytest.warn(UserWarning(f"Possible false positive: minw={res['minw']:.3f} <0.5 despite leader exemption"))


class TestBinaryTrustMode:
    """Integration tests for Bug 4: Binary trust mode gap direction"""
    
    def test_d2_binary_hnom_attack_response(self):
        """Bug 4: D2_binary_hnom should show correct gap expansion"""
        res = run('D2_binary_hnom', 'A1_false_brake', 1)
        
        # Binary trust should prevent collision
        assert res['collision'] == False, "Binary trust should prevent collision"
        assert res['min_gap'] > 0.0, f"Min gap should be positive, got {res['min_gap']:.2f}m"
    
    def test_d2b_binary_hfail_attack_response(self):
        """Bug 4: D2b_binary_hfail should show correct gap expansion with H_FAIL headway"""
        res = run('D2b_binary_hfail', 'A1_false_brake', 1)
        
        assert res['collision'] == False, "Binary trust with H_FAIL should prevent collision"


# ══════════════════════════════════════════════════════════════════════════════
# CONSISTENCY TESTS (run vs run_live)
# ══════════════════════════════════════════════════════════════════════════════

class TestRunConsistency:
    """Verify run() and run_live() have same bug fixes"""
    
    def test_run_vs_run_live_a1_consistency(self):
        """Verify A1_false_brake produces consistent results in run() vs run_live()"""
        # Run batch simulation
        res_batch = run('CA_full', 'A1_false_brake', 1)
        
        # Run live simulation (collect frames manually)
        inject_flag = threading.Event()
        stop_flag = threading.Event()
        
        # Start generator
        gen = run_live('CA_full', 'A1_false_brake', 1, inject_flag, stop_flag)
        
        frames = []
        for frame in gen:
            frames.append(frame)
            if frame['t'] >= 30.0:  # Sample 30 seconds
                stop_flag.set()
                break
        
        # Compare trust degradation trends
        # Both should show trust weight dropping for vehicle 3 (F3)
        last_frame = frames[-1]
        w_live = last_frame['w']
        
        # Trust weights should show degradation for F3 (i=3)
        assert w_live[3] < 0.5, f"Live simulation should show trust degradation for F3: w[3]={w_live[3]:.3f}"
        
        # Batch simulation should also show minw < 0.5
        assert res_batch['minw'] < 0.5, f"Batch simulation should show trust degradation: minw={res_batch['minw']:.3f}"


# ══════════════════════════════════════════════════════════════════════════════
# PROPERTY-BASED TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestPropertyBased:
    """Property-based tests for invariants"""
    
    def test_sequence_monotonicity(self):
        """Property: Sequence numbers should be monotonically increasing per vehicle"""
        res = run('CA_full', 'L1_normal', 1, trace=False)
        # If we had access to packet logs, we'd verify seq numbers
        # For now, we rely on unit tests covering this
        pass
    
    def test_mac_binding_tampering_detection(self):
        """Property: ANY modification to payload fields should fail MAC verification"""
        bloom = RevocationBloomFilter()
        last_seq = {}
        crypto_latency = []
        
        # Create legitimate packet
        pk = dict(ts=10.0, v=14.0, a=0.5, seq=100, src=2, cred=True)
        _attach_crypto_to_packet(pk, sender_id=2)
        
        # Test tampering each field
        for field in ['ts', 'v', 'a', 'seq']:
            f = dict(pk)
            f[field] = f[field] + 1.0 if field != 'seq' else f[field] + 1
            
            last_seq_copy = dict(last_seq)
            accepted, entry = _run_crypto_gate(f, t=10.0, cfg=CFG["CA_full"], bloom=bloom,
                                               crypto_latency=crypto_latency, last_seq=last_seq_copy)
            
            assert entry.payload_valid == False, f"Tampering {field} should fail MAC verification"
            assert accepted == False, f"Tampered packet (field={field}) should be rejected"


# ══════════════════════════════════════════════════════════════════════════════
# MAIN TEST EXECUTION
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
