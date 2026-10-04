"""PEAK LIN Linux character-device adapter for PLIN-USB."""

import time
from typing import Protocol

from ..exceptions import ProtocolError
from ..lin import LinFrame


class _PLINMessage(Protocol):
    type: int
    flags: int
    id: int
    len: int
    dir: int
    cs_type: int
    data: bytes


class _PLINDevice(Protocol):
    def start(self, mode: object, baudrate: int = 19200) -> None: ...

    def stop(self) -> None: ...

    def clear_id_filter(self, allow_all: bool = True) -> None: ...

    def write(self, message: _PLINMessage) -> None: ...

    def read(self, block: bool = True) -> _PLINMessage | None: ...


class PeakLinTransport:
    """Adapt PLIN-USB's Linux character device to the LIN transport.

    Install PEAK's Linux LIN driver and grant access to its character device
    (usually ``/dev/plin0``) before opening this adapter.
    """

    def __init__(
        self,
        interface: str = "/dev/plin0",
        baudrate: int = 19200,
        mode: str = "master",
        poll_interval: float = 0.001,
        device: _PLINDevice | None = None,
    ) -> None:
        if not interface:
            raise ValueError("interface cannot be empty")
        if not 1000 <= baudrate <= 20000:
            raise ValueError("LIN baudrate must be between 1000 and 20000")
        if mode not in ("master", "slave"):
            raise ValueError("mode must be 'master' or 'slave'")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be greater than zero")
        self._interface = interface
        self._baudrate = baudrate
        self._mode = mode
        self._poll_interval = poll_interval
        self._device = device
        self._opened = False

    def open(self) -> None:
        if self._opened:
            return
        if self._device is None:
            try:
                from plin.device import PLIN
            except ImportError as exc:
                raise RuntimeError(
                    "PEAK LIN support requires the 'peak' extra: "
                    "install automotive-com-test-wrappers[peak]"
                ) from exc
            self._device = PLIN(self._interface)

        try:
            from plin.enums import PLINMode
        except ImportError as exc:
            raise RuntimeError(
                "PEAK LIN support requires the 'peak' extra: "
                "install automotive-com-test-wrappers[peak]"
            ) from exc
        mode = PLINMode.MASTER if self._mode == "master" else PLINMode.SLAVE
        self._device.start(mode=mode, baudrate=self._baudrate)
        self._device.clear_id_filter(allow_all=True)
        self._opened = True

    def send(self, frame: LinFrame) -> None:
        device = self._require_device()
        try:
            from plin.enums import (
                PLINFrameChecksumType,
                PLINFrameDirection,
                PLINMessageType,
            )
            from plin.structs import PLINMessage
        except ImportError as exc:
            raise RuntimeError(
                "PEAK LIN support requires the 'peak' extra: "
                "install automotive-com-test-wrappers[peak]"
            ) from exc

        message = PLINMessage()
        message.type = PLINMessageType.FRAME
        message.flags = 0
        message.id = frame.identifier
        message.len = len(frame.data)
        message.dir = PLINFrameDirection.PUBLISHER
        message.cs_type = (
            PLINFrameChecksumType.ENHANCED
            if frame.enhanced_checksum
            else PLINFrameChecksumType.CLASSIC
        )
        message.data = bytearray(frame.data).ljust(8, b"\x00")
        device.write(message)

    def receive(
        self, identifier: int, timeout: float | None = None
    ) -> LinFrame | None:
        if not 0 <= identifier <= 0x3F:
            raise ValueError("LIN identifier must fit in 6 bits")
        if timeout is not None and timeout < 0:
            raise ValueError("timeout cannot be negative")
        device = self._require_device()
        deadline = None if timeout is None else time.monotonic() + timeout

        while True:
            message = device.read(block=deadline is None)
            if message is not None:
                frame = self._convert_message(message)
                if frame.identifier == identifier:
                    return frame
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                time.sleep(min(self._poll_interval, remaining))

    def close(self) -> None:
        if self._opened:
            self._require_device().stop()
            self._opened = False

    def _convert_message(self, message: _PLINMessage) -> LinFrame:
        try:
            from plin.enums import (
                PLINFrameChecksumType,
                PLINFrameErrorFlag,
                PLINMessageType,
            )
        except ImportError as exc:
            raise RuntimeError(
                "PEAK LIN support requires the 'peak' extra: "
                "install automotive-com-test-wrappers[peak]"
            ) from exc

        if message.type != PLINMessageType.FRAME:
            raise ProtocolError(f"Received non-frame PLIN message type {message.type}")
        error_flags = PLINFrameErrorFlag(message.flags)
        if error_flags:
            raise ProtocolError(
                f"PEAK LIN driver reported frame error flags {error_flags!s}"
            )
        data = bytes(message.data[: message.len])
        if message.cs_type == PLINFrameChecksumType.ENHANCED:
            enhanced_checksum = True
        elif message.cs_type == PLINFrameChecksumType.CLASSIC:
            enhanced_checksum = False
        else:
            raise ProtocolError(
                f"Cannot validate LIN checksum type {message.cs_type}"
            )
        frame = LinFrame.create(message.id, data, enhanced_checksum)
        return frame

    def _require_device(self) -> _PLINDevice:
        if not self._opened or self._device is None:
            raise RuntimeError("PEAK LIN transport is not open; call open() first")
        return self._device

    def __enter__(self) -> "PeakLinTransport":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
