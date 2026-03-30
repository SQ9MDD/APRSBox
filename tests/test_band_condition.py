import unittest

from app.services.band_condition import build_station_key, format_band_label
from app.services.content import parse_tnc2_frame


class BandConditionHelpersTests(unittest.TestCase):
    def test_parse_tnc2_frame_accepts_spacing_from_kiss_decoder(self) -> None:
        parsed = parse_tnc2_frame("SRCCALL-9 > APRS , WIDE1-1,WIDE2-1 :!5218.37N/02104.87E-Test")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["source_key"], "SRCCALL-9")
        self.assertEqual(parsed["destination"], "APRS")
        self.assertEqual(parsed["classification"], "fixed")

    def test_build_station_key_normalizes_callsign_and_ssid(self) -> None:
        self.assertEqual(build_station_key("sq9mdd", "9"), "SQ9MDD-9")
        self.assertEqual(build_station_key("sq9mdd", "abc"), "SQ9MDD")

    def test_format_band_label_preserves_common_aprs_band_names(self) -> None:
        self.assertEqual(format_band_label("2m"), "2m")
        self.assertEqual(format_band_label("70cm"), "70cm")
        self.assertEqual(format_band_label("hf"), "HF")


if __name__ == "__main__":
    unittest.main()
