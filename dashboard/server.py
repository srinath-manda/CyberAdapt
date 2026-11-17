import argparse
import csv
import functools
import http.server
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "dashboard"
SIM = ROOT / "sim"
NATIVE = ROOT / "native"
RESULTS = ROOT / "results"
SCENARIOS = [
    "L1_normal",
    "L2_legit_brake",
    "L3_moderate_brake",
    "A1_false_brake",
    "A2_false_accel",
    "A3_stealth_ramp",
    "A4_replay",
    "A5_forged",
]
JERK_SWEEPS = ["J3.0", "J6.0", "J10.0", "J15.0"]
VARIANTS = [
    ("D0_none", "No protection"),
    ("D1_crypto", "Crypto gate only"),
    ("D1_ma_abse_ar", "MA-ABSE-AR baseline"),
    ("D2_binary_hnom", "Binary switch · nominal headway"),
    ("D2b_binary_hfail", "Binary switch · fail-safe headway"),
    ("CA_full", "CyberAdapt"),
    ("CA_norevoke", "CyberAdapt · no revocation"),
    ("CA_fixedh", "CyberAdapt · fixed headway"),
]
SCENARIO_LABELS = {
    "L1_normal": "L1 · Normal driving",
    "L2_legit_brake": "L2 · Severe legitimate braking",
    "L3_moderate_brake": "L3 · Moderate legitimate braking",
    "A1_false_brake": "A1 · False braking",
    "A2_false_accel": "A2 · False acceleration",
    "A3_stealth_ramp": "A3 · Stealth acceleration ramp",
    "A4_replay": "A4 · Replay",
    "A5_forged": "A5 · Forged outsider packets",
}
STATE_LOCK = threading.RLock()
JOB = {
    "id": None,
    "kind": None,
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "args": [],
    "step": 0,
    "total": 0,
    "step_name": "",
    "exit_code": None,
    "message": "",
    "log_path": None,
    "process": None,
}
LOG_DIR = ROOT / "run_logs"
LOG_DIR.mkdir(exist_ok=True)

# ── Live-run shared state ─────────────────────────────────────────────────────
_SIM_DIR = Path(__file__).resolve().parent.parent / "sim"
if str(_SIM_DIR) not in sys.path:
    sys.path.insert(0, str(_SIM_DIR))

try:
    from sim_integrated import run_live as _run_live, CFG as _SIM_CFG
    _SIM_INTEGRATED_AVAILABLE = True
except ImportError:
    _SIM_INTEGRATED_AVAILABLE = False
    _run_live = None
    _SIM_CFG = {}

LIVE_LOCK = threading.Lock()

_LIVE_JOB = {
    "status": "idle",        # idle | running | completed | failed
    "mode": None,            # "live" | "compare"
    "cfg": None,
    "scenario": None,
    "seed": None,
    "attack_active": False,
    "state_snapshot": None,  # latest state dict from sim generator
    "compare_snapshot": None,# {"ma": state, "ca": state} for compare mode
    "crypto_log": [],        # list of last 20 PacketLogEntry dicts
    "stop_flag": threading.Event(),
    "inject_flag": threading.Event(),
    "error": None,
    "gap_divergence_t": None,
}

KNOWN_LIVE_CONFIGS = [
    "D0_none", "D1_crypto", "D1_ma_abse_ar", "D2_binary_hnom",
    "D2b_binary_hfail", "CA_full", "CA_norevoke", "CA_fixedh",
]


def load_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def summarize_rows(rows):
    if not rows:
        return None
    gaps = [float(row["min_gap"]) for row in rows]
    detections = [row for row in rows if row.get("first_det") is not None]
    revocations = [row for row in rows if row.get("rev") is not None]
    return {
        "runs": len(rows),
        "collisions": sum(bool(row["collision"]) for row in rows),
        "mean_min_gap": sum(gaps) / len(gaps),
        "std_min_gap": (
            (sum((gap - sum(gaps) / len(gaps)) ** 2 for gap in gaps) / (len(gaps) - 1)) ** 0.5
            if len(gaps) > 1
            else 0.0
        ),
        "mean_vmin": sum(float(row["vmin"]) for row in rows) / len(rows),
        "mean_headway": sum(float(row["mean_headway"]) for row in rows) / len(rows),
        "detections": len(detections),
        "mean_detection_delay": (
            sum(float(row["first_det"]) for row in detections) / len(detections)
            if detections
            else None
        ),
        "revocations": len(revocations),
        "mean_revocation_delay": (
            sum(float(row["rev"]) for row in revocations) / len(revocations)
            if revocations
            else None
        ),
        "mean_min_weight": sum(float(row["minw"]) for row in rows) / len(rows),
    }


