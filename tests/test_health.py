import os
import unittest

from fastapi.testclient import TestClient

os.environ.setdefault("AUTO_CREATE_TABLES", "false")

from backend.app.main import app


class HealthTestCase(unittest.TestCase):
    def test_health_returns_ok(self) -> None:
        client = TestClient(app)
        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
