"""SOME/IP message encoding and TCP/UDP clients."""

import struct
from dataclasses import dataclass
from enum import IntEnum

from ..exceptions import ProtocolError
from .tcp import TCPClient
from .udp import UDPClient


class SomeIpMessageType(IntEnum):
    REQUEST = 0x00
    REQUEST_NO_RETURN = 0x01
    NOTIFICATION = 0x02
    RESPONSE = 0x80
    ERROR = 0x81


@dataclass(frozen=True)
class SomeIpMessage:
    service_id: int
    method_id: int
    client_id: int
    session_id: int
    interface_version: int
    message_type: int
    return_code: int
    payload: bytes = b""
    protocol_version: int = 1

    _HEADER = struct.Struct("!HHIIBBBB")

    def __post_init__(self) -> None:
        fields = (
            ("service_id", self.service_id, 0xFFFF),
            ("method_id", self.method_id, 0xFFFF),
            ("client_id", self.client_id, 0xFFFF),
            ("session_id", self.session_id, 0xFFFF),
            ("interface_version", self.interface_version, 0xFF),
            ("message_type", self.message_type, 0xFF),
            ("return_code", self.return_code, 0xFF),
            ("protocol_version", self.protocol_version, 0xFF),
        )
        for name, value, maximum in fields:
            if not 0 <= value <= maximum:
                raise ValueError(f"{name} must be between 0 and {maximum:#x}")

    @property
    def message_id(self) -> int:
        return (self.service_id << 16) | self.method_id

    @property
    def request_id(self) -> int:
        return (self.client_id << 16) | self.session_id

    def to_bytes(self) -> bytes:
        length = 8 + len(self.payload)
        if length > 0xFFFFFFFF:
            raise ValueError("SOME/IP payload is too large")
        header = self._HEADER.pack(
            self.service_id,
            self.method_id,
            length,
            self.request_id,
            self.protocol_version,
            self.interface_version,
            self.message_type,
            self.return_code,
        )
        return header + self.payload

    @classmethod
    def from_bytes(cls, data: bytes) -> "SomeIpMessage":
        if len(data) < cls._HEADER.size:
            raise ProtocolError("SOME/IP message is shorter than its 16-byte header")
        (
            service_id,
            method_id,
            length,
            request_id,
            protocol_version,
            interface_version,
            message_type,
            return_code,
        ) = cls._HEADER.unpack_from(data)
        if length < 8:
            raise ProtocolError("SOME/IP length field must be at least 8")
        if len(data) != length + 8:
            raise ProtocolError(
                f"SOME/IP length mismatch: header declares {length + 8} bytes, "
                f"received {len(data)}"
            )
        return cls(
            service_id=service_id,
            method_id=method_id,
            client_id=request_id >> 16,
            session_id=request_id & 0xFFFF,
            interface_version=interface_version,
            message_type=message_type,
            return_code=return_code,
            payload=data[cls._HEADER.size :],
            protocol_version=protocol_version,
        )


class SomeIpUdpClient:
    """Send and receive one complete SOME/IP message per UDP datagram."""

    def __init__(self, client: UDPClient) -> None:
        self._client = client

    def send(self, message: SomeIpMessage) -> None:
        self._client.send(message.to_bytes())

    def receive(self, max_size: int = 65535) -> SomeIpMessage:
        return SomeIpMessage.from_bytes(self._client.receive(max_size))

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SomeIpUdpClient":
        self._client.__enter__()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self._client.__exit__(exc_type, exc_value, traceback)


class SomeIpTcpClient:
    """Send and receive length-delimited SOME/IP messages over a TCP stream."""

    def __init__(self, client: TCPClient) -> None:
        self._client = client

    def send(self, message: SomeIpMessage) -> None:
        self._client.send(message.to_bytes())

    def receive(self) -> SomeIpMessage:
        prefix = self._client.receive_exactly(8)
        length = int.from_bytes(prefix[4:8], byteorder="big")
        if length < 8:
            raise ProtocolError("SOME/IP length field must be at least 8")
        return SomeIpMessage.from_bytes(
            prefix + self._client.receive_exactly(length)
        )

    def connect(self) -> None:
        self._client.connect()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SomeIpTcpClient":
        self._client.__enter__()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self._client.__exit__(exc_type, exc_value, traceback)
