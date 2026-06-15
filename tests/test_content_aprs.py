import unittest
from unittest.mock import patch

from app.services.content import (
    _clean_decoded_tokens,
    _format_qsy_offset_display,
    _parse_position_with_timestamp,
    _parse_position_without_timestamp,
    _parse_qsy_fields,
    get_aprs_symbol_icon_fallback_path,
    get_aprs_symbol_icon_path,
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

    @classmethod
    def _build_compressed_packet_with_symbol_table(
        cls,
        latitude: float,
        longitude: float,
        *,
        symbol_table: str,
        symbol_code: str = ">",
        cst: str = " sT",
    ) -> str:
        lat_value = int(round(380926 * (90 - latitude)))
        lon_value = int(round(190463 * (180 + longitude)))
        return f"!{symbol_table}{cls._encode_base91(lat_value)}{cls._encode_base91(lon_value)}{symbol_code}{cst}"

    @classmethod
    def _build_timestamped_compressed_packet_with_symbol_table(
        cls,
        latitude: float,
        longitude: float,
        *,
        symbol_table: str,
        symbol_code: str = ">",
        cst: str = " sT",
    ) -> str:
        lat_value = int(round(380926 * (90 - latitude)))
        lon_value = int(round(190463 * (180 + longitude)))
        return f"@010203z{symbol_table}{cls._encode_base91(lat_value)}{cls._encode_base91(lon_value)}{symbol_code}{cst}"

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

    def test_format_qsy_offset_display_formats_sub_mhz_shift_in_khz(self) -> None:
        self.assertEqual(_format_qsy_offset_display(60), "+600kHz")

    def test_format_qsy_offset_display_formats_large_shift_in_mhz(self) -> None:
        self.assertEqual(_format_qsy_offset_display(760), "+7,6MHz")

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

    def test_parse_tnc2_frame_decodes_compressed_position_with_alpha_overlay_symbol_table(self) -> None:
        parsed = parse_tnc2_frame("M0IGA-9 > APLRFT , WIDE1-1,WIDE2-1:!L2efTN.PAv:HQLoRa APRS 1200")
        aprs_data = (parsed or {}).get("aprs_data") or {}
        self.assertEqual(aprs_data.get("packet_type_code"), "position_compressed")
        self.assertEqual(aprs_data.get("latitude"), "54.87469")
        self.assertEqual(aprs_data.get("longitude"), "-1.36868")
        self.assertEqual(aprs_data.get("symbol"), "Lv")

    def test_parse_tnc2_frame_decodes_timestamped_compressed_position_with_alpha_overlay_symbol_table(self) -> None:
        compressed_info = self._build_timestamped_compressed_packet_with_symbol_table(
            52.2297,
            21.0122,
            symbol_table="L",
        )
        parsed = parse_tnc2_frame(f"SP8ABC-9>APRS:{compressed_info}")
        aprs_data = (parsed or {}).get("aprs_data") or {}
        self.assertEqual(aprs_data.get("packet_type_code"), "position_compressed_timestamped")
        self.assertEqual(aprs_data.get("latitude"), "52.22970")
        self.assertEqual(aprs_data.get("longitude"), "21.01220")
        self.assertEqual(aprs_data.get("symbol"), "L>")

    def test_parse_tnc2_frame_decodes_compressed_position_with_legacy_lowercase_overlay_digit(self) -> None:
        compressed_info = self._build_compressed_packet_with_symbol_table(
            52.2297,
            21.0122,
            symbol_table="a",
        )
        parsed = parse_tnc2_frame(f"SP8ABC-9>APRS:{compressed_info}")
        aprs_data = (parsed or {}).get("aprs_data") or {}
        self.assertEqual(aprs_data.get("packet_type_code"), "position_compressed")
        self.assertEqual(aprs_data.get("latitude"), "52.22970")
        self.assertEqual(aprs_data.get("longitude"), "21.01220")
        self.assertEqual(aprs_data.get("symbol"), "0>")

    def test_parse_tnc2_frame_decodes_compressed_position_when_cst_is_spaces(self) -> None:
        compressed_info = self._build_compressed_packet(52.2297, 21.0122)[:-3] + "   "
        parsed = parse_tnc2_frame(f"SP8ABC-9>APRS:{compressed_info}")
        aprs_data = (parsed or {}).get("aprs_data") or {}
        self.assertEqual(aprs_data.get("packet_type_code"), "position_compressed")
        self.assertEqual(aprs_data.get("latitude"), "52.22970")
        self.assertEqual(aprs_data.get("longitude"), "21.01220")

    def test_parse_tnc2_frame_decodes_timestamped_compressed_position_when_cst_is_spaces(self) -> None:
        compressed_info = "@010203z/4)HLSj:R>   "
        parsed = parse_tnc2_frame(f"SP8ABC-9>APRS:{compressed_info}")
        aprs_data = (parsed or {}).get("aprs_data") or {}
        self.assertEqual(aprs_data.get("packet_type_code"), "position_compressed_timestamped")
        self.assertEqual(aprs_data.get("latitude"), "52.22970")
        self.assertEqual(aprs_data.get("longitude"), "21.01220")

    def test_parse_tnc2_frame_decodes_uncompressed_position(self) -> None:
        parsed = parse_tnc2_frame("SP8ABC-9>APRS:!5218.37N\\02104.87E-Test")
        aprs_data = (parsed or {}).get("aprs_data") or {}
        self.assertEqual(aprs_data.get("packet_type_code"), "position")
        self.assertEqual(aprs_data.get("latitude"), "52.30617")
        self.assertEqual(aprs_data.get("longitude"), "21.08117")

    def test_parse_tnc2_frame_detects_emergency_comment_prefix(self) -> None:
        parsed = parse_tnc2_frame("SP8ABC-9>APRS:!5218.37N\\02104.87E$!EMERGENCY!Need help")
        aprs_data = (parsed or {}).get("aprs_data") or {}
        self.assertTrue(bool(aprs_data.get("emergency")))
        self.assertEqual(aprs_data.get("emergency_code"), "EMERGENCY")

    def test_parse_tnc2_frame_detects_emergency_symbol(self) -> None:
        parsed = parse_tnc2_frame("SP8ABC-9>APRS:!5218.37N\\02104.87E!")
        aprs_data = (parsed or {}).get("aprs_data") or {}
        self.assertTrue(bool(aprs_data.get("emergency")))
        self.assertEqual(aprs_data.get("symbol"), "\\!")

    def test_parse_tnc2_frame_does_not_mark_weather_symbol_position_as_mobile(self) -> None:
        parsed = parse_tnc2_frame("SP8WX-1>APRS:!5218.37N/02104.87E_090/010g015t020r000p000P000h50b10150")
        self.assertIsNotNone(parsed)
        aprs_data = (parsed or {}).get("aprs_data") or {}
        self.assertEqual(aprs_data.get("entity_class"), "stationary")
        self.assertEqual(aprs_data.get("frame_type"), "S")
        self.assertEqual((parsed or {}).get("classification"), "fixed")

    def test_parse_tnc2_frame_decodes_weather_radiation_extension_and_cleans_comment(self) -> None:
        parsed = parse_tnc2_frame("SQ9MDD-3>APBOX0,RFONLY:=5215.03N/02055.60E_.../...t050h75b10161X111")
        self.assertIsNotNone(parsed)
        aprs_data = (parsed or {}).get("aprs_data") or {}
        metrics = dict(aprs_data.get("data") or {})
        self.assertEqual(aprs_data.get("comment"), "")
        self.assertEqual(metrics.get("temperature_f"), 50)
        self.assertEqual(metrics.get("humidity_percent"), 75)
        self.assertEqual(metrics.get("pressure_hpa"), 1016.1)
        self.assertEqual(metrics.get("radiation_nsv_h"), 110.0)

    def test_parse_tnc2_frame_decodes_mic_e_position(self) -> None:
        parsed = parse_tnc2_frame('SO5AJM-7 > URTW13 , SR5NWR*,WIDE1*,WIDE2*:`14M^\\^]D[/"4N}Witam!')
        aprs_data = (parsed or {}).get("aprs_data") or {}
        self.assertEqual(aprs_data.get("packet_type_code"), "mic_e")
        self.assertEqual(aprs_data.get("latitude"), "52.78550")
        self.assertEqual(aprs_data.get("longitude"), "21.40817")

    def test_parse_tnc2_frame_decodes_mic_e_longitude_hundredths_without_60_wrap(self) -> None:
        parsed = parse_tnc2_frame('SO5AJM-7 > URTW13 , SR5NWR*,WIDE1*,WIDE2*:`14d^\\^]D[/"4N}Witam!')
        aprs_data = (parsed or {}).get("aprs_data") or {}
        self.assertEqual(aprs_data.get("packet_type_code"), "mic_e")
        self.assertEqual(aprs_data.get("latitude"), "52.78550")
        self.assertEqual(aprs_data.get("longitude"), "21.41200")

    def test_parse_tnc2_frame_accepts_mic_e_destination_with_ambiguity_space(self) -> None:
        line = "SP0DN>UQUQ1L,WIDE1-1,WIDE2-1:`12Xl \x1cy/446.006MHz Dejw wilga. zapraszm do kontaktu i testow_%"
        parsed = parse_tnc2_frame(line)
        self.assertIsNotNone(parsed)
        self.assertEqual((parsed or {}).get("source_callsign"), "SP0DN")
        aprs_data = (parsed or {}).get("aprs_data")
        self.assertIsNotNone(aprs_data)
        aprs_data = aprs_data or {}
        self.assertEqual(aprs_data.get("packet_type_code"), "mic_e")
        self.assertTrue(bool(aprs_data.get("latitude")))
        self.assertTrue(bool(aprs_data.get("longitude")))
        self.assertEqual(aprs_data.get("position_ambiguity_digits"), 1)
        self.assertTrue(bool(aprs_data.get("position_ambiguous")))

    def test_parse_tnc2_frame_rejects_mic_e_destination_with_invalid_character(self) -> None:
        line = "SP0DN>UQUQ1M,WIDE1-1,WIDE2-1:`12Xl \x1cy/446.006MHz Dejw wilga. zapraszm do kontaktu i testow_%"
        parsed = parse_tnc2_frame(line)
        self.assertIsNotNone(parsed)
        self.assertIsNone((parsed or {}).get("aprs_data"))

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

    def test_get_aprs_symbol_icon_path_switches_to_modern_png_set(self) -> None:
        with patch("app.services.content.get_app_setting", return_value="modern"):
            self.assertEqual(get_aprs_symbol_icon_path("/!"), "icons/aprs-symbols/00.png")
            self.assertEqual(get_aprs_symbol_icon_path("\\!"), "icons/aprs-symbols/a00.png")
            self.assertEqual(get_aprs_symbol_icon_fallback_path(), "icons/aprs-symbols/x.png")

    def test_parse_tnc2_frame_decodes_object_state_marker(self) -> None:
        live = parse_tnc2_frame("SP8ABC-9>APRS:;OBJTEST  *010203z5228.23N/02101.28E#Object")
        killed = parse_tnc2_frame("SP8ABC-9>APRS:;OBJTEST  _010203z5228.23N/02101.28E#Object")

        self.assertEqual((live or {}).get("aprs_data", {}).get("state"), "live")
        self.assertEqual((killed or {}).get("aprs_data", {}).get("state"), "killed")

    def test_parse_tnc2_frame_exposes_message_group_for_bulletin_and_ack(self) -> None:
        bulletin = parse_tnc2_frame("SP8ABC-9>APRS::BLN1     :System bulletin")
        ack = parse_tnc2_frame("SP8ABC-9>APRS::SQ9MDD-4:ack12")

        self.assertEqual((bulletin or {}).get("aprs_data", {}).get("packet_group"), "message")
        self.assertEqual((bulletin or {}).get("aprs_data", {}).get("packet_type_code"), "bulletin")
        self.assertEqual((ack or {}).get("aprs_data", {}).get("packet_group"), "message")
        self.assertEqual((ack or {}).get("aprs_data", {}).get("packet_type_code"), "ack")

    def test_parse_tnc2_frame_third_party_position_uses_inner_logical_source(self) -> None:
        line = "SR0DZ>APDW16,SR5NWA*,WIDE1*:}SQ2IBK>U2QU28,TCPIP,SR0DZ*:`0SZl4{[/>145.575MHz&"
        parsed = parse_tnc2_frame(line)
        assert parsed is not None
        aprs_data = dict(parsed.get("aprs_data") or {})

        self.assertEqual(parsed.get("source_key"), "SR0DZ")
        self.assertEqual(parsed.get("logical_source_key"), "SQ2IBK")
        self.assertEqual(parsed.get("logical_destination"), "U2QU28")
        self.assertEqual(parsed.get("logical_path"), "TCPIP,SR0DZ*")
        self.assertTrue(bool(parsed.get("is_third_party")))
        self.assertTrue(bool(parsed.get("third_party_inner_valid")))
        self.assertEqual(aprs_data.get("outer_source"), "SR0DZ")
        self.assertEqual(aprs_data.get("packet_group"), "position")
        self.assertEqual(aprs_data.get("packet_type_code"), "mic_e")

    def test_parse_tnc2_frame_third_party_message_uses_inner_sender(self) -> None:
        line = "SR0DZ>APDW16,SR5NWA*,WIDE1*:}SQ2IBK>APRS,TCPIP,SR0DZ*::SQ9MDD-4 :test third-party{12"
        parsed = parse_tnc2_frame(line)
        assert parsed is not None
        aprs_data = dict(parsed.get("aprs_data") or {})

        self.assertEqual(parsed.get("source_key"), "SR0DZ")
        self.assertEqual(parsed.get("logical_source_key"), "SQ2IBK")
        self.assertTrue(bool(parsed.get("is_third_party")))
        self.assertTrue(bool(parsed.get("third_party_inner_valid")))
        self.assertEqual(aprs_data.get("packet_group"), "message")
        self.assertEqual(aprs_data.get("packet_type_code"), "message")
        self.assertEqual(aprs_data.get("addressee"), "SQ9MDD-4")
        self.assertEqual(aprs_data.get("comment"), "test third-party")

    def test_parse_tnc2_frame_third_party_invalid_inner_keeps_outer_source(self) -> None:
        line = "SR0DZ>APDW16,SR5NWA*,WIDE1*:}NOT_A_VALID_FRAME"
        parsed = parse_tnc2_frame(line)
        assert parsed is not None
        aprs_data = dict(parsed.get("aprs_data") or {})

        self.assertEqual(parsed.get("source_key"), "SR0DZ")
        self.assertEqual(parsed.get("logical_source_key"), "SR0DZ")
        self.assertTrue(bool(parsed.get("is_third_party")))
        self.assertFalse(bool(parsed.get("third_party_inner_valid")))
        self.assertEqual(aprs_data.get("packet_type_code"), "third_party")
        self.assertEqual(aprs_data.get("outer_source"), "SR0DZ")

    def test_parse_tnc2_frame_non_third_party_keeps_existing_source_contract(self) -> None:
        parsed = parse_tnc2_frame("SP8ABC-9>APRS:!5218.37N\\02104.87E-Test")
        assert parsed is not None

        self.assertEqual(parsed.get("source_key"), "SP8ABC-9")
        self.assertEqual(parsed.get("logical_source_key"), "SP8ABC-9")
        self.assertFalse(bool(parsed.get("is_third_party")))
        self.assertFalse(bool(parsed.get("third_party_inner_valid")))


if __name__ == "__main__":
    unittest.main()
