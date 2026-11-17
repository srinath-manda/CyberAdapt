import os
import sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim
part = sys.argv[1:]
f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "sim_results.json")
out = json.load(open(f)) if os.path.exists(f) else {"main": {}, "jsweep": {}}
VAR = list(sim.CFG.keys()); SEEDS = list(range(1, 21)); t0 = time.time()
default_j_lim = sim.J_LIM
out["main"] = {key: value for key, value in out.get("main", {}).items()
               if key.split("|")[-1] in VAR}
for sc in part:
    if sc.startswith("J"):
        J = float(sc[1:]); sim.J_LIM = J
        for s2 in ("L1_normal", "L2_legit_brake", "L3_moderate_brake", "A1_false_brake", "A3_stealth_ramp"):
            out["jsweep"][f"{J}|{s2}"] = [sim.run("CA_full", s2, s) for s in SEEDS]
        sim.J_LIM = default_j_lim
    else:
        for v in VAR: out["main"][f"{sc}|{v}"] = [sim.run(v, sc, s) for s in SEEDS]
    json.dump(out, open(f, "w")); print(sc, "done", round(time.time() - t0), flush=True)
