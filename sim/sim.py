"""Longitudinal platoon simulator for CyberAdapt evaluation (custom, Python). 8 vehicles, 100 s, dt=10 ms, 10 Hz V2X beacons."""
import math, random
DT = 0.01; T = 100.0; N = 8
V0, D0, H_NOM, H_FAIL = 14.0, 2.5, 0.6, 1.6
KP, KD, KFF, TAU = 0.2, 0.7, 1.0, 0.1
A_MIN, A_MAX, JERK_LIM = -8.0, 3.0, 3.8
DEFAULT_J_LIM = 10.0
J_LIM, DV_LIM, KAPPA, RHO = DEFAULT_J_LIM, 1.5, 4.0, 0.98
ALPHA, BETA, W_MIN = 8.0, 0.45, 0.05
SLEW = 0.25          # max headway change rate [s/s] (engineering addition)
T_STALE, T_ATK = 0.5, 20.0
CFG = {  # defence variants
 "D0_none":      dict(gate=False, trust=None),
 "D1_crypto":    dict(gate=True,  trust=None),
 "D2_binary_hnom":  dict(gate=True, trust="binary", hfail=False),
 "D2b_binary_hfail":dict(gate=True, trust="binary", hfail=True),
 "CA_full":      dict(gate=True, trust="graded", dynh=True,  revoke=True,  enhanced_checks=True),
 "CA_norevoke":  dict(gate=True, trust="graded", dynh=True,  revoke=False, enhanced_checks=True),
 "CA_fixedh":    dict(gate=True, trust="graded", dynh=False, revoke=True,  enhanced_checks=True),
}
def w_of_S(S): return max(W_MIN, min(1.0, (1 + math.exp(-ALPHA*BETA)) / (1 + math.exp(ALPHA*(S - BETA)))))
def leader_profile(t, scen):
    a_base = 1.0 * 2*math.pi*0.05 * math.cos(2*math.pi*0.05*t)      # +-1 m/s sinusoid at 0.05 Hz
    if scen in ("L2_legit_brake", "A4_replay") and 30.0 <= t:
        tt = t - 30.0                                   # ramp to -6 m/s^2 (15 m/s^3), hold, ramp back, rest, recover at +1 m/s^2
        if tt < 0.4: return -15.0*tt
        if tt < 1.8: return -6.0
        if tt < 2.2: return -6.0 + 15.0*(tt-1.8)
        if tt < 10.2: return 0.0
        if tt < 21.2: return 1.0
        return a_base
    if scen == "L3_moderate_brake" and 30.0 <= t:
        tt = t - 30.0                                   # ramp to -3.5 m/s^2 (8 m/s^3), hold, ramp back, rest, recover
        if tt < 0.4375: return -8.0*tt
        if tt < 2.0: return -3.5
        if tt < 2.4375: return -3.5 + 8.0*(tt-2.0)
        if tt < 10.4375: return 0.0
        if tt < 17.4375: return 1.0
        return a_base
    return a_base
