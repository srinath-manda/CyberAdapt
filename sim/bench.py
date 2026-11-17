import sys, time, json, hashlib, hmac, os, random, statistics, math
sys.path.insert(0, "/tmp/ca")
from ed25519 import *
random.seed(20261031)
def sc(): return random.randrange(1, L)
def hs(*parts):
    h = hashlib.sha256()
    for p in parts: h.update(len(p).to_bytes(4, "big")); h.update(p)
    return int.from_bytes(h.digest(), "big") % L
def bench(fn, n):
    ts = []
    for _ in range(n):
        t = time.perf_counter(); fn(); ts.append(time.perf_counter() - t)
    ts.sort(); return {"mean_us": 1e6*statistics.mean(ts), "p95_us": 1e6*ts[int(0.95*n)-1], "n": n}
R = {}
# ---------- E1: fixed-base scalar multiplication ----------
ks = [sc() for _ in range(300)]
reset(); [smul_var(k, G) for k in ks[:50]]; c_var = dict(CNT); reset()
var = bench(lambda: smul_var(random.choice(ks), G), 150)
R["smul_var"] = {**var, "dbl_per_op": c_var["dbl"]/50, "add_per_op": c_var["add"]/50}
R["fixed"] = {}
for w in (1, 2, 4, 8):
    t0 = time.perf_counter(); fb = FixedBase(G, w); setup = time.perf_counter() - t0
    reset(); [fb.mul(k) for k in ks[:50]]; c = dict(CNT); reset()
    b = bench(lambda: fb.mul(random.choice(ks)), 150)
    pts = sum(len(r) - 1 for r in fb.tab)
    R["fixed"][w] = {**b, "add_per_op": c["add"]/50, "dbl_per_op": 0, "setup_s": setup, "stored_points": pts,
                     "mem_compressed_KiB": pts*32/1024, "mem_affine_KiB": pts*64/1024, "mem_extended_KiB": pts*128/1024,
                     "speedup_vs_var": var["mean_us"]/b["mean_us"],
                     "opcount_speedup": (c_var["dbl"]+c_var["add"])/50/(c["add"]/50)}
# compressed w=1 table: decompress every used entry
fb1 = FixedBase(G, 1); ctab = [compress(fb1.tab[i][1]) for i in range(len(fb1.tab))]
def mul_compressed(k):
    r = IDENT
    for i in range(len(ctab)):
        if (k >> i) & 1: r = add(r, decompress(ctab[i]))
    return r
for k in ks[:20]: assert eq(mul_compressed(k), smul_var(k, G))
R["fixed_w1_compressed"] = bench(lambda: mul_compressed(random.choice(ks)), 100)
R["fixed_w1_compressed"]["speedup_vs_var"] = var["mean_us"]/R["fixed_w1_compressed"]["mean_us"]
# ---------- E2: ZK-TAT with RSU-certified pseudonym ----------
fbG, fbH = FixedBase(G, 1), FixedBase(H, 1)
xI = sc(); pkI = fbG.mul(xI); pkIb = compress(pkI)
def Hs(*a): return hs(b"CyberAdapt/ZK-TAT/v1", compress(G), compress(H), *a)
def issue(Cb, validity):
    k = sc(); Rc = compress(fbG.mul(k)); c = hs(b"CERT", Rc, pkIb, Cb, validity)
    return Rc, (k + c*xI) % L
def cert_ok(Cb, validity, cert):
    Rc, s = cert
    try: Rp = decompress(Rc)
    except Exception: return False
    c = hs(b"CERT", Rc, pkIb, Cb, validity)
    return eq(add(fbG.mul(s), neg(smul_var(c, pkI))), Rp)
def prove(VID, r, ctx, nonces=None):
    C = add(fbG.mul(r), fbH.mul(VID)); Cb = compress(C)
    k1, k2 = nonces if nonces else (sc(), sc())
    Rb = compress(add(fbG.mul(k1), fbH.mul(k2)))
    e = Hs(Cb, Rb, ctx)
    return Cb, e, (k1 + e*r) % L, (k2 + e*VID) % L
def verify(tok, ctx):
    Cb, e, s1, s2 = tok
    try: C = decompress(Cb)
    except Exception: return False
    if not (0 <= e < L and 0 <= s1 < L and 0 <= s2 < L): return False
    Rp = add(add(fbG.mul(s1), fbH.mul(s2)), neg(smul_var(e, C)))
    return Hs(Cb, compress(Rp), ctx) == e
VID, r = hs(b"vehicle-identity", b"VIN-0001"), sc()
ctx = hashlib.sha256(b"telemetry|ts|seq|tag").digest()
tok = prove(VID, r, ctx); validity = b"epoch-0001"
cert = issue(tok[0], validity)
assert verify(tok, ctx) and cert_ok(tok[0], validity, cert)
R["zktat"] = {"prove": bench(lambda: prove(VID, r, ctx), 100), "verify": bench(lambda: verify(tok, ctx), 100),
              "cert_verify": bench(lambda: cert_ok(tok[0], validity, cert), 100),
              "token_bytes": 32*4, "cert_bytes": 64}
