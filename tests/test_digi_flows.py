import contextlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db import connect, fetch_one, init_db
from app.services.digi_flows import (
    create_digi_flow,
    get_digi_flow,
    get_digi_flow_endpoint_options,
    get_digi_flow_type_meta,
    normalize_digi_flow_payload,
    set_digi_flow_enabled,
    update_digi_flow,
)


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


def sample_rf_flow_payload(*, name: str, source_ref: str, target_ref: str, enabled: int = 1) -> dict:
    return {
        "name": name,
        "description": "RF target flow",
        "source_kind": "receiver_rf",
        "source_ref": source_ref,
        "target_kind": "tx_rf",
        "target_ref": target_ref,
        "enabled": enabled,
        "steps": [
            {
                "step_type": "receiver_rf",
                "title": "Receiver RF",
                "enabled": 1,
                "config": {"rf_port": source_ref},
            },
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
                "config": {"rf_target": target_ref},
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

    def test_init_db_repairs_digi_flow_event_log_foreign_key_after_steps_table_rebuild(self) -> None:
        with temporary_database() as database_path:
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            try:
                connection.executescript(
                    """
                    ALTER TABLE digi_flow_steps RENAME TO digi_flow_steps_old;
                    CREATE TABLE digi_flow_steps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        flow_id INTEGER NOT NULL,
                        step_order INTEGER NOT NULL,
                        step_type TEXT NOT NULL CHECK (step_type IN (
                            'receiver_rf',
                            'receiver_aprsis',
                            'filter_dupe',
                            'filter_digi',
                            'filter_path',
                            'filter_strict',
                            'filter_callsign',
                            'filter_packet_type',
                            'filter_icon',
                            'filter_distance',
                            'filter_rate_limit',
                            'filter_rate_limit_per_callsign',
                            'tx_rf',
                            'tx_aprsis',
                            'action_drop',
                            'action_log'
                        )),
                        title TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                        config_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (flow_id) REFERENCES digi_flows(id) ON DELETE CASCADE,
                        UNIQUE (flow_id, step_order)
                    );
                    INSERT INTO digi_flow_steps (
                        id, flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                    )
                    SELECT
                        id, flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                    FROM digi_flow_steps_old;
                    DROP TABLE digi_flow_steps_old;
                    """
                )
                broken_fk = connection.execute("PRAGMA foreign_key_list(digi_flow_event_log)").fetchall()
                self.assertTrue(any(str(row["table"]) == "digi_flow_steps_old" for row in broken_fk))
            finally:
                connection.close()

            init_db()

            connection = connect()
            try:
                repaired_fk = connection.execute("PRAGMA foreign_key_list(digi_flow_event_log)").fetchall()
                self.assertTrue(any(str(row["table"]) == "digi_flow_steps" for row in repaired_fk))
                self.assertFalse(any(str(row["table"]) == "digi_flow_steps_old" for row in repaired_fk))
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

    def test_endpoint_options_hide_drop_target_unless_current_flow_uses_it(self) -> None:
        with temporary_database():
            default_targets = get_digi_flow_endpoint_options()["target"]
            self.assertFalse(any(option["value"] == "action_drop::drop" for option in default_targets))

            preserved_targets = get_digi_flow_endpoint_options(selected_target_selector="action_drop::drop")["target"]
            self.assertTrue(any(option["value"] == "action_drop::drop" for option in preserved_targets))

    def test_endpoint_options_keep_rf_target_available_for_multiple_sources(self) -> None:
        with temporary_database():
            connection = connect()
            try:
                connection.executemany(
                    """
                    INSERT INTO modems (
                        name, modem_type, band, device_path, baud_rate, enabled,
                        expose_port_enabled, expose_bind_address, expose_port, expose_whitelist,
                        notes, created_at, updated_at
                    )
                    VALUES (?, 'TCP', ?, ?, NULL, 1, 0, '127.0.0.1', 8002, '', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                    """,
                    (
                        ("TNC-2m", "2m", "127.0.0.1:9001"),
                        ("TNC-70cm", "70cm", "127.0.0.1:9002"),
                    ),
                )
                connection.commit()
            finally:
                connection.close()
            flow_id = create_digi_flow(sample_rf_flow_payload(name="2m to 70cm", source_ref="TNC-2m", target_ref="TNC-70cm"))
            target_values = {option["value"] for option in get_digi_flow_endpoint_options()["target"]}
            self.assertIn("tx_rf::TNC-70cm", target_values)

            preserved_values = {
                option["value"]
                for option in get_digi_flow_endpoint_options(
                    selected_target_selector="tx_rf::TNC-70cm",
                    current_flow_id=flow_id,
                )["target"]
            }
            self.assertIn("tx_rf::TNC-70cm", preserved_values)

    def test_type_meta_exposes_runtime_status_for_filters(self) -> None:
        with temporary_database():
            type_meta = get_digi_flow_type_meta()
            self.assertEqual(type_meta["filter_path"]["runtime_status"], "implemented")
            self.assertEqual(type_meta["filter_path"]["runtime_label"], "Runtime")
            self.assertEqual(type_meta["filter_packet_type"]["runtime_status"], "implemented")
            self.assertEqual(type_meta["filter_icon"]["runtime_status"], "implemented")
            self.assertEqual(type_meta["filter_digi"]["runtime_status"], "stub")
            self.assertEqual(type_meta["filter_digi"]["runtime_label"], "Stub")
            self.assertEqual(type_meta["filter_dupe"]["runtime_status"], "config_only")
            self.assertEqual(type_meta["filter_dupe"]["runtime_label"], "Config only")

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

    def test_update_digi_flow_can_replace_middle_step_without_step_order_conflict(self) -> None:
        with temporary_database():
            flow_id = create_digi_flow(
                {
                    "name": "RF log",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
                    "enabled": 1,
                    "steps": [
                        {
                            "step_type": "receiver_rf",
                            "title": "Receiver RF",
                            "enabled": 1,
                            "config": {"rf_port": "TNC-1"},
                        },
                        {
                            "step_type": "filter_callsign",
                            "title": "Callsign Filter",
                            "enabled": 1,
                            "config": {"mode": "allow", "callsigns": ["SQ9MDD*"]},
                        },
                        {
                            "step_type": "action_log",
                            "title": "Log Only",
                            "enabled": 1,
                            "config": {"log_tag": "log-only", "note": ""},
                        },
                    ],
                }
            )

            update_digi_flow(
                flow_id,
                {
                    "name": "RF log",
                    "description": "",
                    "source_kind": "receiver_rf",
                    "source_ref": "TNC-1",
                    "target_kind": "action_log",
                    "target_ref": "log-only",
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
                            "step_type": "action_log",
                            "title": "Log Only",
                            "enabled": 1,
                            "config": {"log_tag": "log-only", "note": ""},
                        },
                    ],
                },
            )

            updated = get_digi_flow(flow_id)
            assert updated is not None
            self.assertEqual([step["step_type"] for step in updated["steps"]], ["receiver_rf", "filter_strict", "action_log"])

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
            self.assertEqual(normalized["steps"][4]["config"]["packet_types"], ["position", "message"])
            self.assertEqual(normalized["steps"][5]["config"]["icons"], ["/>", "\\#"])
            self.assertEqual(normalized["steps"][6]["config"]["packets_per_minute"], 5)

    def test_packet_type_filter_normalizes_main_groups_and_preserves_legacy_codes(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "action_log"
        payload["target_ref"] = "log-only"
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_packet_type",
                "title": "Packet Type Filter",
                "enabled": 1,
                "config": {"mode": "allow", "packet_types": ["Position", "QUERY", "m", " W "]},
            },
            {
                "step_type": "action_log",
                "title": "Log Only",
                "enabled": 1,
                "config": {"log_tag": "log-only", "note": ""},
            },
        ]
        with temporary_database():
            normalized = normalize_digi_flow_payload(payload)
            self.assertEqual(normalized["steps"][1]["config"]["packet_types"], ["position", "query", "M", "W"])

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

    def test_rf_target_does_not_require_strict_filter(self) -> None:
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
            normalized = normalize_digi_flow_payload(payload)
            self.assertEqual(normalized["target_kind"], "tx_rf")

    def test_create_enabled_rf_flow_allows_shared_target_when_source_differs(self) -> None:
        with temporary_database():
            create_digi_flow(sample_rf_flow_payload(name="2m to 70cm", source_ref="TNC-2m", target_ref="TNC-70cm"))
            second_flow_id = create_digi_flow(sample_rf_flow_payload(name="70cm to 70cm", source_ref="TNC-70cm", target_ref="TNC-70cm"))
            self.assertIsInstance(second_flow_id, int)

    def test_create_enabled_rf_flow_rejects_duplicate_source_target_pair(self) -> None:
        with temporary_database():
            create_digi_flow(sample_rf_flow_payload(name="2m to 70cm", source_ref="TNC-2m", target_ref="TNC-70cm"))
            with self.assertRaisesRegex(ValueError, "same source and target already exists"):
                create_digi_flow(sample_rf_flow_payload(name="2m to 70cm clone", source_ref="TNC-2m", target_ref="TNC-70cm"))

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

    def test_enabling_rf_tx_flow_without_enabled_strict_filter_is_allowed(self) -> None:
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
            set_digi_flow_enabled(flow_id, True)
            refreshed = fetch_one("SELECT enabled FROM digi_flows WHERE id = ?", (flow_id,))
            assert refreshed is not None
            self.assertEqual(int(refreshed["enabled"]), 1)

    def test_enabling_rf_flow_allows_shared_target_when_source_differs(self) -> None:
        with temporary_database():
            create_digi_flow(sample_rf_flow_payload(name="2m to 70cm", source_ref="TNC-2m", target_ref="TNC-70cm"))
            second_flow_id = create_digi_flow(
                sample_rf_flow_payload(name="70cm standby", source_ref="TNC-70cm", target_ref="TNC-70cm", enabled=0)
            )
            set_digi_flow_enabled(second_flow_id, True)
            refreshed = fetch_one("SELECT enabled FROM digi_flows WHERE id = ?", (second_flow_id,))
            assert refreshed is not None
            self.assertEqual(int(refreshed["enabled"]), 1)

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
