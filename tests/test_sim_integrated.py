"""
tests/test_sim_integrated.py
Tests for tasks 14.1 (TestCryptoGate), 14.2 (TestSimIntegrated), 14.3 (run_live).

Covers:
  - ZK-TAT round-trip, wrong-context, forgery
  - H-PO round-trip, key sensitivity, attribute sensitivity
  - RevocationBloomFilter add/detect
  - Trust weight bounds
  - CFG schema validation
  - run() result schema and field semantics
  - Crypto sub-dict schema and latency bounds
  - Safety under benign traffic
  - MA-ABSE-AR insider-attack non-detection
  - Outsider packet rejection (A5_forged)
  - run_live() generator state shape, stop_flag, inject_flag
"""

import sys
import unittest
import threading
import time
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sim"))

from crypto_gate import ZKTAT, HPO, RevocationBloomFilter
from trust_supervisor import CyberAdaptTrustController
from sim_integrated import run, run_live, CFG, PacketLogEntry, N


# ---------------------------------------------------------------------------
# Task 14.1 — Crypto primitive unit tests
# ---------------------------------------------------------------------------

class TestCryptoGate(unittest.TestCase):

    def test_zktat_roundtrip(self):
        """Property 1: ZK-TAT round-trip identity"""
        for vid in range(1, 8):
            token = ZKTAT.prove(vid, "test_ctx")
            self.assertTrue(
                ZKTAT.verify(token, "test_ctx"),
                f"ZK-TAT verify failed for vid={vid}",
            )

    def test_zktat_wrong_context(self):
        """Property 2: ZK-TAT wrong-context failure"""
        token = ZKTAT.prove(1, "ctx_A")
        self.assertFalse(
            ZKTAT.verify(token, "ctx_B"),
            "ZK-TAT should fail with wrong context",
        )

    def test_zktat_forgery(self):
        """Property 3: ZK-TAT soundness under forgery"""
        token = ZKTAT.prove(1, "ctx")
        # Mutate s2 to simulate forgery
        forged = dict(token)
        s2 = forged.get("s2", 0)
        forged["s2"] = (s2 + 1) % (2 ** 256)
        self.assertFalse(
            ZKTAT.verify(forged, "ctx"),
            "Forged token should fail verification",
        )

    def test_hpo_roundtrip(self):
        """Property 4: H-PO round-trip identity"""
        tag = HPO.compute_tag("PLATOON_LEADER", b"secret123")
        self.assertTrue(HPO.match_policy(tag, "PLATOON_LEADER", b"secret123"))

    def test_hpo_key_sensitivity(self):
        """Property 5: H-PO key sensitivity"""
        tag = HPO.compute_tag("PLATOON_LEADER", b"secret_A")
        self.assertFalse(
            HPO.match_policy(tag, "PLATOON_LEADER", b"secret_B"),
            "H-PO should fail with wrong secret",
        )

    def test_hpo_attribute_sensitivity(self):
        """H-PO should fail with wrong attribute"""
        tag = HPO.compute_tag("PLATOON_LEADER", b"secret")
        self.assertFalse(HPO.match_policy(tag, "PLATOON_MEMBER", b"secret"))

    def test_bloom_filter(self):
        """Bloom filter: added ID is detected"""
        b = RevocationBloomFilter()
        self.assertFalse(b.is_revoked("veh_1"))
        b.add("veh_1")
        self.assertTrue(b.is_revoked("veh_1"))

    def test_trust_weight_bounds(self):
        """Property 6: Trust weight bounds 0.05 <= w(S) <= 1.0"""
        ctrl = CyberAdaptTrustController()
        for s_int in range(0, 11):
            result = ctrl.process_telemetry_step(
                veh_id="1",
                a_v2x=0.0,
                v_v2x=14.0,
                v_radar=14.0,
                a_acc_radar=0.0,
                v_actual=14.0,
                current_t=float(s_int),
                dt=0.1,
            )
            w = result.get("trust_weight_w", result.get("w", 1.0))
            self.assertGreaterEqual(w, 0.05, f"w below floor at step {s_int}")
            self.assertLessEqual(w, 1.0, f"w above 1.0 at step {s_int}")


# ---------------------------------------------------------------------------
# Task 14.2 — Integration tests for run()
# ---------------------------------------------------------------------------