# negative tests: every mutation must fail closed
N = 300; rej = {}
def flipb(b, i): bb = bytearray(b); bb[i % 32] ^= 1 << random.randrange(8); return bytes(bb)
muts = {"C": lambda t, c: (flipb(t[0], random.randrange(32)), t[1], t[2], t[3], c),
        "e": lambda t, c: (t[0], (t[1] + random.randrange(1, L)) % L, t[2], t[3], c),
        "s1": lambda t, c: (t[0], t[1], (t[2] + random.randrange(1, L)) % L, t[3], c),
        "s2": lambda t, c: (t[0], t[1], t[2], (t[3] + random.randrange(1, L)) % L, c),
        "context": lambda t, c: (t[0], t[1], t[2], t[3], flipb(c, random.randrange(32)))}
for name, m in muts.items():
    acc = 0
    for _ in range(N):
        Cb, e, s1, s2, c2 = m(tok, ctx); acc += verify((Cb, e, s1, s2), c2)
    rej[name] = {"tested": N, "accepted": acc}
R["zktat_negative"] = rej
# unsafe nonce reuse -> key extraction
n1, n2 = sc(), sc(); ctxA, ctxB = b"A"*32, b"B"*32
tA, tB = prove(VID, r, ctxA, (n1, n2)), prove(VID, r, ctxB, (n1, n2))
r_rec = ((tA[2] - tB[2]) * pow((tA[1] - tB[1]) % L, L - 2, L)) % L
R["nonce_reuse_recovers_secret"] = (r_rec == r)
# proof-only is not authorisation: attacker with an arbitrary uncertified VID
VIDx, rx = sc(), sc(); tokx = prove(VIDx, rx, ctx)
R["forged_credential"] = {"proof_only_accepted": verify(tokx, ctx),
                          "with_certificate_accepted": cert_ok(tokx[0], validity, cert)}   # reuse a valid cert for another C -> fails
# ---------- H-PO ----------
Spl = os.urandom(32)
def hpo(attr, epoch): 
    a = attr.encode(); return hashlib.sha256(b"HPO_SALT_V1" + len(a).to_bytes(2, "big") + a + epoch.to_bytes(4, "big") + Spl).digest()
def hpo_match(tag, cands, epoch): return any(hmac.compare_digest(tag, hpo(a, epoch)) for a in cands)
attrs = ["PLATOON_LEADER", "HAZMAT_CARGO", "ROUTE_CORRIDOR_5"] + [f"ATTR_{i}" for i in range(13)]
tag = hpo("HAZMAT_CARGO", 7)
tag16 = hpo(attrs[-1], 7)
R["hpo"] = {"tag": bench(lambda: hpo("HAZMAT_CARGO", 7), 20000),
            "match_1": bench(lambda: hpo_match(tag, attrs[:1], 7), 20000),
            "match_3": bench(lambda: hpo_match(hpo(attrs[2],7), attrs[:3], 7), 20000),
            "match_16": bench(lambda: hpo_match(tag16, attrs, 7), 5000),
            "same_epoch_equal": hpo("HAZMAT_CARGO", 7) == hpo("HAZMAT_CARGO", 7),
            "next_epoch_differs": hpo("HAZMAT_CARGO", 7) != hpo("HAZMAT_CARGO", 8),
            "wrong_attr_match": hpo_match(tag, ["PLATOON_LEADER"], 7), "wrong_secret_match": hashlib.sha256(b"x").digest() == tag}
# ---------- Bloom revocation ----------
m, n, k = 32768, 500, 4
bits = bytearray(m // 8)
def probes(x):
    h = hashlib.sha256(x).digest(); a = int.from_bytes(h[:8], "big"); b = int.from_bytes(h[8:16], "big") | 1
    return [(a + i*b) % m for i in range(k)]
def badd(x):
    for p in probes(x): bits[p >> 3] |= 1 << (p & 7)
def bq(x): return all(bits[p >> 3] >> (p & 7) & 1 for p in probes(x))
for i in range(n): badd(f"REVOKED-{i}".encode())
assert all(bq(f"REVOKED-{i}".encode()) for i in range(n))
Q = 2_000_000; fp = sum(bq(f"VEH-{i}".encode()) for i in range(Q))
theo = (1 - math.exp(-k*n/m))**k
R["bloom"] = {"m": m, "n": n, "k": k, "theory_fp": theo, "queries": Q, "false_positives": fp, "empirical_fp": fp/Q,
              "query": bench(lambda: bq(b"VEH-12345"), 20000), "bytes": m//8}
json.dump(R, open("/tmp/ca/crypto_results.json", "w"), indent=1)
print(json.dumps({k: (v if not isinstance(v, dict) else {kk: (vv if not isinstance(vv, dict) else {a: round(b, 4) if isinstance(b, float) else b for a, b in vv.items()}) for kk, vv in v.items()}) for k, v in R.items()}, indent=1)[:6000])
