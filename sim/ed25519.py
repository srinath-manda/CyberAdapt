"""Minimal Edwards25519 arithmetic (reference implementation, NOT constant-time, NOT for production).
Used only to reproduce operation counts and relative costs for CyberAdapt's crypto components."""
import hashlib, os
P = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
D = (-121665 * pow(121666, P - 2, P)) % P
D2 = (2 * D) % P
I = pow(2, (P - 1) // 4, P)
CNT = {"add": 0, "dbl": 0, "dec": 0, "inv": 0}

def inv(x): CNT["inv"] += 1; return pow(x, P - 2, P)
def recover_x(y, sign):
    xx = ((y*y - 1) * inv(D*y*y + 1)) % P
    x = pow(xx, (P + 3) // 8, P)
    if (x*x - xx) % P: x = x * I % P
    if (x*x - xx) % P: return None
    if x & 1 != sign: x = P - x
    return x
def from_affine(x, y): return (x % P, y % P, 1, x * y % P)
IDENT = (0, 1, 1, 0)
def add(p, q):
    CNT["add"] += 1
    A = (p[1]-p[0]) * (q[1]-q[0]) % P; B = (p[1]+p[0]) * (q[1]+q[0]) % P
    C = p[3] * D2 * q[3] % P; Dd = 2 * p[2] * q[2] % P
    E, F, G, H = B-A, Dd-C, Dd+C, B+A
    return (E*F % P, G*H % P, F*G % P, E*H % P)
def dbl(p):
    CNT["dbl"] += 1
    A = p[0]*p[0] % P; B = p[1]*p[1] % P; C = 2*p[2]*p[2] % P
    H = A+B; E = H - (p[0]+p[1])**2; G = A-B; F = C+G
    return (E*F % P, G*H % P, F*G % P, E*H % P)
def neg(p): return ((-p[0]) % P, p[1], p[2], (-p[3]) % P)
def eq(p, q): return (p[0]*q[2]-q[0]*p[2]) % P == 0 and (p[1]*q[2]-q[1]*p[2]) % P == 0
def compress(p):
    zi = inv(p[2]); x = p[0]*zi % P; y = p[1]*zi % P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")
def decompress(b):
    CNT["dec"] += 1
    y = int.from_bytes(b, "little"); sign = y >> 255; y &= (1 << 255) - 1
    x = recover_x(y, sign)
    if x is None or y >= P: raise ValueError("bad point")
    return from_affine(x, y)
def to_affine(p):
    zi = inv(p[2]); return (p[0]*zi % P, p[1]*zi % P)
Gy = 4 * pow(5, P - 2, P) % P
G = from_affine(recover_x(Gy, 0), Gy)
def smul_var(k, pt):               # double-and-add, MSB first
    r = IDENT
    for i in range(k.bit_length() - 1, -1, -1):
        r = dbl(r)
        if (k >> i) & 1: r = add(r, pt)
    return r
class FixedBase:                    # SMBP-PreComp generalised: radix 2^w, w=1 is the slide design T[i]=2^i G
    def __init__(self, base, w=1, bits=253):
        self.w, self.nwin = w, -(-bits // w)
        self.tab = []; cur = base
        for _ in range(self.nwin):
            row = [IDENT]; acc = IDENT
            for _j in range(1, 1 << w): acc = add(acc, cur); row.append(acc)
            self.tab.append(row)
            for _ in range(w): cur = dbl(cur)
    def mul(self, k):
        r = IDENT; m = (1 << self.w) - 1
        for i in range(self.nwin):
            d = (k >> (self.w * i)) & m
            if d: r = add(r, self.tab[i][d])
        return r
def hash_to_point(tag):
    c = 0
    while True:
        h = hashlib.sha256(tag + c.to_bytes(4, "big")).digest()
        y = int.from_bytes(h, "little") & ((1 << 255) - 1)
        if y < P:
            x = recover_x(y, 0)
            if x is not None:
                pt = from_affine(x, y)
                for _ in range(3): pt = dbl(pt)       # cofactor 8
                if not eq(pt, IDENT): return pt
        c += 1
H = hash_to_point(b"CyberAdapt/ZK-TAT/H/v1")
def reset(): 
    for k in CNT: CNT[k] = 0
