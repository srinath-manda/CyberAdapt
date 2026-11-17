"""
sim_integrated.py — Longitudinal platoon simulator with real crypto pipeline.

Extends sim/sim.py by wiring real Python ZK-TAT, H-PO, and Bloom crypto on
every V2X packet plus a run_live() generator for the live dashboard.

8 vehicles, 100 s, dt=10 ms, 10 Hz V2X beacons.
"""

import math
import random
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from collections import deque
import sys
import hmac
import hashlib

_SIM = Path(__file__).resolve().parent
if str(_SIM) not in sys.path:
    sys.path.insert(0, str(_SIM))

from crypto_gate import ZKTAT, HPO, RevocationBloomFilter
from trust_supervisor import CyberAdaptTrustController

# ── Simulation constants (unchanged from sim.py) ─────────────────────────────
DT = 0.01; T = 100.0; N = 8
V0, D0, H_NOM, H_FAIL = 14.0, 2.5, 0.6, 1.6
KP, KD, KFF, TAU = 0.2, 0.7, 1.0, 0.1
A_MIN, A_MAX, JERK_LIM = -8.0, 3.0, 3.8
DEFAULT_J_LIM = 10.0
J_LIM, DV_LIM, KAPPA, RHO = DEFAULT_J_LIM, 1.5, 4.0, 0.98
ALPHA, BETA, W_MIN = 8.0, 0.45, 0.05
SLEW = 0.25          # max headway change rate [s/s]
T_STALE, T_ATK = 0.5, 20.0

# ── Crypto constants ──────────────────────────────────────────────────────────
_SHARED_SECRET = b"CYBERADAPT_PLATOON_SECRET_2026_CBIT"
_ROLE_ATTR = "PLATOON_MEMBER"
_EPOCH_CTX = "CyberAdapt_epoch_1_highway_E0"

# ── Defence configuration variants ───────────────────────────────────────────
CFG = {
    "D0_none":          dict(gate=False, trust=None,     crypto=False),
    "D1_crypto":        dict(gate=True,  trust=None,     crypto=False),
    "D1_ma_abse_ar":    dict(gate=True,  trust=None,     crypto=True),
    "D2_binary_hnom":   dict(gate=True,  trust="binary", hfail=False, crypto=False),
    "D2b_binary_hfail": dict(gate=True,  trust="binary", hfail=True,  crypto=False),
    "CA_full":          dict(gate=True,  trust="graded", dynh=True,  revoke=True,  enhanced_checks=True, crypto=True),
    "CA_norevoke":      dict(gate=True,  trust="graded", dynh=True,  revoke=False, enhanced_checks=True, crypto=True),
    "CA_fixedh":        dict(gate=True,  trust="graded", dynh=False, revoke=True,  enhanced_checks=True, crypto=True),
}


def w_of_S(S):
    return max(W_MIN, min(1.0, (1 + math.exp(-ALPHA*BETA)) / (1 + math.exp(ALPHA*(S - BETA)))))


def leader_profile(t, scen):
    a_base = 1.0 * 2*math.pi*0.05 * math.cos(2*math.pi*0.05*t)
    if scen in ("L2_legit_brake", "A4_replay") and 30.0 <= t:
        tt = t - 30.0
        if tt < 0.4: return -15.0*tt
        if tt < 1.8: return -6.0
        if tt < 2.2: return -6.0 + 15.0*(tt-1.8)
        if tt < 10.2: return 0.0
        if tt < 21.2: return 1.0
        return a_base
    if scen == "L3_moderate_brake" and 30.0 <= t:
        tt = t - 30.0
        if tt < 0.4375: return -8.0*tt
        if tt < 2.0: return -3.5
        if tt < 2.4375: return -3.5 + 8.0*(tt-2.0)
        if tt < 10.4375: return 0.0
        if tt < 17.4375: return 1.0
        return a_base
    return a_base


# ── Packet log entry dataclass ────────────────────────────────────────────────
@dataclass
class PacketLogEntry:
    t: float
    src: int
    zktat_pass: bool
    hpo_pass: bool
    bloom_hit: bool
    zktat_prove_us: float
    zktat_verify_us: float
    hpo_us: float
    bloom_us: float
    accepted: bool
    payload_valid: bool = True      # Bug 2 fix: payload integrity check
    replay_detected: bool = False   # Bug 3 fix: sequence number freshness


