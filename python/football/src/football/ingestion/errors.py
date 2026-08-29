class CanonicalIngestionError(RuntimeError):
    """A source bundle cannot be published into the canonical store."""


class RetryableIngestionError(CanonicalIngestionError):
    """Concurrent PostgreSQL work aborted and the whole ingestion may be retried."""
