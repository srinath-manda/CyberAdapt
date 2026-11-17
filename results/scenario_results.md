# CyberAdapt simulation results

Generated from `sim_results.json`. Each defense/scenario cell summarizes 20 seeds of the custom eight-vehicle simulator; results are not SUMO or real-road validation.

The unified CyberAdapt variants use radar-corroborated jerk evidence and reported-acceleration/speed consistency checks. `CA_norevoke` and `CA_fixedh` disable revocation and dynamic headway respectively. The simulator models credential acceptance with flags; it does not invoke the native Rust gate.

The default jerk limit is 10 m/s^3, the lowest swept value with no L2 false revocations or collisions while retaining detection in A1 and A3. This was selected using the scripted scenarios in this evaluation; it is not an out-of-sample safety threshold.

A negative minimum gap denotes vehicle overlap in this model. Mean minimum gap is shown with sample standard deviation; collision counts are out of 20. Minimum speed and mean time gap are averages over seeds. Detection/revocation show event counts.

## L1_normal

Normal driving with the leader sinusoid.

| Defense | Collisions | Mean min gap (m) | Mean min speed (m/s) | Mean time gap (s) | Detection/revocation |
|---|---:|---:|---:|---:|---:|
| No protection | 0/20 | 10.21 +/- 0.03 | 13.05 | 0.78 | 0/0 |
| Crypto gate only | 0/20 | 10.21 +/- 0.03 | 13.05 | 0.78 | 0/0 |
| Binary switch, nominal headway | 0/20 | 10.21 +/- 0.03 | 13.05 | 0.78 | 0/0 |
| Binary switch, fail-safe headway | 0/20 | 10.21 +/- 0.03 | 13.05 | 0.78 | 0/0 |
| CyberAdapt | 0/20 | 10.21 +/- 0.03 | 13.05 | 0.78 | 0/0 |
| CyberAdapt without revocation | 0/20 | 10.21 +/- 0.03 | 13.05 | 0.78 | 0/0 |
| CyberAdapt without dynamic headway | 0/20 | 10.21 +/- 0.03 | 13.05 | 0.78 | 0/0 |

## L2_legit_brake

Severe legitimate leader braking, reaching -6 m/s^2.

| Defense | Collisions | Mean min gap (m) | Mean min speed (m/s) | Mean time gap (s) | Detection/revocation |
|---|---:|---:|---:|---:|---:|
| No protection | 0/20 | 1.26 +/- 0.06 | 2.67 | 0.85 | 0/0 |
| Crypto gate only | 0/20 | 1.26 +/- 0.06 | 2.67 | 0.85 | 0/0 |
| Binary switch, nominal headway | 20/20 | -4.25 +/- 0.02 | 1.76 | 0.86 | 0/0 |
| Binary switch, fail-safe headway | 20/20 | -4.07 +/- 0.03 | 1.75 | 0.86 | 0/0 |
| CyberAdapt | 0/20 | 1.19 +/- 0.11 | 2.66 | 0.85 | 0/0 |
| CyberAdapt without revocation | 0/20 | 1.19 +/- 0.11 | 2.66 | 0.85 | 0/0 |
| CyberAdapt without dynamic headway | 0/20 | 1.21 +/- 0.09 | 2.66 | 0.85 | 0/0 |

## L3_moderate_brake

Moderate legitimate leader braking, reaching -3.5 m/s^2.

| Defense | Collisions | Mean min gap (m) | Mean min speed (m/s) | Mean time gap (s) | Detection/revocation |
|---|---:|---:|---:|---:|---:|
| No protection | 0/20 | 6.29 +/- 0.03 | 6.88 | 0.81 | 0/0 |
| Crypto gate only | 0/20 | 6.29 +/- 0.03 | 6.88 | 0.81 | 0/0 |
| Binary switch, nominal headway | 0/20 | 6.29 +/- 0.03 | 6.88 | 0.81 | 0/0 |
| Binary switch, fail-safe headway | 0/20 | 6.29 +/- 0.03 | 6.88 | 0.81 | 0/0 |
| CyberAdapt | 0/20 | 6.29 +/- 0.03 | 6.88 | 0.81 | 0/0 |
| CyberAdapt without revocation | 0/20 | 6.29 +/- 0.03 | 6.88 | 0.81 | 0/0 |
| CyberAdapt without dynamic headway | 0/20 | 6.29 +/- 0.03 | 6.88 | 0.81 | 0/0 |

## A1_false_brake

Insider reports false -6 m/s^2 acceleration.

| Defense | Collisions | Mean min gap (m) | Mean min speed (m/s) | Mean time gap (s) | Detection/revocation |
|---|---:|---:|---:|---:|---:|
| No protection | 0/20 | 8.17 +/- 0.06 | 9.16 | 1.21 | 0/0 |
| Crypto gate only | 0/20 | 8.17 +/- 0.06 | 9.16 | 1.21 | 0/0 |
| Binary switch, nominal headway | 0/20 | 8.60 +/- 0.06 | 9.99 | 1.21 | 0/0 |
| Binary switch, fail-safe headway | 0/20 | 9.26 +/- 0.04 | 11.15 | 1.21 | 0/0 |
| CyberAdapt | 0/20 | 10.13 +/- 0.02 | 12.68 | 0.98 | 20/20 |
| CyberAdapt without revocation | 0/20 | 10.06 +/- 0.02 | 12.54 | 0.99 | 20/0 |
| CyberAdapt without dynamic headway | 0/20 | 9.31 +/- 0.01 | 12.98 | 0.78 | 20/20 |

