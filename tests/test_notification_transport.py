import io
import json
import socket
import ssl
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from app.services.notifications import (
    _create_ipv4_connection,
    _deliver_event_to_transport,
    _send_json_request,
)


class NotificationTransportTests(unittest.TestCase):
    def test_telegram_succeeds_when_ipv6_tls_stalls_and_preserves_https_hostname(self) -> None:
        ipv4 = "192.0.2.10"
        ipv6 = "2001:db8::10"
        opened_sockets = []
        tls_hosts = []

        def resolve(host, port, family=socket.AF_UNSPEC, type=0):
            addresses = []
            if family != socket.AF_INET and host != ipv4:
                addresses.append((socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ipv6, port, 0, 0)))
            addresses.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", (ipv4, port)))
            return addresses

        def make_socket(family, socktype, proto):
            sock = Mock(family=family)
            sock.makefile.return_value = io.BytesIO(
                b'HTTP/1.1 200 OK\r\nContent-Length: 11\r\n\r\n{"ok":true}'
            )
            opened_sockets.append(sock)
            return sock

        def wrap_socket(context, sock, *, server_hostname):
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            tls_hosts.append(server_hostname)
            if sock.family == socket.AF_INET6:
                raise TimeoutError("The handshake operation timed out")
            return sock

        transport = {"transport_type": "telegram", "bot_token": "123:TEST", "chat_id": "42", "timeout_s": 5}
        event = {"message": "APRS message", "data": {"text": "Zażółć"}}
        with (
            patch("urllib.request.getproxies", return_value={}),
            patch("urllib.request._opener", None),
            patch("socket.getaddrinfo", side_effect=resolve),
            patch("socket.socket", side_effect=make_socket),
            patch.object(ssl.SSLContext, "wrap_socket", autospec=True, side_effect=wrap_socket),
        ):
            # The default connection reproduces the reported TLS timeout on IPv6.
            self.assertEqual(
                _deliver_event_to_transport(transport, event),
                (False, "Request timed out after 5s"),
            )
            result = _deliver_event_to_transport(
                {**transport, "force_ipv4": True},
                event,
            )

        self.assertEqual(result, (True, None))
        self.assertEqual([sock.family for sock in opened_sockets], [socket.AF_INET6, socket.AF_INET])
        self.assertEqual(tls_hosts, ["api.telegram.org", "api.telegram.org"])
        ipv4_socket = opened_sockets[-1]
        ipv4_socket.connect.assert_called_once_with((ipv4, 443))
        ipv4_socket.settimeout.assert_called_once_with(5)
        sent = b"".join(call.args[0] for call in ipv4_socket.sendall.call_args_list)
        head, body = sent.split(b"\r\n\r\n", 1)
        self.assertIn(b"POST /bot123:TEST/sendMessage HTTP/1.1", head)
        self.assertIn(b"Host: api.telegram.org", head)
        self.assertEqual(json.loads(body), {"chat_id": "42", "text": "APRS message\nZażółć"})

    def test_ipv4_connection_tries_remaining_addresses_after_connect_failure(self) -> None:
        addresses = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.10", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.11", 443)),
        ]
        connected_socket = Mock()
        with (
            patch("socket.getaddrinfo", return_value=addresses),
            patch("socket.create_connection", side_effect=[OSError("unreachable"), connected_socket]) as connect,
        ):
            result = _create_ipv4_connection(("api.telegram.org", 443), 5)
        self.assertIs(result, connected_socket)
        self.assertEqual([call.args[0] for call in connect.call_args_list], [item[-1] for item in addresses])

    def test_ipv4_connection_reports_missing_addresses_and_dns_errors(self) -> None:
        with patch("socket.getaddrinfo", return_value=[]):
            with self.assertRaisesRegex(OSError, "No IPv4 address"):
                _create_ipv4_connection(("api.telegram.org", 443), 5)
        with patch("socket.getaddrinfo", side_effect=socket.gaierror(-2, "Name or service not known")):
            with self.assertRaises(socket.gaierror):
                _create_ipv4_connection(("api.telegram.org", 443), 5)

    def test_webhook_uses_default_networking_and_preserves_secret_header(self) -> None:
        with (
            patch("app.services.notifications.urlopen") as open_request,
            patch("app.services.notifications.build_opener") as custom_opener,
        ):
            result = _deliver_event_to_transport(
                {
                    "transport_type": "webhook",
                    "url": "https://webhook.example/events",
                    "secret_header_name": "Authorization",
                    "secret_token": "Bearer secret",
                    "timeout_s": 9,
                },
                {"message": "test"},
            )
        self.assertEqual(result, (True, None))
        custom_opener.assert_not_called()
        request = open_request.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(json.loads(request.data), {"message": "test"})
        self.assertEqual(open_request.call_args.kwargs, {"timeout": 9})

    def test_network_errors_include_reason_without_exposing_telegram_token(self) -> None:
        url = "https://api.telegram.org/bot123:TEST/sendMessage"
        cases = [
            (URLError(socket.gaierror(-2, "Name or service not known")), "Name or service not known"),
            (URLError(ssl.SSLCertVerificationError(1, "certificate verify failed")), "certificate verify failed"),
            (URLError(TimeoutError("TLS handshake timed out")), "Request timed out after 5s"),
            (TimeoutError("read timed out"), "Request timed out after 5s"),
            (URLError(f"Unable to connect to {url} with token 123:TEST"), "[redacted URL]"),
            (HTTPError(url, 401, "Unauthorized", {}, None), "HTTP 401"),
        ]
        for failure, expected_detail in cases:
            with self.subTest(failure=type(failure).__name__, detail=expected_detail):
                with patch("app.services.notifications.urlopen", side_effect=failure):
                    ok, error = _send_json_request(url, {}, timeout_s=5)
                self.assertFalse(ok)
                self.assertIn(expected_detail, error)
                self.assertNotIn("123:TEST", error)


if __name__ == "__main__":
    unittest.main()