def read_dashboard_data():
    # Prefer sim_integrated_results.json when available
    integrated_path = RESULTS / "sim_integrated_results.json"
    if integrated_path.exists():
        try:
            result_data = load_json(integrated_path, None)
            if not result_data:
                result_data = load_json(RESULTS / "sim_results.json", {"main": {}, "jsweep": {}})
        except Exception:
            result_data = load_json(RESULTS / "sim_results.json", {"main": {}, "jsweep": {}})
    else:
        result_data = load_json(RESULTS / "sim_results.json", {"main": {}, "jsweep": {}})

    result_path = RESULTS / "sim_results.json"

    main = result_data.get("main", {})
    jsweep = result_data.get("jsweep", {})
    scenarios = {}
    for scenario in SCENARIOS:
        scenarios[scenario] = {}
        for variant, _ in VARIANTS:
            scenarios[scenario][variant] = summarize_rows(
                main.get(f"{scenario}|{variant}", [])
            )
    sweep_data = {}
    for jerk in ("3.0", "6.0", "10.0", "15.0"):
        sweep_data[jerk] = {}
        for scenario in ("L1_normal", "L2_legit_brake", "L3_moderate_brake", "A1_false_brake", "A3_stealth_ramp"):
            rows = jsweep.get(f"{jerk}|{scenario}", [])
            sweep_data[jerk][scenario] = summarize_rows(rows)

    native = load_json(RESULTS / "native_results.json", {})
    native.update(load_json(RESULTS / "crypto_results.json", {}))

    # Determine generated_at from whichever results file was used
    gen_at = None
    if integrated_path.exists():
        try:
            gen_at = datetime.fromtimestamp(integrated_path.stat().st_mtime).isoformat(timespec="seconds")
        except OSError:
            pass
    if gen_at is None and result_path.exists():
        try:
            gen_at = datetime.fromtimestamp(result_path.stat().st_mtime).isoformat(timespec="seconds")
        except OSError:
            pass

    return {
        "scenarios": scenarios,
        "scenario_labels": SCENARIO_LABELS,
        "scenario_ids": SCENARIOS,
        "variants": [{"id": key, "label": label} for key, label in VARIANTS],
        "jerk_sweeps": sweep_data,
        "native": native,
        "generated_at": gen_at,
        "result_groups": sum(bool(scenarios[s][v]) for s in scenarios for v, _ in VARIANTS),
    }


def make_csv():
    data = read_dashboard_data()
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "scenario",
            "defense",
            "runs",
            "collisions",
            "mean_min_gap_m",
            "std_min_gap_m",
            "mean_min_speed_mps",
            "mean_time_gap_s",
            "detections",
            "mean_detection_delay_s",
            "revocations",
            "mean_revocation_delay_s",
            "mean_min_weight",
        ]
    )
    for scenario in SCENARIOS:
        for variant, label in VARIANTS:
            row = data["scenarios"][scenario][variant]
            if not row:
                continue
            writer.writerow(
                [
                    scenario,
                    label,
                    row["runs"],
                    row["collisions"],
                    f'{row["mean_min_gap"]:.5f}',
                    f'{row["std_min_gap"]:.5f}',
                    f'{row["mean_vmin"]:.5f}',
                    f'{row["mean_headway"]:.5f}',
                    row["detections"],
                    "" if row["mean_detection_delay"] is None else f'{row["mean_detection_delay"]:.5f}',
                    row["revocations"],
                    "" if row["mean_revocation_delay"] is None else f'{row["mean_revocation_delay"]:.5f}',
                    f'{row["mean_min_weight"]:.5f}',
                ]
            )
    return output.getvalue().encode("utf-8")


