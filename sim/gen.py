import os
import json, math, statistics as st, sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
R=json.load(open(os.path.join(BASE_DIR, "..", "results", "sim_results.json")))
N=json.load(open(os.path.join(BASE_DIR, "..", "results", "native_results.json")))
OUT=os.path.join(BASE_DIR, "..", "paper") + os.sep
SC=["L1_normal","L2_legit_brake","L3_moderate_brake","A1_false_brake","A2_false_accel","A3_stealth_ramp","A4_replay","A5_forged"]
SH=["L1","L2","L3","A1","A2","A3","A4","A5"]
VAR=[("D0_none","No protection"),("D1_crypto","Crypto gate only"),("D2_binary_hnom","Binary, $h_{\\rm nom}$"),("D2b_binary_hfail","Binary, $h_{\\rm fail}$"),("CA_full","CyberAdapt"),("CA_norevoke","\\quad w/o revocation"),("CA_fixedh","\\quad w/o dyn.\\ headway")]
M=lambda sc,v: R["main"][f"{sc}|{v}"]
mean=lambda sc,v,k: st.mean(r[k] for r in M(sc,v))
coll=lambda sc,v: sum(r["collision"] for r in M(sc,v))
def cnt(sc,v,k): return sum(r[k] is not None for r in M(sc,v))
def fmt(x): return (f"{x:.1f}" if x>=0 else f"$-${abs(x):.1f}")
# ---- tables
def cell(sc,v):
    c=coll(sc,v); return fmt(mean(sc,v,"min_gap"))+(f" [{c}]" if c else "")
L=["\\begin{table*}[!t]\\centering\\caption{Mean minimum inter-vehicle gap (m) over 20 seeds; brackets give the number of runs (out of 20) with a collision. L: legitimate scenarios, A: attacks.}\\label{tab:gap}\\small\\setlength{\\tabcolsep}{4pt}\\begin{tabular}{l"+"c"*8+"}\\toprule","Defence & "+" & ".join(SH)+"\\\\\\midrule"]
for v,n in VAR: L.append(n+" & "+" & ".join(cell(sc,v) for sc in SC)+"\\\\")
L.append("\\bottomrule\\end{tabular}\\end{table*}"); open(OUT+"tab_gap.tex","w").write("\n".join(L))
cs=["L1_normal","L2_legit_brake","L3_moderate_brake","A1_false_brake","A2_false_accel","A3_stealth_ramp"]
L=["\\begin{table}[!t]\\centering\\caption{Mean time gap (s) of vehicles 3--7 after $t=30$\\,s (platoon efficiency; lower is better). Scenarios with a collision are marked $^\\dagger$.}\\label{tab:hw}\\footnotesize\\setlength{\\tabcolsep}{2.5pt}\\begin{tabular}{l"+"c"*6+"}\\toprule","Defence & "+" & ".join(["L1","L2","L3","A1","A2","A3"])+"\\\\\\midrule"]
for v,n in VAR: L.append(n+" & "+" & ".join(f"{mean(sc,v,'mean_headway'):.2f}"+("$^\\dagger$" if coll(sc,v) else "") for sc in cs)+"\\\\")
L.append("\\bottomrule\\end{tabular}\\end{table}"); open(OUT+"tab_hw.tex","w").write("\n".join(L))
def dr(sc,v):
    fd=[r["first_det"] for r in M(sc,v) if r["first_det"] is not None]; rv=[r["rev"] for r in M(sc,v) if r["rev"] is not None]
    return (f"{st.mean(fd):.2f}\\,s ({len(fd)}/20)" if fd else "--"),(f"{st.mean(rv):.1f}\\,s ({len(rv)}/20)" if rv else "--")
L=["\\begin{table}[!t]\\centering\\caption{Detection delay ($S>0.5$ at the receiver of the attacked sender, measured from $t=20$\\,s) and trust-triggered revocation time (same origin). Counts give runs out of 20. In L2 and L3 nothing is attacked, so any entry is a false alarm; the braking starts at $t=30$\\,s, i.e.\\ 10\\,s on this scale.}\\label{tab:det}\\footnotesize\\setlength{\\tabcolsep}{2pt}\\begin{tabular}{llcc}\\toprule","Scenario & Variant & Detection & Revocation\\\\\\midrule"]
for sc,sh in (("A1_false_brake","A1"),("A2_false_accel","A2"),("A3_stealth_ramp","A3"),("L2_legit_brake","L2"),("L3_moderate_brake","L3")):
    for v,n in (("CA_full","CyberAdapt"),):
        d,r_=dr(sc,v); L.append(f"{sh} & {n} & {d} & {r_}\\\\")
