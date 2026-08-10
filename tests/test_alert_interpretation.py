import unittest

from app.services.alert_interpretation import interpret_group_alert


class AlertInterpretationTests(unittest.TestCase):
    def test_cawf_uses_registered_event_and_defined_colour_scale(self) -> None:
        result = interpret_group_alert(
            destination_group="PL-WARN",
            event_code="TSTORM2",
            severity_level=2,
        )

        self.assertEqual(result["format_label"], "CAWF v1")
        self.assertEqual(result["event_label"], "Thunderstorm")
        self.assertTrue(result["event_known"])
        self.assertEqual(result["severity_level_label"], "Level 2")
        self.assertEqual(result["severity_color_label"], "Orange")

    def test_nws_warn_marks_event_as_category_and_level_as_relay_mapping(self) -> None:
        result = interpret_group_alert(
            destination_group="NWS-WARN",
            event_code="TORNADO3",
            severity_level=3,
        )

        self.assertEqual(result["format_label"], "NWS-WARN")
        self.assertEqual(result["event_label"], "Tornado")
        self.assertTrue(result["event_known"])
        self.assertEqual(result["severity_color_label"], "Red")

    def test_format_specific_unknown_values_are_not_overstated(self) -> None:
        cawf = interpret_group_alert(
            destination_group="PL-WARN",
            event_code="ALIENS9",
            severity_level=9,
        )
        nws = interpret_group_alert(
            destination_group="NWS-WARN",
            event_code="LOCALPHRASE",
            severity_level=None,
        )

        self.assertEqual(cawf["event_label"], "Unrecognized CAWF event code")
        self.assertFalse(cawf["event_known"])
        self.assertEqual(cawf["severity_level_label"], "Unknown level")
        self.assertEqual(cawf["severity_color_label"], "")
        self.assertEqual(nws["event_label"], "Unrecognized sender event label")
        self.assertFalse(nws["event_known"])


if __name__ == "__main__":
    unittest.main()
