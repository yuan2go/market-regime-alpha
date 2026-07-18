"""Conservative XtQuant runtime capability probe."""

from __future__ import annotations

import importlib
import platform
from typing import Any, Callable


def probe_xtquant_pit_capabilities(
    *, importer: Callable[[str], object] = importlib.import_module
) -> dict[str, Any]:
    try:
        importer("xtquant.xtdata")
        import_status = "AVAILABLE_UNVERIFIED_SEMANTICS"
    except (ImportError, ModuleNotFoundError):
        import_status = "EXTERNAL_XTQUANT_RUNTIME_REQUIRED"
    unverified = {"status": "UNVERIFIED", "reason": "METHOD_PRESENCE_IS_NOT_SEMANTIC_EVIDENCE"}
    return {
        "schema_version": "xuntou-pit-capability-probe-v1",
        "platform": platform.platform(),
        "xtquant_import_status": import_status,
        "runtime_version": platform.python_version(),
        "available_documented_methods": [],
        "historical_bar_capability": dict(unverified),
        "historical_quote_capability": dict(unverified),
        "historical_membership_capability": dict(unverified),
        "historical_st_capability": dict(unverified),
        "historical_suspension_capability": dict(unverified),
        "limit_price_capability": dict(unverified),
        "timezone_semantics": dict(unverified),
        "entitlement_limitations": ["ACCOUNT_AND_RUNTIME_SPECIFIC"],
        "research_evidence_produced": False,
    }
