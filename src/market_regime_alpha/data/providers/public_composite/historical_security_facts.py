"""BaoStock acquisition for effective/publication-dated historical business facts."""

from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import partial
from io import StringIO
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import tempfile
from typing import Any, Callable, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.providers.public_composite.contracts import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
    PublicCompositeProviderResult,
)
from market_regime_alpha.data.providers.public_composite.replay_archive import (
    source_archive_id,
)
from market_regime_alpha.data.providers.public_composite.research_universe import (
    _consume_result,
    _historical_source_payload,
)
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.data_sources.a_share_bars import (
    AShareDataError,
    baostock_credentials,
)
from market_regime_alpha.universe.historical_facts import (
    HistoricalSecurityFact,
    HistoricalSecurityFactCoverageGap,
    HistoricalSecurityFactKind,
    HistoricalSecurityFactsOwner,
)


Clock = Callable[[], datetime]
_FactQueryResponse = tuple[
    str,
    str,
    tuple[tuple[str, str], ...],
    tuple[str, ...],
    datetime,
    datetime,
    dict[str, Any],
]


@dataclass(frozen=True, slots=True)
class _FactQuerySpec:
    product: str
    locator: str
    parameters: tuple[tuple[str, str], ...]
    scope: tuple[str, ...]
    query: Callable[[], Any]


@dataclass(frozen=True, slots=True)
class HistoricalSecurityFactsAcquisition:
    provider_result: PublicCompositeProviderResult
    source_manifest: SourceManifest
    owner: HistoricalSecurityFactsOwner
    query_count: int
    empty_query_count: int
    rejected_row_count: int
    coverage_gap_count: int
    fact_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if self.query_count != len(self.provider_result.raw_payloads):
            raise ValueError("Historical fact query count does not match archive")
        if self.empty_query_count < 0 or self.rejected_row_count < 0 or self.coverage_gap_count < 0:
            raise ValueError("Historical fact acquisition counts cannot be negative")
        if self.fact_counts != tuple(sorted(self.fact_counts)):
            raise ValueError("Historical fact counts must be ordered")


@dataclass(frozen=True, slots=True)
class HistoricalSecurityFactsPrefetch:
    expected_query_count: int
    assigned_query_count: int
    worker_index: int
    worker_count: int

    def __post_init__(self) -> None:
        if self.expected_query_count <= 0 or self.assigned_query_count <= 0:
            raise ValueError("Historical fact prefetch requires assigned queries")
        assigned = _assigned_fact_query_indices(
            total=self.expected_query_count,
            worker_index=self.worker_index,
            worker_count=self.worker_count,
        )
        if self.assigned_query_count != len(assigned):
            raise ValueError("Historical fact prefetch assignment count drifted")


def _assigned_fact_query_indices(
    *,
    total: int,
    worker_index: int,
    worker_count: int,
) -> tuple[int, ...]:
    if total <= 0:
        raise ValueError("Historical fact query total must be positive")
    if worker_count <= 0:
        raise ValueError("Historical fact worker count must be positive")
    if not 0 <= worker_index < worker_count:
        raise ValueError("Historical fact worker index is outside worker count")
    return tuple(range(worker_index, total, worker_count))


