import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))
import server


class DashboardDataTests(unittest.TestCase):
    def test_summary_aggregates_seed_outcomes(self):
        rows = [
            {
                "min_gap": -1.0,
                "collision": True,
                "vmin": 4.0,
                "mean_headway": 0.8,
                "first_det": 0.5,
                "rev": 2.0,
                "minw": 0.1,
            },
            {
                "min_gap": 3.0,
                "collision": False,
                "vmin": 8.0,
                "mean_headway": 1.2,
                "first_det": None,
                "rev": None,
                "minw": 0.9,
            },
        ]
        result = server.summarize_rows(rows)
        self.assertEqual(result["collisions"], 1)
        self.assertAlmostEqual(result["mean_min_gap"], 1.0)
        self.assertAlmostEqual(result["std_min_gap"], 2**1.5)
        self.assertEqual(result["detections"], 1)
        self.assertEqual(result["revocations"], 1)
        self.assertAlmostEqual(result["mean_detection_delay"], 0.5)
        self.assertAlmostEqual(result["mean_revocation_delay"], 2.0)

    def test_shipped_results_have_all_expected_groups(self):
        data = server.read_dashboard_data()
        self.assertEqual(data["result_groups"], 56)
        self.assertEqual(len(data["scenario_ids"]), 8)
        self.assertEqual(len(data["variants"]), 7)
        self.assertEqual(data["scenarios"]["A2_false_accel"]["CA_full"]["collisions"], 0)
        self.assertEqual(data["scenarios"]["L2_legit_brake"]["CA_full"]["collisions"], 0)
        self.assertEqual(data["scenarios"]["L2_legit_brake"]["CA_full"]["revocations"], 0)

    def test_run_request_allows_only_known_scenarios_and_sweeps(self):
        self.assertEqual(
            server.validate_run_request(
                {"scenarios": ["L1_normal"], "jerk_sweeps": ["J3.0"]}
            ),
            ["L1_normal", "J3.0"],
        )
        for request in (
            {"scenarios": ["../../outside"], "jerk_sweeps": []},
            {"scenarios": [], "jerk_sweeps": ["J99"]},
            {"scenarios": [], "jerk_sweeps": []},
            [],
        ):
            with self.subTest(request=request), self.assertRaises(ValueError):
                server.validate_run_request(request)


class DashboardHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.DashboardHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=3)

    def test_dashboard_and_data_endpoints(self):
        with urllib.request.urlopen(self.base + "/") as response:
            page = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("CyberAdapt at a glance", page)
            self.assertIn("Content-Security-Policy", response.headers)
        with urllib.request.urlopen(self.base + "/api/data") as response:
            payload = json.loads(response.read())
        self.assertEqual(payload["result_groups"], 56)
        with urllib.request.urlopen(self.base + "/api/export.csv") as response:
            csv_data = response.read().decode("utf-8")
            self.assertIn(
                'attachment; filename="cyberadapt-results.csv"',
                response.headers["Content-Disposition"],
            )
        self.assertEqual(len(csv_data.splitlines()), 57)

    def test_bad_host_and_invalid_simulation_request_are_rejected(self):
        request = urllib.request.Request(
            self.base + "/",
            headers={"Host": "not-local.example"},
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 403)

        payload = json.dumps(
            {"scenarios": ["../../outside"], "jerk_sweeps": []}
        ).encode("utf-8")
        request = urllib.request.Request(
            self.base + "/api/run",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
