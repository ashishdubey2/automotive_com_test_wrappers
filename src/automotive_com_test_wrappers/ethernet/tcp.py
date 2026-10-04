"""A small TCP client for exercising automotive Ethernet endpoints."""

import socket
from typing import Callable


class TCPClient:
    def __init__(
        self,
        host: str,
        port: int,
        timeout: float | None = 1.0,
        socket_factory: Callable[..., socket.socket] = socket.create_connection,
    ) -> None:
        if not 0 < port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        self._address = (host, port)
        self._timeout = timeout
        self._socket_factory = socket_factory
        self._socket: socket.socket | None = None

    def connect(self) -> None:
        if self._socket is not None:
            return
        self._socket = self._socket_factory(self._address, self._timeout)

    def send(self, payload: bytes) -> None:
        self._require_socket().sendall(payload)

    def receive(self, size: int) -> bytes:
        if size <= 0:
            raise ValueError("size must be greater than zero")
        return self._require_socket().recv(size)

    def receive_exactly(self, size: int) -> bytes:
        if size < 0:
            raise ValueError("size cannot be negative")
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self.receive(size - len(chunks))
            if not chunk:
                raise ConnectionError("TCP connection closed before message was complete")
            chunks.extend(chunk)
        return bytes(chunks)

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def _require_socket(self) -> socket.socket:
        if self._socket is None:
            raise RuntimeError("TCP client is not connected; call connect() first")
        return self._socket

    def __enter__(self) -> "TCPClient":
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
