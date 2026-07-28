"""Daily-loop runtime errors."""


class RuntimeJournalConflictError(ValueError):
    """A compare-and-set or immutable journal binding conflicted."""