L.append("\\bottomrule\\end{tabular}\\end{table}"); open(OUT+"tab_det.tex","w").write("\n".join(L))
J=lambda j,sc: R["jsweep"][f"{j}|{sc}"]
L=["\\begin{table}[!t]\\centering\\caption{Sensitivity to the jerk limit $J_{\\rm lim}$ (CyberAdapt, 20 seeds). Min $w$ is the mean over seeds of the lowest weight seen anywhere in the platoon; Coll.: runs with a collision; Rev.: runs in which the legitimate leader was revoked.}\\label{tab:jsweep}\\footnotesize\\setlength{\\tabcolsep}{2pt}\\begin{tabular}{rcccccc}\\toprule","$J_{\\rm lim}$ & L1 min $w$ & L2 min $w$ & L2 coll./rev. & L3 min $w$ & L3 rev. & A1 detected\\\\\\midrule"]
for j in ("3.0","6.0","10.0","15.0"):
    f=lambda sc,k: st.mean(r[k] for r in J(j,sc))
    rv=lambda sc: sum(r["rev"] is not None for r in J(j,sc))
    L.append(f"{float(j):.0f} & {min(r['minw'] for r in J(j,'L1_normal')):.2f} & {f('L2_legit_brake','minw'):.2f} & {sum(r['collision'] for r in J(j,'L2_legit_brake'))}/{rv('L2_legit_brake')} & {f('L3_moderate_brake','minw'):.2f} & {rv('L3_moderate_brake')}/20 & {sum(r['first_det'] is not None for r in J(j,'A1_false_brake'))}/20\\\\")
L.append("\\bottomrule\\end{tabular}\\end{table}"); open(OUT+"tab_j.tex","w").write("\n".join(L))
# ---- number macros
D={}
def put(name,val): D[name]=val
for sc,t in (("L1_normal","Lone"),("L2_legit_brake","Ltwo"),("L3_moderate_brake","Lthree"),("A1_false_brake","Aone"),("A2_false_accel","Atwo"),("A3_stealth_ramp","Athree"),("A4_replay","Afour"),("A5_forged","Afive")):
    for v,vt in (("D0_none","Dzero"),("D1_crypto","Done"),("D2_binary_hnom","Dtwo"),("D2b_binary_hfail","Dtwob"),("CA_full","CA"),("CA_norevoke","CAnr"),("CA_fixedh","CAfh")):
        put(f"gap{t}{vt}",fmt(mean(sc,v,"min_gap")).replace("$-$","$-$")); put(f"coll{t}{vt}",str(coll(sc,v))); put(f"vmin{t}{vt}",f"{mean(sc,v,'vmin'):.1f}"); put(f"hw{t}{vt}",f"{mean(sc,v,'mean_headway'):.2f}"); put(f"revn{t}{vt}",str(cnt(sc,v,"rev"))); put(f"minw{t}{vt}",f"{mean(sc,v,'minw'):.2f}")
        rv=[r["rev"] for r in M(sc,v) if r["rev"] is not None]; put(f"revt{t}{vt}",f"{st.mean(rv):.1f}" if rv else "--")
        fd=[r["first_det"] for r in M(sc,v) if r["first_det"] is not None]; put(f"det{t}{vt}",f"{st.mean(fd):.2f}" if fd else "--")
put("LoneCAminwAll",f"{min(r['minw'] for r in M('L1_normal','CA_full')):.2f}")
fa=[r["vmin"] for r in M("L1_normal","D2b_binary_hfail") if r["vmin"]<11]; put("LoneBinFalseRuns",str(len(fa))); put("LoneBinFalseVmin",f"{min(fa):.1f}--{max(fa):.1f}" if fa else "--")
# native crypto
for k,v in N.items():
    if isinstance(v,(int,float)) and not isinstance(v,bool): put("nat"+"".join(c for c in k.title().replace("_","") if c.isalpha()),f"{v:.2f}" if abs(v)>=1 else f"{v:.3f}")