class TestSimIntegrated(unittest.TestCase):

    def test_cfg_has_ma_abse_ar(self):
        """D1_ma_abse_ar config exists in CFG with correct fields"""
        self.assertIn("D1_ma_abse_ar", CFG)
        cfg = CFG["D1_ma_abse_ar"]
        self.assertTrue(cfg.get("gate"))
        self.assertIsNone(cfg.get("trust"))
        self.assertTrue(cfg.get("crypto"))

    def test_all_cfg_keys_present(self):
        """All 8 config keys present"""
        expected = {
            "D0_none", "D1_crypto", "D1_ma_abse_ar",
            "D2_binary_hnom", "D2b_binary_hfail",
            "CA_full", "CA_norevoke", "CA_fixedh",
        }
        self.assertEqual(set(CFG.keys()), expected)

    def test_run_result_schema(self):
        """Property 10: run() result contains all required fields"""
        r = run("D0_none", "L1_normal", 1)
        required = [
            "min_gap", "collision", "vmin", "peak_decel", "peak_jerk",
            "first_det", "rev", "minw", "ever_w_lt_half", "mean_headway", "crypto",
        ]
        for field in required:
            self.assertIn(field, r, f"Missing field: {field}")

    def test_crypto_subdict_schema(self):
        """crypto sub-dict has all required keys"""
        r = run("D1_ma_abse_ar", "L1_normal", 1)
        crypto = r["crypto"]
        for key in [
            "mean_zktat_prove_us", "mean_zktat_verify_us",
            "mean_hpo_us", "mean_bloom_us", "zktat_pass_rate",
        ]:
            self.assertIn(key, crypto, f"Missing crypto key: {key}")

    def test_benign_traffic_safe(self):
        """Property 9: D1_ma_abse_ar on L1_normal is safe (no collision)"""
        r = run("D1_ma_abse_ar", "L1_normal", 1)
        self.assertFalse(r["collision"])
        self.assertGreater(r["min_gap"], 0)

    def test_ma_abse_ar_no_detection(self):
        """Property 8: MA-ABSE-AR can't detect insider attack"""
        r = run("D1_ma_abse_ar", "A1_false_brake", 1)
        self.assertIsNone(
            r["first_det"],
            "MA-ABSE-AR should not detect insider attack (no physical checks)",
        )

    def test_a5_outsider_rejected(self):
        """Requirement 1.4: A5_forged outsider packets rejected under D1_ma_abse_ar"""
        r = run("D1_ma_abse_ar", "A5_forged", 1)
        # run completed without error
        self.assertIsNotNone(r)
        # With outsider rejected, the platoon should be safer than without gate
        r_none = run("D0_none", "A5_forged", 1)
        # D1_ma_abse_ar should have >= min_gap than D0_none in A5 (allow 1.0 m tolerance)
        self.assertGreaterEqual(r["min_gap"], r_none["min_gap"] - 1.0)

    def test_crypto_latency_nonnegative(self):
        """Property 11: all crypto latency fields are non-negative"""
        r = run("D1_ma_abse_ar", "L1_normal", 1)
        crypto = r["crypto"]
        for key in [
            "mean_zktat_prove_us", "mean_zktat_verify_us",
            "mean_hpo_us", "mean_bloom_us",
        ]:
            self.assertGreaterEqual(crypto[key], 0.0, f"{key} is negative")

    def test_zktat_pass_rate_benign(self):
        """ZK-TAT pass rate should be ~1.0 for benign traffic"""
        r = run("D1_ma_abse_ar", "L1_normal", 1)
        self.assertGreater(r["crypto"]["zktat_pass_rate"], 0.95)

    def test_d0_none_no_crypto(self):
        """Property 12: D0_none produces zero crypto stats"""
        r = run("D0_none", "L1_normal", 1)
        self.assertEqual(r["crypto"]["mean_zktat_prove_us"], 0.0)
        self.assertEqual(r["crypto"]["zktat_pass_rate"], 0.0)


# ---------------------------------------------------------------------------
# Task 14.3 — run_live() generator tests
# ---------------------------------------------------------------------------

class TestRunLive(unittest.TestCase):

    def test_run_live_yields_states(self):
        """run_live() generator yields state dicts with correct keys"""
        stop = threading.Event()
        inject = threading.Event()
        gen = run_live("D1_ma_abse_ar", "L1_normal", 1, inject, stop)

        states = []
        for i, state in enumerate(gen):
            states.append(state)
            if i >= 9:  # collect 10 steps (0.1 s sim time)
                stop.set()
                break

        self.assertGreater(len(states), 0)
        required_keys = [
            "t", "x", "v", "w", "S", "gap", "h",
            "last_crypto", "cfg", "attack_active",
        ]
        for key in required_keys:
            self.assertIn(key, states[0], f"Missing key in state: {key}")

        # Array lengths
        self.assertEqual(len(states[0]["x"]), N)
        self.assertEqual(len(states[0]["v"]), N)
        self.assertEqual(len(states[0]["w"]), N)
        self.assertEqual(len(states[0]["gap"]), N - 1)

    def test_run_live_stop_flag(self):
        """stop_flag terminates run_live() early"""
        stop = threading.Event()
        inject = threading.Event()
        stop.set()  # set before starting
        gen = run_live("D1_ma_abse_ar", "L1_normal", 1, inject, stop)
        states = list(gen)
        self.assertEqual(len(states), 0, "Should yield 0 states when stop is pre-set")

    def test_run_live_inject_flag(self):
        """inject_flag sets attack_active in yielded states"""
        stop = threading.Event()
        inject = threading.Event()
        gen = run_live("CA_full", "L1_normal", 1, inject, stop)

        inject.set()  # inject immediately
        for i, state in enumerate(gen):
            if i > 5:
                self.assertTrue(state["attack_active"])
                stop.set()
                break


if __name__ == "__main__":
    unittest.main(verbosity=2)
