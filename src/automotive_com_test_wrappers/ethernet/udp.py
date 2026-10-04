"""A connected UDP client for exercising automotive Ethernet endpoints."""

import socket
from typing import Callable


class UDPClient:
    def __init__(
        self,
        host: str,
        port: int,
        timeout: float | None = 1.0,
        socket_factory: Callable[[int, int], socket.socket] = socket.socket,
    ) -> None:
        if not 0 < port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        self._address = (host, port)
        self._socket = socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.settimeout(timeout)
        self._socket.connect(self._address)

    def send(self, payload: bytes) -> None:
        self._socket.send(payload)

    def receive(self, max_size: int = 65535) -> bytes:
        if not 0 < max_size <= 65535:
            raise ValueError("max_size must be between 1 and 65535")
        return self._socket.recv(max_size)

    def close(self) -> None:
        self._socket.close()

    def __enter__(self) -> "UDPClient":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
