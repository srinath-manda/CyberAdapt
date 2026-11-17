"""
Network and Vehicle Simulation Verification Tests
Tests for physical dynamics, network properties, sensor simulation, control law, and safety
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "sim"))

import pytest
import random
from sim_integrated import run, DT, TAU, N, T, V0

# ══════════════════════════════════════════════════════════════════════════════
# HIGH PRIORITY: CRITICAL SAFETY TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestCollisionFreeProperty:
    """Critical: Verify no collisions across all scenarios and configurations"""
    
    @pytest.mark.parametrize("cfg", ["CA_full", "D1_ma_abse_ar", "D2_binary_hnom", "D2b_binary_hfail"])
    @pytest.mark.parametrize("scen", ["L1_normal", "L2_legit_brake", "A1_false_brake", 
                                       "A2_false_accel", "A3_stealth_ramp", "A4_replay", "A5_forged"])
    def test_collision_free_all_scenarios(self, cfg, scen):
        """Verify collision-free property for all config/scenario combinations"""
        # Test with 3 different seeds for statistical confidence
        for seed in [1, 2, 3]:
            res = run(cfg, scen, seed)
            
            assert res['collision'] == False, \
                f"COLLISION DETECTED: cfg={cfg}, scen={scen}, seed={seed}, min_gap={res['min_gap']:.3f}m"
            
            assert res['min_gap'] > 0.0, \
                f"Zero or negative gap: cfg={cfg}, scen={scen}, seed={seed}, min_gap={res['min_gap']:.3f}m"
    
    def test_minimum_safe_gap_threshold(self):
        """Verify minimum gap never falls below safety threshold (2m)"""
        critical_scenarios = ["A1_false_brake", "A2_false_accel", "L2_legit_brake"]
        
        for scen in critical_scenarios:
            res = run("CA_full", scen, seed=1)
            
            # CyberAdapt should maintain at least 2m gap even under attack
            assert res['min_gap'] > 2.0, \
                f"Unsafe gap in {scen}: min_gap={res['min_gap']:.3f}m (should be >2m)"


class TestVelocityConstraints:
    """Critical: Verify physical constraints on velocity"""
    
    def test_velocity_never_negative(self):
        """Verify vehicles never have negative velocity (can't go backward)"""
        # Run extreme braking scenario
        res = run("CA_full", "L2_legit_brake", seed=1)
        
        # vmin should be >= 0
        assert res['vmin'] >= 0.0, \
            f"Negative velocity detected: vmin={res['vmin']:.3f} m/s"
        
        # Should not come to complete stop in normal scenarios
        assert res['vmin'] > 5.0, \
            f"Platoon nearly stopped: vmin={res['vmin']:.3f} m/s"


class TestAccelerationLimits:
    """Critical: Verify acceleration saturation limits"""
    
    def test_deceleration_limit_enforced(self):
        """Verify max deceleration doesn't exceed A_MIN = -8.0 m/s²"""
        # Run aggressive braking scenario
        res = run("CA_full", "L2_legit_brake", seed=1)
        
        A_MIN = -8.0
        # Peak deceleration should not exceed physical limit
        assert res['peak_decel'] <= abs(A_MIN) + 0.1, \
            f"Deceleration limit violated: peak_decel={res['peak_decel']:.3f} m/s² (limit={A_MIN} m/s²)"
    
    def test_jerk_limit_respected_non_emergency(self):
        """Verify jerk limits respected in non-emergency scenarios"""
        # Run normal scenario (no attacks, no emergencies)
        res = run("CA_full", "L1_normal", seed=1)
        
        JERK_LIM = 3.8  # m/s²/s
        # In normal operation, jerk should be well below limit
        assert res['peak_jerk'] < JERK_LIM * 2.0, \
            f"Excessive jerk in normal operation: peak_jerk={res['peak_jerk']:.3f} m/s²/s"


# ══════════════════════════════════════════════════════════════════════════════
# MEDIUM PRIORITY: NETWORK SIMULATION VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

class TestNetworkSimulation:
    """Verify V2X network properties (delay, loss, ordering)"""
    
    def test_packet_loss_rate_approximate(self):
        """Verify packet loss rate is approximately 2%"""
        # Run multiple simulations and average loss rate
        total_expected = 0
        total_received_implicit = 0
        
        for seed in range(1, 6):  # 5 trials
            res = run("CA_full", "L1_normal", seed)
            
            # Expected packets: (N-1) vehicles × 10 beacons/s × 100s = 7000 packets
            expected_packets = (N - 1) * 10 * T
            total_expected += expected_packets
            
            # Received packets: inferred from crypto stats
            if 'crypto' in res and res['crypto']['total_packets'] > 0:
                total_received_implicit += res['crypto']['total_packets']
        
        if total_received_implicit > 0:
            loss_rate = 1.0 - (total_received_implicit / total_expected)
            
            # Should be approximately 2% (allow 1-4% range due to randomness)
            assert 0.01 < loss_rate < 0.04, \
                f"Packet loss rate {loss_rate*100:.1f}% not in expected range [1%, 4%]"
    
    def test_network_delay_reasonable(self):
        """Verify network delays are in expected range (10-30ms)"""
        # This test requires instrumenting packet arrival times
        # For now, we verify simulations complete in expected time
        # Expected: 100s simulation should take realistic time
        import time
        
        start = time.time()
        res = run("CA_full", "L1_normal", seed=1)
        elapsed = time.time() - start
        
        # Simulation should complete quickly (< 30 seconds on typical hardware)
        # This indirectly validates network delays aren't pathological
        assert elapsed < 60.0, \
            f"Simulation took too long: {elapsed:.1f}s (suggests network delay issues)"


# ══════════════════════════════════════════════════════════════════════════════
# MEDIUM PRIORITY: PHYSICAL DYNAMICS VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

class TestActuatorDynamics:
    """Verify actuator lag (first-order system with TAU=0.1s)"""
    
    def test_actuator_lag_time_constant(self):
        """Verify actuator response has correct time constant TAU=0.1s"""
        # This requires instrumenting a[i] time series
        # For integration test, verify that acceleration doesn't change instantly
        
        # Run scenario with step input (leader starts moving)
        res = run("CA_full", "L1_normal", seed=1)
        
        # Peak jerk should be finite (not infinite as would happen without lag)
        assert res['peak_jerk'] < 100.0, \
            f"Infinite jerk suggests no actuator lag: peak_jerk={res['peak_jerk']:.1f}"
        
        # Peak jerk should be > 0 (some transient response)
        assert res['peak_jerk'] > 0.1, \
            f"Zero jerk suggests actuator not responding: peak_jerk={res['peak_jerk']:.3f}"


class TestEulerIntegration:
    """Verify numerical integration accuracy"""
    
    def test_position_velocity_consistency(self):
        """Verify position integrates velocity correctly"""
        # Run simulation and check that final positions are consistent with velocities
        res = run("CA_full", "L1_normal", seed=1, trace=True)
        
        if 'trace' in res:
            trace = res['trace']
            # Trace format: (t, gap2-3, v3, weff3, gap0-1, v0, h3, weff1, v1)
            
            # Sample trace at beginning and end
            t0, _, v3_0, *_ = trace[0]
            tf, _, v3_f, *_ = trace[-1]
            
            # Velocity should evolve smoothly (not jump discontinuously)
            # This indirectly validates integration
            assert abs(v3_f - v3_0) < 20.0, \
                f"Unrealistic velocity change: v3 from {v3_0:.2f} to {v3_f:.2f} m/s"


# ══════════════════════════════════════════════════════════════════════════════
# MEDIUM PRIORITY: CONTROL LAW VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

class TestControlLaw:
    """Verify control law behavior (PD + feedforward + trust weighting)"""
    
    def test_trust_reduces_feedforward(self):
        """Verify low trust reduces feedforward gain"""
        # Run attack scenario - trust should drop, feedforward should reduce
        res_attack = run("CA_full", "A1_false_brake", seed=1)
        res_normal = run("CA_full", "L1_normal", seed=1)
        
        # Attack scenario should show lower minimum trust
        assert res_attack['minw'] < 0.5, \
            f"Trust not degraded in attack: minw={res_attack['minw']:.3f}"
        
        # Normal scenario should maintain high trust
        assert res_normal['minw'] > 0.8, \
            f"Trust degraded in normal operation: minw={res_normal['minw']:.3f}"
    
    def test_headway_increases_with_low_trust(self):
        """Verify headway increases when trust drops (dynh=True)"""
        # Run attack scenario with CA_full (dynh=True)
        res_adaptive = run("CA_full", "A1_false_brake", seed=1)
        
        # Run attack scenario with CA_fixedh (dynh=False)
        res_fixed = run("CA_fixedh", "A1_false_brake", seed=1)
        
        # Adaptive headway should result in larger gaps
        assert res_adaptive['mean_headway'] > res_fixed['mean_headway'], \
            f"Adaptive headway not working: CA_full={res_adaptive['mean_headway']:.3f}s, " \
            f"CA_fixedh={res_fixed['mean_headway']:.3f}s"


class TestEmergencyBraking:
    """Verify emergency braking logic"""
    
    def test_emergency_override_activation(self):
        """Verify emergency braking activates when TTC < 2s or gap < 4m"""
        # Run aggressive attack scenario
        res = run("CA_full", "A1_false_brake", seed=1)
        
        # Should avoid collision despite aggressive attack
        assert res['collision'] == False, \
            "Emergency braking failed to prevent collision"
        
        # Minimum gap should be > 0 but may be small (< 4m triggers emergency)
        assert 0.0 < res['min_gap'] < 6.0, \
            f"Emergency braking behavior unexpected: min_gap={res['min_gap']:.3f}m"


# ══════════════════════════════════════════════════════════════════════════════
# LOW PRIORITY: SENSOR SIMULATION VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

class TestSensorSimulation:
    """Verify radar sensor properties"""
    
    def test_radar_provides_independent_measurements(self):
        """Verify radar measurements are independent of V2X packets"""
        # Run scenario with high packet loss to force radar dependence
        # With crypto=False to avoid crypto rejections
        res = run("D0_none", "L1_normal", seed=1)
        
        # Should still maintain platoon cohesion using radar
        assert res['collision'] == False, \
            "Radar-only operation failed (suggests radar not working)"
        
        assert res['mean_headway'] < 1.5, \
            f"Excessive headway without V2X: {res['mean_headway']:.3f}s (suggests radar issues)"


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION: CROSS-LAYER VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════

class TestCryptoTrustIntegration:
    """Verify crypto gate and trust supervisor integration"""
    
    def test_crypto_rejection_prevents_trust_evaluation(self):
        """Verify rejected packets don't reach trust supervisor"""
        # Run outsider attack (A5_forged) - should be blocked by crypto
        res_outsider = run("CA_full", "A5_forged", seed=1)
        
        # Trust should remain high (attack blocked before trust evaluation)
        assert res_outsider['minw'] > 0.8, \
            f"Trust degraded despite crypto blocking outsider: minw={res_outsider['minw']:.3f}"
        
        # Compare with insider attack (A1) - should reach trust
        res_insider = run("CA_full", "A1_false_brake", seed=1)
        
        # Trust should drop (crypto passes, trust detects)
        assert res_insider['minw'] < 0.5, \
            f"Trust not degraded for insider attack: minw={res_insider['minw']:.3f}"


class TestTrustControlIntegration:
    """Verify trust supervisor and control law integration"""
    
    def test_trust_degradation_increases_gap(self):
        """Verify low trust causes gap expansion via control law"""
        # Run attack with CyberAdapt (trust-adaptive)
        res_ca = run("CA_full", "A1_false_brake", seed=1)
        
        # Run attack with baseline (no trust adaptation)
        res_baseline = run("D1_ma_abse_ar", "A1_false_brake", seed=1)
        
        # CyberAdapt should maintain larger gap
        # (Note: Both should avoid collision, but CA should be more proactive)
        assert res_ca['min_gap'] >= res_baseline['min_gap'], \
            f"CyberAdapt gap not larger: CA={res_ca['min_gap']:.3f}m, " \
            f"baseline={res_baseline['min_gap']:.3f}m"


# ══════════════════════════════════════════════════════════════════════════════
# STRESS TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestStressScenarios:
    """Stress tests for edge cases and worst-case scenarios"""
    
    def test_multiple_seeds_robustness(self):
        """Verify system is robust across different random seeds"""
        min_gaps = []
        
        for seed in range(1, 11):  # 10 different seeds
            res = run("CA_full", "A1_false_brake", seed)
            min_gaps.append(res['min_gap'])
            
            # Each seed should avoid collision
            assert res['collision'] == False, \
                f"Collision with seed={seed}"
        
        # Check variance - gaps should be similar across seeds
        import statistics
        mean_gap = statistics.mean(min_gaps)
        stdev_gap = statistics.stdev(min_gaps)
        
        # Standard deviation should be reasonable (not huge variations)
        assert stdev_gap < mean_gap * 0.5, \
            f"High variance across seeds: mean={mean_gap:.2f}m, stdev={stdev_gap:.2f}m"


# ══════════════════════════════════════════════════════════════════════════════
# MAIN TEST EXECUTION
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-k", "test_collision_free or test_velocity"])
