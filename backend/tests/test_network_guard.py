"""The test run never reaches the outside network (conftest's autouse guard)."""

import socket

import pytest


def test_external_network_blocked_but_loopback_allowed() -> None:
    with pytest.raises(OSError, match="blocked"):
        socket.create_connection(("example.com", 80), timeout=2)
    server = socket.socket()
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        client = socket.create_connection(("127.0.0.1", port), timeout=2)
        client.close()
    finally:
        server.close()
