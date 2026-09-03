from datetime import UTC, datetime
from uuid import uuid4

import pytest

from market_regime_alpha.research_qualification.domain.exploratory import (
    ExploratoryRetrospectiveDatasetScope,
    ResearchEvidenceLane,
)


def test_exploratory_scope_freezes_dual_clock_and_evidence_ceiling() -> None:
    scope = ExploratoryRetrospectiveDatasetScope(
        market_archive_id=uuid4(),
        market_archive_seal_id=uuid4(),
        knowledge_cutoff=datetime(2026, 9, 3, 8, tzinfo=UTC),
        simulated_event_cutoff=datetime(2026, 1, 5, 6, 55, tzinfo=UTC),
    )

    assert scope.evidence_lane is ResearchEvidenceLane.EXPLORATORY_RETROSPECTIVE
    assert len(str(scope.content_sha256)) == 64


def test_exploratory_scope_rejects_collapsed_or_reversed_clocks() -> None:
    cutoff = datetime(2026, 9, 3, 8, tzinfo=UTC)
    with pytest.raises(ValueError, match="precede"):
        ExploratoryRetrospectiveDatasetScope(
            market_archive_id=uuid4(),
            market_archive_seal_id=uuid4(),
            knowledge_cutoff=cutoff,
            simulated_event_cutoff=cutoff,
        )
