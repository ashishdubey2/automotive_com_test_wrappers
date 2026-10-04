"""Loopback integration tests using Linux vcan and localhost sockets."""

import importlib.util
import platform
import socket
import socketserver
import threading
import unittest
from contextlib import contextmanager
from typing import Iterator

from automotive_com_test_wrappers.can import CanFrame, CanTester
from automotive_com_test_wrappers.ethernet.someip import (
    SomeIpMessage,
    SomeIpTcpClient,
    SomeIpUdpClient,
)
from automotive_com_test_wrappers.ethernet.tcp import TCPClient
from automotive_com_test_wrappers.ethernet.udp import UDPClient
from automotive_com_test_wrappers.lin import LinFrame, LinTester
from automotive_com_test_wrappers.peak import PeakCanTransport
from automotive_com_test_wrappers.virtual import VirtualLinBus


def _vcan_ready() -> bool:
    if platform.system() != "Linux" or importlib.util.find_spec("can") is None:
        return False
    try:
        socket.if_nametoindex("vcan0")
        with open("/sys/class/net/vcan0/flags", encoding="ascii") as flags_file:
            return bool(int(flags_file.read().strip(), 16) & 0x1)
    except (OSError, ValueError):
        return False


def _tcp_exact_echo_handler(size: int) -> type[socketserver.BaseRequestHandler]:
    class ExactEchoHandler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            received = bytearray()
            # TCP is a byte stream; this test fixture reads the known test-frame size.
            while len(received) < size:
                chunk = self.request.recv(size - len(received))
                if not chunk:
                    return
                received.extend(chunk)
            self.request.sendall(received)

    return ExactEchoHandler


class _UDPExactEchoHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        payload, server_socket = self.request
        server_socket.sendto(payload, self.client_address)


