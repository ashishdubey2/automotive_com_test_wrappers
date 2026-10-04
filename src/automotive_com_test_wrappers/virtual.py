"""Software loopback transports for protocol-level tests without hardware."""

import queue
import threading
import time
from collections import deque

from .lin import LinFrame


class VirtualLinTransport:
    """One side of a paired in-process LIN loopback.

    This transports complete logical LIN frames between two Python endpoints.
    It does not model LIN break/sync timing, dominant/recessive levels, or the
    physical bus.
    """

    def __init__(
        self,
        incoming: queue.Queue[LinFrame],
        outgoing: queue.Queue[LinFrame],
    ) -> None:
        self._incoming = incoming
        self._outgoing = outgoing
        self._pending: deque[LinFrame] = deque()
        self._receive_lock = threading.Lock()
        self._closed = False

    def send(self, frame: LinFrame) -> None:
        if self._closed:
            raise RuntimeError("Virtual LIN transport is closed")
        frame.validate()
        self._outgoing.put(frame)

    def receive(
        self, identifier: int, timeout: float | None = None
    ) -> LinFrame | None:
        if self._closed:
            raise RuntimeError("Virtual LIN transport is closed")
        if not 0 <= identifier <= 0x3F:
            raise ValueError("LIN identifier must fit in 6 bits")
        if timeout is not None and timeout < 0:
            raise ValueError("timeout cannot be negative")

        deadline = None if timeout is None else time.monotonic() + timeout
        with self._receive_lock:
            for index, frame in enumerate(self._pending):
                if frame.identifier == identifier:
                    del self._pending[index]
                    return frame

            while True:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return None
                try:
                    frame = self._incoming.get(timeout=remaining)
                except queue.Empty:
                    return None
                if frame.identifier == identifier:
                    return frame
                self._pending.append(frame)

    def close(self) -> None:
        self._closed = True

    def __enter__(self) -> "VirtualLinTransport":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()


class VirtualLinBus:
    """Factory for two connected software LIN loopback endpoints."""

    @staticmethod
    def create_pair() -> tuple[VirtualLinTransport, VirtualLinTransport]:
        first_inbox: queue.Queue[LinFrame] = queue.Queue()
        second_inbox: queue.Queue[LinFrame] = queue.Queue()
        return (
            VirtualLinTransport(first_inbox, second_inbox),
            VirtualLinTransport(second_inbox, first_inbox),
        )
