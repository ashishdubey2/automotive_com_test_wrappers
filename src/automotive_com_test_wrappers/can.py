"""CAN frame types and a transport-agnostic CAN test wrapper."""

from dataclasses import dataclass
from typing import Protocol

from .exceptions import FrameMismatchError, ProtocolError


@dataclass(frozen=True)
class CanFrame:
    arbitration_id: int
    data: bytes
    is_extended: bool = False
    is_remote_frame: bool = False

    def __post_init__(self) -> None:
        max_id = 0x1FFFFFFF if self.is_extended else 0x7FF
        if not 0 <= self.arbitration_id <= max_id:
            raise ValueError(f"arbitration_id must be in range 0..{max_id:#x}")
        if len(self.data) > 8:
            raise ValueError("Classical CAN payload cannot exceed 8 bytes")
        if self.is_remote_frame and self.data:
            raise ValueError("Remote CAN frames cannot contain data")


class CanTransport(Protocol):
    """Minimal adapter contract implemented by a CAN hardware driver."""

    def send(self, frame: CanFrame) -> None: ...

    def receive(self, timeout: float | None = None) -> CanFrame | None: ...


class CanTester:
    """Send, receive, and compare classical CAN frames through an adapter."""

    def __init__(self, transport: CanTransport) -> None:
        self._transport = transport

    def transmit(self, frame: CanFrame) -> None:
        self._transport.send(frame)

    def receive(self, timeout: float | None = None) -> CanFrame:
        frame = self._transport.receive(timeout=timeout)
        if frame is None:
            raise TimeoutError("No CAN frame received before timeout")
        return frame

    def expect(self, expected: CanFrame, timeout: float | None = None) -> CanFrame:
        actual = self.receive(timeout=timeout)
        if actual != expected:
            raise FrameMismatchError(
                f"Expected CAN frame {expected!r}, received {actual!r}"
            )
        return actual

    def receive_standard(self, timeout: float | None = None) -> CanFrame:
        frame = self.receive(timeout=timeout)
        if frame.is_extended:
            raise ProtocolError("Received an extended frame where standard CAN was expected")
        return frame
