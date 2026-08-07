import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.routers import pages


class HelpMarkdownTests(unittest.TestCase):
    def test_alerts_have_dedicated_localized_help_with_autoplay_guidance(self) -> None:
        expected_headings = {
            "en": "# APRS emergency alerts",
            "pl": "# Alarmy APRS emergency",
            "de": "# APRS-Notfallalarme",
            "es": "# Alarmas de emergencia APRS",
        }
        for language, heading in expected_headings.items():
            with self.subTest(language=language):
                resolved = pages._read_help_markdown(
                    page="application/alerts",
                    language=language,
                )
                self.assertIsNotNone(resolved)
                assert resolved is not None
                self.assertEqual(resolved[0], f"application/alerts.{language}.md")
                self.assertTrue(resolved[1].startswith(heading))
                self.assertIn("aut", resolved[1].lower())
                self.assertIn("NWS-WARN", resolved[1])
                self.assertIn(
                    f"settings_alarms_nws_warn.{language}.md",
                    resolved[1],
                )

    def test_aprsis_message_delivery_rule_has_dedicated_localized_help(self) -> None:
        expected_headings = {
            "en": "# APRS-IS Message Delivery Rule",
            "pl": "# Reguła dostarczania wiadomości APRS-IS",
            "de": "# APRS-IS-Nachrichten-Zustellregel",
            "es": "# Regla de entrega de mensajes APRS-IS",
        }
        for language, heading in expected_headings.items():
            with self.subTest(language=language):
                resolved = pages._read_help_markdown(
                    page="application/packet_routing_flow_aprsis_message_delivery_rule",
                    language=language,
                )
                self.assertIsNotNone(resolved)
                assert resolved is not None
                self.assertEqual(
                    resolved[0],
                    f"application/packet_routing_flow_aprsis_message_delivery_rule.{language}.md",
                )
                self.assertTrue(resolved[1].startswith(heading))

    def test_aprsis_callsign_radius_rule_has_dedicated_localized_help(self) -> None:
        expected_headings = {
            "en": "# APRS-IS Callsign and Radius Rule",
            "pl": "# Reguła znaku i promienia APRS-IS",
            "de": "# APRS-IS-Rufzeichen- und Radiusregel",
            "es": "# Regla APRS-IS de indicativo y radio",
        }
        for language, heading in expected_headings.items():
            with self.subTest(language=language):
                resolved = pages._read_help_markdown(
                    page="application/packet_routing_flow_aprsis_callsign_radius_rule",
                    language=language,
                )
                self.assertIsNotNone(resolved)
                assert resolved is not None
                self.assertEqual(
                    resolved[0],
                    f"application/packet_routing_flow_aprsis_callsign_radius_rule.{language}.md",
                )
                self.assertTrue(resolved[1].startswith(heading))

    def test_reads_german_help_file_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            help_root = Path(temp_dir) / "help"
            application_dir = help_root / "application"
            application_dir.mkdir(parents=True)
            (application_dir / "objects.de.md").write_text("# DE", encoding="utf-8")
            (application_dir / "objects.en.md").write_text("# EN", encoding="utf-8")
            with patch.object(pages, "_HELP_ROOT_DIR", help_root):
                resolved = pages._read_help_markdown(page="application/objects", language="de")
            self.assertEqual(resolved, ("application/objects.de.md", "# DE"))

    def test_reads_language_specific_help_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            help_root = Path(temp_dir) / "help"
            application_dir = help_root / "application"
            application_dir.mkdir(parents=True)
            (application_dir / "objects.pl.md").write_text("# PL", encoding="utf-8")
            (application_dir / "objects.en.md").write_text("# EN", encoding="utf-8")
            with patch.object(pages, "_HELP_ROOT_DIR", help_root):
                resolved = pages._read_help_markdown(page="application/objects", language="pl")
            self.assertEqual(resolved, ("application/objects.pl.md", "# PL"))

    def test_help_falls_back_to_english(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            help_root = Path(temp_dir) / "help"
            application_dir = help_root / "application"
            application_dir.mkdir(parents=True)
            (application_dir / "objects.en.md").write_text("# EN", encoding="utf-8")
            with patch.object(pages, "_HELP_ROOT_DIR", help_root):
                resolved = pages._read_help_markdown(page="application/objects", language="es")
            self.assertEqual(resolved, ("application/objects.en.md", "# EN"))

    def test_reads_relative_help_link_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            help_root = Path(temp_dir) / "help"
            target_dir = help_root / "protocoll"
            target_dir.mkdir(parents=True)
            (target_dir / "repeaters_qsy.pl.md").write_text("# Repeaters", encoding="utf-8")
            with patch.object(pages, "_HELP_ROOT_DIR", help_root):
                resolved = pages._read_help_markdown(path="protocoll/repeaters_qsy.pl.md")
            self.assertEqual(resolved, ("protocoll/repeaters_qsy.pl.md", "# Repeaters"))

    def test_rejects_path_traversal_outside_help_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            help_root = Path(temp_dir) / "help"
            help_root.mkdir(parents=True)
            with patch.object(pages, "_HELP_ROOT_DIR", help_root):
                self.assertIsNone(pages._read_help_markdown(path="../secrets.md"))
                self.assertIsNone(pages._read_help_markdown(page="../application/objects", language="en"))


if __name__ == "__main__":
    unittest.main()