def _run_crypto_gate(p, t, cfg, bloom, crypto_latency, last_seq,
                     prove_us_override=None, zktat_pass_override=None):
    """
    Run the four-stage crypto gate on a received packet.
    Returns (accepted: bool, entry: PacketLogEntry).
    
    Bug 2 & 3 Fixes:
    - Stage 4: Payload integrity verification (MAC check)
    - Sequence number tracking for replay detection
    """
    src = p.get("src", -1)
    cred_id = p.get("cred_id", str(src))

    # Stage 1 — Bloom revocation check
    t0 = time.perf_counter()
    bloom_hit = bloom.is_revoked(cred_id)
    bloom_us = (time.perf_counter() - t0) * 1e6

    # Stage 2 — ZK-TAT verify
    token = p.get("token")
    prove_us = p.get("prove_us", 0.0) if prove_us_override is None else prove_us_override

    if zktat_pass_override is not None:
        zktat_pass = zktat_pass_override
        zktat_verify_us = 0.0
    elif token is None:
        zktat_pass = False
        zktat_verify_us = 0.0
    else:
        t0 = time.perf_counter()
        try:
            zktat_pass = ZKTAT.verify(token, _EPOCH_CTX, smbp=True)
        except Exception:
            zktat_pass = False
        zktat_verify_us = (time.perf_counter() - t0) * 1e6

    # Stage 3 — H-PO match
    hpo_tag = p.get("hpo_tag")
    if hpo_tag is None:
        hpo_pass = False
        hpo_us = 0.0
    else:
        t0 = time.perf_counter()
        try:
            hpo_pass = HPO.match_policy(hpo_tag, _ROLE_ATTR, _SHARED_SECRET)
        except Exception:
            hpo_pass = False
        hpo_us = (time.perf_counter() - t0) * 1e6

    # Bug 3 fix: Sequence number freshness check for replay detection
    seq = p.get("seq", 0)
    replay_detected = False
    if src in last_seq and seq <= last_seq[src]:
        replay_detected = True
    else:
        last_seq[src] = seq

    # Stage 4 — Payload integrity check (Bug 2 fix)
    payload_valid = True
    payload_mac = p.get("payload_mac")
    if payload_mac is not None:
        # Reconstruct payload and verify MAC
        ts = p.get("ts", 0.0)
        v = p.get("v", 0.0)
        a = p.get("a", 0.0)
        payload_str = f"{ts}|{v}|{a}|{seq}"
        payload_bytes = payload_str.encode('utf-8')
        expected_mac = hmac.new(_SHARED_SECRET, payload_bytes, hashlib.sha256).hexdigest()
        payload_valid = hmac.compare_digest(payload_mac, expected_mac)
    else:
        # No MAC present (e.g., forged outsider packet) - fail payload check
        payload_valid = False

    # Final acceptance: all stages must pass
    accepted = zktat_pass and hpo_pass and not bloom_hit and payload_valid and not replay_detected

    entry = PacketLogEntry(
        t=t, src=src,
        zktat_pass=zktat_pass, hpo_pass=hpo_pass, bloom_hit=bloom_hit,
        zktat_prove_us=prove_us,
        zktat_verify_us=zktat_verify_us,
        hpo_us=hpo_us,
        bloom_us=bloom_us,
        accepted=accepted,
        payload_valid=payload_valid,
        replay_detected=replay_detected,
    )
    crypto_latency.append(entry)
    return accepted, entry


def _attach_crypto_to_packet(pk, sender_id):
    """
    Prove ZK-TAT and compute H-PO tag for an outbound packet.
    Attaches token, hpo_tag, cred_id, prove_us, payload_mac in-place and returns pk.
    
    Bug 2 & 3 Fix: Add payload MAC over "ts|v|a|seq" for tampering detection.
    """
    # ZK-TAT prove with precomputed table (smbp=True avoids slow baseline scalar mult)
    t0 = time.perf_counter()
    token = ZKTAT.prove(sender_id, _EPOCH_CTX, smbp=True)
    prove_us = (time.perf_counter() - t0) * 1e6

    # H-PO tag
    hpo_tag = HPO.compute_tag(_ROLE_ATTR, _SHARED_SECRET)

    # Payload MAC (Bug 2 & 3 fix): HMAC-SHA256 over "ts|v|a|seq"
    # Binds crypto credentials to message payload for integrity verification
    payload_str = f"{pk['ts']}|{pk['v']}|{pk['a']}|{pk['seq']}"
    payload_bytes = payload_str.encode('utf-8')
    payload_mac = hmac.new(_SHARED_SECRET, payload_bytes, hashlib.sha256).hexdigest()

    pk["token"] = token
    pk["hpo_tag"] = hpo_tag
    pk["cred_id"] = str(sender_id)
    pk["prove_us"] = prove_us
    pk["payload_mac"] = payload_mac  # Bug 2 & 3 fix
    return pk


