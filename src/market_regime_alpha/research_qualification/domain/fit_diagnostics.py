"""Descriptive conditioning of a frozen FIT matrix, never parameter selection."""

import numpy as np
from decimal import Decimal

from market_regime_alpha.research_qualification.domain.research_models import LinearTrainingRow


def fit_matrix_diagnostics(rows: tuple[LinearTrainingRow, ...]) -> dict:
    if not rows or not rows[0].features or any(len(r.features)!=len(rows[0].features) for r in rows):
        raise ValueError("FIT diagnostics require a nonempty rectangular frozen matrix")
    matrix = np.asarray([[float(v) for v in r.features] for r in rows],dtype=np.float64)
    if not np.isfinite(matrix).all():
        raise ValueError("FIT diagnostics require finite representable inputs")
    with np.errstate(over="raise",invalid="raise",divide="raise"):
        centered = matrix-matrix.mean(axis=0)
        magnitude = np.max(np.abs(centered),axis=0)
        divisor = np.where(magnitude==0,1,magnitude)
        scales = divisor*np.sqrt(np.mean((centered/divisor)**2,axis=0))
        normalized = centered/np.where(scales==0,1,scales)
        singular = np.linalg.svd(normalized,compute_uv=False)
        rank = int(np.linalg.matrix_rank(normalized))
        width = matrix.shape[1]
        correlation = normalized.T@normalized/len(rows)
        entries = tuple(tuple(None if scales[i]==0 or scales[j]==0 else Decimal(str(float(correlation[i,j]))) for j in range(width)) for i in range(width))
        condition = None if rank<width else Decimal(str(float(singular[0]/singular[-1])))
    return {"schema":"mra-fit-conditioning-v1","input":"EXACT_REGISTERED_ESTIMABLE_FIT_ROWS",
        "sample_rows":len(rows),"feature_count":width,"constant_feature_ordinals":tuple(int(i)+1 for i in np.flatnonzero(scales==0)),
        "fit_feature_correlation":entries,"centered_matrix_rank":rank,
        "standardized_matrix_condition_number":condition,"condition_state":"SINGULAR" if condition is None else "DESCRIPTIVE",
        "singular_values":tuple(Decimal(str(float(v))) for v in singular),"scaling":"FIT_POPULATION_STD_DDOF_0",
        "numeric_contract":"BINARY64_DIAGNOSTICS_CANONICAL_DECIMAL_REPR",
        "interpretation":"CONDITIONING_DIAGNOSTIC_NOT_CAUSAL_OVERFITTING_PROOF"}
