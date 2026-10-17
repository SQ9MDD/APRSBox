import errno
import importlib.util
import socket
import unittest
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "web_bind_host", Path(__file__).resolve().parents[1] / "scripts" / "web-bind-host.py"
)
web_bind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_bind)


class WebBindHostTests(unittest.TestCase):
    def test_available_ipv6_enables_both_families(self) -> None:
        try:
            with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
                probe.bind(("::", 0))
        except OSError:
            self.skipTest("IPv6 binding is unavailable")
        self.assertEqual(web_bind.web_bind_host(), "")

    def test_missing_ipv6_support_keeps_ipv4(self) -> None:
        with patch.object(web_bind.socket, "socket", side_effect=OSError(errno.EAFNOSUPPORT, "No IPv6")):
            self.assertEqual(web_bind.web_bind_host(), "0.0.0.0")

    def test_disabled_ipv6_interfaces_keep_ipv4_and_close_probe(self) -> None:
        with patch.object(web_bind.socket, "socket") as socket_factory:
            probe = socket_factory.return_value.__enter__.return_value
            probe.bind.side_effect = OSError(errno.EADDRNOTAVAIL, "IPv6 disabled")
            self.assertEqual(web_bind.web_bind_host(), "0.0.0.0")
            socket_factory.return_value.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