def run(cfgname, scen, seed, trace=False):
    cfg = CFG[cfgname]
    rnd = random.Random(seed)
    n = int(T/DT)

    x = [0.0]*N; v = [V0]*N; a = [0.0]*N; u = [0.0]*N
    d_init = D0 + H_NOM*V0
    for i in range(N): x[i] = -i*(d_init + 4.5)
    VL = 4.5

    link = [[] for _ in range(N)]; lastp = [None]*N
    prevp = [None]*N; S = [0.0]*N; w = [1.0]*N; lowt = [0.0]*N
    radar = [(0.0, V0)]*N; vrad_hist = [[] for _ in range(N)]; arep = [[] for _ in range(N)]
    revoked = set(); rev_pending = {}; rev_time = None; first_det = None
    seqn = [0]*N; rec_for_replay = []
    minw = 1.0; sw_until = [0.0]*N; viol_time = [-9.0]*N
    res = dict(min_gap=1e9, collision=False, vmin=1e9, peak_decel=0.0, peak_jerk=0.0,
               headway=[], first_det=None, rev=None, minw=1.0, ever_w_lt_half=False)
    u_prev = [0.0]*N; a_prev_true = [0.0]*N; t_atk_end = T
    next_beacon = 0.0
    hstate = [H_NOM]*N
    weff = [1.0]*N; tr = []
    tm = 55.0 if scen == "A4_replay" else 5.0

    # Crypto state
    use_crypto = cfg.get("crypto", False)
    crypto_latency = []
    bloom = RevocationBloomFilter() if use_crypto else None
    last_seq = {}  # Bug 3 fix: sequence number tracking for replay detection

    for i in range(1, N):
        wp = dict(ts=-0.1, v=V0, a=0.0, seq=0, cred=True, src=i-1, rx=0.0)
        lastp[i] = wp; prevp[i] = wp
        radar[i] = (d_init, V0)

    for step in range(n):
        t = step*DT

        # ── V2X beacons ───────────────────────────────────────────────────────
        if t >= next_beacon - 1e-9:
            next_beacon += 0.1
            for i in range(N-1):
                av = a[i] + rnd.gauss(0, 0.05); vv = v[i] + rnd.gauss(0, 0.02)
                seqn[i] += 1
                pk = dict(ts=t, v=vv, a=av, seq=seqn[i], cred=True, src=i)

                # Attach crypto to legitimate outbound packet
                if use_crypto:
                    _attach_crypto_to_packet(pk, i)

                if i == 2: rec_for_replay.append(pk)

                if rnd.random() > 0.02:
                    link[i+1].append(dict(pk, arr=t + rnd.uniform(0.010, 0.030)))

                # Attack injection
                if i == 2 and t >= T_ATK and scen in ("A1_false_brake", "A2_false_accel",
                                                        "A3_stealth_ramp", "A5_forged"):
                    f = dict(pk)
                    tt = t - T_ATK
                    if scen == "A1_false_brake": f["a"] = -6.0
                    elif scen == "A2_false_accel": f["a"] = 3.0
                    elif scen == "A3_stealth_ramp": f["a"] = -min(3.0, 1.5*tt)
                    elif scen == "A5_forged":
                        f["a"] = -6.0; f["cred"] = False
                        # Outsider forged packet: no token, cred=False
                        f.pop("token", None); f.pop("hpo_tag", None); f.pop("cred_id", None)
                        f.pop("payload_mac", None)  # Bug 7 fix: Remove payload MAC as well
                    
                    # Bug 8 fix: Insider attacks recompute payload MAC (compromised insider with key access)
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

                # Bug 3 fix: Strip credentials from A4_replay replayed packets
                if i == 2 and scen == "A4_replay" and t >= 60.0:
                    k = int((t - 60.0)/0.1) + 300
                    if k < len(rec_for_replay):
                        old = rec_for_replay[min(k, len(rec_for_replay)-1)]
                        # Copy ONLY payload fields, exclude crypto credentials
                        replay_pkt = dict(
                            src=old["src"],
                            ts=old["ts"],
                            v=old["v"],
                            a=old["a"],
                            seq=old["seq"],
                            arr=t + 0.035,
                            cred=False,
                            replay=True
                        )
                        link[3].append(replay_pkt)

        # ── Receive & trust ───────────────────────────────────────────────────
        for i in range(1, N):
            q = link[i]; ready = [p for p in q if p["arr"] <= t]
            if not ready: continue
            link[i] = [p for p in q if p["arr"] > t]

            for p in sorted(ready, key=lambda z: z["arr"]):
                # Hard gate (credential, freshness, revocation)
                if cfg["gate"]:
                    if (not p.get("cred", True)) or abs(t - p["ts"]) > 0.2 or (p["src"] in revoked):
                        continue

                # Crypto pipeline gate
                if use_crypto:
                    # A5_forged outsider packets: no token => ZK-TAT fails immediately
                    if not p.get("cred", True) or p.get("token") is None:
                        zktat_pass_override = False
                    else:
                        zktat_pass_override = None

                    accepted, _entry = _run_crypto_gate(
                        p, t, cfg, bloom, crypto_latency, last_seq,
                        zktat_pass_override=zktat_pass_override,
                    )
                    if not accepted:
                        continue

                lastp[i] = dict(p, rx=t)
                if cfg["trust"] is None: continue

                vr = radar[i][1]
                vrep = p["v"] + p["a"]*(t - p["ts"]); dv = abs(vrep - vr)
                z = 0.0; pp = prevp[i]
                zJ = zc = 0.0
                if pp is not None and 0.05 < p["ts"] - pp["ts"] < 0.35:
                    dts = p["ts"] - pp["ts"]
                    J = abs(p["a"] - pp["a"]) / dts
                    # Bug 5 fix: Leader exemption - use higher threshold for leader (src=0)
                    J_threshold = J_LIM * 2.5 if p["src"] == 0 else J_LIM
                    zJ = min(1.0, max(0.0, (J/J_threshold - 1)/(KAPPA - 1)))
                    if cfg.get("enhanced_checks", False):
                        arep[i].append((p["ts"], p["a"]))
                        arep[i] = [z_ for z_ in arep[i] if z_[0] > p["ts"] - 0.5]
                        h_ = vrad_hist[i]
                        if len(h_) > 0 and arep[i]:
                            old_r = [z_ for z_ in h_ if z_[0] <= t - 0.5]
                            if old_r:
                                a_rad = (vr - old_r[-1][1]) / (t - old_r[-1][0])
                                am = sum(z_[1] for z_ in arep[i]) / len(arep[i])
                                if abs(am - a_rad) < 0.7: zJ = 0.0
                        a_from_v = (p["v"] - pp["v"]) / dts
                        inc = abs(p["a"] - a_from_v)
                        zc = min(1.0, max(0.0, (inc/1.2 - 1)/(KAPPA - 1)))

                zV = min(1.0, max(0.0, (dv/DV_LIM - 1)/(KAPPA - 1)))
                z = max(zJ, zV, zc)
                prevp[i] = p
                S[i] = max(z, RHO*S[i]) if cfg["trust"] == "graded" else S[i]
                if cfg["trust"] == "binary" and (z >= 0.1): viol_time[i] = t
                if cfg["trust"] == "graded":
                    w[i] = w_of_S(S[i])
                    if i == 3 or scen.startswith("L"): minw = min(minw, w[i])
                    if i == 3 and t >= T_ATK and first_det is None and S[i] > 0.5:
                        first_det = t
                    if cfg.get("revoke"):
                        if w[i] <= 0.2:
                            if lowt[i] == 0.0: lowt[i] = t
                            if t - lowt[i] >= 1.0 and p["src"] not in rev_pending:
                                rev_pending[p["src"]] = t + 1.0
                                # Also add to bloom on revocation
                                if use_crypto and bloom is not None:
                                    bloom.add(str(p["src"]))
                        else:
                            lowt[i] = 0.0

        for srcid, tt in list(rev_pending.items()):
            if t >= tt and srcid not in revoked:
                revoked.add(srcid); rev_time = rev_time or t

        # ── Sensing & control ─────────────────────────────────────────────────
        if step % 5 == 0:
            for i in range(1, N):
                gap = x[i-1] - x[i] - VL + rnd.gauss(0, 0.05)
                vrr = v[i-1] + rnd.gauss(0, 0.05)
                radar[i] = (gap, vrr)
                vrad_hist[i].append((t, vrr))
                vrad_hist[i] = [z_ for z_ in vrad_hist[i] if z_[0] > t - 1.0]

        a_leader = leader_profile(t, scen); u[0] = a_leader
        for i in range(1, N):
            gap, vrr = radar[i]
            lp = lastp[i]; stale = (lp is None) or (t - lp["rx"] > T_STALE)
            mode = cfg["trust"]
            if mode is None:
                wi = 1.0; h = H_NOM
            elif mode == "binary":
                latched = (t - viol_time[i]) < 5.0
                wi = 0.0 if (latched or stale) else 1.0
                h = (H_FAIL if cfg.get("hfail") else H_NOM) if wi == 0.0 else H_NOM
                if stale: h = H_FAIL
            else:
                wi = 0.0 if stale else w[i]
                h_t = (H_NOM + (1 - wi)*(H_FAIL - H_NOM)) if cfg.get("dynh") else H_NOM
                if stale: h_t = H_FAIL if cfg.get("dynh") else H_NOM
                hs_ = hstate[i]; step_ = SLEW*DT
                hstate[i] = hs_ + max(-step_, min(step_, h_t - hs_)); h = hstate[i]

            if mode is None and lp is None: wi = 0.0
            d_t = D0 + h*v[i]
            e = gap - d_t; ed = vrr - v[i] - h*a[i]
            a_acc = KP*e + KD*ed
            a_ff = 0.0
            if lp is not None and wi > 0.0:
                a_ff = KFF*(lp["a"] - 0.0)
            cmd = a_acc + wi*a_ff; weff[i] = wi
            ttc = gap/max(1e-3, v[i]-vrr) if v[i] > vrr else 1e9
            emergency = (ttc < 2.0) or (gap < 4.0)
            if not emergency:
                cmd = max(u_prev[i] - JERK_LIM*DT, min(u_prev[i] + JERK_LIM*DT, cmd))
            cmd = max(A_MIN, min(A_MAX, cmd)); u_prev[i] = cmd; u[i] = cmd

        # ── Dynamics ──────────────────────────────────────────────────────────
        for i in range(N):
            a_new = a[i] + DT*(u[i] - a[i])/TAU if i > 0 else u[i]
            jerk = abs(a_new - a[i])/DT
            a[i] = a_new; v[i] = max(0.0, v[i] + a[i]*DT); x[i] += v[i]*DT
            if i > 0 and t >= tm:
                res["peak_jerk"] = max(res["peak_jerk"], jerk)
                res["peak_decel"] = max(res["peak_decel"], -a[i])

        if trace and step % 10 == 0:
            tr.append((t, x[2]-x[3]-VL, v[3], weff[3], x[0]-x[1]-VL, v[0], hstate[3], weff[1], v[1]))

        if t >= tm:
            for i in range(1, N):
                g = x[i-1] - x[i] - VL
                res["min_gap"] = min(res["min_gap"], g)
                if g <= 0: res["collision"] = True
                res["vmin"] = min(res["vmin"], v[i])
            if step % 10 == 0 and t >= max(30.0, tm):
                res["headway"].append(
                    sum((x[i-1]-x[i]-VL)/max(v[i], 1.0) for i in range(3, 8)) / 5
                )

    hw = res.pop("headway")
    res["mean_headway"] = sum(hw)/len(hw) if hw else 0.0
    res["first_det"] = (first_det - T_ATK) if first_det else None
    res["rev"] = (rev_time - T_ATK) if rev_time else None
    res["minw"] = minw
    if trace: res["trace"] = tr

    # ── Crypto summary ────────────────────────────────────────────────────────
    if use_crypto and crypto_latency:
        prove_times = [e.zktat_prove_us for e in crypto_latency if e.zktat_prove_us > 0]
        verify_times = [e.zktat_verify_us for e in crypto_latency if e.zktat_verify_us > 0]
        hpo_times = [e.hpo_us for e in crypto_latency if e.hpo_us > 0]
        bloom_times = [e.bloom_us for e in crypto_latency]
        n_total = len(crypto_latency)
        n_pass = sum(1 for e in crypto_latency if e.zktat_pass)

        res["crypto"] = {
            "mean_zktat_prove_us": sum(prove_times)/len(prove_times) if prove_times else 0.0,
            "mean_zktat_verify_us": sum(verify_times)/len(verify_times) if verify_times else 0.0,
            "mean_hpo_us": sum(hpo_times)/len(hpo_times) if hpo_times else 0.0,
            "mean_bloom_us": sum(bloom_times)/len(bloom_times) if bloom_times else 0.0,
            "zktat_pass_rate": n_pass / n_total if n_total > 0 else 0.0,
            "total_packets": n_total,
        }
    else:
        res["crypto"] = {
            "mean_zktat_prove_us": 0.0,
            "mean_zktat_verify_us": 0.0,
            "mean_hpo_us": 0.0,
            "mean_bloom_us": 0.0,
            "zktat_pass_rate": 0.0,
            "total_packets": 0,
        }

    return res


