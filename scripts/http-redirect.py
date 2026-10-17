#!/usr/bin/env python3

import errno
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class RedirectHandler(BaseHTTPRequestHandler):
    def redirect(self) -> None:
        try:
            host = urlsplit(f"//{self.headers.get('Host', '')}").hostname
        except ValueError:
            host = None
        if not host:
            self.send_error(400, "Invalid Host header")
            return
        if ":" in host:
            host = f"[{host}]"
        self.send_response(308)
        self.send_header("Location", f"https://{host}{self.path}")
        self.end_headers()

    do_GET = redirect
    do_POST = redirect
    do_PUT = redirect
    do_DELETE = redirect
    do_PATCH = redirect
    do_HEAD = redirect

    def log_message(self, format: str, *args: object) -> None:
        pass


class DualStackHTTPServer(HTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self) -> None:
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def create_server(port: int = 80) -> HTTPServer:
    if socket.has_dualstack_ipv6():
        try:
            return DualStackHTTPServer(("::", port), RedirectHandler)
        except OSError as exc:
            # IPv6 may be supported by the kernel but disabled on interfaces.
            if exc.errno not in {errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT, errno.EADDRNOTAVAIL}:
                raise
    return HTTPServer(("0.0.0.0", port), RedirectHandler)


def main() -> None:
    install_root = Path(os.getenv("APRSBOX_INSTALL_ROOT", "/opt/aprsbox"))
    if not (install_root / "data" / "ssl" / "https-enabled").is_file():
        return
    with create_server() as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
