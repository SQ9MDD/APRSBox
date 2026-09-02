import asyncio
import contextlib
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import execute, fetch_all, fetch_one, init_db
from app.services import content
from app.services.aprsis import AprsisClientService
from app.services.aprsis_rf import (
    APRSIS_FLOW_SOURCE_KIND,
    RF_GUARD_DEFAULTS,
    aprsis_rf_guard_reject_reason,
    get_aprsis_rf_stats,
    logical_packet_hash,
    matches_default_deny_filter,
    normalize_default_deny_config,
)
from app.services.content import dashboard_activity_series, dashboard_traffic_summary, parse_tnc2_frame
from app.services.digi_flow_runtime import DigiFlowRuntimeService
from app.services.digi_flows import (
    build_digi_flow_editor_payload,
    create_digi_flow,
    get_digi_flow,
    get_digi_flow_endpoint_options,
    get_digi_flow_execution_summaries,
    get_digi_flow_type_meta,
    normalize_digi_flow_payload,
    set_digi_flow_enabled,
    update_digi_flow,
)
from app.services.outbound import (
    build_aprsis_third_party_tnc2,
    build_tnc2_kiss_frame,
    claim_next_outbound_job,
    get_outbound_job,
)
from app.services.outbound_runtime import OutboundService


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


def insert_interface(
    name: str,
    modem_type: str,
    *,
    enabled: int = 1,
    tx_blocked: int = 0,
) -> int:
    execute(
        """
        INSERT INTO modems(
            name, modem_type, band, device_path, enabled, tx_blocked,
            notes, created_at, updated_at
        )
        VALUES (?, ?, '2m', ?, ?, ?, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (name, modem_type, "127.0.0.1:9001" if modem_type == "TCP" else "", enabled, tx_blocked),
    )
    row = fetch_one("SELECT id FROM modems WHERE name = ?", (name,))
    assert row is not None
    return int(row["id"])


def set_station_identity() -> None:
    execute(
        """
        UPDATE station_settings
        SET callsign = 'SQ9MDD', ssid = '4',
            latitude = '52.2297', longitude = '21.0122',
            updated_at = '2026-01-01T00:00:00+00:00'
        WHERE id = 1
        """
    )


def aprsis_rf_payload(
    *,
    callsigns: list[str] | None = None,
    radius_km: str = "",
    guard_config: dict | None = None,
    include_guard: bool = True,
    include_tx_guard: bool = True,
    include_allow: bool = True,
    enabled: int = 1,
    target_kind: str = "tx_rf",
    target_ref: str = "RF-OUT",
) -> dict:
    steps = [
        {
            "step_type": APRSIS_FLOW_SOURCE_KIND,
            "title": "APRS-IS source",
            "enabled": 1,
            "config": {"aprsis_source": "APRSIS-RX"},
        }
    ]
    if include_guard:
        steps.append(
            {
                "step_type": "filter_rf_guard",
                "title": "APRS-IS Input Guard",
                "enabled": 0,
                "config": {},
            }
        )
    if include_allow:
        steps.append(
            {
                "step_type": "filter_allow_rules",
                "title": "APRS-IS Default Deny Filter",
                "enabled": 1,
                "config": {
                    "callsigns": callsigns or [],
                    "radius_km": radius_km,
                },
            }
        )
    if target_kind == "tx_rf":
        if include_tx_guard:
            steps.append(
                {
                    "step_type": "filter_rf_tx_guard",
                    "title": "RF TX Guard",
                    "enabled": 0,
                    "config": guard_config or dict(RF_GUARD_DEFAULTS),
                }
            )
        steps.append(
            {
                "step_type": "tx_rf",
                "title": "TX RF",
                "enabled": 1,
                "config": {"rf_target": target_ref, "rf_path": "WIDE1-1"},
            }
        )
    elif target_kind == "tx_aprsis":
        steps.append(
            {
                "step_type": "tx_aprsis",
                "title": "TX APRS-IS",
                "enabled": 1,
                "config": {"aprsis_target": target_ref},
            }
        )
    else:
        steps.append(
            {
                "step_type": target_kind,
                "title": "Action",
                "enabled": 1,
                "config": {"log_tag": target_ref} if target_kind == "action_log" else {"note": target_ref},
            }
        )
    return {
        "name": "APRS-IS to RF",
        "description": "Safe iGate flow",
        "source_kind": APRSIS_FLOW_SOURCE_KIND,
        "source_ref": "APRSIS-RX",
        "target_kind": target_kind,
        "target_ref": target_ref,
        "enabled": enabled,
        "steps": steps,
    }


def message_line(*, source: str = "SP5ABC", text: str = "hello", path: str = "TCPIP*,qAC,SERVER") -> str:
    return f"{source}>APRS,{path}::SQ9MDD-7:{text}"


def position_line(
    *,
    source: str = "SP5ABC",
    latitude: str = "5213.78N",
    longitude: str = "02100.72E",
    text: str = "Test",
    path: str = "TCPIP*,qAR,IGATE",
) -> str:
    return f"{source}>APRS,{path}:!{latitude}/{longitude}>{text}"


class AprsisRfModelTests(unittest.TestCase):
    def test_aprsis_source_guard_palette_and_frontend_locks_are_available(self) -> None:
        with temporary_database():
            insert_interface("APRSIS-RX", "APRSIS")
            insert_interface("RF-OUT", "TCP")
            options = get_digi_flow_endpoint_options()
            source_values = {option["value"] for option in options["source"]}
            aprsis_targets = {option["value"] for option in options["target_by_source_kind"][APRSIS_FLOW_SOURCE_KIND]}
            self.assertIn("receiver_aprsis::APRSIS-RX", source_values)
            self.assertIn("tx_rf::RF-OUT", aprsis_targets)
            self.assertNotIn("tx_aprsis::aprsis", aprsis_targets)
            self.assertIn("filter_rf_guard", get_digi_flow_type_meta())
            self.assertIn("filter_rf_tx_guard", get_digi_flow_type_meta())
            default_deny_meta = get_digi_flow_type_meta()["filter_allow_rules"]
            self.assertEqual(default_deny_meta["label"], "APRS-IS Callsign and Radius Rule")
            self.assertEqual(default_deny_meta["badge"], "Rule")
            self.assertEqual(default_deny_meta["scope_label"], "APRS-IS → RF")
            self.assertEqual(default_deny_meta["scope_tone"], "aprsis-to-rf")
            self.assertEqual(
                [field["name"] for field in default_deny_meta["config_fields"]],
                ["callsigns", "radius_km"],
            )

        template = Path("app/templates/digi_flow_form.html").read_text(encoding="utf-8")
        self.assertIn("filter_rf_guard", template)
        self.assertIn("filter_aprsis_message_delivery", template)
        self.assertIn("filter_rf_tx_guard", template)
        self.assertNotIn("rf_sources", template)
        self.assertNotIn("heard_window_minutes", template)
        self.assertNotIn("max_consumed_hops", template)
        self.assertIn("rfGuardSystemManaged", template)
        self.assertIn("const isStrictAprsisToRfFlow = () => isAprsisSourceFlow() && isTxRfTargetFlow();", template)
        self.assertIn("button.hidden = strictAprsisToRf && !isAprsisSourceSystemStepType(stepType);", template)
        self.assertIn("if (isStrictAprsisToRfFlow())", template)
        self.assertIn("const aprsisSourceSystemStep = isAprsisSourceFlow() && isAprsisSourceSystemStepType", template)
        self.assertIn('clearCallsignsAndRadius: {{ t("Clear callsigns and radius")|tojson }}', template)
        self.assertIn('step.config.callsigns = [];', template)
        self.assertIn('step.config.radius_km = "";', template)
        self.assertIn("return i18n.messageOnlyMode;", template)
        self.assertNotIn("data.allowRulesEmpty", template.replace("dataset", "data"))
        self.assertNotIn("data.addAllowRule", template.replace("dataset", "data"))
        self.assertNotIn('["packet_type", i18n.packetType', template)
        self.assertNotIn('["destination", i18n.destination', template)
        self.assertNotIn('["addressee", i18n.addressee', template)
        self.assertNotIn('["object_name", i18n.objectName', template)
        self.assertNotIn('["icon", i18n.icon', template)
        self.assertNotIn('["center_latitude", i18n.centerLatitude', template)
        self.assertNotIn('["center_longitude", i18n.centerLongitude', template)
        polish_catalog = Path("app/languages/pl.json").read_text(encoding="utf-8")
        self.assertIn("Warunki dokładnego znaku i promienia są połączone operatorem AND.", polish_catalog)

    def test_backend_adds_one_enabled_guard_and_empty_allow_rules(self) -> None:
        with temporary_database():
            insert_interface("APRSIS-RX", "APRSIS")
            insert_interface("RF-OUT", "TCP")
            normalized = normalize_digi_flow_payload(
                aprsis_rf_payload(include_guard=False, include_tx_guard=False, include_allow=False)
            )
            types = [step["step_type"] for step in normalized["steps"]]
            self.assertEqual(
                types,
                [
                    "receiver_aprsis",
                    "filter_rf_guard",
                    "filter_aprsis_message_delivery",
                    "filter_allow_rules",
                    "filter_rf_tx_guard",
                    "tx_rf",
                ],
            )
            input_guard = normalized["steps"][1]
            self.assertEqual(input_guard["enabled"], 1)
            self.assertEqual(input_guard["config"], {})
            self.assertEqual(
                normalized["steps"][2]["config"],
                {},
            )
            self.assertEqual(normalized["steps"][3]["config"], {"callsigns": [], "radius_km": ""})
            self.assertEqual(normalized["steps"][4]["config"], RF_GUARD_DEFAULTS)

            flow_id = create_digi_flow(
                aprsis_rf_payload(include_guard=False, include_tx_guard=False, include_allow=False)
            )
            set_digi_flow_enabled(flow_id, True)
            self.assertEqual(int(get_digi_flow(flow_id)["enabled"]), 1)

    def test_existing_callsign_and_radius_rule_can_be_cleared_for_message_only_mode(self) -> None:
        with temporary_database():
            insert_interface("APRSIS-RX", "APRSIS")
            insert_interface("RF-OUT", "TCP")
            flow_id = create_digi_flow(
                aprsis_rf_payload(callsigns=["SP5ABC"], radius_km="25")
            )

            update_digi_flow(
                flow_id,
                aprsis_rf_payload(callsigns=[], radius_km=""),
            )

            flow = get_digi_flow(flow_id)
            allow_step = next(
                step for step in flow["steps"] if step["step_type"] == "filter_allow_rules"
            )
            self.assertEqual(allow_step["config"], {"callsigns": [], "radius_km": ""})
            self.assertEqual(int(flow["enabled"]), 1)

    def test_backend_reorders_guard_before_rules_and_rejects_duplicates_or_non_aprs_flow(self) -> None:
        with temporary_database():
            insert_interface("APRSIS-RX", "APRSIS")
            insert_interface("RF-OUT", "TCP")
            payload = aprsis_rf_payload(callsigns=["SP5ABC"], radius_km="25")
            payload["steps"][1], payload["steps"][2] = payload["steps"][2], payload["steps"][1]
            normalized = normalize_digi_flow_payload(payload)
            self.assertEqual(normalized["steps"][1]["step_type"], "filter_rf_guard")
            self.assertEqual(normalized["steps"][2]["step_type"], "filter_aprsis_message_delivery")
            self.assertEqual(normalized["steps"][3]["step_type"], "filter_allow_rules")
            self.assertEqual(normalized["steps"][-2]["step_type"], "filter_rf_tx_guard")

            duplicate = aprsis_rf_payload()
            duplicate["steps"].insert(2, dict(duplicate["steps"][1]))
            with self.assertRaisesRegex(ValueError, "only one Input Guard"):
                normalize_digi_flow_payload(duplicate)

            duplicate_tx_guard = aprsis_rf_payload()
            duplicate_tx_guard["steps"].insert(-1, dict(duplicate_tx_guard["steps"][-2]))
            with self.assertRaisesRegex(ValueError, "only one RF TX Guard"):
                normalize_digi_flow_payload(duplicate_tx_guard)

            additional_filter = aprsis_rf_payload()
            additional_filter["steps"].insert(
                -1,
                {
                    "step_type": "filter_callsign",
                    "title": "Source Callsign Filter",
                    "enabled": 1,
                    "config": {"mode": "allow", "callsigns": ["SP5ABC"]},
                },
            )
            with self.assertRaisesRegex(ValueError, "cannot include additional filters or rules"):
                normalize_digi_flow_payload(additional_filter)

            restricted_flow_id = create_digi_flow(aprsis_rf_payload(enabled=0))
            execute(
                "UPDATE digi_flow_steps SET step_order = 7 WHERE flow_id = ? AND step_type = 'tx_rf'",
                (restricted_flow_id,),
            )
            execute(
                """
                INSERT INTO digi_flow_steps(
                    flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                )
                VALUES (?, 6, 'filter_callsign', 'Source Callsign Filter', 1, ?, ?, ?)
                """,
                (
                    restricted_flow_id,
                    json.dumps({"mode": "allow", "callsigns": ["SP5ABC"]}),
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            with self.assertRaisesRegex(ValueError, "cannot include additional filters or rules"):
                set_digi_flow_enabled(restricted_flow_id, True)

            non_aprs = aprsis_rf_payload()
            non_aprs.update(source_kind="receiver_rf", source_ref="RF-IN")
            non_aprs["steps"][0] = {
                "step_type": "receiver_rf",
                "title": "Receiver RF",
                "enabled": 1,
                "config": {"rf_port": "RF-IN"},
            }
            with self.assertRaisesRegex(ValueError, "only with an APRS-IS source"):
                normalize_digi_flow_payload(non_aprs)

    def test_backend_rejects_aprsis_target_rx_only_disabled_and_tx_blocked_targets(self) -> None:
        with temporary_database():
            insert_interface("APRSIS-RX", "APRSIS")
            insert_interface("RF-OUT", "TCP")
            insert_interface("RX-ONLY", "OPENWEBRX_MQTT")
            insert_interface("RF-DISABLED", "TCP", enabled=0)
            insert_interface("RF-BLOCKED", "TCP", tx_blocked=1)

            with self.assertRaisesRegex(ValueError, "APRS-IS source can target only"):
                normalize_digi_flow_payload(
                    aprsis_rf_payload(target_kind="tx_aprsis", target_ref="aprsis")
                )
            for target in ("RX-ONLY", "RF-DISABLED", "RF-BLOCKED"):
                with self.assertRaisesRegex(ValueError, "not a usable active physical TX interface"):
                    normalize_digi_flow_payload(aprsis_rf_payload(target_ref=target))

            invalid_source = aprsis_rf_payload()
            invalid_source["source_ref"] = "RF-OUT"
            invalid_source["steps"][0]["config"]["aprsis_source"] = "RF-OUT"
            with self.assertRaisesRegex(ValueError, "existing APRSIS interface"):
                normalize_digi_flow_payload(invalid_source)

    def test_guard_limits_and_outbound_rf_path_are_validated_on_backend(self) -> None:
        with temporary_database():
            insert_interface("APRSIS-RX", "APRSIS")
            insert_interface("RF-OUT", "TCP")
            invalid_guard = aprsis_rf_payload(guard_config={**RF_GUARD_DEFAULTS, "flow_burst": 0})
            with self.assertRaisesRegex(ValueError, "flow_burst must be between"):
                normalize_digi_flow_payload(invalid_guard)

            invalid_path = aprsis_rf_payload()
            invalid_path["steps"][-1]["config"]["rf_path"] = "WIDE2-2*"
            with self.assertRaisesRegex(ValueError, "invalid address"):
                normalize_digi_flow_payload(invalid_path)

    def test_editor_repairs_missing_guards_without_changing_database_or_rules(self) -> None:
        with temporary_database():
            insert_interface("APRSIS-RX", "APRSIS")
            insert_interface("RF-OUT", "TCP")
            filter_config = {"callsigns": ["SP5ABC", "SP5ABC-1"], "radius_km": "25"}
            flow_id = create_digi_flow(aprsis_rf_payload(**filter_config))
            guard = fetch_one(
                "SELECT id FROM digi_flow_steps WHERE flow_id = ? AND step_type = 'filter_rf_guard'",
                (flow_id,),
            )
            execute("DELETE FROM digi_flow_steps WHERE id = ?", (int(guard["id"]),))
            execute(
                """
                INSERT INTO digi_flow_steps(
                    flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                )
                VALUES (?, 2, 'filter_callsign', 'Source Callsign Filter', 1, ?, ?, ?)
                """,
                (
                    flow_id,
                    json.dumps({"mode": "allow", "callsigns": ["SP5ABC"]}),
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            flow = get_digi_flow(flow_id)
            editor = build_digi_flow_editor_payload(flow)
            self.assertEqual(editor["steps"][1]["step_type"], "filter_rf_guard")
            self.assertEqual(editor["steps"][-2]["step_type"], "filter_rf_tx_guard")
            allow = next(step for step in editor["steps"] if step["step_type"] == "filter_allow_rules")
            self.assertEqual(allow["config"], filter_config)
            self.assertNotIn("filter_callsign", [step["step_type"] for step in editor["steps"]])
            self.assertIsNone(fetch_one(
                "SELECT id FROM digi_flow_steps WHERE flow_id = ? AND step_type = 'filter_rf_guard'",
                (flow_id,),
            ))

    def test_database_migrates_legacy_combined_guard_to_two_ordered_guards(self) -> None:
        with temporary_database():
            insert_interface("APRSIS-RX", "APRSIS")
            insert_interface("RF-OUT", "TCP")
            flow_id = create_digi_flow(aprsis_rf_payload())
            legacy_config = {
                **RF_GUARD_DEFAULTS,
                "flow_rate_per_minute": 9,
                "source_rate_per_minute": 4,
            }
            execute(
                """
                UPDATE digi_flow_steps
                SET title = 'RF Guard', config_json = ?
                WHERE flow_id = ? AND step_type = 'filter_rf_guard'
                """,
                (json.dumps(legacy_config), flow_id),
            )
            execute(
                """
                DELETE FROM digi_flow_steps
                WHERE flow_id = ?
                  AND step_type IN (
                      'filter_aprsis_message_delivery',
                      'filter_allow_rules',
                      'filter_rf_tx_guard'
                  )
                """,
                (flow_id,),
            )

            init_db()

            flow = get_digi_flow(flow_id)
            self.assertEqual(
                [step["step_type"] for step in flow["steps"]],
                [
                    "receiver_aprsis",
                    "filter_rf_guard",
                    "filter_aprsis_message_delivery",
                    "filter_allow_rules",
                    "filter_rf_tx_guard",
                    "tx_rf",
                ],
            )
            self.assertEqual(flow["steps"][1]["title"], "APRS-IS Input Safety Rule")
            self.assertEqual(flow["steps"][1]["config"], {})
            self.assertEqual(flow["steps"][2]["title"], "APRS-IS Message Delivery Rule")
            self.assertEqual(
                flow["steps"][2]["config"],
                {},
            )
            self.assertEqual(flow["steps"][4]["title"], "APRS-IS to RF TX Safety Rule")
            self.assertEqual(flow["steps"][4]["config"], legacy_config)
            migrated_updated_at = flow["updated_at"]

            init_db()
            idempotent_flow = get_digi_flow(flow_id)
            self.assertEqual(idempotent_flow["updated_at"], migrated_updated_at)
            self.assertEqual(
                sum(1 for step in idempotent_flow["steps"] if step["step_type"] == "filter_rf_tx_guard"),
                1,
            )
            self.assertEqual(
                sum(
                    1
                    for step in idempotent_flow["steps"]
                    if step["step_type"] == "filter_aprsis_message_delivery"
                ),
                1,
            )

            execute(
                """
                UPDATE digi_flow_steps
                SET config_json = ?
                WHERE flow_id = ? AND step_type = 'filter_aprsis_message_delivery'
                """,
                (
                    json.dumps(
                        {
                            "rf_sources": ["RF-OUT"],
                            "heard_window_minutes": 15,
                            "max_consumed_hops": 2,
                        }
                    ),
                    flow_id,
                ),
            )
            init_db()
            normalized_legacy_flow = get_digi_flow(flow_id)
            message_step = next(
                step
                for step in normalized_legacy_flow["steps"]
                if step["step_type"] == "filter_aprsis_message_delivery"
            )
            self.assertEqual(message_step["config"], {})


class AprsisRfRuleAndProtocolTests(unittest.TestCase):
    def test_default_deny_filter_uses_exact_callsign_and_my_station_radius_as_and(self) -> None:
        parsed = parse_tnc2_frame(position_line(source="SP5ABC-1"))
        station = {"latitude": "52.2297", "longitude": "21.0122"}
        config = normalize_default_deny_config(
            {"callsigns": ["sp5abc", "sp5abc-1"], "radius_km": "2"}
        )
        self.assertEqual(config, {"callsigns": ["SP5ABC", "SP5ABC-1"], "radius_km": "2"})
        self.assertTrue(matches_default_deny_filter(parsed, config, station))

        callsign_without_ssid = normalize_default_deny_config(
            {"callsigns": ["SP5ABC"], "radius_km": "2"}
        )
        self.assertFalse(matches_default_deny_filter(parsed, callsign_without_ssid, station))

        too_small_radius = normalize_default_deny_config(
            {"callsigns": ["SP5ABC-1"], "radius_km": "0.01"}
        )
        self.assertFalse(matches_default_deny_filter(parsed, too_small_radius, station))

    def test_default_deny_filter_rejects_wildcards_removed_fields_and_partial_config(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact AX.25 callsign"):
            normalize_default_deny_config({"callsigns": ["SP5*"], "radius_km": "25"})
        with self.assertRaisesRegex(ValueError, "unsupported fields: packet_type"):
            normalize_default_deny_config(
                {"callsigns": ["SP5ABC"], "radius_km": "25", "packet_type": "position"}
            )
        with self.assertRaisesRegex(ValueError, "requires both callsigns and radius_km"):
            normalize_default_deny_config({"callsigns": ["SP5ABC"]})
        with self.assertRaisesRegex(ValueError, "requires both callsigns and radius_km"):
            normalize_default_deny_config({"radius_km": "25"})

    def test_default_deny_filter_rejects_missing_packet_or_my_station_position(self) -> None:
        config = normalize_default_deny_config({"callsigns": ["SP5ABC"], "radius_km": "25"})
        self.assertFalse(
            matches_default_deny_filter(parse_tnc2_frame(message_line()), config, {
                "latitude": "52.2297",
                "longitude": "21.0122",
            })
        )
        self.assertFalse(
            matches_default_deny_filter(parse_tnc2_frame(position_line()), config, {})
        )
        self.assertFalse(matches_default_deny_filter(parse_tnc2_frame(position_line()), {}, {}))

    def test_guard_blocks_markers_bad_q_and_third_party_but_not_tcpip(self) -> None:
        expected = {
            "NOGATE": "blocked_nogate",
            "RFONLY": "blocked_rfonly",
            "TCPXX": "blocked_tcpxx",
        }
        for marker, reason in expected.items():
            parsed = parse_tnc2_frame(message_line(path=f"{marker},qAR,IGATE"))
            self.assertEqual(aprsis_rf_guard_reject_reason(parsed), reason)

        self.assertIsNone(aprsis_rf_guard_reject_reason(parse_tnc2_frame(message_line())))
        self.assertEqual(
            aprsis_rf_guard_reject_reason(parse_tnc2_frame(message_line(path="TCPIP*,qAZ,SERVER"))),
            "invalid_q_construct",
        )
        third_party = parse_tnc2_frame("IGATE>APRS,TCPIP*,qAR,SERVER:}SP5ABC>APRS,TCPIP,IGATE*:>status")
        self.assertIn(aprsis_rf_guard_reject_reason(third_party), {"invalid_third_party", "recursive_third_party"})

    def test_logical_duplicate_hash_ignores_rf_and_aprsis_paths(self) -> None:
        aprsis = parse_tnc2_frame(message_line(path="TCPIP*,qAR,SERVER", text="same{42"))
        rf = parse_tnc2_frame("SP5ABC>APRS,WIDE1-1*,WIDE2-1::SQ9MDD-7:same{42")
        self.assertEqual(logical_packet_hash(aprsis), logical_packet_hash(rf))

    def test_third_party_builder_removes_is_path_and_preserves_payload_and_message_id(self) -> None:
        parsed = parse_tnc2_frame(message_line(text="hello{123"))
        line = build_aprsis_third_party_tnc2(
            parsed,
            igate_callsign="SQ9MDD-4",
            rf_path="WIDE1-1",
        )
        self.assertEqual(
            line,
            "SQ9MDD-4>APBOX0,WIDE1-1:}SP5ABC>APRS,TCPIP,SQ9MDD-4*::SQ9MDD-7:hello{123",
        )
        self.assertNotIn("qAC", line)
        self.assertNotIn("SERVER", line)

    def test_third_party_builder_rejects_oversize_without_truncating(self) -> None:
        parsed = parse_tnc2_frame(message_line(text="x" * 250))
        with self.assertRaisesRegex(ValueError, "packet_too_long"):
            build_aprsis_third_party_tnc2(parsed, igate_callsign="SQ9MDD-4")

    def test_aprsis_utf8_payload_is_transliterated_to_ascii_before_rf_tx(self) -> None:
        incoming = (
            "SQ5TM-1>AESPG4,TCPIP*,qAC,T2FINLAND:"
            "@231411z5214.39N/02054.94E_WX Gorce T=27° H=44% P=997 "
            "PM 1:[0] , 2.5:[1] , 10:[1] (μg/m3)"
        )
        parsed = parse_tnc2_frame(incoming)
        line = build_aprsis_third_party_tnc2(parsed, igate_callsign="SQ9MDD-4")

        self.assertEqual(
            line,
            "SQ9MDD-4>APBOX0:}SQ5TM-1>AESPG4,TCPIP,SQ9MDD-4*:"
            "@231411z5214.39N/02054.94E_WX Gorce T=27deg H=44% P=997 "
            "PM 1:[0] , 2.5:[1] , 10:[1] (ug/m3)",
        )
        self.assertTrue(line.isascii())
        frame = build_tnc2_kiss_frame(line)
        self.assertEqual(frame[18:-1].decode("ascii"), line.split(":", 1)[1])

    def test_third_party_builder_checks_size_after_transliteration(self) -> None:
        inner_prefix = "}SP5ABC>APRS,TCPIP,SQ9MDD-4*:"
        payload_at_limit = ("x" * (256 - len(inner_prefix) - len("deg"))) + "°"
        line = build_aprsis_third_party_tnc2(
            parse_tnc2_frame(f"SP5ABC>APRS:{payload_at_limit}"),
            igate_callsign="SQ9MDD-4",
        )
        self.assertEqual(len(line.split(":", 1)[1].encode("ascii")), 256)

        oversized_payload = f"x{payload_at_limit}"
        with self.assertRaisesRegex(ValueError, "packet_too_long"):
            build_aprsis_third_party_tnc2(
                parse_tnc2_frame(f"SP5ABC>APRS:{oversized_payload}"),
                igate_callsign="SQ9MDD-4",
            )

    def test_aprsis_client_decodes_valid_utf8_before_packet_routing(self) -> None:
        received: list[tuple[tuple, dict]] = []
        service = AprsisClientService(
            rx_processor=lambda *_args, **_kwargs: True,
            frame_consumer=lambda *args, **kwargs: received.append((args, kwargs)),
        )
        service._desired_rx_interface = {"id": 9, "name": "APRSIS-RX", "filter": "m/20"}
        raw_line = "SP5ABC>APRS,TCPIP*,qAC,SERVER:>T=27° (μg/m3)\r\n".encode("utf-8")

        self.assertTrue(service._process_server_line(raw_line))
        self.assertEqual(received[0][0][0], "SP5ABC>APRS,TCPIP*,qAC,SERVER:>T=27° (μg/m3)")
        self.assertEqual(received[0][1]["metadata"]["payload"], ">T=27° (μg/m3)")

    def test_aprsis_client_dispatches_parsed_metadata_without_creating_rf_rx(self) -> None:
        received: list[tuple[tuple, dict]] = []
        service = AprsisClientService(
            rx_processor=lambda *_args, **_kwargs: True,
            frame_consumer=lambda *args, **kwargs: received.append((args, kwargs)),
        )
        service._desired_rx_interface = {"id": 9, "name": "APRSIS-RX", "filter": "m/20"}
        self.assertTrue(service._process_server_line(message_line(text="metadata{77")))
        self.assertEqual(len(received), 1)
        _args, kwargs = received[0]
        metadata = kwargs["metadata"]
        self.assertEqual(metadata["source_type"], "APRSIS")
        self.assertEqual(metadata["source_callsign"], "SP5ABC")
        self.assertEqual(metadata["destination"], "APRS")
        self.assertEqual(metadata["q_construct"], "qAC")
        self.assertFalse(metadata["is_third_party"])


class AprsisRfRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = temporary_database()
        self.database.__enter__()
        insert_interface("APRSIS-RX", "APRSIS")
        self.target_id = insert_interface("RF-OUT", "TCP")
        set_station_identity()

    async def asyncTearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def create_flow(
        self,
        *,
        callsigns: list[str] | None = None,
        radius_km: str = "25",
        guard_config: dict | None = None,
    ) -> int:
        return create_digi_flow(
            aprsis_rf_payload(
                callsigns=["SP5ABC"] if callsigns is None else callsigns,
                radius_km=radius_km,
                guard_config=guard_config,
            )
        )

    async def run_lines(self, *lines: str, delay: float = 0.01) -> tuple[DigiFlowRuntimeService, list[dict]]:
        runtime = DigiFlowRuntimeService(aprsis_rf_delay_override=delay)
        await runtime.start()
        frames: list[dict] = []
        for line in lines:
            frames.append(
                runtime.enqueue_tnc2_frame(
                    source_kind=APRSIS_FLOW_SOURCE_KIND,
                    source_ref="APRSIS-RX",
                    raw_payload=line,
                    metadata={"aprsis_interface_id": 1},
                )
            )
        await runtime.wait_until_idle()
        await runtime.stop()
        return runtime, frames

    async def test_aprsis_flow_uses_routing_snapshot_for_station_and_target(self) -> None:
        self.create_flow(callsigns=["SP5ABC"], radius_km="2")
        runtime = DigiFlowRuntimeService(aprsis_rf_delay_override=0)
        await runtime.start()
        try:
            with patch("app.services.digi_flow_runtime.get_station_settings", create=True) as station_read:
                with patch("app.services.aprsis_rf.fetch_one") as modem_read:
                    with patch("app.services.igate_messaging.fetch_all") as active_modems_read:
                        runtime.enqueue_tnc2_frame(
                            source_kind=APRSIS_FLOW_SOURCE_KIND,
                            source_ref="APRSIS-RX",
                            raw_payload=position_line(),
                        )
                        runtime.enqueue_tnc2_frame(
                            source_kind=APRSIS_FLOW_SOURCE_KIND,
                            source_ref="APRSIS-RX",
                            raw_payload=message_line(),
                        )
                        await runtime.wait_until_idle()
            station_read.assert_not_called()
            modem_read.assert_not_called()
            active_modems_read.assert_not_called()
        finally:
            await runtime.stop()

    async def test_aprsis_stat_persistence_does_not_hold_digiflow_worker(self) -> None:
        self.create_flow(callsigns=[], radius_km="")
        persistence_started = threading.Event()
        release_persistence = threading.Event()

        def slow_persist(*_args, **_kwargs) -> None:
            persistence_started.set()
            release_persistence.wait(timeout=1.0)

        runtime = DigiFlowRuntimeService(aprsis_rf_delay_override=0)
        await runtime.start()
        try:
            with patch("app.services.digi_flow_runtime.record_aprsis_rf_stat", side_effect=slow_persist):
                runtime.enqueue_tnc2_frame(
                    source_kind=APRSIS_FLOW_SOURCE_KIND,
                    source_ref="APRSIS-RX",
                    raw_payload=position_line(),
                )
                await asyncio.wait_for(runtime._queue.join(), timeout=0.25)
                await asyncio.wait_for(asyncio.to_thread(persistence_started.wait), timeout=1.0)
                release_persistence.set()
                await runtime.wait_until_idle()
        finally:
            release_persistence.set()
            await runtime.stop()

    async def test_empty_filter_is_valid_and_default_deny_without_pending_or_job(self) -> None:
        flow_id = self.create_flow(callsigns=[], radius_km="")
        _runtime, frames = await self.run_lines(position_line())
        stats = get_aprsis_rf_stats(flow_id)
        self.assertEqual(stats["received_from_aprsis"], 1)
        self.assertEqual(stats["dropped_no_allow_rule"], 1)
        self.assertEqual(stats["queued_to_rf"], 0)
        self.assertIsNone(fetch_one("SELECT id FROM outbound_jobs LIMIT 1"))
        events = fetch_all(
            "SELECT message FROM digi_flow_event_log WHERE frame_uid = ?",
            (frames[0]["frame_uid"],),
        )
        self.assertTrue(any("default_deny_filter_mismatch" in row["message"] for row in events))

    async def test_matching_callsign_and_radius_queue_existing_digi_tx_job_with_origin_metadata(self) -> None:
        flow_id = self.create_flow(callsigns=["SP5ABC"], radius_km="2")
        _runtime, frames = await self.run_lines(position_line(text="queue{123"))
        row = fetch_one("SELECT kind, payload_json FROM outbound_jobs ORDER BY id DESC LIMIT 1")
        self.assertIsNotNone(row)
        self.assertEqual(row["kind"], "digi_tx")
        payload = json.loads(row["payload_json"])
        self.assertEqual(payload["origin"], "aprsis_to_rf")
        self.assertEqual(payload["flow_id"], flow_id)
        self.assertEqual(payload["target_interface_id"], self.target_id)
        self.assertTrue(payload["normalized_packet_hash"])
        self.assertIn("}SP5ABC>APRS,TCPIP,SQ9MDD-4*:!5213.78N/02100.72E>queue{123", payload["line"])
        stats = get_aprsis_rf_stats(flow_id)
        self.assertEqual(stats["matched_allow_rule"], 1)
        self.assertEqual(stats["queued_to_rf"], 1)

        summaries = get_digi_flow_execution_summaries(flow_id)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["frame_uid"], frames[0]["frame_uid"])
        self.assertEqual(summaries[0]["final_result"], "TX")
        self.assertEqual(
            [step["status"] for step in summaries[0]["steps"]],
            ["passed", "passed", "skipped", "passed", "passed", "executed"],
        )
        self.assertIn("APRS-IS Input Safety Rule passed", summaries[0]["steps"][1]["description"])
        self.assertIn("not message traffic", summaries[0]["steps"][2]["description"])
        self.assertIn("Callsign and Radius Rule matched exact callsign AND radius", summaries[0]["steps"][3]["description"])
        self.assertIn("APRS-IS to RF TX Safety Rule passed final", summaries[0]["steps"][4]["description"])

    async def test_execution_summary_marks_rejected_default_deny_step_as_reached(self) -> None:
        flow_id = self.create_flow(callsigns=[], radius_km="")
        _runtime, frames = await self.run_lines(position_line(text="blocked"))

        summaries = get_digi_flow_execution_summaries(flow_id)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["frame_uid"], frames[0]["frame_uid"])
        self.assertEqual(summaries[0]["final_result"], "REJECTED")
        self.assertEqual(
            [step["status"] for step in summaries[0]["steps"]],
            ["passed", "passed", "skipped", "rejected", "not_reached", "not_reached"],
        )
        self.assertIn("default_deny_filter_mismatch", summaries[0]["steps"][3]["description"])

    async def test_tx_queue_failure_happens_after_rf_tx_guard_passes(self) -> None:
        flow_id = self.create_flow()
        with patch(
            "app.services.digi_flow_runtime.enqueue_digi_tx_job",
            return_value=(False, "queue_unavailable"),
        ):
            _runtime, _frames = await self.run_lines(position_line(text="queue failure"))

        summary = get_digi_flow_execution_summaries(flow_id)[0]
        self.assertEqual(summary["final_result"], "DROPPED")
        self.assertEqual(summary["steps"][-2]["status"], "passed")
        self.assertIn("APRS-IS to RF TX Safety Rule passed final", summary["steps"][-2]["description"])
        self.assertEqual(summary["steps"][-1]["status"], "executed")
        self.assertIn("queue_unavailable", summary["steps"][-1]["description"])
        self.assertEqual(get_aprsis_rf_stats(flow_id)["tx_failed"], 1)

    async def test_invalid_input_marks_receiver_reached_before_input_guard_rejects(self) -> None:
        flow_id = self.create_flow()
        _runtime, frames = await self.run_lines(
            "SN5S-S>APDG01,TCPIP*,qAC,SN5S-GS:;SN5S B *231306z5213.77NW02057.15EiRNG0001"
        )

        summary = get_digi_flow_execution_summaries(flow_id)[0]
        self.assertEqual(summary["frame_uid"], frames[0]["frame_uid"])
        self.assertEqual(summary["final_result"], "REJECTED")
        self.assertEqual(
            [step["status"] for step in summary["steps"]],
            ["passed", "rejected", "not_reached", "not_reached", "not_reached", "not_reached"],
        )
        self.assertIn("invalid_aprs", summary["steps"][1]["description"])

    async def test_existing_outbound_transport_records_separate_transmit_stat_and_source_kind(self) -> None:
        flow_id = self.create_flow()
        await self.run_lines(position_line(text="physical tx"))
        job = claim_next_outbound_job()
        self.assertIsNotNone(job)
        written_frames: list[bytes] = []

        class FakeWriter:
            def write(self, data: bytes) -> None:
                written_frames.append(data)

            async def drain(self) -> None:
                return None

            def close(self) -> None:
                return None

            async def wait_closed(self) -> None:
                return None

        async def fake_open_connection(_host: str, _port: int):
            return object(), FakeWriter()

        with patch("app.services.outbound_runtime.asyncio.open_connection", side_effect=fake_open_connection):
            await OutboundService()._process_job(job)

        self.assertTrue(written_frames)
        self.assertEqual(get_outbound_job(int(job["id"]))["status"], "sent")
        traffic = fetch_one("SELECT source_kind, direction FROM traffic_frames ORDER BY id DESC LIMIT 1")
        self.assertEqual(traffic["source_kind"], "aprsis_to_rf")
        self.assertEqual(traffic["direction"], "tx")
        self.assertEqual(get_aprsis_rf_stats(flow_id)["transmitted_to_rf"], 1)
        content._TRAFFIC_SNAPSHOT_CACHE.clear()
        self.assertEqual(dashboard_traffic_summary()["decoded_aprs"], 0)
        self.assertEqual(dashboard_activity_series()["totals"]["tx"], 0)

    async def test_outbound_target_loss_records_tx_failed(self) -> None:
        flow_id = self.create_flow()
        await self.run_lines(position_line(text="target disappears"))
        execute("UPDATE modems SET enabled = 0 WHERE id = ?", (self.target_id,))
        job = claim_next_outbound_job()
        self.assertIsNotNone(job)
        self.assertEqual(job["payload"]["origin"], "aprsis_to_rf")
        service = OutboundService()
        self.assertEqual(service._aprsis_rf_target_reject_reason(self.target_id), "target_unavailable")
        await service._process_job(job)
        completed_job = get_outbound_job(int(job["id"]))
        self.assertEqual(completed_job["status"], "sent")
        self.assertEqual(completed_job["last_error"], "target_unavailable")
        self.assertEqual(get_aprsis_rf_stats(flow_id)["tx_failed"], 1)

    async def test_same_aprsis_frame_is_not_added_twice_to_pending(self) -> None:
        flow_id = self.create_flow()
        await self.run_lines(position_line(text="same{12"), position_line(text="same{12"), delay=0.03)
        count = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs")
        self.assertEqual(int(count["total"]), 1)
        stats = get_aprsis_rf_stats(flow_id)
        self.assertEqual(stats["dropped_duplicate"], 1)

    async def test_rf_copy_during_viscous_delay_cancels_pending_even_with_other_path(self) -> None:
        flow_id = self.create_flow()
        runtime = DigiFlowRuntimeService(aprsis_rf_delay_override=0.05)
        await runtime.start()
        try:
            runtime.enqueue_tnc2_frame(
                source_kind=APRSIS_FLOW_SOURCE_KIND,
                source_ref="APRSIS-RX",
                raw_payload=position_line(text="cancel{45"),
            )
            await runtime._queue.join()
            runtime.enqueue_rx_tnc2_frame(
                "SP5ABC>APRS,WIDE1-1*,WIDE2-1:!5213.78N/02100.72E>cancel{45",
                source_ref="TNC@RF-OUT",
            )
            await runtime.wait_until_idle()
        finally:
            await runtime.stop()
        self.assertIsNone(fetch_one("SELECT id FROM outbound_jobs LIMIT 1"))
        self.assertEqual(get_aprsis_rf_stats(flow_id)["cancelled_during_viscous_delay"], 1)

    async def test_runtime_guard_still_applies_when_guard_row_was_manually_deleted(self) -> None:
        flow_id = self.create_flow()
        execute(
            "DELETE FROM digi_flow_steps WHERE flow_id = ? AND step_type = 'filter_rf_guard'",
            (flow_id,),
        )
        await self.run_lines(position_line(path="NOGATE,qAR,IGATE"))
        self.assertIsNone(fetch_one("SELECT id FROM outbound_jobs LIMIT 1"))
        stats = get_aprsis_rf_stats(flow_id)
        self.assertEqual(stats["dropped_safety_guard"], 1)

    async def test_flow_and_source_token_buckets_drop_without_growing_queue(self) -> None:
        flow_config = {
            **RF_GUARD_DEFAULTS,
            "flow_burst": 1,
            "source_burst": 5,
            "source_rate_per_minute": 30,
        }
        flow_id = self.create_flow(callsigns=["SP5AAA", "SP5BBB"], guard_config=flow_config)
        await self.run_lines(
            position_line(source="SP5AAA", text="one"),
            position_line(source="SP5BBB", text="two"),
        )
        self.assertEqual(get_aprsis_rf_stats(flow_id)["dropped_rate_limit"], 1)
        self.assertEqual(int(fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs")["total"]), 1)
        rejected = next(
            summary
            for summary in get_digi_flow_execution_summaries(flow_id)
            if summary["final_result"] == "REJECTED"
        )
        self.assertEqual(rejected["steps"][-2]["step_type"], "filter_rf_tx_guard")
        self.assertEqual(rejected["steps"][-2]["status"], "rejected")
        self.assertIn("rate_limit_flow", rejected["steps"][-2]["description"])
        self.assertEqual(rejected["steps"][-1]["status"], "not_reached")

        execute("DELETE FROM outbound_jobs")
        execute("DELETE FROM digi_flow_steps WHERE flow_id = ?", (flow_id,))
        execute("DELETE FROM digi_flows WHERE id = ?", (flow_id,))
        source_config = {
            **RF_GUARD_DEFAULTS,
            "flow_burst": 5,
            "source_burst": 1,
        }
        source_flow_id = self.create_flow(callsigns=["SP5CCC"], guard_config=source_config)
        await self.run_lines(
            position_line(source="SP5CCC", text="one"),
            position_line(source="SP5CCC", text="two"),
        )
        self.assertEqual(get_aprsis_rf_stats(source_flow_id)["dropped_rate_limit"], 1)
        self.assertEqual(int(fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs")["total"]), 1)

    async def test_oversize_is_dropped_and_runtime_restart_does_not_recover_pending(self) -> None:
        flow_id = self.create_flow()
        await self.run_lines(position_line(text="x" * 250))
        self.assertEqual(get_aprsis_rf_stats(flow_id)["dropped_oversize"], 1)
        self.assertIsNone(fetch_one("SELECT id FROM outbound_jobs LIMIT 1"))

        runtime = DigiFlowRuntimeService(aprsis_rf_delay_override=60)
        await runtime.start()
        runtime.enqueue_tnc2_frame(
            source_kind=APRSIS_FLOW_SOURCE_KIND,
            source_ref="APRSIS-RX",
            raw_payload=position_line(text="restart"),
        )
        await runtime._queue.join()
        self.assertTrue(runtime._aprsis_rf_pending)
        await runtime.stop()
        restarted = DigiFlowRuntimeService(aprsis_rf_delay_override=0)
        await restarted.start()
        await asyncio.sleep(0)
        await restarted.stop()
        self.assertIsNone(fetch_one("SELECT id FROM outbound_jobs LIMIT 1"))

    async def test_aprsis_runtime_does_not_create_rf_rx_or_classic_digi_traffic_stats(self) -> None:
        flow_id = self.create_flow()
        await self.run_lines(position_line(text="separate stats"))
        self.assertEqual(get_aprsis_rf_stats(flow_id)["received_from_aprsis"], 1)
        self.assertEqual(get_aprsis_rf_stats(flow_id)["queued_to_rf"], 1)
        self.assertIsNone(fetch_one("SELECT id FROM traffic_frames LIMIT 1"))


if __name__ == "__main__":
    unittest.main()
