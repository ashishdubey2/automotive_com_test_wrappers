import unittest

from automotive_com_test_wrappers.can import CanFrame, CanTester
from automotive_com_test_wrappers.ethernet.someip import (
    SomeIpMessage,
    SomeIpTcpClient,
    SomeIpUdpClient,
)
from automotive_com_test_wrappers.ethernet.tcp import TCPClient
from automotive_com_test_wrappers.ethernet.udp import UDPClient
from automotive_com_test_wrappers.exceptions import FrameMismatchError, ProtocolError
from automotive_com_test_wrappers.j1939 import J1939Identifier, J1939Tester
from automotive_com_test_wrappers.lin import (
    LinFrame,
    LinTester,
    lin_checksum,
    protected_identifier,
)


class FakeCanTransport:
    def __init__(self) -> None:
        self.sent: list[CanFrame] = []
        self.received: CanFrame | None = None

    def send(self, frame: CanFrame) -> None:
        self.sent.append(frame)

    def receive(self, timeout: float | None = None) -> CanFrame | None:
        return self.received


class FakeLinTransport:
    def __init__(self) -> None:
        self.sent: list[LinFrame] = []
        self.received: LinFrame | None = None

    def send(self, frame: LinFrame) -> None:
        self.sent.append(frame)

    def receive(
        self, identifier: int, timeout: float | None = None
    ) -> LinFrame | None:
        return self.received


class FakeStreamSocket:
    def __init__(self, incoming: bytes = b"") -> None:
        self.incoming = bytearray(incoming)
        self.sent: list[bytes] = []
        self.closed = False

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def recv(self, size: int) -> bytes:
        chunk = bytes(self.incoming[: min(size, 3)])
        del self.incoming[: len(chunk)]
        return chunk

    def close(self) -> None:
        self.closed = True


class FakeDatagramSocket:
    def __init__(self, incoming: bytes = b"") -> None:
        self.incoming = incoming
        self.sent: list[bytes] = []
        self.address: tuple[str, int] | None = None
        self.timeout: float | None = None
        self.closed = False

    def settimeout(self, timeout: float | None) -> None:
        self.timeout = timeout

    def connect(self, address: tuple[str, int]) -> None:
        self.address = address

    def send(self, data: bytes) -> int:
        self.sent.append(data)
        return len(data)

    def recv(self, size: int) -> bytes:
        return self.incoming[:size]

    def close(self) -> None:
        self.closed = True


class CanTests(unittest.TestCase):
    def test_can_transmit_receive_and_expect(self) -> None:
        transport = FakeCanTransport()
        tester = CanTester(transport)
        frame = CanFrame(0x123, b"\x10\x20")
        tester.transmit(frame)
        transport.received = frame
        self.assertEqual(tester.expect(frame), frame)
        self.assertEqual(transport.sent, [frame])

    def test_can_expect_reports_mismatch(self) -> None:
        transport = FakeCanTransport()
        transport.received = CanFrame(0x123, b"\x01")
        with self.assertRaises(FrameMismatchError):
            CanTester(transport).expect(CanFrame(0x123, b"\x02"))


class J1939Tests(unittest.TestCase):
    def test_pdu1_identifier_round_trip(self) -> None:
        identifier = J1939Identifier(3, 0x00EA00, 0x80, 0xF9)
        self.assertEqual(
            J1939Identifier.from_arbitration_id(identifier.arbitration_id),
            identifier,
        )

    def test_pdu2_identifier_round_trip(self) -> None:
        identifier = J1939Identifier(6, 0x00F004, 0xA5)
        self.assertEqual(
            J1939Identifier.from_arbitration_id(identifier.arbitration_id),
            identifier,
        )

    def test_j1939_uses_extended_can_frames(self) -> None:
        transport = FakeCanTransport()
        tester = J1939Tester(transport)
        identifier = J1939Identifier(3, 0x00EA00, 0x80, 0xF9)
        tester.transmit(identifier, b"\x01")
        self.assertTrue(transport.sent[0].is_extended)
        transport.received = transport.sent[0]
        self.assertEqual(tester.receive(), (identifier, b"\x01"))


