class QueueError(Exception):
    """Base error raised by the queue boundary."""


class QueueConnectionError(QueueError):
    """Raised when Redis cannot complete a queue operation."""


class QueueMessageError(QueueError):
    """Raised when a stream message is malformed or unsupported."""