@contextmanager
def _tcp_echo_server(size: int) -> Iterator[tuple[str, int]]:
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = Server(("127.0.0.1", 0), _tcp_exact_echo_handler(size))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield ("127.0.0.1", server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@contextmanager
def _udp_echo_server() -> Iterator[tuple[str, int]]:
    class Server(socketserver.ThreadingUDPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = Server(("127.0.0.1", 0), _UDPExactEchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield ("127.0.0.1", server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class VirtualLinIntegrationTests(unittest.TestCase):
    def test_pair_transmits_and_receives_validated_frames(self) -> None:
        master_transport, slave_transport = VirtualLinBus.create_pair()
        master = LinTester(master_transport)
        slave = LinTester(slave_transport)
        try:
            enhanced = LinFrame.create(0x12, b"\x10\x20\x30")
            master.transmit(0x12, enhanced.data)
            received = slave.receive(0x12, timeout=0.2)
            self.assertEqual(received, enhanced)
            self.assertEqual(received.protected_id, 0x92)
            self.assertEqual(received.data, b"\x10\x20\x30")
            self.assertEqual(received.checksum, 0x0D)
            self.assertTrue(received.enhanced_checksum)

            classic = LinFrame.create(0x22, b"\xA5", enhanced_checksum=False)
            slave.transmit(0x22, classic.data, enhanced_checksum=False)
            response = master.receive(0x22, timeout=0.2)
            self.assertEqual(response, classic)
            self.assertEqual(response.checksum, 0x5A)
            self.assertFalse(response.enhanced_checksum)
        finally:
            master_transport.close()
            slave_transport.close()

    def test_filtering_preserves_separate_pending_frames(self) -> None:
        first, second = VirtualLinBus.create_pair()
        try:
            first.send(LinFrame.create(0x10, b"\x01"))
            first.send(LinFrame.create(0x11, b"\x02"))
            self.assertEqual(second.receive(0x11, timeout=0.2).data, b"\x02")
            self.assertEqual(second.receive(0x10, timeout=0.2).data, b"\x01")
            self.assertIsNone(second.receive(0x12, timeout=0.01))
        finally:
            first.close()
            second.close()


@unittest.skipUnless(
    _vcan_ready(),
    "Linux vcan0 is not up; run 'sudo bash scripts/setup_vcan.sh' first",
)
class VirtualCanIntegrationTests(unittest.TestCase):
    def test_can_frame_is_received_from_another_socketcan_endpoint(self) -> None:
        frame = CanFrame(
            arbitration_id=0x321,
            data=bytes((0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80)),
        )
        with (
            PeakCanTransport(channel="vcan0") as sender,
            PeakCanTransport(channel="vcan0") as receiver,
        ):
            CanTester(sender).transmit(frame)
            received = CanTester(receiver).expect(frame, timeout=1.0)

        self.assertEqual(received.arbitration_id, 0x321)
        self.assertFalse(received.is_extended)
        self.assertFalse(received.is_remote_frame)
        self.assertEqual(len(received.data), 8)
        self.assertEqual(received.data, b"\x10\x20\x30\x40\x50\x60\x70\x80")


class LocalhostEthernetIntegrationTests(unittest.TestCase):
    def test_tcp_sends_and_receives_a_separate_known_length_message(self) -> None:
        payload = (
            b"\x10"  # Application byte 0
            b"\x20"  # Application byte 1
            b"\x30"  # Application byte 2
            b"\x40"  # Application byte 3
            b"\x50"  # Application byte 4
        )
        with _tcp_echo_server(len(payload)) as (host, port):
            with TCPClient(host, port) as client:
                client.send(payload)
                received = client.receive_exactly(len(payload))

        self.assertEqual(received, payload)

    def test_udp_preserves_datagram_message_boundaries(self) -> None:
        # Each tuple entry is one separate UDP datagram/message.
        messages = (
            b"\xA1\xA2",  # Datagram 1: bytes 0-1
            b"\xB1\xB2\xB3",  # Datagram 2: bytes 0-2
        )
        with _udp_echo_server() as (host, port):
            with UDPClient(host, port) as client:
                for payload in messages:
                    client.send(payload)
                    self.assertEqual(client.receive(), payload)

    def test_someip_tcp_receives_each_encoded_field(self) -> None:
        message = SomeIpMessage(
            service_id=0x1234,
            method_id=0x5678,
            client_id=0xABCD,
            session_id=0x0102,
            interface_version=2,
            message_type=0,
            return_code=0,
            payload=b"\xDE\xAD",
        )
        # Byte 0-1 service; 2-3 method; 4-7 length; 8-9 client; 10-11 session.
        # Byte 12 protocol version; 13 interface version; 14 message type;
        # byte 15 return code; byte 16 onward is the application payload.
        expected_wire = (
            b"\x12\x34"  # 0-1: service ID
            b"\x56\x78"  # 2-3: method ID
            b"\x00\x00\x00\x0A"  # 4-7: length, including bytes 8-15 and payload
            b"\xAB\xCD"  # 8-9: client ID
            b"\x01\x02"  # 10-11: session ID
            b"\x01"  # 12: SOME/IP protocol version
            b"\x02"  # 13: interface version
            b"\x00"  # 14: request message type
            b"\x00"  # 15: success return code
            b"\xDE\xAD"  # 16-17: payload bytes
        )
        self.assertEqual(message.to_bytes(), expected_wire)

        with _tcp_echo_server(len(expected_wire)) as (host, port):
            client = SomeIpTcpClient(TCPClient(host, port))
            with client:
                client.send(message)
                received = client.receive()

        self.assertEqual(received, message)
        self.assertEqual(received.service_id, 0x1234)
        self.assertEqual(received.method_id, 0x5678)
        self.assertEqual(received.client_id, 0xABCD)
        self.assertEqual(received.session_id, 0x0102)
        self.assertEqual(received.interface_version, 2)
        self.assertEqual(received.message_type, 0)
        self.assertEqual(received.return_code, 0)
        self.assertEqual(received.payload, b"\xDE\xAD")

    def test_someip_udp_receives_one_complete_message_per_datagram(self) -> None:
        message = SomeIpMessage(
            service_id=0x4321,
            method_id=0x0010,
            client_id=0x0001,
            session_id=0x0002,
            interface_version=1,
            message_type=0x80,
            return_code=0,
            payload=b"\x01\x02\x03",
        )
        wire = message.to_bytes()
        with _udp_echo_server() as (host, port):
            client = SomeIpUdpClient(UDPClient(host, port))
            with client:
                client.send(message)
                received = client.receive()

        self.assertEqual(received, message)
        self.assertEqual(len(wire), 19)
        self.assertEqual(int.from_bytes(wire[4:8], byteorder="big"), 11)
        self.assertEqual(wire[16:], b"\x01\x02\x03")


if __name__ == "__main__":
    unittest.main()
