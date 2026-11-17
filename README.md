# CyberAdapt Final

This is the consolidated, runnable CyberAdapt evaluation package. It combines the current seven-configuration simulator, the Ristretto255 Rust cryptographic prototype, regenerated results, the manuscript sources, and a local browser dashboard. The old v1 demonstration is deliberately not included.

## Start the dashboard (Windows)

1. Install Python 3.10 or later.
2. Double-click `START_DASHBOARD.bat`, or run:

   ```powershell
   python dashboard\server.py
   ```

3. Open `http://127.0.0.1:8765`.

The dashboard is local-only and uses Python's standard library. You can explore the included results without installing dependencies. Running the simulator also uses only Python's standard library. Regenerating the manuscript plots/tables requires NumPy and Matplotlib; install `sim\requirements.txt` if the dashboard reports that the generator could not run. Native cryptographic benchmarks require Rust/Cargo and the pinned crate dependencies.

## Dashboard functions

- Inspect the 8 scenarios, 7 defense configurations, 20 seeds, and jerk-limit sensitivity results.
- Compare minimum gaps, collisions, detection/revocation counts, speed, and time gaps.
- Run selected scenarios, the complete simulation suite, or the native Rust cryptographic checks.
- View job progress and logs, download the scenario report, and export a CSV summary.

The complete 8-scenario suite plus four jerk sweeps is CPU-intensive and takes substantially longer than a single scenario. The page shows progress; it can remain open while the local process runs.

## Reproduce from a terminal

```powershell
python sim\runpart.py L1_normal L2_legit_brake L3_moderate_brake A1_false_brake A2_false_accel A3_stealth_ramp A4_replay A5_forged J3.0 J6.0 J10.0 J15.0
python sim\report.py
python sim\gen.py
```

For the cryptographic prototype, run `cargo run --release` from `native\`. Its self-checks and benchmark are separate from the platoon simulation.

Run the dashboard/data API regression checks with:

```powershell
python -m unittest discover -s tests -v
```

## What is implemented

1. **SMBP fixed-base multiplication and Bloom revocation filter** in the native Rust prototype.
2. **ZK telemetry token and roadside-issued pseudonym certificate** in the native Rust prototype.
3. **Epoch-scoped policy tags** with SHA-256 and HMAC options in the native Rust prototype.
4. **Trust score** with leaky-maximum anomaly fusion and shifted sigmoid weight in the simulator.
5. **Cyber-physical checks and graded control**: radar corroboration, acceleration/speed consistency, radar-speed residual, actuator blending, jerk limiting, and trust-triggered revocation in the simulator.
6. **Trust-dependent headway** and stale-packet fallback in the simulator.

## Scope and limitations

- The selected MA-ABSE-AR paper is the motivating base paper, not the implementation delivered here. CyberAdapt is a complementary authenticated telemetry and control prototype; it does **not** implement multi-authority attribute-based searchable encryption.
- The Rust gate and the custom Python platoon simulator are tested separately. The simulator represents credential decisions with flags; it does not call the Rust gate.
- The simulator is not SUMO/Veins and is not a real-vehicle deployment, formal verification, or a safety certification.
- The default jerk-plausibility limit is 10 m/s³, the lowest tested sweep setting with no L2 false revocations or collisions across the 20 bundled seeds. A1, A2, and A3 detection is retained in those seeds. This calibration uses the scripted evaluation scenarios; independent, out-of-sample validation remains needed.
- Do not interpret the A2 or L2 results as a general collision-prevention guarantee.

See `results\scenario_results.md`, `paper\paper.tex`, and `REPO_REVIEW.md` for measured outcomes and prior-project limitations.
