//! Native benchmark and security tests for the CyberAdapt cryptographic gate.
//! Real Ristretto255 arithmetic from curve25519-dalek (constant-time library code).
use curve25519_dalek::constants::{RISTRETTO_BASEPOINT_POINT, RISTRETTO_BASEPOINT_TABLE};
use curve25519_dalek::ristretto::{CompressedRistretto, RistrettoBasepointTable, RistrettoPoint};
use curve25519_dalek::scalar::Scalar;
use curve25519_dalek::traits::VartimeMultiscalarMul;
use hmac::{Hmac, Mac};
use rand::rngs::OsRng;
use rand::RngCore;
use sha2::{Digest, Sha256, Sha512};
use std::hint::black_box;
use std::time::Instant;

fn bench<F: FnMut()>(n: usize, mut f: F) -> (f64, f64) {
    for _ in 0..(n / 10).max(5) { f(); }
    let mut t = Vec::with_capacity(n);
    for _ in 0..n { let s = Instant::now(); f(); t.push(s.elapsed().as_secs_f64() * 1e6); }
    t.sort_by(|a, b| a.partial_cmp(b).unwrap());
    (t.iter().sum::<f64>() / n as f64, t[(n as f64 * 0.95) as usize - 1])
}
fn hs(parts: &[&[u8]]) -> Scalar {
    let mut h = Sha512::new();
    for p in parts { h.update((p.len() as u32).to_be_bytes()); h.update(p); }
    Scalar::from_hash(h)
}
struct Ctx { g: RistrettoPoint, h: RistrettoPoint, tg: &'static RistrettoBasepointTable, th: RistrettoBasepointTable }
fn challenge(c: &Ctx, cb: &[u8], rb: &[u8], ctx: &[u8]) -> Scalar {
    hs(&[b"CyberAdapt/ZK-TAT/v1", c.g.compress().as_bytes(), c.h.compress().as_bytes(), cb, rb, ctx])
}
type Token = ([u8; 32], Scalar, Scalar, Scalar);
fn prove(c: &Ctx, vid: &Scalar, r: &Scalar, ctx: &[u8], nonces: Option<(Scalar, Scalar)>) -> Token {
    let cc = (r * c.tg) + (vid * &c.th);
    let (k1, k2) = nonces.unwrap_or_else(|| (Scalar::random(&mut OsRng), Scalar::random(&mut OsRng)));
    let rr = (&k1 * c.tg) + (&k2 * &c.th);
    let cb = cc.compress().to_bytes();
    let e = challenge(c, &cb, rr.compress().as_bytes(), ctx);
    (cb, e, k1 + e * r, k2 + e * vid)
}
fn verify(c: &Ctx, t: &Token, ctx: &[u8]) -> bool {
    let cp = match CompressedRistretto(t.0).decompress() { Some(p) => p, None => return false };
    let rp = RistrettoPoint::vartime_multiscalar_mul([t.2, t.3, -t.1], [c.g, c.h, cp]);
    challenge(c, &t.0, rp.compress().as_bytes(), ctx) == t.1
}
fn cert_msg(cb: &[u8; 32], validity: &[u8]) -> Vec<u8> { let mut m = cb.to_vec(); m.extend_from_slice(validity); m }
fn issue(c: &Ctx, x: &Scalar, pk: &RistrettoPoint, cb: &[u8; 32], validity: &[u8]) -> (CompressedRistretto, Scalar) {
    let k = Scalar::random(&mut OsRng); let rc = (&k * c.tg).compress();
    let ch = hs(&[b"CERT", rc.as_bytes(), pk.compress().as_bytes(), &cert_msg(cb, validity)]);
    (rc, k + ch * x)
}
fn cert_ok(c: &Ctx, pk: &RistrettoPoint, cb: &[u8; 32], validity: &[u8], cert: &(CompressedRistretto, Scalar)) -> bool {
    let rc = match cert.0.decompress() { Some(p) => p, None => return false };
    let ch = hs(&[b"CERT", cert.0.as_bytes(), pk.compress().as_bytes(), &cert_msg(cb, validity)]);
    RistrettoPoint::vartime_multiscalar_mul([cert.1, -ch], [c.g, *pk]) == rc
}
fn naive_mul(k: &Scalar, p: &RistrettoPoint) -> RistrettoPoint {      // double-and-add; doubling = unified addition
    let b = k.to_bytes(); let mut acc = RistrettoPoint::default(); let mut first = true;
    for i in (0..253).rev() {
        if !first { acc = acc + acc; }
        if (b[i / 8] >> (i % 8)) & 1 == 1 { acc = if first { *p } else { acc + p }; first = false; }
    }
    acc
}
fn hpo_sha(attr: &[u8], epoch: u32, secret: &[u8; 32]) -> [u8; 32] {
    let mut h = Sha256::new(); h.update(b"HPO_SALT_V1"); h.update((attr.len() as u16).to_be_bytes()); h.update(attr); h.update(epoch.to_be_bytes()); h.update(secret);
    h.finalize().into()
}
fn hpo_hmac(attr: &[u8], epoch: u32, secret: &[u8; 32]) -> [u8; 32] {
    let mut m = <Hmac<Sha256> as Mac>::new_from_slice(secret).unwrap(); m.update(b"HPO_V2"); m.update(&(attr.len() as u16).to_be_bytes()); m.update(attr); m.update(&epoch.to_be_bytes());
    m.finalize().into_bytes().into()
}
fn ct_eq(a: &[u8; 32], b: &[u8; 32]) -> bool { let mut d = 0u8; for i in 0..32 { d |= a[i] ^ b[i]; } d == 0 }
const M: usize = 32768; const K: usize = 4;
fn probes(x: &[u8]) -> [usize; K] {
    let h: [u8; 32] = Sha256::digest(x).into();
    let a = u64::from_be_bytes(h[0..8].try_into().unwrap()); let b = u64::from_be_bytes(h[8..16].try_into().unwrap()) | 1;
    let mut o = [0usize; K]; for i in 0..K { o[i] = (a.wrapping_add((i as u64).wrapping_mul(b)) % M as u64) as usize; } o
}
fn main() {
    let g = RISTRETTO_BASEPOINT_POINT;
    let h = RistrettoPoint::hash_from_bytes::<Sha512>(b"CyberAdapt/ZK-TAT/H/v1");
    let c = Ctx { g, h, tg: RISTRETTO_BASEPOINT_TABLE, th: RistrettoBasepointTable::create(&h) };
    let ks: Vec<Scalar> = (0..256).map(|_| Scalar::random(&mut OsRng)).collect();
    let mut idx = 0usize; let mut nk = || { idx = (idx + 1) % 256; ks[idx] };
    // ---- E1 scalar multiplication
    let mut tab = vec![g]; for i in 1..253 { let p = tab[i - 1]; tab.push(p + p); }
    let smbp = |k: &Scalar| { let b = k.to_bytes(); let mut acc = RistrettoPoint::default(); for i in 0..253 { if (b[i / 8] >> (i % 8)) & 1 == 1 { acc += tab[i]; } } acc };
    for k in ks.iter().take(20) { assert_eq!(smbp(k), k * g); assert_eq!(naive_mul(k, &g), k * g); }
    let n = 3000;
    let (naive, naive95) = bench(n, || { black_box(naive_mul(&nk(), &g)); });
    let (smbp_t, smbp95) = bench(n, || { black_box(smbp(&nk())); });
    let (dvar, dvar95) = bench(n, || { black_box(nk() * g); });
    let (dfix, dfix95) = bench(n, || { black_box(&nk() * c.tg); });
    // ---- E2 ZK-TAT
    let x = Scalar::random(&mut OsRng); let pk = &x * c.tg;
    let vid = hs(&[b"vehicle-identity", b"VIN-0001"]); let r = Scalar::random(&mut OsRng);
    let ctx = Sha256::digest(b"telemetry|ts|seq|tag").to_vec();
    let tok = prove(&c, &vid, &r, &ctx, None); let validity = b"epoch-0001".to_vec();
    let cert = issue(&c, &x, &pk, &tok.0, &validity);
    assert!(verify(&c, &tok, &ctx) && cert_ok(&c, &pk, &tok.0, &validity, &cert));
    let (tp, tp95) = bench(n, || { black_box(prove(&c, &vid, &r, &ctx, None)); });
    let (tv, tv95) = bench(n, || { black_box(verify(&c, &tok, &ctx)); });
    let (cv, cv95) = bench(n, || { black_box(cert_ok(&c, &pk, &tok.0, &validity, &cert)); });
    let (ci, _) = bench(n, || { black_box(issue(&c, &x, &pk, &tok.0, &validity)); });
    // negative tests
    let nn = 300usize; let mut acc = [0usize; 5];
    let mut rng = OsRng;
    for _ in 0..nn {
        let mut t = tok.clone(); t.0[(rng.next_u32() % 32) as usize] ^= 1 << (rng.next_u32() % 8); acc[0] += verify(&c, &t, &ctx) as usize;
        let mut t = tok.clone(); t.1 += Scalar::random(&mut OsRng); acc[1] += verify(&c, &t, &ctx) as usize;
        let mut t = tok.clone(); t.2 += Scalar::random(&mut OsRng); acc[2] += verify(&c, &t, &ctx) as usize;
        let mut t = tok.clone(); t.3 += Scalar::random(&mut OsRng); acc[3] += verify(&c, &t, &ctx) as usize;
        let mut cx = ctx.clone(); cx[(rng.next_u32() % 32) as usize] ^= 1 << (rng.next_u32() % 8); acc[4] += verify(&c, &tok, &cx) as usize;
    }
    let (n1, n2) = (Scalar::random(&mut OsRng), Scalar::random(&mut OsRng));
    let ta = prove(&c, &vid, &r, b"A", Some((n1, n2))); let tb = prove(&c, &vid, &r, b"B", Some((n1, n2)));
    let r_rec = (ta.2 - tb.2) * (ta.1 - tb.1).invert(); let nonce_reuse_recovers = r_rec == r;
    let (vx, rx) = (Scalar::random(&mut OsRng), Scalar::random(&mut OsRng)); let tokx = prove(&c, &vx, &rx, &ctx, None);
    let forged_proof_only = verify(&c, &tokx, &ctx); let forged_with_cert = cert_ok(&c, &pk, &tokx.0, &validity, &cert);
    // ---- H-PO
    let mut sec = [0u8; 32]; OsRng.fill_bytes(&mut sec);
    let attrs: Vec<Vec<u8>> = (0..16).map(|i| format!("ATTR_{}", i).into_bytes()).collect();
    let tag = hpo_hmac(&attrs[15], 7, &sec);
    let (h1, _) = bench(200000, || { black_box(hpo_sha(b"HAZMAT_CARGO", 7, &sec)); });
    let (h2, _) = bench(200000, || { black_box(hpo_hmac(b"HAZMAT_CARGO", 7, &sec)); });
    let (m16, _) = bench(50000, || { let mut f = false; for a in &attrs { f |= ct_eq(&tag, &hpo_hmac(a, 7, &sec)); } black_box(f); });
    // ---- Bloom
    let mut bits = vec![0u8; M / 8];
    for i in 0..500 { for p in probes(format!("REVOKED-{}", i).as_bytes()) { bits[p >> 3] |= 1 << (p & 7); } }
    let q = |x: &[u8]| probes(x).iter().all(|&p| (bits[p >> 3] >> (p & 7)) & 1 == 1);
    let qn = 2_000_000usize; let mut fp = 0usize; for i in 0..qn { if q(format!("VEH-{}", i).as_bytes()) { fp += 1; } }
    let (bq, _) = bench(200000, || { black_box(q(b"VEH-12345")); });
    let theory = (1.0 - (-((K * 500) as f64) / M as f64).exp()).powi(K as i32);
    println!("{{\n \"naive_us\":{naive:.3},\"naive_p95\":{naive95:.3},\"smbp_w1_us\":{smbp_t:.3},\"smbp_p95\":{smbp95:.3},\"dalek_var_us\":{dvar:.3},\"dalek_var_p95\":{dvar95:.3},\"dalek_fixed_us\":{dfix:.3},\"dalek_fixed_p95\":{dfix95:.3},\n \"zk_prove_us\":{tp:.3},\"zk_prove_p95\":{tp95:.3},\"zk_verify_us\":{tv:.3},\"zk_verify_p95\":{tv95:.3},\"cert_verify_us\":{cv:.3},\"cert_verify_p95\":{cv95:.3},\"cert_issue_us\":{ci:.3},\n \"neg_C\":{},\"neg_e\":{},\"neg_s1\":{},\"neg_s2\":{},\"neg_ctx\":{},\"neg_n\":{nn},\"nonce_reuse_recovers\":{nonce_reuse_recovers},\"forged_proof_only\":{forged_proof_only},\"forged_with_cert\":{forged_with_cert},\n \"hpo_sha_us\":{h1:.4},\"hpo_hmac_us\":{h2:.4},\"hpo_match16_us\":{m16:.3},\n \"bloom_query_us\":{bq:.4},\"bloom_fp\":{fp},\"bloom_queries\":{qn},\"bloom_theory\":{theory:.6e},\"bloom_bytes\":{}\n}}", acc[0], acc[1], acc[2], acc[3], acc[4], M / 8);
}
