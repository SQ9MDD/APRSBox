import unittest
from pathlib import Path

from app.services.alert_event_icons import (
    DEFAULT_ALERT_EVENT_ICON,
    normalize_alert_event_family,
    resolve_alert_event_icon,
)


class AlertEventIconTests(unittest.TestCase):
    def test_event_family_ignores_severity_suffix_and_separators(self) -> None:
        self.assertEqual(normalize_alert_event_family(" t-storm_12 "), "TSTORM")

    def test_weather_event_families_use_local_icons(self) -> None:
        expected_icons = {
            "TSTORM1": "weather-lightning-rainy.svg",
            "RAIN2": "weather-pouring.svg",
            "WIND3": "weather-windy.svg",
            "HEAT1": "heat-wave.svg",
            "COLD2": "thermometer-low.svg",
            "SNOW3": "weather-snowy-heavy.svg",
            "HAIL1": "weather-hail.svg",
            "FLOOD2": "home-flood.svg",
            "FOG1": "weather-fog.svg",
            "TORNADO3": "weather-tornado.svg",
            "FIRE2": "fire-alert.svg",
        }
        for event_code, expected_icon in expected_icons.items():
            with self.subTest(event_code=event_code):
                self.assertEqual(
                    resolve_alert_event_icon(event_code),
                    expected_icon,
                )
                self.assertTrue(
                    (Path("app/static/icons") / expected_icon).is_file(),
                    expected_icon,
                )

    def test_unknown_and_emergency_categories_use_neutral_fallback(self) -> None:
        self.assertEqual(resolve_alert_event_icon("OTHER7"), DEFAULT_ALERT_EVENT_ICON)
        self.assertEqual(
            resolve_alert_event_icon("", alert_type="emergency"),
            DEFAULT_ALERT_EVENT_ICON,
        )
        self.assertTrue(
            (Path("app/static/icons") / DEFAULT_ALERT_EVENT_ICON).is_file()
        )


if __name__ == "__main__":
    unittest.main()