## A2_false_accel

Insider reports false +3 m/s^2 acceleration.

| Defense | Collisions | Mean min gap (m) | Mean min speed (m/s) | Mean time gap (s) | Detection/revocation |
|---|---:|---:|---:|---:|---:|
| No protection | 20/20 | -5.87 +/- 0.02 | 12.95 | 0.56 | 0/0 |
| Crypto gate only | 20/20 | -5.87 +/- 0.02 | 12.95 | 0.56 | 0/0 |
| Binary switch, nominal headway | 20/20 | -5.92 +/- 0.02 | 12.99 | 0.56 | 0/0 |
| Binary switch, fail-safe headway | 20/20 | -5.98 +/- 0.02 | 12.17 | 0.57 | 0/0 |
| CyberAdapt | 0/20 | 9.86 +/- 0.04 | 12.35 | 0.97 | 20/20 |
| CyberAdapt without revocation | 0/20 | 10.20 +/- 0.02 | 13.01 | 0.86 | 20/0 |
| CyberAdapt without dynamic headway | 0/20 | 6.48 +/- 0.33 | 12.57 | 0.77 | 20/20 |

## A3_stealth_ramp

Insider ramps reported acceleration while reporting truthful speed.

| Defense | Collisions | Mean min gap (m) | Mean min speed (m/s) | Mean time gap (s) | Detection/revocation |
|---|---:|---:|---:|---:|---:|
| No protection | 0/20 | 9.73 +/- 0.03 | 11.81 | 0.99 | 0/0 |
| Crypto gate only | 0/20 | 9.73 +/- 0.03 | 11.81 | 0.99 | 0/0 |
| Binary switch, nominal headway | 0/20 | 9.73 +/- 0.03 | 11.81 | 0.99 | 0/0 |
| Binary switch, fail-safe headway | 0/20 | 9.73 +/- 0.03 | 11.81 | 0.99 | 0/0 |
| CyberAdapt | 0/20 | 10.09 +/- 0.03 | 12.64 | 0.98 | 20/20 |
| CyberAdapt without revocation | 0/20 | 10.09 +/- 0.03 | 12.64 | 0.98 | 20/0 |
| CyberAdapt without dynamic headway | 0/20 | 9.29 +/- 0.03 | 12.91 | 0.78 | 20/20 |

## A4_replay

Recorded braking packets are replayed; metrics begin at t=55 s.

| Defense | Collisions | Mean min gap (m) | Mean min speed (m/s) | Mean time gap (s) | Detection/revocation |
|---|---:|---:|---:|---:|---:|
| No protection | 0/20 | 5.65 +/- 0.05 | 11.43 | 0.77 | 0/0 |
| Crypto gate only | 0/20 | 10.30 +/- 0.03 | 12.62 | 0.78 | 0/0 |
| Binary switch, nominal headway | 0/20 | 10.33 +/- 0.03 | 12.65 | 0.78 | 0/0 |
| Binary switch, fail-safe headway | 0/20 | 10.21 +/- 0.17 | 12.40 | 0.78 | 0/0 |
| CyberAdapt | 0/20 | 10.30 +/- 0.03 | 12.62 | 0.78 | 0/0 |
| CyberAdapt without revocation | 0/20 | 10.30 +/- 0.03 | 12.62 | 0.78 | 0/0 |
| CyberAdapt without dynamic headway | 0/20 | 10.30 +/- 0.03 | 12.62 | 0.78 | 0/0 |

## A5_forged

Outsider injects packets without valid credentials.

| Defense | Collisions | Mean min gap (m) | Mean min speed (m/s) | Mean time gap (s) | Detection/revocation |
|---|---:|---:|---:|---:|---:|
| No protection | 0/20 | 8.27 +/- 0.05 | 9.24 | 1.21 | 0/0 |
| Crypto gate only | 0/20 | 10.21 +/- 0.03 | 13.05 | 0.78 | 0/0 |
| Binary switch, nominal headway | 0/20 | 10.21 +/- 0.03 | 13.05 | 0.78 | 0/0 |
| Binary switch, fail-safe headway | 0/20 | 10.21 +/- 0.03 | 13.05 | 0.78 | 0/0 |
| CyberAdapt | 0/20 | 10.21 +/- 0.03 | 13.05 | 0.78 | 0/0 |
| CyberAdapt without revocation | 0/20 | 10.21 +/- 0.03 | 13.05 | 0.78 | 0/0 |
| CyberAdapt without dynamic headway | 0/20 | 10.21 +/- 0.03 | 13.05 | 0.78 | 0/0 |

## Jerk-limit sensitivity

| J limit (m/s^3) | L2 min weight | L2 collisions/revocations | L3 min weight | L3 revocations | A1 detected |
|---:|---:|---:|---:|---:|---:|
| 3 | 0.58 | 6/8 | 0.99 | 0/20 | 20/20 |
| 6 | 0.77 | 4/0 | 1.00 | 0/20 | 20/20 |
| 10 | 0.97 | 0/0 | 1.00 | 0/20 | 20/20 |
| 15 | 1.00 | 0/0 | 1.00 | 0/20 | 20/20 |
