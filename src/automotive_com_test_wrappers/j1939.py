"""J1939 identifier helpers and a test wrapper over a CAN transport."""

from dataclasses import dataclass

from .can import CanFrame, CanTransport
from .exceptions import ProtocolError


@dataclass(frozen=True)
class J1939Identifier:
    priority: int
    pgn: int
    source_address: int
    destination_address: int | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.priority <= 7:
            raise ValueError("priority must be between 0 and 7")
        if not 0 <= self.pgn <= 0x3FFFF:
            raise ValueError("pgn must fit in 18 bits")
        if not 0 <= self.source_address <= 0xFF:
            raise ValueError("source_address must fit in 8 bits")
        pdu_format = (self.pgn >> 8) & 0xFF
        if pdu_format < 240:
            if self.pgn & 0xFF:
                raise ValueError("PDU1 PGNs must have a zero group extension")
            if self.destination_address is None or not 0 <= self.destination_address <= 0xFF:
                raise ValueError("PDU1 PGNs require an 8-bit destination address")
        elif self.destination_address is not None:
            raise ValueError("PDU2 PGNs do not have a destination address")

    @property
    def arbitration_id(self) -> int:
        identifier_pgn = self.pgn
        if self.destination_address is not None:
            identifier_pgn |= self.destination_address
        return (self.priority << 26) | (identifier_pgn << 8) | self.source_address

    @classmethod
    def from_arbitration_id(cls, arbitration_id: int) -> "J1939Identifier":
        if not 0 <= arbitration_id <= 0x1FFFFFFF:
            raise ValueError("J1939 arbitration ID must fit in 29 bits")
        priority = (arbitration_id >> 26) & 0x7
        identifier_pgn = (arbitration_id >> 8) & 0x3FFFF
        source_address = arbitration_id & 0xFF
        pdu_format = (identifier_pgn >> 8) & 0xFF
        if pdu_format < 240:
            return cls(
                priority,
                identifier_pgn & 0x3FF00,
                source_address,
                identifier_pgn & 0xFF,
            )
        return cls(priority, identifier_pgn, source_address)


class J1939Tester:
    """Transmit and decode J1939 messages using a CAN adapter."""

    def __init__(self, transport: CanTransport) -> None:
        self._transport = transport

    def transmit(self, identifier: J1939Identifier, data: bytes) -> None:
        if len(data) > 8:
            raise ValueError("A single J1939 CAN frame cannot exceed 8 data bytes")
        self._transport.send(
            CanFrame(identifier.arbitration_id, data, is_extended=True)
        )

    def receive(self, timeout: float | None = None) -> tuple[J1939Identifier, bytes]:
        frame = self._transport.receive(timeout=timeout)
        if frame is None:
            raise TimeoutError("No J1939 frame received before timeout")
        if not frame.is_extended:
            raise ProtocolError("J1939 requires a 29-bit extended CAN frame")
        return J1939Identifier.from_arbitration_id(frame.arbitration_id), frame.data
