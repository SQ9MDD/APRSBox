import errno
import importlib.util
import socket
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "http_redirect", Path(__file__).resolve().parents[1] / "scripts" / "http-redirect.py"
)
redirect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(redirect)


class HttpRedirectTests(unittest.TestCase):
    def request(self, server, address: str, host: str) -> tuple[int, str | None]:
        thread = threading.Thread(target=server.handle_request)
        server.timeout = 2
        thread.start()
        connection = HTTPConnection(address, server.server_port, timeout=2)
        try:
            connection.request("GET", "/login?next=%2Fmap", headers={"Host": host})
            response = connection.getresponse()
            response.read()
            return response.status, response.getheader("Location")
        finally:
            connection.close()
            thread.join(timeout=3)

    def test_redirect_preserves_hostname_ipv4_and_bracketed_ipv6(self) -> None:
        with patch.object(redirect.socket, "has_dualstack_ipv6", return_value=False):
            server = redirect.create_server(0)
        with server:
            for host, expected in (
                ("aprsbox.local:80", "aprsbox.local"),
                ("192.0.2.1:80", "192.0.2.1"),
                ("[2001:db8::1]:80", "[2001:db8::1]"),
                ("[2001:db8::1]", "[2001:db8::1]"),
            ):
                with self.subTest(host=host):
                    self.assertEqual(
                        self.request(server, "127.0.0.1", host),
                        (308, f"https://{expected}/login?next=%2Fmap"),
                    )

    def test_invalid_host_returns_bad_request(self) -> None:
        with patch.object(redirect.socket, "has_dualstack_ipv6", return_value=False):
            server = redirect.create_server(0)
        with server:
            self.assertEqual(self.request(server, "127.0.0.1", "[broken"), (400, None))

    def test_one_listener_accepts_ipv4_and_ipv6(self) -> None:
        if not socket.has_dualstack_ipv6():
            self.skipTest("Dual-stack IPv6 is unavailable")
        with redirect.create_server(0) as server:
            if server.socket.family != socket.AF_INET6:
                self.skipTest("IPv6 is disabled on local interfaces")
            for address, host in (("127.0.0.1", "127.0.0.1"), ("::1", "[::1]")):
                with self.subTest(address=address):
                    self.assertEqual(
                        self.request(server, address, host),
                        (308, f"https://{host}/login?next=%2Fmap"),
                    )

    def test_disabled_ipv6_falls_back_to_working_ipv4(self) -> None:
        with (
            patch.object(redirect.socket, "has_dualstack_ipv6", return_value=True),
            patch.object(redirect, "DualStackHTTPServer", side_effect=OSError(errno.EADDRNOTAVAIL, "IPv6 disabled")),
            redirect.create_server(0) as server,
        ):
            self.assertEqual(server.socket.family, socket.AF_INET)
            self.assertEqual(self.request(server, "127.0.0.1", "aprsbox.local")[0], 308)

    def test_bind_conflict_does_not_silently_fall_back(self) -> None:
        with (
            patch.object(redirect.socket, "has_dualstack_ipv6", return_value=True),
            patch.object(redirect, "DualStackHTTPServer", side_effect=OSError(errno.EADDRINUSE, "Port in use")),
            patch.object(redirect, "HTTPServer") as ipv4_server,
        ):
            with self.assertRaises(OSError):
                redirect.create_server(0)
            ipv4_server.assert_not_called()


if __name__ == "__main__":
    unittest.main()
