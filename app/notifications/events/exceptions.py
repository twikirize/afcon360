"""
Event backbone exceptions.

The distinction between *retryable* and *permanent* consumer failures is what
drives the event-level DLQ: retryable errors go back on the queue with
exponential backoff, permanent errors are dead-lettered immediately instead of
burning retry budget on something that will never succeed.
"""


class EventError(Exception):
    """Base class for all event backbone errors."""


class UnknownEventTypeError(EventError):
    """Raised when an event type is not present in the EventRegistry."""


class EventValidationError(EventError):
    """Raised when an event payload fails its registered schema validation."""


class ConsumerError(EventError):
    """Base class for consumer processing failures."""


class RetryableConsumerError(ConsumerError):
    """
    A transient failure (provider timeout, temporary DB error, rate limit).

    The event is retried with exponential backoff and only dead-lettered after
    the retry budget is exhausted.
    """


class PermanentConsumerError(ConsumerError):
    """
    A failure that will never succeed on retry (malformed payload, deleted
    aggregate, unknown recipient).

    The event is dead-lettered immediately.
    """


class PublishError(EventError):
    """Raised when the transport (Redis Streams) rejects a publish."""
