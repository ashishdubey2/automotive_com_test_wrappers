"""LIN frame encoding, checksum validation, and transport-agnostic testing."""

from dataclasses import dataclass
from typing import Protocol

from .exceptions import FrameMismatchError, ProtocolError


def protected_identifier(identifier: int) -> int:
    """Return the LIN protected identifier (6-bit ID plus parity bits)."""
    if not 0 <= identifier <= 0x3F:
        raise ValueError("LIN identifier must fit in 6 bits")
    bits = [(identifier >> index) & 1 for index in range(6)]
    parity_0 = bits[0] ^ bits[1] ^ bits[2] ^ bits[4]
    parity_1 = 1 ^ (bits[1] ^ bits[3] ^ bits[4] ^ bits[5])
    return identifier | (parity_0 << 6) | (parity_1 << 7)


def lin_checksum(data: bytes, protected_id: int, enhanced: bool = True) -> int:
    """Calculate classic or enhanced LIN checksum."""
    if not 1 <= len(data) <= 8:
        raise ValueError("LIN payload must contain between 1 and 8 bytes")
    if not 0 <= protected_id <= 0xFF:
        raise ValueError("protected_id must fit in 8 bits")
    total = sum(data) + (protected_id if enhanced else 0)
    while total > 0xFF:
        total = (total & 0xFF) + (total >> 8)
    return (~total) & 0xFF


@dataclass(frozen=True)
class LinFrame:
    protected_id: int
    data: bytes
    checksum: int
    enhanced_checksum: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.protected_id <= 0xFF:
            raise ValueError("protected_id must fit in 8 bits")
        if not 1 <= len(self.data) <= 8:
            raise ValueError("LIN payload must contain between 1 and 8 bytes")
        if not 0 <= self.checksum <= 0xFF:
            raise ValueError("checksum must fit in 8 bits")

    @classmethod
    def create(
        cls, identifier: int, data: bytes, enhanced_checksum: bool = True
    ) -> "LinFrame":
        pid = protected_identifier(identifier)
        return cls(pid, data, lin_checksum(data, pid, enhanced_checksum), enhanced_checksum)

    @property
    def identifier(self) -> int:
        return self.protected_id & 0x3F

    def validate(self) -> None:
        if self.protected_id != protected_identifier(self.identifier):
            raise ProtocolError("Invalid LIN protected-identifier parity")
        expected = lin_checksum(self.data, self.protected_id, self.enhanced_checksum)
        if self.checksum != expected:
            raise ProtocolError(
                f"Invalid LIN checksum: expected {expected:#04x}, got {self.checksum:#04x}"
            )


class LinTransport(Protocol):
    """Minimal adapter contract implemented by a LIN hardware driver."""

    def send(self, frame: LinFrame) -> None: ...

    def receive(
        self, identifier: int, timeout: float | None = None
    ) -> LinFrame | None: ...


class LinTester:
    def __init__(self, transport: LinTransport) -> None:
        self._transport = transport

    def transmit(
        self, identifier: int, data: bytes, enhanced_checksum: bool = True
    ) -> LinFrame:
        frame = LinFrame.create(identifier, data, enhanced_checksum)
        self._transport.send(frame)
        return frame

    def receive(self, identifier: int, timeout: float | None = None) -> LinFrame:
        if not 0 <= identifier <= 0x3F:
            raise ValueError("LIN identifier must fit in 6 bits")
        frame = self._transport.receive(identifier, timeout=timeout)
        if frame is None:
            raise TimeoutError("No LIN frame received before timeout")
        if frame.identifier != identifier:
            raise ProtocolError(
                f"Expected LIN identifier {identifier:#04x}, got {frame.identifier:#04x}"
            )
        frame.validate()
        return frame

    def expect(
        self, expected: LinFrame, timeout: float | None = None
    ) -> LinFrame:
        actual = self.receive(expected.identifier, timeout=timeout)
        if actual != expected:
            raise FrameMismatchError(
                f"Expected LIN frame {expected!r}, received {actual!r}"
            )
        return actual
