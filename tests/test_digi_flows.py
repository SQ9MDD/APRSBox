import contextlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db import connect, init_db
from app.services.digi_flows import create_digi_flow, get_digi_flow, normalize_digi_flow_payload, set_digi_flow_enabled, update_digi_flow


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
                "step_type": "filter_path",
                "title": "Path Filter",
                "enabled": 1,
                "config": {"mode": "allow", "trace_paths": ["WIDE1-1"], "no_trace_paths": ["SP2-2"]},
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
            self.assertEqual(flow["steps"][1]["step_type"], "filter_path")
            self.assertEqual(flow["steps"][2]["step_type"], "tx_aprsis")

    def test_update_digi_flow_preserves_existing_step_ids_when_step_identity_matches(self) -> None:
        with temporary_database():
            flow_id = create_digi_flow(sample_flow_payload())
            original = get_digi_flow(flow_id)
            assert original is not None
            original_ids = {step["step_type"]: int(step["id"]) for step in original["steps"]}

            update_digi_flow(
                flow_id,
                {
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
                            "step_type": "filter_strict",
                            "title": "Strict Filter",
                            "enabled": 1,
                            "config": {},
                        },
                        {
                            "step_type": "filter_path",
                            "title": "Path Rule",
                            "enabled": 1,
                            "config": {"mode": "allow", "trace_paths": ["WIDE1-1"], "no_trace_paths": ["SP2-2"]},
                        },
                        {
                            "step_type": "tx_aprsis",
                            "title": "TX APRS-IS",
                            "enabled": 1,
                            "config": {"aprsis_target": "APRS-IS Main"},
                        },
                    ],
                },
            )

            updated = get_digi_flow(flow_id)
            assert updated is not None
            updated_steps = {step["step_type"]: step for step in updated["steps"]}
            self.assertEqual(int(updated_steps["receiver_rf"]["id"]), original_ids["receiver_rf"])
            self.assertEqual(int(updated_steps["filter_path"]["id"]), original_ids["filter_path"])
            self.assertEqual(int(updated_steps["tx_aprsis"]["id"]), original_ids["tx_aprsis"])
            self.assertIn("filter_strict", updated_steps)

    def test_new_filter_types_and_packet_type_mode_are_accepted(self) -> None:
        payload = sample_flow_payload()
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_strict",
                "title": "Strict Filter",
                "enabled": 1,
                "config": {},
            },
            {
                "step_type": "filter_digi",
                "title": "DIGI Filter",
                "enabled": 1,
                "config": {"mode": "deny", "digis": ["WIDE1-1", "TRACE2-2"]},
            },
            {
                "step_type": "filter_path",
                "title": "Path Filter",
                "enabled": 1,
                "config": {"mode": "allow", "trace_paths": ["WIDE1-1"], "no_trace_paths": ["SP2-2"]},
            },
            {
                "step_type": "filter_packet_type",
                "title": "Packet Type Filter",
                "enabled": 1,
                "config": {"mode": "allow", "packet_types": ["position", "message"]},
            },
            {
                "step_type": "filter_icon",
                "title": "Icon Filter",
                "enabled": 1,
                "config": {"mode": "allow", "icons": ["/>", "\\#"]},
            },
            {
                "step_type": "filter_rate_limit_per_callsign",
                "title": "Rate Limit Per Callsign",
                "enabled": 1,
                "config": {"packets_per_minute": 5},
            },
            payload["steps"][2],
        ]
        with temporary_database():
            normalized = normalize_digi_flow_payload(payload)
            self.assertEqual(normalized["steps"][1]["config"], {})
            self.assertEqual(normalized["steps"][2]["config"]["mode"], "deny")
            self.assertEqual(normalized["steps"][3]["config"]["trace_paths"], ["WIDE1-1"])
            self.assertEqual(normalized["steps"][4]["config"]["mode"], "allow")
            self.assertEqual(normalized["steps"][5]["config"]["icons"], ["/>", "\\#"])
            self.assertEqual(normalized["steps"][6]["config"]["packets_per_minute"], 5)

    def test_path_filter_uses_trace_and_no_trace_fields(self) -> None:
        payload = sample_flow_payload()
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_path",
                "title": "Path Filter",
                "enabled": 1,
                "config": {
                    "mode": "allow",
                    "trace_paths": ["TRACE2-2", "WIDE1-1"],
                    "no_trace_paths": ["TCPIP", "NOGATE"],
                },
            },
            payload["steps"][2],
        ]
        with temporary_database():
            normalized = normalize_digi_flow_payload(payload)
            self.assertEqual(normalized["steps"][1]["config"]["trace_paths"], ["TRACE2-2", "WIDE1-1"])
            self.assertEqual(normalized["steps"][1]["config"]["no_trace_paths"], ["TCPIP", "NOGATE"])

    def test_non_log_target_requires_path_filter(self) -> None:
        payload = sample_flow_payload()
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_dupe",
                "title": "Duplicate Filter",
                "enabled": 1,
                "config": {"window_sec": 30},
            },
            payload["steps"][2],
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "must include at least one enabled Path Rule"):
                normalize_digi_flow_payload(payload)

    def test_rf_target_requires_strict_filter(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "tx_rf"
        payload["target_ref"] = "RF-OUT"
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_path",
                "title": "Path Rule",
                "enabled": 1,
                "config": {"mode": "allow", "trace_paths": ["WIDE1-1"], "no_trace_paths": []},
            },
            {
                "step_type": "tx_rf",
                "title": "TX RF",
                "enabled": 1,
                "config": {"rf_target": "RF-OUT"},
            },
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "must include at least one enabled Strict Filter"):
                normalize_digi_flow_payload(payload)

    def test_action_drop_target_does_not_require_path_filter(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "action_drop"
        payload["target_ref"] = "Test drop"
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_callsign",
                "title": "Callsign Filter",
                "enabled": 1,
                "config": {"mode": "deny", "callsigns": ["SP9XYZ"]},
            },
            {
                "step_type": "action_drop",
                "title": "Action Drop",
                "enabled": 1,
                "config": {"note": "Test drop"},
            },
        ]
        with temporary_database():
            normalized = normalize_digi_flow_payload(payload)
            self.assertEqual(normalized["target_kind"], "action_drop")

    def test_enabling_tx_flow_without_enabled_path_rule_is_blocked(self) -> None:
        with temporary_database():
            connection = connect()
            try:
                connection.execute(
                    """
                    INSERT INTO digi_flows (
                        name, description, source_kind, source_ref, target_kind, target_ref, enabled, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "Legacy TX flow",
                        "",
                        "receiver_rf",
                        "TNC-1",
                        "tx_aprsis",
                        "APRS-IS Main",
                        0,
                        "2026-01-01T00:00:00+00:00",
                        "2026-01-01T00:00:00+00:00",
                    ),
                )
                flow_id = int(connection.execute("SELECT id FROM digi_flows WHERE name = 'Legacy TX flow'").fetchone()["id"])
                connection.executemany(
                    """
                    INSERT INTO digi_flow_steps (
                        flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            flow_id,
                            1,
                            "receiver_rf",
                            "Receiver RF",
                            1,
                            '{"rf_port":"TNC-1"}',
                            "2026-01-01T00:00:00+00:00",
                            "2026-01-01T00:00:00+00:00",
                        ),
                        (
                            flow_id,
                            2,
                            "filter_path",
                            "Path Rule",
                            0,
                            '{"mode":"allow","trace_paths":["WIDE1-1"],"no_trace_paths":[]}',
                            "2026-01-01T00:00:00+00:00",
                            "2026-01-01T00:00:00+00:00",
                        ),
                        (
                            flow_id,
                            3,
                            "tx_aprsis",
                            "TX APRS-IS",
                            1,
                            '{"aprsis_target":"APRS-IS Main"}',
                            "2026-01-01T00:00:00+00:00",
                            "2026-01-01T00:00:00+00:00",
                        ),
                    ),
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaisesRegex(ValueError, "cannot be enabled without an enabled Path Rule"):
                set_digi_flow_enabled(flow_id, True)

    def test_enabling_rf_tx_flow_without_enabled_strict_filter_is_blocked(self) -> None:
        with temporary_database():
            connection = connect()
            try:
                connection.execute(
                    """
                    INSERT INTO digi_flows (
                        name, description, source_kind, source_ref, target_kind, target_ref, enabled, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "Legacy RF TX flow",
                        "",
                        "receiver_rf",
                        "TNC-1",
                        "tx_rf",
                        "RF-OUT",
                        0,
                        "2026-01-01T00:00:00+00:00",
                        "2026-01-01T00:00:00+00:00",
                    ),
                )
                flow_id = int(connection.execute("SELECT id FROM digi_flows WHERE name = 'Legacy RF TX flow'").fetchone()["id"])
                connection.executemany(
                    """
                    INSERT INTO digi_flow_steps (
                        flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            flow_id,
                            1,
                            "receiver_rf",
                            "Receiver RF",
                            1,
                            '{"rf_port":"TNC-1"}',
                            "2026-01-01T00:00:00+00:00",
                            "2026-01-01T00:00:00+00:00",
                        ),
                        (
                            flow_id,
                            2,
                            "filter_path",
                            "Path Rule",
                            1,
                            '{"mode":"allow","trace_paths":["WIDE1-1"],"no_trace_paths":[]}',
                            "2026-01-01T00:00:00+00:00",
                            "2026-01-01T00:00:00+00:00",
                        ),
                        (
                            flow_id,
                            3,
                            "tx_rf",
                            "TX RF",
                            1,
                            '{"rf_target":"RF-OUT"}',
                            "2026-01-01T00:00:00+00:00",
                            "2026-01-01T00:00:00+00:00",
                        ),
                    ),
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaisesRegex(ValueError, "cannot be enabled without an enabled Strict Filter"):
                set_digi_flow_enabled(flow_id, True)

    def test_path_filter_allows_only_allow_mode(self) -> None:
        payload = sample_flow_payload()
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_path",
                "title": "Path Filter",
                "enabled": 1,
                "config": {
                    "mode": "deny",
                    "trace_paths": ["WIDE1-1"],
                    "no_trace_paths": [],
                },
            },
            payload["steps"][2],
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "Path filter mode must be allow"):
                normalize_digi_flow_payload(payload)


if __name__ == "__main__":
    unittest.main()