def run_live(cfgname, scen, seed, inject_flag, stop_flag):
    """
    Generator version of run() for the live dashboard.

    Yields a state dict every simulation step.
    inject_flag (threading.Event): when set, injects a=-6.0 from vehicle 2.
    stop_flag   (threading.Event): when set, stops the generator.
    """
    cfg = CFG[cfgname]
    rnd = random.Random(seed)
    n = int(T/DT)

    x = [0.0]*N; v = [V0]*N; a = [0.0]*N; u = [0.0]*N
    d_init = D0 + H_NOM*V0
    for i in range(N): x[i] = -i*(d_init + 4.5)
    VL = 4.5

    link = [[] for _ in range(N)]; lastp = [None]*N
    prevp = [None]*N; S = [0.0]*N; w = [1.0]*N; lowt = [0.0]*N
    radar = [(0.0, V0)]*N; vrad_hist = [[] for _ in range(N)]; arep = [[] for _ in range(N)]
    revoked = set(); rev_pending = {}; rev_time = None; first_det = None
    seqn = [0]*N; rec_for_replay = []
    minw = 1.0; viol_time = [-9.0]*N
    u_prev = [0.0]*N
    next_beacon = 0.0
    hstate = [H_NOM]*N
    weff = [1.0]*N
    tm = 55.0 if scen == "A4_replay" else 5.0

    # Crypto state
    use_crypto = cfg.get("crypto", False)
    crypto_latency = []
    crypto_log_live = deque(maxlen=50)
    bloom = RevocationBloomFilter() if use_crypto else None
    last_seq = {}  # Bug 3 fix: sequence number tracking

    attack_active = False

    for i in range(1, N):
        wp = dict(ts=-0.1, v=V0, a=0.0, seq=0, cred=True, src=i-1, rx=0.0)
        lastp[i] = wp; prevp[i] = wp
        radar[i] = (d_init, V0)

    for step in range(n):
        if stop_flag.is_set():
            return

        t = step*DT

        # Check inject flag
        if inject_flag.is_set():
            attack_active = True

        # ── V2X beacons ───────────────────────────────────────────────────────
        if t >= next_beacon - 1e-9:
            next_beacon += 0.1
            for i in range(N-1):
                av = a[i] + rnd.gauss(0, 0.05); vv = v[i] + rnd.gauss(0, 0.02)
                seqn[i] += 1
                pk = dict(ts=t, v=vv, a=av, seq=seqn[i], cred=True, src=i)

                if use_crypto:
                    _attach_crypto_to_packet(pk, i)

                if i == 2: rec_for_replay.append(pk)

                if rnd.random() > 0.02:
                    link[i+1].append(dict(pk, arr=t + rnd.uniform(0.010, 0.030)))

                # Scenario-based attacks
                if i == 2 and t >= T_ATK and scen in ("A1_false_brake", "A2_false_accel",
                                                        "A3_stealth_ramp", "A5_forged"):
                    f = dict(pk)
                    tt_a = t - T_ATK
                    if scen == "A1_false_brake": f["a"] = -6.0
                    elif scen == "A2_false_accel": f["a"] = 3.0
                    elif scen == "A3_stealth_ramp": f["a"] = -min(3.0, 1.5*tt_a)
                    elif scen == "A5_forged":
                        f["a"] = -6.0; f["cred"] = False
                        f.pop("token", None); f.pop("hpo_tag", None); f.pop("cred_id", None)
                        f.pop("payload_mac", None)  # Bug 7 fix: Remove payload MAC as well
                    
                    # Bug 8 fix: Insider attacks recompute payload MAC (compromised insider with key access)
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

                # Live inject flag attack: inject a=-6.0 from vehicle 2
                if i == 2 and attack_active:
                    f = dict(pk); f["a"] = -6.0
                    # Bug 9 fix: Recompute payload MAC for live inject
                    payload_str = f"{f['ts']}|{f['v']}|{f['a']}|{f['seq']}"
                    payload_bytes = payload_str.encode('utf-8')
                    f["payload_mac"] = hmac.new(_SHARED_SECRET, payload_bytes, hashlib.sha256).hexdigest()
                    link[3] = [p for p in link[3] if not (p["ts"] == pk["ts"])] + (
                        [dict(f, arr=t + rnd.uniform(0.010, 0.030))] if rnd.random() > 0.02 else []
                    )

                # Bug 3 fix: Strip credentials from A4_replay replayed packets (run_live)
                if i == 2 and scen == "A4_replay" and t >= 60.0:
                    k = int((t - 60.0)/0.1) + 300
                    if k < len(rec_for_replay):
                        old = rec_for_replay[min(k, len(rec_for_replay)-1)]
                        # Copy ONLY payload fields, exclude crypto credentials
                        replay_pkt = dict(
                            src=old["src"],
                            ts=old["ts"],
                            v=old["v"],
                            a=old["a"],
                            seq=old["seq"],
                            arr=t + 0.035,
                            cred=False,
                            replay=True
                        )
                        link[3].append(replay_pkt)

        # ── Receive & trust ───────────────────────────────────────────────────
        for i in range(1, N):
            q = link[i]; ready = [p for p in q if p["arr"] <= t]
            if not ready: continue
            link[i] = [p for p in q if p["arr"] > t]

            for p in sorted(ready, key=lambda z: z["arr"]):
                if cfg["gate"]:
                    if (not p.get("cred", True)) or abs(t - p["ts"]) > 0.2 or (p["src"] in revoked):
                        continue

                if use_crypto:
                    if not p.get("cred", True) or p.get("token") is None:
                        zktat_pass_override = False
                    else:
                        zktat_pass_override = None

                    accepted, entry = _run_crypto_gate(
                        p, t, cfg, bloom, crypto_latency, last_seq,
                        zktat_pass_override=zktat_pass_override,
                    )
                    crypto_log_live.append(entry)
                    if not accepted:
                        continue

                lastp[i] = dict(p, rx=t)
                if cfg["trust"] is None: continue

                vr = radar[i][1]
                vrep = p["v"] + p["a"]*(t - p["ts"]); dv = abs(vrep - vr)
                z = 0.0; pp = prevp[i]
                zJ = zc = 0.0
                if pp is not None and 0.05 < p["ts"] - pp["ts"] < 0.35:
                    dts = p["ts"] - pp["ts"]
                    J = abs(p["a"] - pp["a"]) / dts
                    # Bug 5 fix: Leader exemption - use higher threshold for leader (src=0)
                    J_threshold = J_LIM * 2.5 if p["src"] == 0 else J_LIM
                    zJ = min(1.0, max(0.0, (J/J_threshold - 1)/(KAPPA - 1)))
                    if cfg.get("enhanced_checks", False):
                        arep[i].append((p["ts"], p["a"]))
                        arep[i] = [z_ for z_ in arep[i] if z_[0] > p["ts"] - 0.5]
                        h_ = vrad_hist[i]
                        if len(h_) > 0 and arep[i]:
                            old_r = [z_ for z_ in h_ if z_[0] <= t - 0.5]
                            if old_r:
                                a_rad = (vr - old_r[-1][1]) / (t - old_r[-1][0])
                                am = sum(z_[1] for z_ in arep[i]) / len(arep[i])
                                if abs(am - a_rad) < 0.7: zJ = 0.0
                        a_from_v = (p["v"] - pp["v"]) / dts
                        inc = abs(p["a"] - a_from_v)
                        zc = min(1.0, max(0.0, (inc/1.2 - 1)/(KAPPA - 1)))

                zV = min(1.0, max(0.0, (dv/DV_LIM - 1)/(KAPPA - 1)))
                z = max(zJ, zV, zc)
                prevp[i] = p
                S[i] = max(z, RHO*S[i]) if cfg["trust"] == "graded" else S[i]
                if cfg["trust"] == "binary" and (z >= 0.1): viol_time[i] = t
                if cfg["trust"] == "graded":
                    w[i] = w_of_S(S[i])
                    if i == 3 or scen.startswith("L"): minw = min(minw, w[i])
                    if i == 3 and t >= T_ATK and first_det is None and S[i] > 0.5:
                        first_det = t
                    if cfg.get("revoke"):
                        if w[i] <= 0.2:
                            if lowt[i] == 0.0: lowt[i] = t
                            if t - lowt[i] >= 1.0 and p["src"] not in rev_pending:
                                rev_pending[p["src"]] = t + 1.0
                                if use_crypto and bloom is not None:
                                    bloom.add(str(p["src"]))
                        else:
                            lowt[i] = 0.0

        for srcid, tt in list(rev_pending.items()):
            if t >= tt and srcid not in revoked:
                revoked.add(srcid); rev_time = rev_time or t

        # ── Sensing & control ─────────────────────────────────────────────────
        if step % 5 == 0:
            for i in range(1, N):
                gap = x[i-1] - x[i] - VL + rnd.gauss(0, 0.05)
                vrr = v[i-1] + rnd.gauss(0, 0.05)
                radar[i] = (gap, vrr)
                vrad_hist[i].append((t, vrr))
                vrad_hist[i] = [z_ for z_ in vrad_hist[i] if z_[0] > t - 1.0]

        a_leader = leader_profile(t, scen); u[0] = a_leader
        for i in range(1, N):
            gap, vrr = radar[i]
            lp = lastp[i]; stale = (lp is None) or (t - lp["rx"] > T_STALE)
            mode = cfg["trust"]
            if mode is None:
                wi = 1.0; h = H_NOM
            elif mode == "binary":
                latched = (t - viol_time[i]) < 5.0
                wi = 0.0 if (latched or stale) else 1.0
                h = (H_FAIL if cfg.get("hfail") else H_NOM) if wi == 0.0 else H_NOM
                if stale: h = H_FAIL
            else:
                wi = 0.0 if stale else w[i]
                h_t = (H_NOM + (1 - wi)*(H_FAIL - H_NOM)) if cfg.get("dynh") else H_NOM
                if stale: h_t = H_FAIL if cfg.get("dynh") else H_NOM
                hs_ = hstate[i]; step_ = SLEW*DT
                hstate[i] = hs_ + max(-step_, min(step_, h_t - hs_)); h = hstate[i]

            if mode is None and lp is None: wi = 0.0
            d_t = D0 + h*v[i]
            e = gap - d_t; ed = vrr - v[i] - h*a[i]
            a_acc = KP*e + KD*ed
            a_ff = 0.0
            if lp is not None and wi > 0.0:
                a_ff = KFF*(lp["a"] - 0.0)
            cmd = a_acc + wi*a_ff; weff[i] = wi
            ttc = gap/max(1e-3, v[i]-vrr) if v[i] > vrr else 1e9
            emergency = (ttc < 2.0) or (gap < 4.0)
            if not emergency:
                cmd = max(u_prev[i] - JERK_LIM*DT, min(u_prev[i] + JERK_LIM*DT, cmd))
            cmd = max(A_MIN, min(A_MAX, cmd)); u_prev[i] = cmd; u[i] = cmd

        # ── Dynamics ──────────────────────────────────────────────────────────
        for i in range(N):
            a_new = a[i] + DT*(u[i] - a[i])/TAU if i > 0 else u[i]
            a[i] = a_new; v[i] = max(0.0, v[i] + a[i]*DT); x[i] += v[i]*DT

        # ── Yield live state ──────────────────────────────────────────────────
        yield {
            "t": t,
            "x": list(x),
            "v": list(v),
            "w": list(w),
            "S": list(S),
            "gap": [x[i-1]-x[i]-VL for i in range(1, N)],
            "h": list(hstate),
            "last_crypto": [asdict(e) for e in list(crypto_log_live)[-7:]],
            "cfg": cfgname,
            "attack_active": attack_active,
        }


