import unittest

from app.services.content import (
    _clean_decoded_tokens,
    _parse_position_with_timestamp,
    _parse_position_without_timestamp,
    _parse_qsy_fields,
    parse_tnc2_frame,
)


class AprsContentParsingTests(unittest.TestCase):
    @staticmethod
    def _encode_base91(value: int) -> str:
        encoded = []
        remainder = value
        for divisor in (91**3, 91**2, 91, 1):
            digit, remainder = divmod(remainder, divisor)
            encoded.append(chr(digit + 33))
        return "".join(encoded)

    @classmethod
    def _build_compressed_packet(cls, latitude: float, longitude: float) -> str:
        lat_value = int(round(380926 * (90 - latitude)))
        lon_value = int(round(190463 * (180 + longitude)))
        return f"!/{cls._encode_base91(lat_value)}{cls._encode_base91(lon_value)}> sT"

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

    def test_parse_compressed_position_decodes_expected_coordinates(self) -> None:
        parsed = _parse_position_without_timestamp(self._build_compressed_packet(52.2297, 21.0122))
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["latitude"], "52.22970")
        self.assertEqual(parsed["longitude"], "21.01220")

    def test_parse_compressed_position_with_timestamp_decodes_expected_coordinates(self) -> None:
        parsed = _parse_position_with_timestamp("@010203z/4)HLSj:R> sT")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["latitude"], "52.22970")
        self.assertEqual(parsed["longitude"], "21.01220")

    def test_parse_tnc2_frame_exposes_packet_group_for_status_query_telemetry_and_item(self) -> None:
        status = parse_tnc2_frame("SP8ABC-9>APRS:>Station online")
        query = parse_tnc2_frame("SP8ABC-9>APRS::SQ9MDD-4:?APRSP")
        telemetry = parse_tnc2_frame("SP8ABC-9>APRS:T#001,111,222,333,444,555,00000000")
        item = parse_tnc2_frame("SP8ABC-9>APRS:)AID01!5228.23N/02101.28E#Test item")

        self.assertEqual((status or {}).get("aprs_data", {}).get("packet_group"), "status")
        self.assertEqual((status or {}).get("aprs_data", {}).get("packet_type_code"), "status")
        self.assertEqual((query or {}).get("aprs_data", {}).get("packet_group"), "query")
        self.assertEqual((query or {}).get("aprs_data", {}).get("packet_type_code"), "query")
        self.assertEqual((telemetry or {}).get("aprs_data", {}).get("packet_group"), "telemetry")
        self.assertEqual((telemetry or {}).get("aprs_data", {}).get("packet_type_code"), "telemetry")
        self.assertEqual((item or {}).get("aprs_data", {}).get("packet_group"), "item")
        self.assertEqual((item or {}).get("aprs_data", {}).get("packet_type_code"), "item")

    def test_parse_tnc2_frame_exposes_message_group_for_bulletin_and_ack(self) -> None:
        bulletin = parse_tnc2_frame("SP8ABC-9>APRS::BLN1     :System bulletin")
        ack = parse_tnc2_frame("SP8ABC-9>APRS::SQ9MDD-4:ack12")

        self.assertEqual((bulletin or {}).get("aprs_data", {}).get("packet_group"), "message")
        self.assertEqual((bulletin or {}).get("aprs_data", {}).get("packet_type_code"), "bulletin")
        self.assertEqual((ack or {}).get("aprs_data", {}).get("packet_group"), "message")
        self.assertEqual((ack or {}).get("aprs_data", {}).get("packet_type_code"), "ack")


if __name__ == "__main__":
    unittest.main()
