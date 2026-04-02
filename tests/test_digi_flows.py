import contextlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db import connect, init_db
from app.services.digi_flows import create_digi_flow, get_digi_flow, normalize_digi_flow_payload


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            init_db()
            yield database_path
        finally:
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


def sample_flow_payload() -> dict:
    return {
        "name": "RF ingress",
        "description": "Simple flow",
        "source_kind": "receiver_rf",
        "source_ref": "TNC-1",
        "target_kind": "tx_aprsis",
        "target_ref": "APRS-IS Main",
        "enabled": 1,
        "steps": [
            {
                "step_type": "receiver_rf",
                "title": "Receiver RF",
                "enabled": 1,
                "config": {"rf_port": "TNC-1"},
            },
            {
                "step_type": "filter_dupe",
                "title": "Duplicate Filter",
                "enabled": 1,
                "config": {"window_sec": 30},
            },
            {
                "step_type": "tx_aprsis",
                "title": "TX APRS-IS",
                "enabled": 1,
                "config": {"aprsis_target": "APRS-IS Main"},
            },
        ],
    }


class DigiFlowsTests(unittest.TestCase):
    def test_init_db_creates_digi_flow_tables_and_constraints(self) -> None:
        with temporary_database():
            connection = connect()
            try:
                table_names = {
                    row["name"]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
                self.assertIn("digi_flows", table_names)
                self.assertIn("digi_flow_steps", table_names)

                create_digi_flow(sample_flow_payload())
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        INSERT INTO digi_flows (
                            name, description, source_kind, source_ref, target_kind, target_ref, enabled, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "Duplicate",
                            "",
                            "receiver_rf",
                            "TNC-1",
                            "tx_aprsis",
                            "APRS-IS Main",
                            1,
                            "2026-01-01T00:00:00+00:00",
                            "2026-01-01T00:00:00+00:00",
                        ),
                    )
            finally:
                connection.close()

    def test_normalize_digi_flow_requires_source_first_and_target_last(self) -> None:
        payload = sample_flow_payload()
        payload["steps"] = [payload["steps"][1], payload["steps"][0], payload["steps"][2]]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "First flow step must be a source step"):
                normalize_digi_flow_payload(payload)

    def test_create_digi_flow_persists_steps(self) -> None:
        with temporary_database():
            flow_id = create_digi_flow(sample_flow_payload())
            flow = get_digi_flow(flow_id)
            assert flow is not None
            self.assertEqual(flow["source_kind"], "receiver_rf")
            self.assertEqual(flow["target_kind"], "tx_aprsis")
            self.assertEqual(len(flow["steps"]), 3)
            self.assertEqual(flow["steps"][0]["step_type"], "receiver_rf")
            self.assertEqual(flow["steps"][1]["step_type"], "filter_dupe")
            self.assertEqual(flow["steps"][2]["step_type"], "tx_aprsis")


if __name__ == "__main__":
    unittest.main()
