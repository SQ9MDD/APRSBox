import unittest

from app.services.content import _clean_decoded_tokens, _parse_position_without_timestamp, _parse_qsy_fields


class AprsContentParsingTests(unittest.TestCase):
    def test_clean_decoded_tokens_removes_compressed_telemetry_and_dao(self) -> None:
        cleaned = _clean_decoded_tokens("|!!!!| Test beacon !w12!")
        self.assertEqual(cleaned, "Test beacon")

    def test_parse_compressed_position_cleans_comment_artifacts_without_decoded_metrics(self) -> None:
        parsed = _parse_position_without_timestamp("!/!!!!!!!!>   |!!!!| Test beacon !w12!")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["comment"], "Test beacon")

    def test_parse_position_comment_removes_course_speed_and_altitude_extensions(self) -> None:
        parsed = _parse_position_without_timestamp("!5218.37N\\02104.87Eu243/002/A=000278Back on track!")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["comment"], "Back on track!")

    def test_clean_decoded_tokens_removes_mice_qsy_prefix_and_case_insensitive_mhz(self) -> None:
        cleaned = _clean_decoded_tokens("m}145.575Mhz op. Maciek_0")
        self.assertEqual(cleaned, "op. Maciek_0")

    def test_parse_qsy_fields_is_case_insensitive_for_mhz(self) -> None:
        parsed = _parse_qsy_fields("m}145.575Mhz op. Maciek_0")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["qsy_frequency_mhz"], 145.575)


if __name__ == "__main__":
    unittest.main()
