import json
import statistics
from pathlib import Path

BASE = Path(__file__).resolve().parent
RESULTS = BASE.parent / "results"
INPUT = RESULTS / "sim_results.json"
OUTPUT = RESULTS / "scenario_results.md"

SCENARIOS = [
    ("L1_normal", "Normal driving with the leader sinusoid."),
    ("L2_legit_brake", "Severe legitimate leader braking, reaching -6 m/s^2."),
    ("L3_moderate_brake", "Moderate legitimate leader braking, reaching -3.5 m/s^2."),
    ("A1_false_brake", "Insider reports false -6 m/s^2 acceleration."),
    ("A2_false_accel", "Insider reports false +3 m/s^2 acceleration."),
    ("A3_stealth_ramp", "Insider ramps reported acceleration while reporting truthful speed."),
    ("A4_replay", "Recorded braking packets are replayed; metrics begin at t=55 s."),
    ("A5_forged", "Outsider injects packets without valid credentials."),
]
VARIANTS = [
    ("D0_none", "No protection"),
    ("D1_crypto", "Crypto gate only"),
    ("D2_binary_hnom", "Binary switch, nominal headway"),
    ("D2b_binary_hfail", "Binary switch, fail-safe headway"),
    ("CA_full", "CyberAdapt"),
    ("CA_norevoke", "CyberAdapt without revocation"),
    ("CA_fixedh", "CyberAdapt without dynamic headway"),
]


def mean(rows, key):
    return statistics.mean(row[key] for row in rows)


def generate_report():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    lines = [
        "# CyberAdapt simulation results",
        "",
        "Generated from `sim_results.json`. Each defense/scenario cell summarizes 20 seeds of the custom eight-vehicle simulator; results are not SUMO or real-road validation.",
        "",
        "The unified CyberAdapt variants use radar-corroborated jerk evidence and reported-acceleration/speed consistency checks. `CA_norevoke` and `CA_fixedh` disable revocation and dynamic headway respectively. The simulator models credential acceptance with flags; it does not invoke the native Rust gate.",
        "",
        "The default jerk limit is 10 m/s^3, the lowest swept value with no L2 false revocations or collisions while retaining detection in A1 and A3. This was selected using the scripted scenarios in this evaluation; it is not an out-of-sample safety threshold.",
        "",
        "A negative minimum gap denotes vehicle overlap in this model. Mean minimum gap is shown with sample standard deviation; collision counts are out of 20. Minimum speed and mean time gap are averages over seeds. Detection/revocation show event counts.",
        "",
    ]

    for scenario, description in SCENARIOS:
        lines.extend(
            [
                f"## {scenario}",
                "",
                description,
                "",
                "| Defense | Collisions | Mean min gap (m) | Mean min speed (m/s) | Mean time gap (s) | Detection/revocation |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for variant, label in VARIANTS:
            rows = data["main"][f"{scenario}|{variant}"]
            gap_values = [row["min_gap"] for row in rows]
            collisions = sum(bool(row["collision"]) for row in rows)
            detections = sum(row["first_det"] is not None for row in rows)
            revocations = sum(row["rev"] is not None for row in rows)
            lines.append(
                f"| {label} | {collisions}/20 | "
                f"{statistics.mean(gap_values):.2f} +/- {statistics.stdev(gap_values):.2f} | "
                f"{mean(rows, 'vmin'):.2f} | {mean(rows, 'mean_headway'):.2f} | "
                f"{detections}/{revocations} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Jerk-limit sensitivity",
            "",
            "| J limit (m/s^3) | L2 min weight | L2 collisions/revocations | L3 min weight | L3 revocations | A1 detected |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for jerk in ("3.0", "6.0", "10.0", "15.0"):
        l2 = data["jsweep"][f"{jerk}|L2_legit_brake"]
        l3 = data["jsweep"][f"{jerk}|L3_moderate_brake"]
        a1 = data["jsweep"][f"{jerk}|A1_false_brake"]
        collisions = sum(bool(row["collision"]) for row in l2)
        revocations = sum(row["rev"] is not None for row in l2)
        l3_revocations = sum(row["rev"] is not None for row in l3)
        a1_detections = sum(row["first_det"] is not None for row in a1)
        lines.append(
            f"| {float(jerk):.0f} | {mean(l2, 'minw'):.2f} | "
            f"{collisions}/{revocations} | {mean(l3, 'minw'):.2f} | "
            f"{l3_revocations}/20 | {a1_detections}/20 |"
        )

    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    generate_report()
