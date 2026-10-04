"""PEAK CAN adapter using the Linux SocketCAN interface."""

from typing import Protocol

from ..can import CanFrame


class _CanMessage(Protocol):
    arbitration_id: int
    data: bytes
    is_extended_id: bool
    is_remote_frame: bool


class _CanBus(Protocol):
    def send(self, message: _CanMessage) -> None: ...

    def recv(self, timeout: float | None = None) -> _CanMessage | None: ...

    def shutdown(self) -> None: ...


class PeakCanTransport:
    """Adapt a PEAK PCAN SocketCAN interface to the package's CAN transport.

    The PEAK Linux driver must be installed and the CAN network interface
    configured before opening this transport. On Linux the interface is
    typically named ``can0``.
    """

    def __init__(
        self,
        channel: str = "can0",
        receive_own_messages: bool = False,
        bus: _CanBus | None = None,
    ) -> None:
        if not channel:
            raise ValueError("channel cannot be empty")
        self._channel = channel
        self._receive_own_messages = receive_own_messages
        self._bus = bus
        self._owns_bus = bus is None

    def open(self) -> None:
        if self._bus is not None:
            return
        try:
            import can
        except ImportError as exc:
            raise RuntimeError(
                "PEAK CAN support requires the 'peak' extra: "
                "install automotive-com-test-wrappers[peak]"
            ) from exc
        self._bus = can.Bus(
            interface="socketcan",
            channel=self._channel,
            receive_own_messages=self._receive_own_messages,
        )

    def send(self, frame: CanFrame) -> None:
        bus = self._require_bus()
        try:
            import can
        except ImportError as exc:
            raise RuntimeError(
                "PEAK CAN support requires the 'peak' extra: "
                "install automotive-com-test-wrappers[peak]"
            ) from exc
        message = can.Message(
            arbitration_id=frame.arbitration_id,
            data=frame.data,
            is_extended_id=frame.is_extended,
            is_remote_frame=frame.is_remote_frame,
        )
        bus.send(message)

    def receive(self, timeout: float | None = None) -> CanFrame | None:
        message = self._require_bus().recv(timeout=timeout)
        if message is None:
            return None
        return CanFrame(
            arbitration_id=message.arbitration_id,
            data=bytes(message.data),
            is_extended=message.is_extended_id,
            is_remote_frame=message.is_remote_frame,
        )

    def close(self) -> None:
        if self._bus is None or not self._owns_bus:
            return
        self._bus.shutdown()
        self._bus = None

    def _require_bus(self) -> _CanBus:
        if self._bus is None:
            raise RuntimeError("PEAK CAN transport is not open; call open() first")
        return self._bus

    def __enter__(self) -> "PeakCanTransport":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