class BaoStockHistoricalSecurityFactsClient:
    """Acquire only real BaoStock facts; missing/invalid rows stay missing."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        maximum_source_queries: int = 20_000,
        clock: Clock = lambda: datetime.now(UTC),
    ) -> None:
        if timeout_seconds <= 0 or maximum_source_queries <= 0:
            raise ValueError("Historical Security Facts limits must be positive")
        self._timeout_seconds = timeout_seconds
        self._maximum_source_queries = maximum_source_queries
        self._clock = clock

    def acquire(
        self,
        *,
        symbols: tuple[str, ...],
        cohort_dates: tuple[date, ...],
        start_date: date,
        end_date: date,
        universe_scope_references: tuple[ValidationArtifactReference, ...],
        checkpoint_root: Path | None = None,
    ) -> HistoricalSecurityFactsAcquisition:
        if not symbols or symbols != tuple(sorted(set(symbols))):
            raise ValueError("Historical fact symbols must be ordered")
        if not cohort_dates or cohort_dates != tuple(sorted(set(cohort_dates))):
            raise ValueError("Historical fact cohort dates must be ordered")
        if start_date > end_date:
            raise ValueError("Historical fact range is reversed")
        try:
            import baostock as bs
        except ImportError as exc:
            raise AShareDataError("baostock is not installed") from exc
        specs = _historical_fact_query_specs(
            bs,
            symbols=symbols,
            cohort_dates=cohort_dates,
            start_date=start_date,
            end_date=end_date,
        )
        self._verify_query_ceiling(len(specs))
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self._timeout_seconds)
        try:
            user_id, password = baostock_credentials()
            with redirect_stdout(StringIO()):
                login = bs.login(user_id=user_id, password=password)
            if getattr(login, "error_code", "0") != "0":
                raise AShareDataError(f"BaoStock login failed: {login.error_msg}")
            try:
                responses: list[_FactQueryResponse] = []
                def fetch(
                    *,
                    product: str,
                    locator: str,
                    parameters: tuple[tuple[str, str], ...],
                    scope: tuple[str, ...],
                    query: Callable[[], Any],
                ) -> tuple[datetime, datetime, dict[str, Any]]:
                    return _checkpointed_fact_query(
                        checkpoint_root=checkpoint_root,
                        product=product,
                        locator=locator,
                        parameters=parameters,
                        scope=scope,
                        clock=self._clock,
                        query=query,
                    )

                for spec in specs:
                    requested_at, retrieved_at, response = fetch(
                        product=spec.product,
                        locator=spec.locator,
                        parameters=spec.parameters,
                        scope=spec.scope,
                        query=spec.query,
                    )
                    responses.append(
                        (
                            spec.product,
                            spec.locator,
                            spec.parameters,
                            spec.scope,
                            requested_at,
                            retrieved_at,
                            response,
                        )
                    )
            finally:
                with redirect_stdout(StringIO()):
                    bs.logout()
        finally:
            socket.setdefaulttimeout(previous_timeout)
        return _build_acquisition(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            universe_scope_references=universe_scope_references,
            responses=tuple(responses),
        )

    def prefetch(
        self,
        *,
        symbols: tuple[str, ...],
        cohort_dates: tuple[date, ...],
        start_date: date,
        end_date: date,
        checkpoint_root: Path,
        worker_index: int,
        worker_count: int,
    ) -> HistoricalSecurityFactsPrefetch:
        """Fill one deterministic subset of the canonical query checkpoints.

        This method deliberately cannot publish a Facts owner.  The sole
        ``acquire`` path must reload and verify every expected checkpoint before
        it constructs the immutable archive and PostgreSQL owner.
        """

        if not symbols or symbols != tuple(sorted(set(symbols))):
            raise ValueError("Historical fact symbols must be ordered")
        if not cohort_dates or cohort_dates != tuple(sorted(set(cohort_dates))):
            raise ValueError("Historical fact cohort dates must be ordered")
        if start_date > end_date:
            raise ValueError("Historical fact range is reversed")
        try:
            import baostock as bs
        except ImportError as exc:
            raise AShareDataError("baostock is not installed") from exc
        specs = _historical_fact_query_specs(
            bs,
            symbols=symbols,
            cohort_dates=cohort_dates,
            start_date=start_date,
            end_date=end_date,
        )
        self._verify_query_ceiling(len(specs))
        assigned = _assigned_fact_query_indices(
            total=len(specs),
            worker_index=worker_index,
            worker_count=worker_count,
        )
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self._timeout_seconds)
        try:
            user_id, password = baostock_credentials()
            with redirect_stdout(StringIO()):
                login = bs.login(user_id=user_id, password=password)
            if getattr(login, "error_code", "0") != "0":
                raise AShareDataError(f"BaoStock login failed: {login.error_msg}")
            try:
                for index in assigned:
                    spec = specs[index]
                    _checkpointed_fact_query(
                        checkpoint_root=checkpoint_root,
                        product=spec.product,
                        locator=spec.locator,
                        parameters=spec.parameters,
                        scope=spec.scope,
                        clock=self._clock,
                        query=spec.query,
                    )
            finally:
                with redirect_stdout(StringIO()):
                    bs.logout()
        finally:
            socket.setdefaulttimeout(previous_timeout)
        return HistoricalSecurityFactsPrefetch(
            expected_query_count=len(specs),
            assigned_query_count=len(assigned),
            worker_index=worker_index,
            worker_count=worker_count,
        )

    def _verify_query_ceiling(self, query_count: int) -> None:
        if query_count > self._maximum_source_queries:
            raise ValueError("Historical fact acquisition exceeds declared query ceiling")


def _historical_fact_query_specs(
    provider: Any,
    *,
    symbols: tuple[str, ...],
    cohort_dates: tuple[date, ...],
    start_date: date,
    end_date: date,
) -> tuple[_FactQuerySpec, ...]:
    years = tuple(range(start_date.year - 1, end_date.year + 1))
    prior_annual_period = (start_date.year - 1, 4)
    profit_periods = tuple(
        (year, quarter)
        for year in years
        for quarter in range(1, 5)
        if (year, quarter) == prior_annual_period
        or start_date.replace(month=1, day=1)
        <= _quarter_end(year, quarter)
        <= end_date
    )
    specs: list[_FactQuerySpec] = []
    for cohort_date in cohort_dates:
        iso_date = cohort_date.isoformat()
        specs.append(
            _FactQuerySpec(
                product="query_stock_industry:effective-date:v1",
                locator=f"baostock://query-stock-industry/{iso_date}",
                parameters=(("date", iso_date),),
                scope=("A_SHARE_SECURITIES",),
                query=partial(provider.query_stock_industry, date=iso_date),
            )
        )
    for symbol in symbols:
        code = _baostock_code(symbol)
        for year, quarter in profit_periods:
            specs.append(
                _FactQuerySpec(
                    product="query_profit_data:quarter:v1",
                    locator=(
                        f"baostock://query-profit-data/{code}/{year}/{quarter}"
                    ),
                    parameters=(
                        ("code", code),
                        ("quarter", str(quarter)),
                        ("year", str(year)),
                    ),
                    scope=(symbol,),
                    query=partial(
                        provider.query_profit_data,
                        code=code,
                        year=year,
                        quarter=quarter,
                    ),
                )
            )
        specs.append(
            _FactQuerySpec(
                product="query_adjust_factor:range:v1",
                locator=(
                    f"baostock://query-adjust-factor/{code}/"
                    f"{start_date.isoformat()}/{end_date.isoformat()}"
                ),
                parameters=(
                    ("code", code),
                    ("end_date", end_date.isoformat()),
                    ("start_date", start_date.isoformat()),
                ),
                scope=(symbol,),
                query=partial(
                    provider.query_adjust_factor,
                    code=code,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                ),
            )
        )
        for year in years:
            specs.append(
                _FactQuerySpec(
                    product="query_dividend_data:report-year:v1",
                    locator=(
                        f"baostock://query-dividend-data/{code}/{year}/report"
                    ),
                    parameters=(
                        ("code", code),
                        ("year", str(year)),
                        ("year_type", "report"),
                    ),
                    scope=(symbol,),
                    query=partial(
                        provider.query_dividend_data,
                        code=code,
                        year=str(year),
                        yearType="report",
                    ),
                )
            )
    return tuple(specs)


def _checkpointed_fact_query(
    *,
    checkpoint_root: Path | None,
    product: str,
    locator: str,
    parameters: tuple[tuple[str, str], ...],
    scope: tuple[str, ...],
    clock: Clock,
    query: Callable[[], Any],
) -> tuple[datetime, datetime, dict[str, Any]]:
    identity = {
        "schema_version": "historical-security-fact-query-checkpoint/v2",
        "product": product,
        "locator": locator,
        "parameters": [list(item) for item in parameters],
        "scope": list(scope),
    }
    key = sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    path = None if checkpoint_root is None else checkpoint_root / f"{key}.json"
    if path is not None and path.exists():
        return _load_fact_checkpoint(path, identity)
    requested_at = clock()
    if requested_at.tzinfo is None or requested_at.utcoffset() is None:
        raise AShareDataError("Historical fact request time must be aware")
    response = _consume_result(query())
    retrieved_at = clock()
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None or retrieved_at < requested_at:
        raise AShareDataError("Historical fact retrieval time is invalid")
    if response.get("error_code") != "0":
        raise AShareDataError(f"BaoStock historical fact query failed at {locator}: {response.get('error_message')}")
    if not response.get("fields"):
        raise AShareDataError(f"BaoStock historical fact query returned no fields at {locator}")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "identity": identity,
            "requested_at": requested_at.isoformat(),
            "retrieved_at": retrieved_at.isoformat(),
            "response": response,
            "response_hash": _json_hash(response),
        }
        payload["checkpoint_hash"] = _json_hash(payload)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{key}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        try:
            os.link(temporary, path)
        except FileExistsError:
            temporary.unlink()
            return _load_fact_checkpoint(path, identity)
        temporary.unlink()
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    return requested_at, retrieved_at, response


def _load_fact_checkpoint(
    path: Path,
    identity: Mapping[str, Any],
) -> tuple[datetime, datetime, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AShareDataError(f"Historical fact checkpoint is corrupt: {path.name}") from exc
    if not isinstance(payload, dict) or payload.get("identity") != identity:
        raise AShareDataError(f"Historical fact checkpoint identity drift: {path.name}")
    response = payload.get("response")
    checkpoint_hash = payload.get("checkpoint_hash")
    content = {key: value for key, value in payload.items() if key != "checkpoint_hash"}
    if (
        not isinstance(response, dict)
        or payload.get("response_hash") != _json_hash(response)
        or checkpoint_hash != _json_hash(content)
    ):
        raise AShareDataError(f"Historical fact checkpoint content drift: {path.name}")
    try:
        requested_at = datetime.fromisoformat(str(payload["requested_at"]))
        retrieved_at = datetime.fromisoformat(str(payload["retrieved_at"]))
    except (KeyError, ValueError) as exc:
        raise AShareDataError(f"Historical fact checkpoint timestamp is invalid: {path.name}") from exc
    if (
        requested_at.tzinfo is None
        or requested_at.utcoffset() is None
        or retrieved_at.tzinfo is None
        or retrieved_at.utcoffset() is None
        or retrieved_at < requested_at
    ):
        raise AShareDataError(f"Historical fact checkpoint timestamp is invalid: {path.name}")
    return requested_at, retrieved_at, response


def _json_hash(value: Any) -> str:
    return (
        "sha256:"
        + sha256(
            json.dumps(
                value,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
    )


def _json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _quarter_end(year: int, quarter: int) -> date:
    return date(year, quarter * 3, (31, 30, 30, 31)[quarter - 1])


def _build_acquisition(
    *,
    symbols: tuple[str, ...],
    start_date: date,
    end_date: date,
    universe_scope_references: tuple[ValidationArtifactReference, ...],
    responses: tuple[_FactQueryResponse, ...],
) -> HistoricalSecurityFactsAcquisition:
    if not responses:
        raise ValueError("Historical fact acquisition requires responses")
    retrieved_at = max(item[5] for item in responses)
    raw_payloads = tuple(
        _historical_source_payload(
            response=response,
            product=product,
            locator=locator,
            requested_at=requested_at,
            retrieved_at=response_retrieved_at,
            request_parameters=parameters,
            symbol_scope=scope,
        )
        for product, locator, parameters, scope, requested_at, response_retrieved_at, response in responses
    )
    decision_time = DecisionTime(retrieved_at)
    provider_result = PublicCompositeProviderResult(
        profile_id=BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
        decision_time=decision_time,
        raw_payloads=raw_payloads,
        bars=(),
        quotes=(),
        source_conflicts=(),
        limitations=(
            "CORPORATE_RIGHTS_NOT_SEPARATELY_AVAILABLE",
            "FREE_DATA_EXPLORATORY",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "HISTORICAL_AVAILABILITY_NOT_PROVIDED",
            "NO_CURRENT_STATE_BACKFILL",
            "NO_PROVIDER_FALLBACK",
        ),
    )
    manifest = SourceManifest(
        provider_profile_id=BAOSTOCK_RESEARCH_UNIVERSE_PROFILE_ID,
        decision_time=decision_time,
        source_artifacts=provider_result.source_artifact_references,
        fields=(),
        source_conflicts=(),
        limitations=provider_result.limitations,
        data_eligibility=DataEligibility.EXPLORATORY,
    )
    source_by_locator = {source.locator: source for source in raw_payloads}
    facts: dict[tuple[object, ...], HistoricalSecurityFact] = {}
    conflicted_keys: set[tuple[object, ...]] = set()
    coverage_gaps: dict[str, HistoricalSecurityFactCoverageGap] = {}
    rejected = 0
    allowed = set(symbols)
    for product, locator, parameters, scope, _requested_at, _retrieved_at, response in responses:
        source = source_by_locator[locator]
        reference = ValidationArtifactReference("RAW_PROVIDER_REQUEST", source.source_artifact_id, source.raw_hash)
        rows = _rows(response)
        for row in rows:
            fact: HistoricalSecurityFact | None
            try:
                fact = _fact_from_row(
                    product=product,
                    row=row,
                    source_reference=reference,
                )
            except (KeyError, ValueError):
                rejected += 1
                fact = None
            if fact is None:
                if "__provider_field_count" in row:
                    rejected += 1
                gap = _corporate_action_coverage_gap(
                    product=product,
                    parameters=parameters,
                    scope=scope,
                    row=row,
                    start_date=start_date,
                    end_date=end_date,
                    source_reference=reference,
                )
                if gap is not None and gap.symbol in allowed:
                    coverage_gaps.setdefault(str(gap.gap_id), gap)
                continue
            if fact.symbol not in allowed:
                continue
            if fact.effective_date > end_date:
                continue
            key: tuple[object, ...] = (
                fact.symbol,
                fact.fact_kind,
                fact.effective_date,
            )
            if fact.fact_kind is HistoricalSecurityFactKind.DIVIDEND_EVENT:
                key = (*key, fact.published_date)
            if key in conflicted_keys:
                rejected += 1
                gap = _corporate_action_coverage_gap(
                    product=product,
                    parameters=parameters,
                    scope=scope,
                    row=row,
                    start_date=start_date,
                    end_date=end_date,
                    source_reference=reference,
                    reason_codes=(
                        "CORPORATE_ACTION_PROVIDER_FACT_CONFLICT",
                        "RAW_UNADJUSTED_RETURN_FAILS_CLOSED",
                    ),
                )
                if gap is not None and gap.symbol in allowed:
                    coverage_gaps.setdefault(str(gap.gap_id), gap)
                continue
            prior = facts.get(key)
            if prior is not None and dict(prior.values) != dict(fact.values):
                gap = _corporate_action_coverage_gap(
                    product=product,
                    parameters=parameters,
                    scope=scope,
                    row=row,
                    start_date=start_date,
                    end_date=end_date,
                    source_reference=reference,
                    reason_codes=(
                        "CORPORATE_ACTION_PROVIDER_FACT_CONFLICT",
                        "RAW_UNADJUSTED_RETURN_FAILS_CLOSED",
                    ),
                )
                if gap is None:
                    raise AShareDataError(
                        "BaoStock historical fact values drifted for one effective key"
                    )
                rejected += 1
                conflicted_keys.add(key)
                facts.pop(key)
                if gap.symbol in allowed:
                    coverage_gaps.setdefault(str(gap.gap_id), gap)
                continue
            facts.setdefault(key, fact)
    if not facts:
        raise AShareDataError("BaoStock historical fact acquisition returned no facts")
    owner = HistoricalSecurityFactsOwner.create(
        known_at=retrieved_at,
        provider_id=str(BAOSTOCK_PUBLIC_PROVIDER_ID),
        provider_contracts=(
            "baostock-query-adjust-factor/v1",
            "baostock-query-dividend-data/v1",
            "baostock-query-profit-data/v1",
            "baostock-query-stock-industry/v1",
        ),
        source_manifest_reference=ValidationArtifactReference("SOURCE_MANIFEST", manifest.source_manifest_id, manifest.content_hash),
        raw_archive_id=source_archive_id(
            provider_result=provider_result,
            source_manifest=manifest,
        ),
        facts=tuple(facts.values()),
        requested_symbols=symbols,
        acquisition_start_date=start_date,
        acquisition_end_date=end_date,
        universe_scope_references=universe_scope_references,
        coverage_gaps=tuple(coverage_gaps.values()),
    )
    counts: dict[str, int] = {}
    for fact in owner.facts:
        counts[fact.fact_kind.value] = counts.get(fact.fact_kind.value, 0) + 1
    return HistoricalSecurityFactsAcquisition(
        provider_result=provider_result,
        source_manifest=manifest,
        owner=owner,
        query_count=len(responses),
        empty_query_count=sum(not response[6].get("rows") for response in responses),
        rejected_row_count=rejected,
        coverage_gap_count=len(owner.coverage_gaps),
        fact_counts=tuple(sorted(counts.items())),
    )


def _corporate_action_coverage_gap(
    *,
    product: str,
    parameters: tuple[tuple[str, str], ...],
    scope: tuple[str, ...],
    row: Mapping[str, str],
    start_date: date,
    end_date: date,
    source_reference: ValidationArtifactReference,
    reason_codes: tuple[str, ...] = (
        "CORPORATE_ACTION_PROVIDER_ROW_UNRESOLVED",
        "RAW_UNADJUSTED_RETURN_FAILS_CLOSED",
    ),
) -> HistoricalSecurityFactCoverageGap | None:
    values = dict(parameters)
    if product.startswith("query_adjust_factor"):
        fact_kind = HistoricalSecurityFactKind.ADJUSTMENT_EVENT
        coverage_start = date.fromisoformat(values["start_date"])
        coverage_end = date.fromisoformat(values["end_date"])
    elif product.startswith("query_dividend_data"):
        fact_kind = HistoricalSecurityFactKind.DIVIDEND_EVENT
        year = int(values["year"])
        coverage_start = date(year, 1, 1)
        coverage_end = date(year, 12, 31)
    else:
        return None
    coverage_start = max(coverage_start, start_date)
    coverage_end = min(coverage_end, end_date)
    if coverage_start > coverage_end:
        return None
    raw_symbol = row.get("code")
    try:
        symbol = _canonical_symbol(raw_symbol) if raw_symbol else scope[0]
    except ValueError:
        symbol = scope[0]
    return HistoricalSecurityFactCoverageGap.create(
        fact_kind=fact_kind,
        symbol=symbol,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        raw_row_hash=_json_hash(dict(row)),
        source_reference=source_reference,
        reason_codes=reason_codes,
    )


def _rows(response: dict[str, Any]) -> tuple[dict[str, str], ...]:
    if response.get("error_code") != "0":
        raise AShareDataError(f"BaoStock historical fact query failed: {response.get('error_message')}")
    fields = tuple(str(item) for item in response.get("fields", ()))
    if not fields:
        raise AShareDataError("BaoStock historical fact query returned no fields")
    result: list[dict[str, str]] = []
    for raw_row in response.get("rows", ()):
        values = tuple(str(value) for value in raw_row)
        row = dict(zip(fields, values, strict=False))
        if len(values) != len(fields):
            row["__provider_field_count"] = str(len(fields))
            row["__provider_row_count"] = str(len(values))
            row["__provider_extra_values"] = _json_text(values[len(fields) :])
        result.append(row)
    return tuple(result)


def _fact_from_row(
    *,
    product: str,
    row: dict[str, str],
    source_reference: ValidationArtifactReference,
) -> HistoricalSecurityFact | None:
    if "__provider_field_count" in row:
        return None
    symbol = _canonical_symbol(row["code"])
    reason_codes = (
        "REAL_FREE_PROVIDER_OBSERVATION",
        product.split(":", 1)[0].upper(),
    )
    if product.startswith("query_stock_industry"):
        if not row["updateDate"] or not row["industry"] or not row["industryClassification"]:
            return None
        return HistoricalSecurityFact.create(
            fact_kind=HistoricalSecurityFactKind.INDUSTRY,
            effective_date=date.fromisoformat(row["updateDate"]),
            published_date=None,
            values={
                "industry": row["industry"],
                "classification": row["industryClassification"],
            },
            symbol=symbol,
            source_reference=source_reference,
            reason_codes=reason_codes,
        )
    if product.startswith("query_profit_data"):
        if not row["pubDate"] or not row["statDate"] or not (row["totalShare"] or row["liqaShare"]):
            return None
        return HistoricalSecurityFact.create(
            fact_kind=HistoricalSecurityFactKind.SHARE_CAPITAL,
            effective_date=date.fromisoformat(row["statDate"]),
            published_date=date.fromisoformat(row["pubDate"]),
            values={
                "total_shares": row["totalShare"],
                "liquid_shares": row["liqaShare"],
            },
            symbol=symbol,
            source_reference=source_reference,
            reason_codes=reason_codes,
        )
    if product.startswith("query_adjust_factor"):
        if not row["dividOperateDate"] or not row["adjustFactor"]:
            return None
        return HistoricalSecurityFact.create(
            fact_kind=HistoricalSecurityFactKind.ADJUSTMENT_EVENT,
            effective_date=date.fromisoformat(row["dividOperateDate"]),
            published_date=None,
            values={
                "adjustment_factor": row["adjustFactor"],
                "back_adjust_factor": row["backAdjustFactor"],
                "forward_adjust_factor": row["foreAdjustFactor"],
            },
            symbol=symbol,
            source_reference=source_reference,
            reason_codes=reason_codes,
        )
    if product.startswith("query_dividend_data"):
        if not row["dividOperateDate"]:
            return None
        published = next(
            (
                row[name]
                for name in (
                    "dividPreNoticeDate",
                    "dividPlanAnnounceDate",
                    "dividAgmPumDate",
                    "dividPlanDate",
                )
                if row.get(name)
            ),
            None,
        )
        values = {
            "cash_dividend_per_share_before_tax": row["dividCashPsBeforeTax"],
            "stock_dividend_per_share": row["dividStocksPs"],
            "reserve_to_stock_per_share": row["dividReserveToStockPs"],
        }
        if not any(values.values()):
            return None
        return HistoricalSecurityFact.create(
            fact_kind=HistoricalSecurityFactKind.DIVIDEND_EVENT,
            effective_date=date.fromisoformat(row["dividOperateDate"]),
            published_date=(None if published is None else date.fromisoformat(published)),
            values=values,
            symbol=symbol,
            source_reference=source_reference,
            reason_codes=reason_codes,
        )
    raise ValueError(f"unsupported historical fact product: {product}")


def _baostock_code(symbol: str) -> str:
    code, exchange = symbol.split(".", 1)
    if exchange not in {"SH", "SZ", "BJ"} or not code.isdigit():
        raise ValueError(f"unsupported A-share symbol: {symbol}")
    return f"{exchange.lower()}.{code}"


def _canonical_symbol(code: str) -> str:
    exchange, symbol = code.split(".", 1)
    if exchange not in {"sh", "sz", "bj"} or not symbol.isdigit():
        raise ValueError(f"unsupported BaoStock code: {code}")
    return f"{symbol}.{exchange.upper()}"


__all__ = [
    "BaoStockHistoricalSecurityFactsClient",
    "HistoricalSecurityFactsAcquisition",
    "HistoricalSecurityFactsPrefetch",
]
