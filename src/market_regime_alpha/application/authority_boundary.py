"""Machine-readable Canonical/Legacy execution boundary.

This catalog is descriptive and fail-closed: it grants no runtime capability.
Architecture tests use it to prevent historical producers from becoming a
second current authority through a future import or CLI entry point.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AuthorityCapability(str, Enum):
    EXECUTE = "EXECUTE"
    WRITE = "WRITE"
    READ = "READ"
    REPLAY = "REPLAY"
    MIGRATE = "MIGRATE"
    COMPATIBILITY = "COMPATIBILITY"
    CHARACTERIZE = "CHARACTERIZE"


@dataclass(frozen=True, slots=True)
class AuthorityNamespace:
    namespace: str
    owner: str
    capabilities: tuple[AuthorityCapability, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.namespace or not self.owner:
            raise ValueError("Authority namespace and owner must be non-empty")
        if self.capabilities != tuple(
            sorted(set(self.capabilities), key=lambda item: item.value)
        ):
            raise ValueError("Authority capabilities must be unique and sorted")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Authority limitations must be unique and sorted")

    @property
    def executable(self) -> bool:
        return AuthorityCapability.EXECUTE in self.capabilities

    @property
    def writable(self) -> bool:
        return AuthorityCapability.WRITE in self.capabilities


@dataclass(frozen=True, slots=True)
class CanonicalAuthorityCatalog:
    daily_runtime: AuthorityNamespace
    lifecycle_runtime: AuthorityNamespace
    daily_decision: AuthorityNamespace
    entry: AuthorityNamespace
    legacy_namespaces: tuple[AuthorityNamespace, ...]

    def __post_init__(self) -> None:
        legacy_names = tuple(item.namespace for item in self.legacy_namespaces)
        if legacy_names != tuple(sorted(set(legacy_names))):
            raise ValueError("Legacy namespaces must be unique and sorted")
        if not self.daily_runtime.executable or not self.daily_runtime.writable:
            raise ValueError("Canonical daily Runtime must be executable and writable")
        if not self.daily_decision.writable:
            raise ValueError("Canonical Decision must be writable")
        if any(item.executable or item.writable for item in self.legacy_namespaces):
            raise ValueError("Legacy namespaces cannot own current execution or writes")


def canonical_authority_catalog() -> CanonicalAuthorityCatalog:
    canonical = (
        AuthorityCapability.EXECUTE,
        AuthorityCapability.READ,
        AuthorityCapability.REPLAY,
        AuthorityCapability.WRITE,
    )
    return CanonicalAuthorityCatalog(
        daily_runtime=AuthorityNamespace(
            namespace="market_regime_alpha.application.continuous_research",
            owner="CONTINUOUS_RESEARCH",
            capabilities=canonical,
            limitations=("NO_BROKER_AUTHORITY", "NO_POSITION_MUTATION"),
        ),
        lifecycle_runtime=AuthorityNamespace(
            namespace="market_regime_alpha.application.canonical_lifecycle",
            owner="CANONICAL_DECISION_LIFECYCLE",
            capabilities=canonical,
            limitations=(
                "DOWNSTREAM_HUMAN_IN_LOOP_CONTINUATION",
                "NOT_A_PARALLEL_DAILY_RUNTIME",
            ),
        ),
        daily_decision=AuthorityNamespace(
            namespace="market_regime_alpha.application.decision_system",
            owner="DECISION_SYSTEM",
            capabilities=(
                AuthorityCapability.READ,
                AuthorityCapability.REPLAY,
                AuthorityCapability.WRITE,
            ),
            limitations=("NO_ORDER_AUTHORITY",),
        ),
        entry=AuthorityNamespace(
            namespace="market_regime_alpha.daily_decision.entry",
            owner="CANONICAL_ENTRY_PLUMBING",
            capabilities=(AuthorityCapability.READ, AuthorityCapability.WRITE),
            limitations=("ENTER_NOT_IMPLEMENTED", "NO_ORDER_AUTHORITY"),
        ),
        legacy_namespaces=(
            AuthorityNamespace(
                namespace="market_regime_alpha.daily_research",
                owner="LEGACY_DAILY_RESEARCH",
                capabilities=(
                    AuthorityCapability.COMPATIBILITY,
                    AuthorityCapability.MIGRATE,
                    AuthorityCapability.READ,
                    AuthorityCapability.REPLAY,
                ),
                limitations=(
                    "ENTER_IS_HISTORICAL_ONLY",
                    "NO_CANONICAL_COMPOSITION",
                    "NO_CURRENT_WRITE_AUTHORITY",
                ),
            ),
            AuthorityNamespace(
                namespace="market_regime_alpha.dividend_t",
                owner="LEGACY_DIVIDEND_T",
                capabilities=(
                    AuthorityCapability.CHARACTERIZE,
                    AuthorityCapability.COMPATIBILITY,
                    AuthorityCapability.MIGRATE,
                    AuthorityCapability.READ,
                ),
                limitations=(
                    "NO_CANONICAL_COMPOSITION",
                    "NO_CURRENT_WRITE_AUTHORITY",
                    "NO_LIVE_BROKER_AUTHORITY",
                ),
            ),
        ),
    )


__all__ = [
    "AuthorityCapability",
    "AuthorityNamespace",
    "CanonicalAuthorityCatalog",
    "canonical_authority_catalog",
]
