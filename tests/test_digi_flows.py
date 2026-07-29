import contextlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db import connect, fetch_one, init_db
from app.services.content import get_section_row, safe_update_section_row
from app.services.digi_flows import (
    FILTER_STEP_TYPES,
    create_digi_flow,
    get_digi_flow,
    get_digi_flow_endpoint_options,
    get_digi_flow_reference_options,
    get_digi_flow_type_meta,
    list_digi_flows,
    move_digi_flow,
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
        "target_ref": "aprsis",
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
                "step_type": "tx_aprsis",
                "title": "TX APRS-IS",
                "enabled": 1,
                "config": {"aprsis_target": "aprsis"},
            },
        ],
    }


def insert_aprsis_interface(*, enabled: int = 1) -> int:
    connection = connect()
    try:
        cursor = connection.execute(
            """
            INSERT INTO modems (
                name, modem_type, band, device_path, enabled, notes, created_at, updated_at
            )
            VALUES ('APRSIS-CONNECTION', 'APRSIS', '', 'm/20', ?, '', ?, ?)
            """,
            (
                enabled,
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


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


def sample_local_tx_flow_payload(
    *,
    name: str,
    target_kind: str = "tx_aprsis",
    target_ref: str = "aprsis",
    enabled: int = 1,
) -> dict:
    source_step = {
        "step_type": "receiver_local_tx",
        "title": "Local TX",
        "enabled": 1,
        "config": {"local_tx_source": "local_tx"},
    }
    if target_kind == "tx_aprsis":
        steps = [
            source_step,
            {
                "step_type": "filter_strict",
                "title": "Strict Filter",
                "enabled": 1,
                "config": {},
            },
            {
                "step_type": "tx_aprsis",
                "title": "TX APRS-IS",
                "enabled": 1,
                "config": {"aprsis_target": target_ref},
            },
        ]
    else:
        steps = [
            source_step,
            {
                "step_type": "action_log",
                "title": "Black Hole",
                "enabled": 1,
                "config": {"log_tag": "log-only", "note": ""},
            },
        ]
    return {
        "name": name,
        "description": "Local TX flow",
        "source_kind": "receiver_local_tx",
        "source_ref": "local_tx",
        "target_kind": target_kind,
        "target_ref": target_ref,
        "enabled": enabled,
        "steps": steps,
    }


class DigiFlowsTests(unittest.TestCase):
    def test_digi_flows_template_includes_help_and_footer_create_action(self) -> None:
        template_source = Path("app/templates/digi_flows.html").read_text(encoding="utf-8")
        self.assertIn("static/css/help-viewer.css", template_source)
        self.assertIn('data-help-page="application/packet_routing"', template_source)
        self.assertIn('class="help-icon-button page-help-button"', template_source)
        self.assertIn('include "partials/help_modal.html"', template_source)
        self.assertIn("static/js/help-viewer.js", template_source)

        table_index = template_source.index('<div class="table-wrap">')
        create_action_index = template_source.index('{{ t("New routing flow") }}')
        self.assertGreater(create_action_index, table_index)

    def test_digi_flow_form_template_includes_detailed_help(self) -> None:
        template_source = Path("app/templates/digi_flow_form.html").read_text(encoding="utf-8")
        self.assertIn("static/css/help-viewer.css", template_source)
        self.assertIn('data-help-page="application/packet_routing_flow"', template_source)
        self.assertIn('class="help-icon-button page-help-button"', template_source)
        self.assertNotIn('data-help-autoload="1"', template_source)
        self.assertIn('include "partials/help_modal.html"', template_source)
        self.assertIn("static/js/help-viewer.js", template_source)

        script_source = Path("app/static/js/help-viewer.js").read_text(encoding="utf-8")
        self.assertNotIn('data-help-autoload="1"', script_source)

    def test_init_db_creates_digi_flow_tables_and_allows_duplicate_route_pairs(self) -> None:
        with temporary_database():
            insert_aprsis_interface()
            connection = connect()
            try:
                table_names = {
                    row["name"]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
                self.assertIn("digi_flows", table_names)
                self.assertIn("digi_flow_steps", table_names)

                create_digi_flow(sample_flow_payload())
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
                        "aprsis",
                        0,
                        "2026-01-01T00:00:00+00:00",
                        "2026-01-01T00:00:00+00:00",
                    ),
                )
                count_row = connection.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM digi_flows
                    WHERE source_kind = 'receiver_rf'
                      AND source_ref = 'TNC-1'
                      AND target_kind = 'tx_aprsis'
                      AND target_ref = 'aprsis'
                    """
                ).fetchone()
                assert count_row is not None
                self.assertEqual(int(count_row["total"]), 2)
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
                            'filter_direct_only',
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
            insert_aprsis_interface()
            flow_id = create_digi_flow(sample_flow_payload())
            flow = get_digi_flow(flow_id)
            assert flow is not None
            self.assertEqual(flow["source_kind"], "receiver_rf")
            self.assertEqual(flow["target_kind"], "tx_aprsis")
            self.assertEqual(len(flow["steps"]), 3)
            self.assertEqual(flow["steps"][0]["step_type"], "receiver_rf")
            self.assertEqual(flow["steps"][1]["step_type"], "filter_strict")
            self.assertEqual(flow["steps"][2]["step_type"], "tx_aprsis")

    def test_get_digi_flow_uses_black_hole_label_for_action_log_target_display(self) -> None:
        with temporary_database():
            payload = sample_flow_payload()
            payload["target_kind"] = "action_log"
            payload["target_ref"] = "log-only"
            payload["steps"] = [
                payload["steps"][0],
                {
                    "step_type": "action_log",
                    "title": "Black Hole",
                    "enabled": 1,
                    "config": {"log_tag": "log-only", "note": ""},
                },
            ]

            flow_id = create_digi_flow(payload)
            flow = get_digi_flow(flow_id)

            assert flow is not None
            self.assertEqual(flow["target_display"], "Black Hole")

    def test_get_digi_flow_displays_rf_source_and_target_without_kind_prefix(self) -> None:
        with temporary_database():
            flow_id = create_digi_flow(
                sample_rf_flow_payload(
                    name="RF relay",
                    source_ref="tnc-seriall",
                    target_ref="tnc-rf-out",
                )
            )
            flow = get_digi_flow(flow_id)
            assert flow is not None
            self.assertEqual(flow["source_display"], "tnc-seriall")
            self.assertEqual(flow["target_display"], "tnc-rf-out")

    def test_move_digi_flow_persists_manual_order(self) -> None:
        with temporary_database():
            first_id = create_digi_flow(sample_rf_flow_payload(name="Flow A", source_ref="A-1", target_ref="A-2"))
            second_id = create_digi_flow(sample_rf_flow_payload(name="Flow B", source_ref="B-1", target_ref="B-2"))
            third_id = create_digi_flow(sample_rf_flow_payload(name="Flow C", source_ref="C-1", target_ref="C-2"))

            self.assertEqual([int(flow["id"]) for flow in list_digi_flows()], [third_id, second_id, first_id])

            move_digi_flow(second_id, "up")
            self.assertEqual([int(flow["id"]) for flow in list_digi_flows()], [second_id, third_id, first_id])

            move_digi_flow(first_id, "up")
            self.assertEqual([int(flow["id"]) for flow in list_digi_flows()], [second_id, first_id, third_id])

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

    def test_renaming_tnc_updates_digi_flow_references(self) -> None:
        with temporary_database():
            connection = connect()
            try:
                connection.execute(
                    """
                    INSERT INTO modems (
                        name, modem_type, band, device_path, baud_rate, enabled,
                        expose_port_enabled, expose_bind_address, expose_port, expose_whitelist,
                        notes, created_at, updated_at
                    )
                    VALUES (?, 'TCP', '2m', '127.0.0.1:9001', NULL, 1, 0, '127.0.0.1', 8002, '', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                    """,
                    ("TNC-A",),
                )
                connection.commit()
            finally:
                connection.close()

            flow_id = create_digi_flow(sample_rf_flow_payload(name="2m loop", source_ref="TNC-A", target_ref="TNC-A"))
            modem_row = get_section_row("modems", 1)
            assert modem_row is not None
            modem_payload = dict(modem_row)
            modem_payload["name"] = "TNC-B"
            success, error = safe_update_section_row("modems", 1, modem_payload)
            self.assertTrue(success, msg=error or "")

            flow = get_digi_flow(flow_id)
            assert flow is not None
            self.assertEqual(flow["source_ref"], "TNC-B")
            self.assertEqual(flow["target_ref"], "TNC-B")
            self.assertEqual(flow["steps"][0]["config"]["rf_port"], "TNC-B")
            self.assertEqual(flow["steps"][-1]["config"]["rf_target"], "TNC-B")

            source_values = {option["value"] for option in get_digi_flow_endpoint_options()["source"]}
            target_values = {option["value"] for option in get_digi_flow_endpoint_options()["target"]}
            self.assertIn("receiver_rf::TNC-B", source_values)
            self.assertIn("tx_rf::TNC-B", target_values)
            self.assertNotIn("receiver_rf::TNC-A", source_values)
            self.assertNotIn("tx_rf::TNC-A", target_values)

    def test_openwebrx_mqtt_is_available_as_source_but_not_as_tx_target(self) -> None:
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
                    VALUES (?, ?, ?, ?, NULL, 1, 0, '127.0.0.1', 8002, '', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                    """,
                    (
                        ("OpenWebRX-1", "OPENWEBRX_MQTT", "2m", "mqtt://127.0.0.1:1883/rxqwe/APRS"),
                        ("TNC-TX", "TCP", "2m", "127.0.0.1:9001"),
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            options = get_digi_flow_endpoint_options()
            source_values = {option["value"] for option in options["source"]}
            target_values = {option["value"] for option in options["target"]}

            self.assertIn("receiver_rf::OpenWebRX-1", source_values)
            self.assertNotIn("tx_rf::OpenWebRX-1", target_values)
            self.assertIn("tx_rf::TNC-TX", target_values)

    def test_endpoint_options_include_local_tx_source_with_restricted_target_set(self) -> None:
        with temporary_database():
            options = get_digi_flow_endpoint_options()
            source_values = {option["value"] for option in options["source"]}
            self.assertIn("receiver_local_tx::local_tx", source_values)
            self.assertNotIn("tx_aprsis::aprsis", {option["value"] for option in options["target"]})

            by_source_kind = options.get("target_by_source_kind") or {}
            local_targets = {option["kind"] for option in by_source_kind.get("receiver_local_tx") or []}
            self.assertEqual(local_targets, {"action_log"})

            insert_aprsis_interface()
            options = get_digi_flow_endpoint_options()
            by_source_kind = options.get("target_by_source_kind") or {}
            local_targets = {option["kind"] for option in by_source_kind.get("receiver_local_tx") or []}
            self.assertEqual(local_targets, {"tx_aprsis", "action_log"})

    def test_aprsis_endpoints_and_backend_require_a_defined_interface(self) -> None:
        with temporary_database():
            options = get_digi_flow_endpoint_options()
            source_values = {option["value"] for option in options["source"]}
            target_values = {option["value"] for option in options["target"]}
            references = get_digi_flow_reference_options()
            self.assertFalse(any(value.startswith("receiver_aprsis::") for value in source_values))
            self.assertNotIn("tx_aprsis::aprsis", target_values)
            self.assertEqual(references["receiver_aprsis"], [])
            self.assertEqual(references["tx_aprsis"], [])
            with self.assertRaisesRegex(ValueError, "requires a defined APRSIS interface"):
                normalize_digi_flow_payload(sample_flow_payload())

            interface_id = insert_aprsis_interface(enabled=0)
            options = get_digi_flow_endpoint_options()
            self.assertIn(
                "receiver_aprsis::APRSIS-CONNECTION",
                {option["value"] for option in options["source"]},
            )
            self.assertIn("tx_aprsis::aprsis", {option["value"] for option in options["target"]})
            self.assertEqual(get_digi_flow_reference_options()["tx_aprsis"], ["aprsis"])

            payload = sample_flow_payload()
            payload["enabled"] = 0
            flow_id = create_digi_flow(payload)
            connection = connect()
            try:
                connection.execute("DELETE FROM modems WHERE id = ?", (interface_id,))
                connection.commit()
            finally:
                connection.close()
            with self.assertRaisesRegex(ValueError, "requires a defined APRSIS interface"):
                set_digi_flow_enabled(flow_id, True)

    def test_type_meta_exposes_runtime_status_for_filters(self) -> None:
        with temporary_database():
            type_meta = get_digi_flow_type_meta()
            self.assertEqual(type_meta["filter_path"]["runtime_status"], "implemented")
            self.assertEqual(type_meta["filter_path"]["runtime_label"], "Runtime")
            self.assertEqual(type_meta["filter_path"]["help_page"], "application/packet_routing_flow_path_rule_and_digi_guard")
            self.assertIn("WIDE1-1", type_meta["filter_path"]["config_fields"][1]["help_lines"])
            self.assertEqual(type_meta["filter_direct_only"]["runtime_status"], "implemented")
            self.assertEqual(type_meta["filter_direct_only"]["runtime_label"], "Runtime")
            self.assertEqual(type_meta["filter_packet_type"]["runtime_status"], "implemented")
            self.assertEqual(type_meta["filter_icon"]["runtime_status"], "implemented")
            self.assertEqual(type_meta["filter_digi"]["runtime_status"], "implemented")
            self.assertEqual(type_meta["filter_digi"]["runtime_label"], "Runtime")
            self.assertEqual(type_meta["filter_dupe"]["runtime_status"], "implemented")
            self.assertEqual(type_meta["filter_dupe"]["runtime_label"], "Runtime")
            self.assertEqual(type_meta["filter_distance"]["runtime_status"], "implemented")
            self.assertEqual(type_meta["filter_distance"]["runtime_label"], "Runtime")
            self.assertEqual(type_meta["filter_rate_limit"]["runtime_status"], "implemented")
            self.assertEqual(type_meta["filter_rate_limit"]["config_fields"][0]["name"], "rate_limit_rules_text")
            self.assertEqual(type_meta["action_log"]["help_page"], "application/packet_routing_flow_black_hole")
            palette_types = [step_type for step_type in FILTER_STEP_TYPES if step_type != "filter_rate_limit_per_callsign"]
            palette_labels = [type_meta[step_type]["label"] for step_type in palette_types]
            self.assertEqual(len(palette_labels), len(set(palette_labels)))
            mandatory_rules = {
                "filter_rf_guard",
                "filter_aprsis_message_delivery",
                "filter_allow_rules",
                "filter_rf_tx_guard",
                "filter_path",
                "filter_strict",
            }
            for step_type in palette_types:
                expected_kind = "rule" if step_type in mandatory_rules else "filter"
                expected_badge = "Rule" if step_type in mandatory_rules else "Filter"
                self.assertEqual(type_meta[step_type]["palette_kind"], expected_kind)
                self.assertEqual(type_meta[step_type]["badge"], expected_badge)
                self.assertTrue(type_meta[step_type]["scope_label"])
                self.assertTrue(type_meta[step_type]["scope_tone"])
            self.assertEqual(type_meta["filter_path"]["scope_label"], "RF → RF")
            self.assertEqual(type_meta["filter_rf_guard"]["scope_label"], "APRS-IS → RF")
            self.assertEqual(type_meta["filter_aprsis_message_delivery"]["scope_label"], "APRS-IS → RF")
            self.assertEqual(type_meta["filter_aprsis_message_delivery"]["config_fields"], [])
            self.assertEqual(
                type_meta["filter_aprsis_message_delivery"]["help_page"],
                "application/packet_routing_flow_aprsis_message_delivery_rule",
            )
            self.assertEqual(type_meta["filter_allow_rules"]["scope_label"], "APRS-IS → RF")
            self.assertEqual(
                type_meta["filter_allow_rules"]["help_page"],
                "application/packet_routing_flow_aprsis_callsign_radius_rule",
            )
            self.assertEqual(type_meta["filter_direct_only"]["scope_label"], "RF → RF")
            self.assertEqual(type_meta["filter_callsign"]["scope_label"], "RF → RF")
            self.assertEqual(type_meta["filter_strict"]["scope_label"], "RF → APRS-IS")

    def test_update_digi_flow_preserves_existing_step_ids_when_step_identity_matches(self) -> None:
        with temporary_database():
            insert_aprsis_interface()
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
                    "target_ref": "aprsis",
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
                            "step_type": "tx_aprsis",
                            "title": "TX APRS-IS",
                            "enabled": 1,
                            "config": {"aprsis_target": "aprsis"},
                        },
                    ],
                },
            )

            updated = get_digi_flow(flow_id)
            assert updated is not None
            updated_steps = {step["step_type"]: step for step in updated["steps"]}
            self.assertEqual(int(updated_steps["receiver_rf"]["id"]), original_ids["receiver_rf"])
            self.assertEqual(int(updated_steps["filter_strict"]["id"]), original_ids["filter_strict"])
            self.assertEqual(int(updated_steps["tx_aprsis"]["id"]), original_ids["tx_aprsis"])

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
                            "step_type": "filter_digi",
                            "title": "DIGI Filter",
                            "enabled": 1,
                            "config": {"mode": "allow", "digis": ["SQ9MDD*"]},
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
            self.assertEqual([step["step_type"] for step in updated["steps"]], ["receiver_rf", "filter_digi", "action_log"])

    def test_new_filter_types_and_packet_type_mode_are_accepted(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "action_log"
        payload["target_ref"] = "log-only"
        payload["steps"] = [
            payload["steps"][0],
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
            {
                "step_type": "action_log",
                "title": "Log Only",
                "enabled": 1,
                "config": {"log_tag": "log-only", "note": ""},
            },
        ]
        with temporary_database():
            normalized = normalize_digi_flow_payload(payload)
            self.assertEqual(normalized["steps"][1]["config"]["mode"], "deny")
            self.assertEqual(normalized["steps"][2]["config"]["trace_paths"], ["WIDE1-1"])
            self.assertEqual(normalized["steps"][3]["config"]["mode"], "allow")
            self.assertEqual(normalized["steps"][3]["config"]["packet_types"], ["position", "message"])
            self.assertEqual(normalized["steps"][4]["config"]["mode"], "allow")
            self.assertEqual(normalized["steps"][4]["config"]["icons"], ["/>", "\\#"])
            self.assertEqual(normalized["steps"][5]["config"]["packets_per_minute"], 5)

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
        payload["target_kind"] = "action_log"
        payload["target_ref"] = "log-only"
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
            {
                "step_type": "action_log",
                "title": "Log Only",
                "enabled": 1,
                "config": {"log_tag": "log-only", "note": ""},
            },
        ]
        with temporary_database():
            normalized = normalize_digi_flow_payload(payload)
            self.assertEqual(normalized["steps"][1]["config"]["trace_paths"], ["TRACE2-2", "WIDE1-1"])
            self.assertEqual(normalized["steps"][1]["config"]["no_trace_paths"], ["TCPIP", "NOGATE"])

    def test_distance_filter_accepts_configurations_with_one_two_and_three_zones(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "action_log"
        payload["target_ref"] = "log-only"

        def _build_zones(count: int) -> list[dict[str, object]]:
            base = [
                {"latitude": 50.06143, "longitude": 19.93658, "radius_km": 0.5},
                {"latitude": 52.22977, "longitude": 21.01178, "radius_km": 3},
                {"latitude": 51.10788, "longitude": 17.03854, "radius_km": 15},
            ]
            return base[:count]

        with temporary_database():
            for zone_count in (1, 2, 3):
                payload["steps"] = [
                    payload["steps"][0],
                    {
                        "step_type": "filter_distance",
                        "title": "Distance Filter",
                        "enabled": 1,
                        "config": {"zones": _build_zones(zone_count)},
                    },
                    {
                        "step_type": "action_log",
                        "title": "Log Only",
                        "enabled": 1,
                        "config": {"log_tag": "log-only", "note": ""},
                    },
                ]
                normalized = normalize_digi_flow_payload(payload)
                zones = normalized["steps"][1]["config"]["zones"]
                self.assertEqual(len(zones), zone_count)
                self.assertTrue(all(float(zone["radius_km"]) > 0 for zone in zones))

    def test_distance_filter_rejects_invalid_zone_configurations(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "action_log"
        payload["target_ref"] = "log-only"

        with temporary_database():
            payload["steps"] = [
                payload["steps"][0],
                {
                    "step_type": "filter_distance",
                    "title": "Distance Filter",
                    "enabled": 1,
                    "config": {"zones": [{"latitude": "", "longitude": "19.9", "radius_km": "1"}]},
                },
                {"step_type": "action_log", "title": "Log Only", "enabled": 1, "config": {"log_tag": "log-only", "note": ""}},
            ]
            with self.assertRaisesRegex(ValueError, "requires latitude, longitude and radius"):
                normalize_digi_flow_payload(payload)

            payload["steps"][1]["config"] = {"zones": [{"latitude": "95", "longitude": "19.9", "radius_km": "1"}]}
            with self.assertRaisesRegex(ValueError, "latitude must be between -90 and 90"):
                normalize_digi_flow_payload(payload)

            payload["steps"][1]["config"] = {"zones": [{"latitude": "50", "longitude": "190", "radius_km": "1"}]}
            with self.assertRaisesRegex(ValueError, "longitude must be between -180 and 180"):
                normalize_digi_flow_payload(payload)

            payload["steps"][1]["config"] = {"zones": [{"latitude": "50", "longitude": "19.9", "radius_km": "0"}]}
            with self.assertRaisesRegex(ValueError, "radius must be greater than 0 km"):
                normalize_digi_flow_payload(payload)

            payload["steps"][1]["config"] = {"zones": [{"latitude": "50", "longitude": "19.9", "radius_km": "0.25"}]}
            with self.assertRaisesRegex(ValueError, "radius below 1 km must use 0.1 km steps"):
                normalize_digi_flow_payload(payload)

            payload["steps"][1]["config"] = {
                "zones": [
                    {"latitude": "50.0", "longitude": "19.9", "radius_km": "1"},
                    {"latitude": "51.0", "longitude": "20.9", "radius_km": "1"},
                    {"latitude": "52.0", "longitude": "21.9", "radius_km": "1"},
                    {"latitude": "53.0", "longitude": "22.9", "radius_km": "1"},
                ]
            }
            with self.assertRaisesRegex(ValueError, "supports at most 3 zones"):
                normalize_digi_flow_payload(payload)

    def test_distance_filter_can_be_used_only_once_in_flow(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "action_log"
        payload["target_ref"] = "log-only"
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_distance",
                "title": "Distance Filter",
                "enabled": 1,
                "config": {"zones": [{"latitude": 50.0, "longitude": 19.9, "radius_km": 1}]},
            },
            {
                "step_type": "filter_distance",
                "title": "Distance Filter",
                "enabled": 1,
                "config": {"zones": [{"latitude": 52.0, "longitude": 21.0, "radius_km": 2}]},
            },
            {
                "step_type": "action_log",
                "title": "Log Only",
                "enabled": 1,
                "config": {"log_tag": "log-only", "note": ""},
            },
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "Distance filter can be used only once in a flow"):
                normalize_digi_flow_payload(payload)

    def test_rf_target_requires_path_filter(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "tx_rf"
        payload["target_ref"] = "RF-OUT"
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_dupe",
                "title": "Duplicate Filter",
                "enabled": 1,
                "config": {"window_sec": 5},
            },
            {
                "step_type": "tx_rf",
                "title": "TX RF",
                "enabled": 1,
                "config": {"rf_target": "RF-OUT"},
            },
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "RF TX target"):
                normalize_digi_flow_payload(payload)

    def test_duplicate_filter_can_be_used_only_once_in_flow(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "action_log"
        payload["target_ref"] = "log-only"
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_dupe",
                "title": "Duplicate Filter",
                "enabled": 1,
                "config": {"window_sec": 5},
            },
            {
                "step_type": "filter_dupe",
                "title": "Duplicate Filter",
                "enabled": 1,
                "config": {"window_sec": 6},
            },
            {
                "step_type": "action_log",
                "title": "Log Only",
                "enabled": 1,
                "config": {"log_tag": "log-only", "note": ""},
            },
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "can be used only once"):
                normalize_digi_flow_payload(payload)

    def test_duplicate_filter_must_be_first_filter_step(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "action_log"
        payload["target_ref"] = "log-only"
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_callsign",
                "title": "Callsign Filter",
                "enabled": 1,
                "config": {"mode": "allow", "callsigns": ["SP8ABC-9"]},
            },
            {
                "step_type": "filter_dupe",
                "title": "Duplicate Filter",
                "enabled": 1,
                "config": {"window_sec": 5},
            },
            {
                "step_type": "action_log",
                "title": "Log Only",
                "enabled": 1,
                "config": {"log_tag": "log-only", "note": ""},
            },
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "must be the first filter step"):
                normalize_digi_flow_payload(payload)

    def test_duplicate_filter_can_be_used_only_once_in_flow(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "action_log"
        payload["target_ref"] = "log-only"
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_dupe",
                "title": "Duplicate Filter",
                "enabled": 1,
                "config": {"window_sec": 5},
            },
            {
                "step_type": "filter_dupe",
                "title": "Duplicate Filter",
                "enabled": 1,
                "config": {"window_sec": 6},
            },
            {
                "step_type": "action_log",
                "title": "Log Only",
                "enabled": 1,
                "config": {"log_tag": "log-only", "note": ""},
            },
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "can be used only once"):
                normalize_digi_flow_payload(payload)

    def test_duplicate_filter_must_be_first_filter_step(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "action_log"
        payload["target_ref"] = "log-only"
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_callsign",
                "title": "Callsign Filter",
                "enabled": 1,
                "config": {"mode": "allow", "callsigns": ["SP8ABC-9"]},
            },
            {
                "step_type": "filter_dupe",
                "title": "Duplicate Filter",
                "enabled": 1,
                "config": {"window_sec": 5},
            },
            {
                "step_type": "action_log",
                "title": "Log Only",
                "enabled": 1,
                "config": {"log_tag": "log-only", "note": ""},
            },
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "must be the first filter step"):
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

    def test_rf_target_normalizes_viscous_delay_first_and_path_rule_last(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "tx_rf"
        payload["target_ref"] = "RF-OUT"
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_callsign",
                "title": "Callsign Filter",
                "enabled": 1,
                "config": {"mode": "allow", "callsigns": ["SP8ABC-9"]},
            },
            {
                "step_type": "filter_path",
                "title": "Path Rule",
                "enabled": 1,
                "config": {"mode": "allow", "trace_paths": ["WIDE1-1"], "no_trace_paths": []},
            },
            {
                "step_type": "filter_dupe",
                "title": "Duplicate Filter",
                "enabled": 1,
                "config": {"window_sec": 5},
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
            self.assertEqual(
                [step["step_type"] for step in normalized["steps"]],
                ["receiver_rf", "filter_dupe", "filter_callsign", "filter_path", "tx_rf"],
            )

    def test_rf_target_normalizes_rate_limit_filter_before_path_rule(self) -> None:
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
                "step_type": "filter_rate_limit",
                "title": "Rate Limit Filter",
                "enabled": 1,
                "config": {"rate_limit_rules_text": "SQ9MDD* - 15s"},
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
            self.assertEqual([step["step_type"] for step in normalized["steps"]], ["receiver_rf", "filter_rate_limit", "filter_path", "tx_rf"])
            self.assertEqual(
                normalized["steps"][1]["config"],
                {"rate_limit_rules": [{"source_callsign_pattern": "SQ9MDD*", "rate_limit_seconds": 15}]},
            )

    def test_rate_limit_filter_rejects_invalid_seconds(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "tx_rf"
        payload["target_ref"] = "RF-OUT"
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_rate_limit",
                "title": "Rate Limit Filter",
                "enabled": 1,
                "config": {"rate_limit_rules_text": "SQ9MDD* - 7s"},
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
                "config": {"rf_target": "RF-OUT"},
            },
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "line #1"):
                normalize_digi_flow_payload(payload)

    def test_rate_limit_filter_rejects_non_rf_targets(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "action_log"
        payload["target_ref"] = "log-only"
        payload["steps"] = [
            payload["steps"][0],
            {
                "step_type": "filter_rate_limit",
                "title": "Rate Limit Filter",
                "enabled": 1,
                "config": {"rate_limit_rules_text": "* - 15s"},
            },
            {
                "step_type": "action_log",
                "title": "Black Hole",
                "enabled": 1,
                "config": {"log_tag": "log-only", "note": ""},
            },
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "RF TX target flows"):
                normalize_digi_flow_payload(payload)

    def test_local_tx_to_aprsis_and_black_hole_are_valid(self) -> None:
        with temporary_database():
            insert_aprsis_interface()
            aprsis_normalized = normalize_digi_flow_payload(
                sample_local_tx_flow_payload(name="Local uplink", target_kind="tx_aprsis", target_ref="aprsis")
            )
            self.assertEqual(aprsis_normalized["source_kind"], "receiver_local_tx")
            self.assertEqual(aprsis_normalized["target_kind"], "tx_aprsis")
            self.assertEqual([step["step_type"] for step in aprsis_normalized["steps"]], ["receiver_local_tx", "filter_strict", "tx_aprsis"])

            black_hole_normalized = normalize_digi_flow_payload(
                sample_local_tx_flow_payload(name="Local blackhole", target_kind="action_log", target_ref="log-only")
            )
            self.assertEqual(black_hole_normalized["source_kind"], "receiver_local_tx")
            self.assertEqual(black_hole_normalized["target_kind"], "action_log")
            self.assertEqual([step["step_type"] for step in black_hole_normalized["steps"]], ["receiver_local_tx", "action_log"])

    def test_local_tx_rejects_rf_and_drop_targets(self) -> None:
        with temporary_database():
            rf_payload = sample_local_tx_flow_payload(name="Local to RF", target_kind="tx_rf", target_ref="RF-OUT")
            rf_payload["steps"] = [
                rf_payload["steps"][0],
                {
                    "step_type": "tx_rf",
                    "title": "TX RF",
                    "enabled": 1,
                    "config": {"rf_target": "RF-OUT"},
                },
            ]
            with self.assertRaisesRegex(ValueError, "Local TX source can target only APRS-IS uplink or Black Hole"):
                normalize_digi_flow_payload(rf_payload)

            drop_payload = sample_local_tx_flow_payload(name="Local drop", target_kind="action_drop", target_ref="drop")
            drop_payload["steps"] = [
                drop_payload["steps"][0],
                {
                    "step_type": "action_drop",
                    "title": "Drop",
                    "enabled": 1,
                    "config": {"note": "drop"},
                },
            ]
            with self.assertRaisesRegex(ValueError, "Local TX source can target only APRS-IS uplink or Black Hole"):
                normalize_digi_flow_payload(drop_payload)

    def test_create_enabled_rf_flow_allows_shared_target_when_source_differs(self) -> None:
        with temporary_database():
            create_digi_flow(sample_rf_flow_payload(name="2m to 70cm", source_ref="TNC-2m", target_ref="TNC-70cm"))
            second_flow_id = create_digi_flow(sample_rf_flow_payload(name="70cm to 70cm", source_ref="TNC-70cm", target_ref="TNC-70cm"))
            self.assertIsInstance(second_flow_id, int)

    def test_create_enabled_rf_flow_with_duplicate_source_target_disables_previous_profile(self) -> None:
        with temporary_database():
            first_flow_id = create_digi_flow(sample_rf_flow_payload(name="2m profile A", source_ref="TNC-2m", target_ref="TNC-70cm"))
            second_flow_id = create_digi_flow(sample_rf_flow_payload(name="2m profile B", source_ref="TNC-2m", target_ref="TNC-70cm"))
            first_row = fetch_one("SELECT enabled FROM digi_flows WHERE id = ?", (first_flow_id,))
            second_row = fetch_one("SELECT enabled FROM digi_flows WHERE id = ?", (second_flow_id,))
            assert first_row is not None
            assert second_row is not None
            self.assertEqual(int(first_row["enabled"]), 0)
            self.assertEqual(int(second_row["enabled"]), 1)

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

    def test_enabling_tx_aprsis_flow_without_enabled_strict_guard_is_blocked(self) -> None:
        with temporary_database():
            insert_aprsis_interface()
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
                        "aprsis",
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
                            "filter_strict",
                            "Strict Filter",
                            0,
                            '{}',
                            "2026-01-01T00:00:00+00:00",
                            "2026-01-01T00:00:00+00:00",
                        ),
                        (
                            flow_id,
                            3,
                            "tx_aprsis",
                            "TX APRS-IS",
                            1,
                            '{"aprsis_target":"aprsis"}',
                            "2026-01-01T00:00:00+00:00",
                            "2026-01-01T00:00:00+00:00",
                        ),
                    ),
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaisesRegex(ValueError, "cannot be enabled without a mandatory enabled Strict APRS-IS guard step"):
                set_digi_flow_enabled(flow_id, True)

    def test_enabling_local_tx_aprsis_flow_without_enabled_strict_guard_is_blocked(self) -> None:
        with temporary_database():
            insert_aprsis_interface()
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
                        "Legacy Local TX flow",
                        "",
                        "receiver_local_tx",
                        "local_tx",
                        "tx_aprsis",
                        "aprsis",
                        0,
                        "2026-01-01T00:00:00+00:00",
                        "2026-01-01T00:00:00+00:00",
                    ),
                )
                flow_id = int(connection.execute("SELECT id FROM digi_flows WHERE name = 'Legacy Local TX flow'").fetchone()["id"])
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
                            "receiver_local_tx",
                            "Local TX",
                            1,
                            '{"local_tx_source":"local_tx"}',
                            "2026-01-01T00:00:00+00:00",
                            "2026-01-01T00:00:00+00:00",
                        ),
                        (
                            flow_id,
                            2,
                            "filter_strict",
                            "Strict Filter",
                            0,
                            '{}',
                            "2026-01-01T00:00:00+00:00",
                            "2026-01-01T00:00:00+00:00",
                        ),
                        (
                            flow_id,
                            3,
                            "tx_aprsis",
                            "TX APRS-IS",
                            1,
                            '{"aprsis_target":"aprsis"}',
                            "2026-01-01T00:00:00+00:00",
                            "2026-01-01T00:00:00+00:00",
                        ),
                    ),
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaisesRegex(ValueError, "cannot be enabled without a mandatory enabled Strict APRS-IS guard step"):
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

    def test_enabling_flow_profile_disables_other_enabled_profile_for_same_route_pair(self) -> None:
        with temporary_database():
            active_flow_id = create_digi_flow(sample_rf_flow_payload(name="2m profile A", source_ref="TNC-2m", target_ref="TNC-70cm"))
            standby_flow_id = create_digi_flow(
                sample_rf_flow_payload(name="2m profile B", source_ref="TNC-2m", target_ref="TNC-70cm", enabled=0)
            )
            set_digi_flow_enabled(standby_flow_id, True)
            active_row = fetch_one("SELECT enabled FROM digi_flows WHERE id = ?", (active_flow_id,))
            standby_row = fetch_one("SELECT enabled FROM digi_flows WHERE id = ?", (standby_flow_id,))
            assert active_row is not None
            assert standby_row is not None
            self.assertEqual(int(active_row["enabled"]), 0)
            self.assertEqual(int(standby_row["enabled"]), 1)

    def test_path_filter_allows_only_allow_mode(self) -> None:
        payload = sample_flow_payload()
        payload["target_kind"] = "tx_rf"
        payload["target_ref"] = "RF-OUT"
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
            {
                "step_type": "tx_rf",
                "title": "TX RF",
                "enabled": 1,
                "config": {"rf_target": "RF-OUT"},
            },
        ]
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "Path filter mode must be allow"):
                normalize_digi_flow_payload(payload)


if __name__ == "__main__":
    unittest.main()
