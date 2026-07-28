"""Daily-loop runtime errors."""


class RuntimeJournalConflictError(ValueError):
    """A compare-and-set or immutable journal binding conflicted."""


class OutcomeNotReadyError(ValueError):
    """No exact next-session MR1 10:30 evidence is available yet."""
