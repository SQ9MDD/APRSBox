#!/usr/bin/env python3

import socket


def web_bind_host() -> str:
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
            probe.bind(("::", 0))
    except OSError:
        return "0.0.0.0"
    # An empty host makes Uvicorn open separate IPv4 and IPv6 listeners.
    return ""


if __name__ == "__main__":
    print(web_bind_host())