def job_snapshot():
    with STATE_LOCK:
        process = JOB.get("process")
        status = JOB["status"]
        log_path = JOB.get("log_path")
        snapshot = {key: value for key, value in JOB.items() if key != "process"}
        if status == "running" and process is not None:
            code = process.poll()
            if code is not None:
                snapshot["status"] = "finishing"
        if log_path:
            try:
                with open(log_path, "rb") as log:
                    log.seek(max(0, os.path.getsize(log_path) - 12000))
                    text = log.read().decode("utf-8", errors="replace")
                snapshot["output"] = text
                matches = re.findall(r"^(\S+) done \d+", text, re.MULTILINE)
                snapshot["step"] = min(len(matches), snapshot["total"])
                if matches:
                    snapshot["step_name"] = matches[-1]
            except OSError:
                snapshot["output"] = ""
        else:
            snapshot["output"] = ""
        snapshot["progress"] = (
            snapshot["step"] / snapshot["total"] if snapshot["total"] else 0.0
        )
        return snapshot


def run_logged(argv, cwd, log):
    with open(log, "a", encoding="utf-8") as output:
        output.write("\n$ " + subprocess.list2cmdline([str(arg) for arg in argv]) + "\n")
        output.flush()
        process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
        )
        with STATE_LOCK:
            JOB["process"] = process
        return process.wait()


def job_worker(job_id, kind, args, log_path):
    try:
        if kind == "simulation":
            code = run_logged(
                [sys.executable, "-u", str(SIM / "runpart.py"), *args], SIM, log_path
            )
            if code:
                raise RuntimeError(f"Experiment runner exited with code {code}.")
            code = run_logged(
                [sys.executable, "-u", str(SIM / "report.py")], SIM, log_path
            )
            if code:
                raise RuntimeError(f"Scenario report generation exited with code {code}.")
            code = run_logged([sys.executable, "-u", str(SIM / "gen.py")], SIM, log_path)
            if code:
                raise RuntimeError(
                    "Results were saved, but paper artifact generation failed. "
                    "Install sim\\requirements.txt and rerun `python sim\\gen.py`."
                )
            message = "Experiment results, report, tables, and plots regenerated."
        else:
            code = run_logged(["cargo", "run", "--release"], NATIVE, log_path)
            if code:
                raise RuntimeError(f"Cargo cryptographic checks exited with code {code}.")
            text = Path(log_path).read_text(encoding="utf-8", errors="replace")
            match = re.search(r'(\{\s*"naive_us".*?\n\})', text, re.DOTALL)
            if match:
                metrics = json.loads(match.group(1))
                (RESULTS / "native_results.json").write_text(
                    json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
                )
                code = run_logged([sys.executable, "-u", str(SIM / "gen.py")], SIM, log_path)
                if code:
                    raise RuntimeError("Crypto checks passed, but paper artifact generation failed.")
                message = "Native Rust self-checks passed; crypto metrics and paper outputs updated."
            else:
                message = "Native Rust checks completed; benchmark JSON was not found in output."
        with STATE_LOCK:
            if JOB["id"] == job_id:
                JOB.update(
                    status="completed",
                    finished_at=time.time(),
                    exit_code=0,
                    message=message,
                    process=None,
                )
    except Exception as error:
        with STATE_LOCK:
            if JOB["id"] == job_id:
                JOB.update(
                    status="failed",
                    finished_at=time.time(),
                    exit_code=1,
                    message=str(error),
                    process=None,
                )


def start_job(kind, args):
    with STATE_LOCK:
        if JOB["status"] == "running":
            return None, "A job is already running."
        job_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = str(LOG_DIR / f"{job_id}-{kind}.log")
        Path(log_path).write_text("", encoding="utf-8")
        total = len(args) if kind == "simulation" else 1
        JOB.update(
            id=job_id,
            kind=kind,
            status="running",
            started_at=time.time(),
            finished_at=None,
            args=args,
            step=0,
            total=total,
            step_name="Starting",
            exit_code=None,
            message="",
            log_path=log_path,
            process=None,
        )
        worker = threading.Thread(
            target=job_worker,
            args=(job_id, kind, args, log_path),
            daemon=True,
        )
        worker.start()
        return job_snapshot(), None


