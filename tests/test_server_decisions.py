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


class ServerDecisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["BOOK_SORTER_DATA_DIR"] = self.tmp.name
        import app
        self.app_module = importlib.reload(app)
        self.client = TestClient(self.app_module.app)

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("BOOK_SORTER_DATA_DIR", None)

    def test_decisions_are_saved_and_loaded_server_side(self):
        initial = self.client.get("/api/decisions")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["decisions"], {})

        saved = self.client.patch(
            "/api/decisions/abc123",
            json={"category": "activity", "decision": "keep", "rotation": 90},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["ok"])

        loaded = self.client.get("/api/decisions")
        self.assertEqual(loaded.status_code, 200)
        record = loaded.json()["decisions"]["abc123"]
        self.assertEqual(record["category"], "activity")
        self.assertEqual(record["decision"], "keep")
        self.assertEqual(record["rotation"], 90)

    def test_clear_decisions(self):
        self.client.patch("/api/decisions/abc123", json={"category": "activity", "decision": "discard", "rotation": 0})
        cleared = self.client.delete("/api/decisions")
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(self.client.get("/api/decisions").json()["decisions"], {})


if __name__ == "__main__":
    unittest.main()