if __name__ == "__main__":
    import json
    from pathlib import Path as _P

    results_dir = _P(__file__).resolve().parents[1] / "results"
    results_dir.mkdir(exist_ok=True)

    configs_to_test = ["D1_ma_abse_ar", "CA_full"]
    scenarios = ["L1_normal", "A1_false_brake"]
    seeds = [1, 2, 3]

    all_results = {}
    t_wall = time.perf_counter()

    for scen in scenarios:
        for cfgname in configs_to_test:
            for seed in seeds:
                key = f"{scen}__{cfgname}__seed{seed}"
                print(f"Running {key} ...", end=" ", flush=True)
                r = run(cfgname, scen, seed)
                crypto = r.get("crypto", {})
                summary = {
                    k: round(v, 3) if isinstance(v, float) else v
                    for k, v in r.items() if k != "trace"
                }
                all_results[key] = summary
                print(
                    f"gap={round(r['min_gap'], 2):6.2f}  "
                    f"col={r['collision']}  "
                    f"zktat_rate={round(crypto.get('zktat_pass_rate', 0.0), 3):.3f}"
                )

    elapsed = time.perf_counter() - t_wall
    print(f"\nTotal wall time: {elapsed:.1f} s")

    out_path = results_dir / "sim_integrated_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"Results written to {out_path}")