def validate_run_request(payload):
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    selected = payload.get("scenarios")
    sweeps = payload.get("jerk_sweeps", [])
    if not isinstance(selected, list) or not isinstance(sweeps, list):
        raise ValueError("Provide scenario and jerk_sweeps arrays.")
    if len(selected) + len(sweeps) == 0:
        raise ValueError("Select at least one scenario or jerk sweep.")
    if any(item not in SCENARIOS for item in selected):
        raise ValueError("One or more scenario IDs are not supported.")
    if any(item not in JERK_SWEEPS for item in sweeps):
        raise ValueError("One or more jerk sweeps are not supported.")
    return list(dict.fromkeys(selected + sweeps))


# ── Live-run helpers ──────────────────────────────────────────────────────────

def _live_job_snapshot():
    with LIVE_LOCK:
        return {
            "status": _LIVE_JOB["status"],
            "mode": _LIVE_JOB["mode"],
            "cfg": _LIVE_JOB["cfg"],
            "scenario": _LIVE_JOB["scenario"],
            "seed": _LIVE_JOB["seed"],
            "attack_active": _LIVE_JOB["attack_active"],
            "error": _LIVE_JOB["error"],
        }


def _live_run_worker(cfg, scenario, seed):
    """Background thread: runs run_live() generator, writes state to _LIVE_JOB."""
    try:
        stop = _LIVE_JOB["stop_flag"]
        inject = _LIVE_JOB["inject_flag"]
        gen = _run_live(cfg, scenario, seed, inject, stop)
        for state in gen:
            if stop.is_set():
                break
            with LIVE_LOCK:
                _LIVE_JOB["state_snapshot"] = state
                _LIVE_JOB["attack_active"] = state.get("attack_active", False)
                # Update crypto log (keep last 20 entries)
                for entry in state.get("last_crypto", []):
                    _LIVE_JOB["crypto_log"].append(entry)
                    if len(_LIVE_JOB["crypto_log"]) > 20:
                        _LIVE_JOB["crypto_log"] = _LIVE_JOB["crypto_log"][-20:]
        with LIVE_LOCK:
            _LIVE_JOB["status"] = "completed"
    except Exception as e:
        with LIVE_LOCK:
            _LIVE_JOB["status"] = "failed"
            _LIVE_JOB["error"] = str(e)


