from decimal import Decimal
from uuid import UUID

import pytest

from market_regime_alpha.research_qualification.domain.fit_diagnostics import fit_matrix_diagnostics
from market_regime_alpha.research_qualification.domain.research_models import LinearTrainingRow


def test_fit_conditioning_marks_collinearity_and_constants_without_inventing_rank_signal():
    rows = tuple(LinearTrainingRow(UUID(int=i+1),(Decimal(i),Decimal(2*i),Decimal(1)),Decimal(99-i)) for i in range(4))
    result = fit_matrix_diagnostics(rows)
    assert result["centered_matrix_rank"]==1
    assert result["constant_feature_ordinals"]==(3,)
    assert result["condition_state"]=="SINGULAR" and result["standardized_matrix_condition_number"] is None
    assert abs(result["fit_feature_correlation"][0][1]-Decimal(1))<=Decimal("1e-15")
    assert result["fit_feature_correlation"][0][2] is None
    from market_regime_alpha.shared.hashing import canonical_json_sha256
    assert len(canonical_json_sha256(result))==64


def test_fit_conditioning_rejects_nonrepresentable_or_empty_inputs():
    with pytest.raises(ValueError):
        fit_matrix_diagnostics(())
    with pytest.raises(ValueError,match="representable"):
        fit_matrix_diagnostics((LinearTrainingRow(UUID(int=1),(Decimal('1e999'),),Decimal(1)),))
