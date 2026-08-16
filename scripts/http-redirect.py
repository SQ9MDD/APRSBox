#!/usr/bin/env python3

from http.server import BaseHTTPRequestHandler, HTTPServer


class RedirectHandler(BaseHTTPRequestHandler):
    def redirect(self) -> None:
        host = self.headers.get("Host", "").split(":")[0]
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


def main() -> None:
    HTTPServer(("0.0.0.0", 80), RedirectHandler).serve_forever()


if __name__ == "__main__":
    main()