def _compare_run_worker(cfg_key, scenario, seed, snapshot_key):
    """One of two threads in comparison mode."""
    try:
        stop = _LIVE_JOB["stop_flag"]
        inject = _LIVE_JOB["inject_flag"]
        gen = _run_live(cfg_key, scenario, seed, inject, stop)
        for state in gen:
            if stop.is_set():
                break
            with LIVE_LOCK:
                if _LIVE_JOB["compare_snapshot"] is None:
                    _LIVE_JOB["compare_snapshot"] = {}
                _LIVE_JOB["compare_snapshot"][snapshot_key] = state
                # Check gap divergence (only computed from MA side)
                if snapshot_key == "ma" and _LIVE_JOB["gap_divergence_t"] is None:
                    ma_gaps = state.get("gap", [1e9])
                    ca_snap = (_LIVE_JOB["compare_snapshot"] or {}).get("ca", {})
                    ca_gaps = ca_snap.get("gap", [1e9]) if ca_snap else [1e9]
                    if min(ma_gaps) <= 0 and min(ca_gaps) > 2.0:
                        _LIVE_JOB["gap_divergence_t"] = state["t"]
    except Exception:
        pass


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    server_version = "CyberAdaptDashboard/1.0"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def request_is_local(self, require_origin=False):
        port = self.server.server_port
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host", "") not in allowed_hosts:
            return False
        origin = self.headers.get("Origin")
        if require_origin and origin:
            parsed = urllib.parse.urlparse(origin)
            if parsed.scheme != "http" or parsed.netloc not in allowed_hosts:
                return False
        return True

    def send_bytes(self, status, payload, content_type, download_name=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if download_name:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{download_name}"'
            )
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
            "base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, status, payload):
        self.send_bytes(
            status,
            json.dumps(payload).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def do_GET(self):
        if not self.request_is_local():
            self.send_error(403, "Use the localhost dashboard URL.")
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/data":
            self.send_json(200, read_dashboard_data())
            return
        if parsed.path == "/api/status":
            self.send_json(200, job_snapshot())
            return
        if parsed.path == "/api/export.csv":
            self.send_bytes(
                200,
                make_csv(),
                "text/csv; charset=utf-8",
                download_name="cyberadapt-results.csv",
            )
            return
        if parsed.path == "/downloads/scenario_results.md":
            self.send_bytes(
                200,
                (RESULTS / "scenario_results.md").read_bytes(),
                "text/markdown; charset=utf-8",
            )
            return
        if parsed.path == "/downloads/paper.tex":
            self.send_bytes(
                200,
                (ROOT / "paper" / "paper.tex").read_bytes(),
                "text/plain; charset=utf-8",
            )
            return
        if parsed.path == "/api/stream":
            # SSE endpoint — streams live-run state to the browser
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                with LIVE_LOCK:
                    status = _LIVE_JOB["status"]
                if status == "idle":
                    self.wfile.write(b'data: {"event":"idle"}\n\n')
                    self.wfile.flush()
                    return

                gap_div_emitted = False
                while True:
                    time.sleep(0.1)
                    with LIVE_LOCK:
                        status = _LIVE_JOB["status"]
                        mode = _LIVE_JOB["mode"]
                        snap = _LIVE_JOB["state_snapshot"]
                        comp = _LIVE_JOB["compare_snapshot"]
                        attack_active = _LIVE_JOB["attack_active"]
                        gap_div_t = _LIVE_JOB["gap_divergence_t"]
                        cfg_name = _LIVE_JOB["cfg"]
                        error = _LIVE_JOB["error"]
                        crypto_log = list(_LIVE_JOB["crypto_log"])

                    # Emit gap divergence event once (compare mode)
                    if gap_div_t is not None and not gap_div_emitted:
                        msg = json.dumps({"event": "gap_divergence", "t": gap_div_t})
                        self.wfile.write(f"data: {msg}\n\n".encode())
                        self.wfile.flush()
                        gap_div_emitted = True

                    if mode == "compare" and comp:
                        frame = {
                            "mode": "compare",
                            "ma": comp.get("ma"),
                            "ca": comp.get("ca"),
                            "attack_active": attack_active,
                        }
                        self.wfile.write(f"data: {json.dumps(frame)}\n\n".encode())
                        self.wfile.flush()
                    elif snap:
                        frame = dict(snap)
                        frame["last_crypto"] = crypto_log
                        self.wfile.write(f"data: {json.dumps(frame)}\n\n".encode())
                        self.wfile.flush()

                    if status in ("completed", "failed"):
                        done_msg = {"event": "done", "cfg": cfg_name or ""}
                        if error:
                            done_msg["error"] = error
                        self.wfile.write(f"data: {json.dumps(done_msg)}\n\n".encode())
                        self.wfile.flush()
                        return
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
            return

        rel = "index.html" if parsed.path in ("", "/") else parsed.path.lstrip("/")
        target = (DASHBOARD / urllib.parse.unquote(rel)).resolve()
        if not target.is_relative_to(DASHBOARD.resolve()) or not target.is_file():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        self.send_bytes(200, target.read_bytes(), content_type)

    def do_POST(self):
        if not self.request_is_local(require_origin=True):
            self.send_error(403, "Local dashboard requests only.")
            return
        path = urllib.parse.urlparse(self.path).path

        # ── Live-run endpoints ────────────────────────────────────────────────
        if path == "/api/live":
            if not _SIM_INTEGRATED_AVAILABLE:
                self.send_json(503, {"error": "sim_integrated not available."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("Body too large or empty.")
                payload = json.loads(self.rfile.read(length))
            except (ValueError, json.JSONDecodeError):
                self.send_json(400, {"error": "Invalid JSON body."})
                return
            scenario = payload.get("scenario", "")
            cfg_id = payload.get("cfg", "")
            seed = payload.get("seed", 1)
            if scenario not in SCENARIOS:
                self.send_json(400, {"error": "Unknown scenario ID."})
                return
            if cfg_id not in KNOWN_LIVE_CONFIGS:
                self.send_json(400, {"error": "Unknown configuration ID."})
                return
            if not isinstance(seed, int) or not (1 <= seed <= 20):
                self.send_json(400, {"error": "Seed must be an integer between 1 and 20."})
                return
            with LIVE_LOCK:
                if _LIVE_JOB["status"] == "running":
                    self.send_json(409, {"error": "A live run is already in progress."})
                    return
                _LIVE_JOB.update(
                    status="running", mode="live", cfg=cfg_id,
                    scenario=scenario, seed=seed, attack_active=False,
                    state_snapshot=None, compare_snapshot=None,
                    crypto_log=[], error=None, gap_divergence_t=None,
                )
                _LIVE_JOB["stop_flag"].clear()
                _LIVE_JOB["inject_flag"].clear()
            t = threading.Thread(
                target=_live_run_worker, args=(cfg_id, scenario, seed), daemon=True
            )
            t.start()
            self.send_json(202, _live_job_snapshot())
            return

        if path == "/api/compare":
            if not _SIM_INTEGRATED_AVAILABLE:
                self.send_json(503, {"error": "sim_integrated not available."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError()
                payload = json.loads(self.rfile.read(length))
            except (ValueError, json.JSONDecodeError):
                self.send_json(400, {"error": "Invalid JSON body."})
                return
            scenario = payload.get("scenario", "")
            seed = payload.get("seed", 1)
            if scenario not in SCENARIOS:
                self.send_json(400, {"error": "Unknown scenario ID."})
                return
            if not isinstance(seed, int):
                self.send_json(400, {"error": "Invalid seed."})
                return
            with LIVE_LOCK:
                if _LIVE_JOB["status"] == "running":
                    self.send_json(409, {"error": "A live run is already in progress."})
                    return
                _LIVE_JOB.update(
                    status="running", mode="compare", cfg="compare",
                    scenario=scenario, seed=seed, attack_active=False,
                    state_snapshot=None, compare_snapshot={},
                    crypto_log=[], error=None, gap_divergence_t=None,
                )
                _LIVE_JOB["stop_flag"].clear()
                _LIVE_JOB["inject_flag"].clear()
            t_ma = threading.Thread(
                target=_compare_run_worker, args=("D1_ma_abse_ar", scenario, seed, "ma"), daemon=True
            )
            t_ca = threading.Thread(
                target=_compare_run_worker, args=("CA_full", scenario, seed, "ca"), daemon=True
            )
            t_ma.start()
            t_ca.start()

            def _watch():
                t_ma.join()
                t_ca.join()
                with LIVE_LOCK:
                    if _LIVE_JOB["status"] == "running":
                        _LIVE_JOB["status"] = "completed"

            threading.Thread(target=_watch, daemon=True).start()
            self.send_json(202, _live_job_snapshot())
            return

        if path == "/api/inject":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length)) if length > 0 else {}
            except Exception:
                payload = {}
            with LIVE_LOCK:
                if _LIVE_JOB["status"] != "running":
                    self.send_json(400, {"error": "No live run is active."})
                    return
                _LIVE_JOB["inject_flag"].set()
                _LIVE_JOB["attack_active"] = True
            self.send_json(200, {"ok": True, "attack": "A1_false_brake"})
            return

        if path == "/api/stop":
            with LIVE_LOCK:
                _LIVE_JOB["stop_flag"].set()
                if _LIVE_JOB["status"] == "running":
                    _LIVE_JOB["status"] = "completed"
            self.send_json(200, {"ok": True})
            return

        # ── Existing batch-run endpoints ──────────────────────────────────────
        if path not in ("/api/run", "/api/native"):
            self.send_json(404, {"error": "Unknown API route."})
            return
        if path == "/api/native":
            snapshot, error = start_job("native", [])
        else:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("Request body must be between 1 and 8192 bytes.")
                payload = json.loads(self.rfile.read(length))
                args = validate_run_request(payload)
                snapshot, error = start_job("simulation", args)
            except (ValueError, json.JSONDecodeError, TypeError) as error:
                self.send_json(400, {"error": str(error)})
                return
        if error:
            self.send_json(409, {"error": error})
            return
        self.send_json(202, snapshot)


def main():
    parser = argparse.ArgumentParser(description="Run the local CyberAdapt dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: localhost only).")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.host != "127.0.0.1":
        parser.error("The dashboard is intended for local use; bind only to 127.0.0.1.")
    server = http.server.ThreadingHTTPServer(
        (args.host, args.port), functools.partial(DashboardHandler)
    )
    print(f"CyberAdapt dashboard: http://127.0.0.1:{server.server_port}")
    print("Press Ctrl+C to stop the dashboard.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
