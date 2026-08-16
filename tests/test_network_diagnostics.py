import unittest
from unittest.mock import patch

from app.services.network_diagnostics import build_web_ui_url, get_network_diagnostics


class NetworkDiagnosticsTests(unittest.TestCase):
    def test_uses_source_selected_by_default_route_and_same_interface_for_ipv6(self) -> None:
        def ip_payload(arguments):
            if arguments == ["-4", "route", "get", "1.1.1.1"]:
                return [{"dev": "enp2s0", "prefsrc": "192.168.10.24"}]
            if arguments == ["-6", "address", "show", "dev", "enp2s0"]:
                return [
                    {
                        "addr_info": [
                            {"local": "::1"},
                            {"local": "fe80::1234"},
                            {"local": "2001:db8::24"},
                        ]
                    }
                ]
            return []

        with (
            patch("app.services.network_diagnostics.socket.gethostname", return_value="aprsbox"),
            patch("app.services.network_diagnostics._read_ip_json", side_effect=ip_payload),
            patch("app.services.network_diagnostics._avahi_status", return_value=("Active", "ok")),
            patch("app.services.network_diagnostics._resolve_mdns", return_value="192.168.10.24"),
        ):
            result = get_network_diagnostics(scheme="https", port=443)

        self.assertEqual(result["interface"], "enp2s0")
        self.assertEqual(result["ipv4"], "192.168.10.24")
        self.assertEqual(result["ipv6"], "2001:db8::24")
        self.assertEqual(result["mdns_name"], "aprsbox.local")
        self.assertEqual(result["web_ui_url"], "https://aprsbox.local")

    def test_missing_avahi_and_addresses_are_reported_without_exceptions(self) -> None:
        with (
            patch("app.services.network_diagnostics.socket.gethostname", return_value="node.example.org"),
            patch("app.services.network_diagnostics._active_ipv4_route", return_value=(None, None)),
            patch("app.services.network_diagnostics._interface_ipv6", return_value=None),
            patch("app.services.network_diagnostics._avahi_status", return_value=("Unavailable", "neutral")),
            patch("app.services.network_diagnostics._resolve_mdns", return_value=None),
        ):
            result = get_network_diagnostics(scheme="http", port=8087, root_path="/aprs")

        self.assertIsNone(result["ipv4"])
        self.assertIsNone(result["interface"])
        self.assertIsNone(result["mdns_resolve"])
        self.assertEqual(result["avahi_status"], "Unavailable")
        self.assertEqual(result["web_ui_url"], "http://node.local:8087/aprs")

    def test_falls_back_to_platform_default_route_when_iproute_is_unavailable(self) -> None:
        with (
            patch("app.services.network_diagnostics._read_ip_json", return_value=[]),
            patch("app.services.network_diagnostics._linux_default_interface", return_value=None),
            patch("app.services.network_diagnostics._bsd_default_interface", return_value="en0"),
            patch("app.services.network_diagnostics._socket_route_ipv4", return_value="192.168.1.40"),
        ):
            from app.services.network_diagnostics import _active_ipv4_route

            self.assertEqual(_active_ipv4_route(), ("en0", "192.168.1.40"))

    def test_web_url_keeps_non_default_ports_and_omits_default_ports(self) -> None:
        self.assertEqual(
            build_web_ui_url(mdns_name="aprsbox.local", scheme="https", port=9443),
            "https://aprsbox.local:9443",
        )
        self.assertEqual(
            build_web_ui_url(mdns_name="aprsbox.local", scheme="http", port=80),
            "http://aprsbox.local",
        )



if __name__ == "__main__":
    unittest.main()