class LinTests(unittest.TestCase):
    def test_protected_identifier_and_checksum(self) -> None:
        self.assertEqual(protected_identifier(0x12), 0x92)
        self.assertEqual(lin_checksum(b"\x01\x02", 0x92), 0x6A)

    def test_lin_transmit_receive_and_validation(self) -> None:
        transport = FakeLinTransport()
        tester = LinTester(transport)
        frame = tester.transmit(0x12, b"\x01\x02")
        self.assertEqual(transport.sent, [frame])
        transport.received = frame
        self.assertEqual(tester.receive(0x12), frame)

    def test_invalid_lin_checksum_is_rejected(self) -> None:
        frame = LinFrame.create(0x12, b"\x01\x02")
        invalid = LinFrame(frame.protected_id, frame.data, frame.checksum ^ 0x01)
        with self.assertRaises(ProtocolError):
            invalid.validate()


class SomeIpTests(unittest.TestCase):
    def test_message_round_trip(self) -> None:
        message = SomeIpMessage(
            service_id=0x1234,
            method_id=0x5678,
            client_id=0x9ABC,
            session_id=0xDEF0,
            interface_version=1,
            message_type=0,
            return_code=0,
            payload=b"\x01\x02\x03",
        )
        encoded = message.to_bytes()
        self.assertEqual(int.from_bytes(encoded[4:8], "big"), 11)
        self.assertEqual(SomeIpMessage.from_bytes(encoded), message)

    def test_invalid_message_lengths_are_rejected(self) -> None:
        with self.assertRaises(ProtocolError):
            SomeIpMessage.from_bytes(b"\x00" * 15)
        encoded = SomeIpMessage(1, 2, 3, 4, 1, 0, 0).to_bytes()
        with self.assertRaises(ProtocolError):
            SomeIpMessage.from_bytes(encoded + b"\x00")

    def test_someip_tcp_handles_fragmented_stream_reads(self) -> None:
        message = SomeIpMessage(1, 2, 3, 4, 1, 0, 0, b"payload")
        stream = FakeStreamSocket(message.to_bytes())
        tcp = TCPClient("localhost", 3000, socket_factory=lambda *_: stream)
        client = SomeIpTcpClient(tcp)
        client.connect()
        self.assertEqual(client.receive(), message)
        client.close()
        self.assertTrue(stream.closed)

    def test_someip_udp_encodes_and_decodes_datagrams(self) -> None:
        message = SomeIpMessage(1, 2, 3, 4, 1, 0, 0, b"payload")
        datagram = FakeDatagramSocket(message.to_bytes())
        udp = UDPClient("localhost", 3000, socket_factory=lambda *_: datagram)
        client = SomeIpUdpClient(udp)
        client.send(message)
        self.assertEqual(datagram.sent, [message.to_bytes()])
        self.assertEqual(client.receive(), message)
        client.close()
        self.assertTrue(datagram.closed)


class EthernetTests(unittest.TestCase):
    def test_tcp_receives_exact_size_across_partial_reads(self) -> None:
        stream = FakeStreamSocket(b"abcdef")
        client = TCPClient("localhost", 3000, socket_factory=lambda *_: stream)
        client.connect()
        self.assertEqual(client.receive_exactly(6), b"abcdef")
        client.close()

    def test_udp_sends_and_receives_datagram(self) -> None:
        datagram = FakeDatagramSocket(b"reply")
        client = UDPClient("localhost", 3001, socket_factory=lambda *_: datagram)
        client.send(b"request")
        self.assertEqual(client.receive(), b"reply")
        self.assertEqual(datagram.sent, [b"request"])
        self.assertEqual(datagram.address, ("localhost", 3001))
        client.close()


if __name__ == "__main__":
    unittest.main()