put("natSpeedupSmbp",f"{N['naive_us']/N['smbp_w1_us']:.2f}"); put("natSpeedupFixedVsVar",f"{N['dalek_var_us']/N['dalek_fixed_us']:.1f}"); put("natSpeedupFixedVsNaive",f"{N['naive_us']/N['dalek_fixed_us']:.1f}")
put("natVerifyPerSecond",f"{1e6/N['zk_verify_us']:.0f}"); put("natClaimRatio",f"{N['zk_verify_us']/7.3:.1f}")
put("natBloomFp",f"{N['bloom_fp']}"); put("natBloomRate",f"{N['bloom_fp']/N['bloom_queries']*1e5:.2f}"); put("natBloomTheory",f"{N['bloom_theory']*1e5:.2f}")
with open(OUT+"nums.tex","w") as f:
    for k,v in D.items(): f.write("\\newcommand{\\%s}{%s}\n"%(k,v))
print(len(D),"macros")
# ---- figures
plt.rcParams.update({"font.family":"serif","font.size":7.5,"axes.linewidth":0.6,"lines.linewidth":1.0,"legend.fontsize":6.5,"legend.frameon":False})
S=np.linspace(0,1,200); a,b=8,0.45; w=np.clip((1+math.exp(-a*b))/(1+np.exp(a*(S-b))),0.05,1)
fig,ax=plt.subplots(1,2,figsize=(3.5,1.7))
ax[0].plot(S,w,color="#1b4f9c"); ax[0].set_xlabel("anomaly score $S$"); ax[0].set_ylabel("trust weight $w$"); ax[0].axhline(0.05,ls=":",c="grey",lw=0.6); ax[0].set_ylim(0,1.05)
ww=np.linspace(0,1,100); ax[1].plot(ww,0.6+(1-ww)*1.0,color="#d95f02"); ax[1].set_xlabel("trust weight $w$"); ax[1].set_ylabel("headway $h$ (s)"); ax[1].set_ylim(0.5,1.7)
plt.tight_layout(pad=0.4); plt.savefig(OUT+"figs/mapping.pdf"); plt.close()
import sim
col={"D0_none":"#7f7f7f","D2_binary_hnom":"#d95f02","D2b_binary_hfail":"#d95f02","CA_full":"#1b4f9c"}
lab={"D0_none":"No protection","D2_binary_hnom":"Binary switch","D2b_binary_hfail":"Binary switch","CA_full":"CyberAdapt"}
def panel(scen,vs,idx,fn,xlim,shade=None,ylab=("gap","speed","w")):
    fig,ax=plt.subplots(3,1,figsize=(3.5,3.6),sharex=True)
    for v in vs:
        tr=sim.run(v,scen,1,trace=True)["trace"]; t=[r[0] for r in tr]
        ax[0].plot(t,[r[idx[0]] for r in tr],color=col[v],label=lab[v]); ax[1].plot(t,[r[idx[1]] for r in tr],color=col[v]); ax[2].plot(t,[r[idx[2]] for r in tr],color=col[v])
    ax[0].set_ylabel(ylab[0]); ax[1].set_ylabel(ylab[1]); ax[2].set_ylabel(ylab[2]); ax[2].set_xlabel("time (s)"); ax[0].set_xlim(*xlim); ax[0].legend(loc="best")
    for a_ in ax:
        if shade: a_.axvspan(*shade,color="#fde0dd",lw=0)
        else: a_.axvline(20,ls=":",c="k",lw=0.6)
    ax[0].axhline(0,c="k",lw=0.5)
    plt.tight_layout(pad=0.4); plt.savefig(OUT+"figs/"+fn); plt.close()
panel("A2_false_accel",("D0_none","D2b_binary_hfail","CA_full"),(1,2,3),"a2.pdf",(0,60),None,("gap 2$\\to$3 (m)","speed of veh. 3 (m/s)","effective $w$"))
panel("L3_moderate_brake",("D0_none","D2_binary_hnom","CA_full"),(4,8,7),"l3.pdf",(20,60),(30,32.4),("gap 0$\\to$1 (m)","speed of veh. 1 (m/s)","effective $w$ (veh. 1)"))
