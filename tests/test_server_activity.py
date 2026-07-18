import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ServerActivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["BOOK_SORTER_DATA_DIR"] = self.tmp.name
        import app
        self.app_module = importlib.reload(app)
        self.client = TestClient(self.app_module.app)

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("BOOK_SORTER_DATA_DIR", None)

    def test_activity_heartbeat_records_session(self):
        res = self.client.post(
            "/api/activity/heartbeat",
            json={"sessionId": "s1", "deviceLabel": "iPhone", "userAgent": "UA", "pageLoad": True, "activeSecondsDelta": 12},
        )
        self.assertEqual(res.status_code, 200)
        activity = self.client.get("/api/activity").json()
        session = activity["sessions"]["s1"]
        self.assertEqual(session["deviceLabel"], "iPhone")
        self.assertEqual(session["pageLoads"], 1)
        self.assertEqual(session["activeSeconds"], 12)

    def test_activity_action_counts_actions(self):
        res = self.client.post(
            "/api/activity/action",
            json={"sessionId": "s2", "deviceLabel": "Mac", "type": "keep", "bookHash": "abc", "label": "Book"},
        )
        self.assertEqual(res.status_code, 200)
        session = self.client.get("/api/activity").json()["sessions"]["s2"]
        self.assertEqual(session["actions"]["keep"], 1)
        self.assertEqual(session["lastAction"]["bookHash"], "abc")

    def test_admin_page_loads(self):
        res = self.client.get("/admin/activity/4f8b2d7c")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Book Sorter Activity", res.text)
        self.assertIn("/api/activity", res.text)


if __name__ == "__main__":
    unittest.main()
