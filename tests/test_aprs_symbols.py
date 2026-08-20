import unittest

from app.aprs_symbols import get_aprs_symbol_description


class AprsSymbolDescriptionTests(unittest.TestCase):
    def test_descriptions_follow_selected_symbol_table(self) -> None:
        self.assertEqual(get_aprs_symbol_description("/", "!"), "Police station")
        self.assertEqual(get_aprs_symbol_description("\\", "!"), "Emergency")
        self.assertEqual(get_aprs_symbol_description("/", ">"), "Car")
        self.assertEqual(get_aprs_symbol_description("\\", ">"), "Red car")

    def test_empty_and_invalid_symbols_have_no_description(self) -> None:
        self.assertEqual(get_aprs_symbol_description("/", '"'), "")
        self.assertEqual(get_aprs_symbol_description("/", ""), "")
        self.assertEqual(get_aprs_symbol_description("/", "ab"), "")
        self.assertEqual(get_aprs_symbol_description("/", " "), "")


if __name__ == "__main__":
    unittest.main()
