import unittest

import can
from plin.enums import PLINFrameChecksumType, PLINFrameDirection, PLINMessageType
from plin.structs import PLINMessage

from automotive_com_test_wrappers.can import CanFrame
from automotive_com_test_wrappers.exceptions import ProtocolError
from automotive_com_test_wrappers.lin import LinFrame
from automotive_com_test_wrappers.peak import PeakCanTransport, PeakLinTransport


class FakeCanBus:
    def __init__(self) -> None:
        self.sent: list[can.Message] = []
        self.received: can.Message | None = None
        self.shutdown_called = False

    def send(self, message: can.Message) -> None:
        self.sent.append(message)

    def recv(self, timeout: float | None = None) -> can.Message | None:
        return self.received

    def shutdown(self) -> None:
        self.shutdown_called = True


class FakePLINDevice:
    def __init__(self) -> None:
        self.started: tuple[object, int] | None = None
        self.stopped = False
        self.allowed_all_ids = False
        self.sent: list[PLINMessage] = []
        self.received: list[PLINMessage] = []

    def start(self, mode: object, baudrate: int = 19200) -> None:
        self.started = (mode, baudrate)

    def stop(self) -> None:
        self.stopped = True

    def clear_id_filter(self, allow_all: bool = True) -> None:
        self.allowed_all_ids = allow_all

    def write(self, message: PLINMessage) -> None:
        self.sent.append(message)

    def read(self, block: bool = True) -> PLINMessage | None:
        return self.received.pop(0) if self.received else None


class PeakCanTransportTests(unittest.TestCase):
    def test_maps_frames_and_leaves_injected_bus_open(self) -> None:
        bus = FakeCanBus()
        transport = PeakCanTransport(channel="can0", bus=bus)
        frame = CanFrame(0x123, b"\x01\x02")

        transport.send(frame)
        self.assertEqual(bus.sent[0].arbitration_id, frame.arbitration_id)
        self.assertEqual(bytes(bus.sent[0].data), frame.data)
        bus.received = bus.sent[0]
        self.assertEqual(transport.receive(), frame)

        transport.close()
        self.assertFalse(bus.shutdown_called)


class PeakLinTransportTests(unittest.TestCase):
    def test_opens_device_sends_and_receives_frame(self) -> None:
        device = FakePLINDevice()
        transport = PeakLinTransport(device=device)
        transport.open()
        self.assertEqual(device.started[1], 19200)
        self.assertTrue(device.allowed_all_ids)

        frame = LinFrame.create(0x12, b"\x01\x02")
        transport.send(frame)
        sent = device.sent[0]
        self.assertEqual(sent.type, PLINMessageType.FRAME)
        self.assertEqual(sent.id, 0x12)
        self.assertEqual(sent.len, 2)
        self.assertEqual(sent.dir, PLINFrameDirection.PUBLISHER)
        self.assertEqual(sent.cs_type, PLINFrameChecksumType.ENHANCED)
        self.assertEqual(bytes(sent.data[: sent.len]), b"\x01\x02")

        incoming = PLINMessage()
        incoming.type = PLINMessageType.FRAME
        incoming.id = frame.identifier
        incoming.len = len(frame.data)
        incoming.dir = PLINFrameDirection.SUBSCRIBER
        incoming.cs_type = PLINFrameChecksumType.ENHANCED
        incoming.data = bytearray(frame.data).ljust(8, b"\x00")
        device.received.append(incoming)
        self.assertEqual(transport.receive(frame.identifier, timeout=0.1), frame)

        transport.close()
        self.assertTrue(device.stopped)

    def test_rejects_driver_reported_frame_errors(self) -> None:
        transport = PeakLinTransport(device=FakePLINDevice())
        transport.open()
        incoming = PLINMessage()
        incoming.type = PLINMessageType.FRAME
        incoming.id = 0x12
        incoming.len = 1
        incoming.cs_type = PLINFrameChecksumType.ENHANCED
        incoming.flags = 0x20
        incoming.data = bytearray([0x01] + [0] * 7)
        with self.assertRaises(ProtocolError):
            transport._convert_message(incoming)
        transport.close()


if __name__ == "__main__":
    unittest.main()
