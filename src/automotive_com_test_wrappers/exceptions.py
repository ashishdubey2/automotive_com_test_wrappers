"""Exceptions shared by the communication wrappers."""


class CommunicationError(Exception):
    """Raised when a transport cannot complete a communication operation."""


class ProtocolError(CommunicationError):
    """Raised when a received message is invalid for its protocol."""


class FrameMismatchError(AssertionError):
    """Raised when a received frame differs from the expected frame."""
