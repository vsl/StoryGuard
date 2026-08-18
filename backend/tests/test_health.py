import unittest

from app.health import readiness_payload


class ReadinessPayloadTest(unittest.TestCase):
    def test_reports_ready_only_when_every_dependency_is_up(self) -> None:
        payload, status = readiness_payload({"postgres": True, "minio": True})
        self.assertEqual((payload["status"], status), ("ready", 200))

        payload, status = readiness_payload({"postgres": True, "minio": False})
        self.assertEqual((payload["status"], status), ("not_ready", 503))
        self.assertEqual(payload["checks"]["minio"], "down")


if __name__ == "__main__":
    unittest.main()