def run(cfgname, scen, seed, trace=False):
    cfg = CFG[cfgname]; rnd = random.Random(seed)
    n = int(T/DT)
    x = [0.0]*N; v = [V0]*N; a = [0.0]*N; u = [0.0]*N
    d_init = D0 + H_NOM*V0 + 0.0
    for i in range(N): x[i] = -i*(d_init + 4.5)             # vehicle length 4.5 m
    VL = 4.5
    link = [[] for _ in range(N)]; lastp = [None]*N          # accepted packets per receiver
    prevp = [None]*N; S = [0.0]*N; w = [1.0]*N; lowt = [0.0]*N
    radar = [(0.0, V0)]*N; vrad_hist = [[] for _ in range(N)]; arep = [[] for _ in range(N)]
    revoked = set(); rev_pending = {}; rev_time = None; first_det = None
    seqn = [0]*N; atk_log = []; rec_for_replay = []
    minw = 1.0; w_hist_clean = []; sw_until = [0.0]*N; viol_time = [-9.0]*N
    res = dict(min_gap=1e9, collision=False, vmin=1e9, peak_decel=0.0, peak_jerk=0.0, headway=[], first_det=None, rev=None, minw=1.0, ever_w_lt_half=False)
    u_prev = [0.0]*N; a_prev_true = [0.0]*N; t_atk_end = T
    next_beacon = 0.0; sh = 0.0
    hstate = [H_NOM]*N
    weff = [1.0]*N; tr = []
    tm = 55.0 if scen == "A4_replay" else 5.0
    for i in range(1, N):
        wp = dict(ts=-0.1, v=V0, a=0.0, seq=0, cred=True, src=i-1, rx=0.0); lastp[i] = wp; prevp[i] = wp
        radar[i] = (d_init, V0)
    for step in range(n):
        t = step*DT
        # ---------------- V2X beacons ----------------
        if t >= next_beacon - 1e-9:
            next_beacon += 0.1
            for i in range(N-1):                                  # sender i -> receiver i+1
                av = a[i] + rnd.gauss(0, 0.05); vv = v[i] + rnd.gauss(0, 0.02)
                seqn[i] += 1
                pk = dict(ts=t, v=vv, a=av, seq=seqn[i], cred=True, src=i)
                if i == 2: rec_for_replay.append(pk)
                if rnd.random() > 0.02:
                    link[i+1].append(dict(pk, arr=t + rnd.uniform(0.010, 0.030)))
                if i == 2 and t >= T_ATK and scen in ("A1_false_brake", "A2_false_accel", "A3_stealth_ramp", "A5_forged"):
                    f = dict(pk); tt = t - T_ATK
                    if scen == "A1_false_brake": f["a"] = -6.0
                    elif scen == "A2_false_accel": f["a"] = 3.0
                    elif scen == "A3_stealth_ramp": f["a"] = -min(3.0, 1.5*tt)
                    elif scen == "A5_forged": f["a"] = -6.0; f["cred"] = False
                    if scen == "A5_forged":      # outsider packet arrives in addition to the legitimate one
                        link[3].append(dict(f, arr=t + 0.035))
                    else:                        # insider replaces its own beacon content (valid credential)
                        link[3] = [p for p in link[3] if not (p["ts"] == pk["ts"])] + ([dict(f, arr=t + rnd.uniform(0.010, 0.030))] if rnd.random() > 0.02 else [])
                if i == 2 and scen == "A4_replay" and t >= 60.0:
                    k = int((t - 60.0)/0.1) + 300 + 0           # recorded packets from vehicle 2 around the t=30 braking event
                    if k < len(rec_for_replay):
                        old = rec_for_replay[min(k, len(rec_for_replay)-1)]
                        link[3].append(dict(old, arr=t + 0.035, cred=False, replay=True))
        # ---------------- receive & trust ----------------
        for i in range(1, N):
            q = link[i]; ready = [p for p in q if p["arr"] <= t]
            if not ready: continue
            link[i] = [p for p in q if p["arr"] > t]
            for p in sorted(ready, key=lambda z: z["arr"]):
                if cfg["gate"]:
                    if (not p["cred"]) or abs(t - p["ts"]) > 0.2 or (p["src"] in revoked): continue   # hard reject
                lastp[i] = dict(p, rx=t)
                if cfg["trust"] is None: continue
                vr = radar[i][1]
                vrep = p["v"] + p["a"]*(t - p["ts"]); dv = abs(vrep - vr)
                z = 0.0; pp = prevp[i]
                zJ = zc = 0.0
                if pp is not None and 0.05 < p["ts"] - pp["ts"] < 0.35:
                    dts = p["ts"] - pp["ts"]
                    J = abs(p["a"] - pp["a"]) / dts
                    zJ = min(1.0, max(0.0, (J/J_LIM - 1)/(KAPPA - 1)))
                    if cfg.get("enhanced_checks", False):
                        arep[i].append((p["ts"], p["a"])); arep[i] = [z_ for z_ in arep[i] if z_[0] > p["ts"] - 0.5]
                        h_ = vrad_hist[i]
                        if len(h_) > 0 and arep[i]:
                            old = [z_ for z_ in h_ if z_[0] <= t - 0.5]
                            if old:
                                a_rad = (vr - old[-1][1]) / (t - old[-1][0]); am = sum(z_[1] for z_ in arep[i])/len(arep[i])
                                if abs(am - a_rad) < 0.7: zJ = 0.0
                        a_from_v = (p["v"] - pp["v"]) / dts; inc = abs(p["a"] - a_from_v)
                        zc = min(1.0, max(0.0, (inc/1.2 - 1)/(KAPPA - 1)))
                zV = min(1.0, max(0.0, (dv/DV_LIM - 1)/(KAPPA - 1)))
                z = max(zJ, zV, zc)
                prevp[i] = p
                S[i] = max(z, RHO*S[i]) if cfg["trust"] == "graded" else S[i]
                if cfg["trust"] == "binary" and (z >= 0.1): viol_time[i] = t
                if cfg["trust"] == "graded":
                    w[i] = w_of_S(S[i]); 
                    if i == 3 or scen.startswith("L"): minw = min(minw, w[i])
                    if i == 3 and t >= T_ATK and first_det is None and S[i] > 0.5: first_det = t
                    if cfg.get("revoke"):
                        if w[i] <= 0.2:
                            if lowt[i] == 0.0: lowt[i] = t
                            if t - lowt[i] >= 1.0 and p["src"] not in rev_pending: rev_pending[p["src"]] = t + 1.0
                        else: lowt[i] = 0.0
        for srcid, tt in list(rev_pending.items()):
            if t >= tt and srcid not in revoked: revoked.add(srcid); rev_time = rev_time or t
        # ---------------- sensing & control ----------------
        if step % 5 == 0:
            for i in range(1, N):
                gap = x[i-1] - x[i] - VL + rnd.gauss(0, 0.05); vrr = v[i-1] + rnd.gauss(0, 0.05)
                radar[i] = (gap, vrr); vrad_hist[i].append((t, vrr)); vrad_hist[i] = [z_ for z_ in vrad_hist[i] if z_[0] > t - 1.0]
        a_leader = leader_profile(t, scen); u[0] = a_leader
        for i in range(1, N):
            gap, vrr = radar[i]
            lp = lastp[i]; stale = (lp is None) or (t - lp["rx"] > T_STALE)
            mode = cfg["trust"]
            if mode is None: wi = 1.0; h = H_NOM
            elif mode == "binary":
                latched = (t - viol_time[i]) < 5.0
                wi = 0.0 if (latched or stale) else 1.0
                h = (H_FAIL if cfg["hfail"] else H_NOM) if wi == 0.0 else H_NOM
                if stale: h = H_FAIL
            else:
                wi = 0.0 if stale else w[i]
                h_t = (H_NOM + (1 - wi)*(H_FAIL - H_NOM)) if cfg["dynh"] else H_NOM
                if stale: h_t = H_FAIL if cfg["dynh"] else H_NOM
                hs_ = hstate[i]; step_ = SLEW*DT
                hstate[i] = hs_ + max(-step_, min(step_, h_t - hs_)); h = hstate[i]
            if mode is None and lp is None: wi = 0.0
            d_t = D0 + h*v[i]
            e = gap - d_t; ed = vrr - v[i] - h*a[i]
            a_acc = KP*e + KD*ed
            a_ff = 0.0
            if lp is not None and wi > 0.0:
                a_ff = KFF*(lp["a"] - 0.0)                      # predecessor's reported acceleration (feed-forward)
            cmd = a_acc + wi*a_ff; weff[i] = wi
            ttc = gap/max(1e-3, v[i]-vrr) if v[i] > vrr else 1e9
            emergency = (ttc < 2.0) or (gap < 4.0)
            if not emergency:
                cmd = max(u_prev[i] - JERK_LIM*DT, min(u_prev[i] + JERK_LIM*DT, cmd))
            cmd = max(A_MIN, min(A_MAX, cmd)); u_prev[i] = cmd; u[i] = cmd
        # ---------------- dynamics ----------------
        for i in range(N):
            a_new = a[i] + DT*(u[i] - a[i])/TAU if i > 0 else u[i]
            jerk = abs(a_new - a[i])/DT
            a[i] = a_new; v[i] = max(0.0, v[i] + a[i]*DT); x[i] += v[i]*DT
            if i > 0 and t >= tm:
                res["peak_jerk"] = max(res["peak_jerk"], jerk)
                res["peak_decel"] = max(res["peak_decel"], -a[i])
        if trace and step % 10 == 0: tr.append((t, x[2]-x[3]-VL, v[3], weff[3], x[0]-x[1]-VL, v[0], hstate[3], weff[1], v[1]))
        if t >= tm:
            for i in range(1, N):
                g = x[i-1] - x[i] - VL
                res["min_gap"] = min(res["min_gap"], g)
                if g <= 0: res["collision"] = True
                res["vmin"] = min(res["vmin"], v[i])
            if step % 10 == 0 and t >= max(30.0, tm): res["headway"].append(sum((x[i-1]-x[i]-VL)/max(v[i], 1.0) for i in range(3, 8))/5)
    hw = res.pop("headway"); res["mean_headway"] = sum(hw)/len(hw) if hw else 0.0
    res["first_det"] = (first_det - T_ATK) if first_det else None
    res["rev"] = (rev_time - T_ATK) if rev_time else None
    res["minw"] = minw
    if trace: res["trace"] = tr
    return res
if __name__ == "__main__":
    import sys, time, json
    t0 = time.time()
    for scen in ("L1_normal", "A1_false_brake"):
        for c in ("D0_none", "D2b_binary_hfail", "CA_full"):
            r = run(c, scen, 1); print(scen, c, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    print("elapsed", time.time() - t0)
