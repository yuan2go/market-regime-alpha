"""Compile prospective archive intent into the one canonical Runtime model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from market_regime_alpha.market.application.archive import StartMarketArchiveRequest
from market_regime_alpha.market.application.archive_manifest import (
    ArchiveManifestSlice,
    ArchiveOperatorManifest,
)
from market_regime_alpha.market.application.archive_operations import (
    ArchiveSliceExecutionRequest,
    ArchiveSliceExecutionResult,
    ArchiveSliceExecutionStatus,
)
from market_regime_alpha.market.ports import (
    ArchiveInspectionPort,
    ArchiveVerificationPort,
    MarketDatabaseClock,
    MarketNormalizer,
    MarketProvider,
)
from market_regime_alpha.market.domain import (
    ArchiveSliceStatus,
    MarketArchive,
    MarketArchiveSlice,
)
from market_regime_alpha.runtime.application import (
    ActorType,
    ArtifactApplication,
    CommandContext,
    RuntimeApplication,
)
from market_regime_alpha.runtime.domain import (
    ExternalEffectClass,
    RetryPolicy,
    RunSpec,
    RuntimeMode,
    ScheduleSpec,
    StepSpec,
)
from market_regime_alpha.runtime.ports import AttemptClaim, RunTrace
from market_regime_alpha.runtime.errors import RuntimeNotFoundError
from market_regime_alpha.shared.hashing import canonical_json_sha256, sha256_bytes


_IMPLEMENTATION = "market.prospective_archive"
_IMPLEMENTATION_VERSION = "1"
_SCHEDULE_REVISION = 1
_SCHEDULE_CODE = "prospective-archive"
_CATALOG_HASH = canonical_json_sha256(
    {
        "implementation": _IMPLEMENTATION,
        "implementation_version": _IMPLEMENTATION_VERSION,
        "step_kinds": ("RECORD_EVIDENCE", "CAPTURE"),
    }
)


@dataclass(frozen=True, slots=True)
class ProspectiveRuntimeRunPlan:
    run_id: UUID
    fire_key: str
    requested_at: datetime
    decision_time: datetime | None
    window_start: datetime | None
    window_end: datetime | None
    schedule_slot: str | None
    steps: tuple[StepSpec, ...]
    slices: tuple[ArchiveManifestSlice, ...]


@dataclass(frozen=True, slots=True)
class ProspectiveArchiveRuntimePlan:
    market_archive_id: UUID
    code_sha: str
    config_bytes: bytes
    config_sha256: str
    schedule: ScheduleSpec
    predeclare: ProspectiveRuntimeRunPlan
    capture_runs: tuple[ProspectiveRuntimeRunPlan, ...]

    @property
    def runs(self) -> tuple[ProspectiveRuntimeRunPlan, ...]:
        return (self.predeclare, *self.capture_runs)


@dataclass(frozen=True, slots=True)
class ProspectiveRuntimeRegistration:
    market_archive_id: UUID
    schedule_id: UUID
    config_artifact_id: UUID
    config_sha256: str
    predeclare_run_id: UUID
    capture_run_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ProspectiveRuntimeFailure:
    run_id: UUID
    step_id: UUID
    market_archive_slice_id: UUID
    error_code: str


@dataclass(frozen=True, slots=True)
class ProspectiveRuntimeExecution:
    market_archive_id: UUID
    observed_at: datetime
    due_run_ids: tuple[UUID, ...]
    recovered_attempt_ids: tuple[UUID, ...]
    slice_results: tuple[ArchiveSliceExecutionResult, ...]
    failures: tuple[ProspectiveRuntimeFailure, ...]


class ProspectiveRuntimeIntegrityError(RuntimeError):
    """Frozen Runtime and Market intent no longer reconcile."""


class _ArchiveCommands(Protocol):
    def start(
        self,
        request: StartMarketArchiveRequest,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> object: ...


class _ArchiveOperations(Protocol):
    def execute_slice(
        self,
        request: ArchiveSliceExecutionRequest,
        *,
        provider: MarketProvider,
        normalizer: MarketNormalizer,
        context: CommandContext,
        runtime_claim: AttemptClaim | None = None,
    ) -> ArchiveSliceExecutionResult: ...


def compile_prospective_runtime_plan(
    manifest: ArchiveOperatorManifest,
    *,
    code_sha: str,
) -> ProspectiveArchiveRuntimePlan:
    """Build stable Run/Step intent; it performs no I/O or Authority writes."""

    config_bytes = manifest.to_bytes()
    config_hash = sha256_bytes(config_bytes)
    archive_id = manifest.start_request.market_archive_id
    schedule_id = _id(f"schedule:{_SCHEDULE_REVISION}:{_CATALOG_HASH}")
    schedule = ScheduleSpec(
        schedule_id=schedule_id,
        schedule_code=_SCHEDULE_CODE,
        revision=_SCHEDULE_REVISION,
        runtime_mode=RuntimeMode.PROSPECTIVE,
        schedule_expression="POSTGRESQL_DUE_QUERY",
        timezone_name="Asia/Shanghai",
        step_catalog_hash=_CATALOG_HASH,
        enabled=True,
    )
    predeclare = ProspectiveRuntimeRunPlan(
        run_id=_id(f"archive:{archive_id}:predeclare"),
        fire_key=f"archive:{archive_id}:predeclare",
        requested_at=manifest.start_request.event_window_start,
        decision_time=None,
        window_start=None,
        window_end=None,
        schedule_slot=None,
        steps=(
            StepSpec(
                step_key="predeclare-archive",
                step_kind="RECORD_EVIDENCE",
                implementation=f"{_IMPLEMENTATION}.predeclare",
                implementation_version=_IMPLEMENTATION_VERSION,
                ordinal=1,
                required=True,
                request_hash=canonical_json_sha256(manifest.start_request),
                input_evidence_hash=config_hash,
                retry_policy=RetryPolicy(
                    max_attempts=1,
                    backoff=(),
                    retryable_codes=frozenset(),
                ),
                external_effect_class=ExternalEffectClass.NONE,
            ),
        ),
        slices=(),
    )
    grouped: dict[tuple[datetime, datetime, str], list[ArchiveManifestSlice]] = {}
    for item in manifest.slices:
        key = (
            item.plan.event_window_start,
            item.plan.event_window_end,
            item.schedule_slot,
        )
        grouped.setdefault(key, []).append(item)
    capture_runs: list[ProspectiveRuntimeRunPlan] = []
    for (window_start, window_end, slot), rows in sorted(
        grouped.items(), key=lambda item: item[0]
    ):
        slices = tuple(sorted(rows, key=lambda item: item.plan.ordinal))
        fire_key = (
            f"archive:{archive_id}:capture:{slot.lower()}:"
            f"{window_start.isoformat()}:{window_end.isoformat()}"
        )
        steps: list[StepSpec] = []
        for ordinal, item in enumerate(slices, start=1):
            request = ArchiveSliceExecutionRequest(
                market_archive_id=archive_id,
                market_archive_slice_id=item.plan.market_archive_slice_id,
                capture_request=item.capture_request,
                schedule_slot=item.schedule_slot,
            )
            steps.append(
                StepSpec(
                    step_key=f"capture-{item.plan.ordinal:04d}",
                    step_kind="CAPTURE",
                    implementation=f"{_IMPLEMENTATION}.capture_slice",
                    implementation_version=_IMPLEMENTATION_VERSION,
                    ordinal=ordinal,
                    required=True,
                    request_hash=canonical_json_sha256(request),
                    input_evidence_hash=config_hash,
                    retry_policy=RetryPolicy(
                        max_attempts=3,
                        backoff=(timedelta(seconds=2), timedelta(seconds=5)),
                        retryable_codes=frozenset(
                            {
                                "CAPTURE_WINDOW_NOT_OPEN",
                                "NETWORK_ERROR",
                                "PROVIDER_TEMPORARY_FAILURE",
                            }
                        ),
                        deadline=window_end,
                    ),
                    external_effect_class=ExternalEffectClass.CONTENT_PUT,
                )
            )
        capture_runs.append(
            ProspectiveRuntimeRunPlan(
                run_id=_id(f"run:{fire_key}"),
                fire_key=fire_key,
                requested_at=manifest.start_request.event_window_start,
                decision_time=window_start,
                window_start=window_start,
                window_end=window_end,
                schedule_slot=slot,
                steps=tuple(steps),
                slices=slices,
            )
        )
    return ProspectiveArchiveRuntimePlan(
        market_archive_id=archive_id,
        code_sha=code_sha,
        config_bytes=config_bytes,
        config_sha256=config_hash,
        schedule=schedule,
        predeclare=predeclare,
        capture_runs=tuple(capture_runs),
    )


class ProspectiveArchiveRuntimeApplication:
    """Compose Market commands with Runtime without acquiring either Authority."""

    def __init__(
        self,
        *,
        runtime: RuntimeApplication,
        artifacts: ArtifactApplication,
        archives: _ArchiveCommands,
        operations: _ArchiveOperations,
        database_clock: MarketDatabaseClock,
        archive_inspection: ArchiveInspectionPort | None = None,
        archive_verification: ArchiveVerificationPort | None = None,
    ) -> None:
        self._runtime = runtime
        self._artifacts = artifacts
        self._archives = archives
        self._operations = operations
        self._database_clock = database_clock
        self._archive_inspection = archive_inspection
        self._archive_verification = archive_verification

    def predeclare(
        self,
        manifest: ArchiveOperatorManifest,
        *,
        code_sha: str,
        actor_id: str,
        lease_duration: timedelta,
    ) -> ProspectiveRuntimeRegistration:
        plan = compile_prospective_runtime_plan(manifest, code_sha=code_sha)
        artifact = self._artifacts.publish(
            plan.config_bytes,
            media_type="application/json",
            expected_sha256=plan.config_sha256,
            pin_reason_code="PROSPECTIVE_RUNTIME_CONFIG",
            context=_context(
                f"prospective:{plan.market_archive_id}:runtime-config",
                actor_id,
                "REGISTER_PROSPECTIVE_CONFIG",
            ),
        )
        self._runtime.create_schedule(
            plan.schedule,
            _context(
                f"prospective-runtime:schedule:{plan.schedule.revision}",
                actor_id,
                "REGISTER_PROSPECTIVE_SCHEDULE",
            ),
        )
        self._register_run(plan, plan.predeclare, artifact.artifact_id, actor_id)
        self._execute_predeclare(
            plan,
            manifest,
            actor_id=actor_id,
            lease_duration=lease_duration,
        )
        for run in plan.capture_runs:
            self._register_run(plan, run, artifact.artifact_id, actor_id)
        return ProspectiveRuntimeRegistration(
            market_archive_id=plan.market_archive_id,
            schedule_id=plan.schedule.schedule_id,
            config_artifact_id=artifact.artifact_id,
            config_sha256=artifact.content_sha256,
            predeclare_run_id=plan.predeclare.run_id,
            capture_run_ids=tuple(run.run_id for run in plan.capture_runs),
        )

    def run_due(
        self,
        manifest: ArchiveOperatorManifest,
        *,
        code_sha: str,
        actor_id: str,
        worker_id: str,
        lease_duration: timedelta,
        provider: MarketProvider,
        normalizer_for: Callable[[ArchiveManifestSlice], MarketNormalizer],
    ) -> ProspectiveRuntimeExecution:
        plan = compile_prospective_runtime_plan(manifest, code_sha=code_sha)
        recovered = self._runtime.recover_expired(
            actor_id=actor_id,
            reason_code="PROSPECTIVE_LEASE_RECOVERY",
        )
        observed_at = self._database_clock.now()
        due = tuple(
            run
            for run in plan.capture_runs
            if run.window_start is not None
            and run.window_end is not None
            and run.window_start <= observed_at <= run.window_end
        )
        results: list[ArchiveSliceExecutionResult] = []
        failures: list[ProspectiveRuntimeFailure] = []
        for run in due:
            trace = self._runtime.inspect_run(run.run_id)
            _verify_trace(plan, run, trace)
            by_key = {
                f"capture-{item.plan.ordinal:04d}": item for item in run.slices
            }
            while trace.run_state == "RUNNING":
                ready = next((item for item in trace.steps if item.state == "READY"), None)
                if ready is None:
                    break
                claim = self._runtime.claim_next(
                    run_id=run.run_id,
                    worker_id=worker_id,
                    lease_duration=lease_duration,
                    context=_context(
                        f"prospective:{run.run_id}:{ready.step_id}:claim:"
                        f"{len(ready.attempt_states) + 1}",
                        actor_id,
                        "CLAIM_PROSPECTIVE_SLICE",
                        actor_type=ActorType.WORKER,
                    ),
                )
                if claim is None:
                    break
                self._runtime.start_attempt(
                    claim,
                    _context(
                        f"prospective:{claim.attempt_id}:start",
                        actor_id,
                        "START_PROSPECTIVE_SLICE",
                        actor_type=ActorType.WORKER,
                    ),
                )
                item = by_key.get(claim.step_key)
                if item is None:
                    self._fail_integrity(claim, actor_id, "UNKNOWN_RUNTIME_STEP")
                assert item is not None
                request = ArchiveSliceExecutionRequest(
                    market_archive_id=plan.market_archive_id,
                    market_archive_slice_id=item.plan.market_archive_slice_id,
                    capture_request=item.capture_request,
                    schedule_slot=item.schedule_slot,
                )
                try:
                    result = self._operations.execute_slice(
                        request,
                        provider=provider,
                        normalizer=normalizer_for(item),
                        context=_context(
                            f"archive:{plan.market_archive_id}:runtime:"
                            f"{item.plan.market_archive_slice_id}",
                            actor_id,
                            "EXECUTE_PROSPECTIVE_SLICE",
                            actor_type=ActorType.WORKER,
                        ),
                        runtime_claim=claim,
                    )
                    if result.status is ArchiveSliceExecutionStatus.ALREADY_TERMINAL:
                        self._runtime.succeed_attempt(
                            claim,
                            result_hash=canonical_json_sha256(result),
                            context=_context(
                                f"prospective:{claim.attempt_id}:reconcile-terminal",
                                actor_id,
                                "RECONCILE_PROSPECTIVE_SLICE",
                                actor_type=ActorType.WORKER,
                            ),
                        )
                    elif result.status is ArchiveSliceExecutionStatus.NOT_DUE:
                        self._runtime.fail_attempt(
                            claim,
                            error_class="SCHEDULE",
                            error_code="CAPTURE_WINDOW_NOT_OPEN",
                            context=_context(
                                f"prospective:{claim.attempt_id}:not-open",
                                actor_id,
                                "DEFER_PROSPECTIVE_SLICE",
                                actor_type=ActorType.WORKER,
                            ),
                        )
                        failures.append(
                            ProspectiveRuntimeFailure(
                                run.run_id,
                                claim.step_id,
                                item.plan.market_archive_slice_id,
                                "CAPTURE_WINDOW_NOT_OPEN",
                            )
                        )
                    else:
                        _require_step_succeeded(self._runtime, claim)
                    results.append(result)
                except (ValueError, ProspectiveRuntimeIntegrityError):
                    if _step_is_live(self._runtime, claim):
                        self._runtime.fail_attempt(
                            claim,
                            error_class="INTEGRITY",
                            error_code="INTEGRITY_ERROR",
                            context=_context(
                                f"prospective:{claim.attempt_id}:integrity",
                                actor_id,
                                "FAIL_PROSPECTIVE_INTEGRITY",
                                actor_type=ActorType.WORKER,
                            ),
                        )
                    raise
                except Exception:
                    if _step_is_live(self._runtime, claim):
                        self._runtime.fail_attempt(
                            claim,
                            error_class="PROVIDER",
                            error_code="PROVIDER_TEMPORARY_FAILURE",
                            context=_context(
                                f"prospective:{claim.attempt_id}:provider-failure",
                                actor_id,
                                "FAIL_PROSPECTIVE_PROVIDER",
                                actor_type=ActorType.WORKER,
                            ),
                        )
                    failures.append(
                        ProspectiveRuntimeFailure(
                            run.run_id,
                            claim.step_id,
                            item.plan.market_archive_slice_id,
                            "PROVIDER_TEMPORARY_FAILURE",
                        )
                    )
                trace = self._runtime.inspect_run(run.run_id)
                _verify_trace(plan, run, trace)
        return ProspectiveRuntimeExecution(
            market_archive_id=plan.market_archive_id,
            observed_at=observed_at,
            due_run_ids=tuple(run.run_id for run in due),
            recovered_attempt_ids=recovered,
            slice_results=tuple(results),
            failures=tuple(failures),
        )

    def _register_run(
        self,
        plan: ProspectiveArchiveRuntimePlan,
        run: ProspectiveRuntimeRunPlan,
        config_artifact_id: UUID,
        actor_id: str,
    ) -> None:
        self._runtime.schedule_run(
            RunSpec(
                run_id=run.run_id,
                schedule_id=plan.schedule.schedule_id,
                fire_key=run.fire_key,
                runtime_mode=RuntimeMode.PROSPECTIVE,
                requested_at=run.requested_at,
                decision_time=run.decision_time,
                code_sha=plan.code_sha,
                config_artifact_id=config_artifact_id,
                config_hash=plan.config_sha256,
            ),
            run.steps,
            (),
            _context(
                f"prospective:{run.run_id}:schedule",
                actor_id,
                "SCHEDULE_PROSPECTIVE_RUN",
            ),
        )
        trace = self._runtime.inspect_run(run.run_id)
        _verify_trace(plan, run, trace)
        if trace.run_state == "QUEUED":
            self._runtime.start_run(
                run.run_id,
                _context(
                    f"prospective:{run.run_id}:start",
                    actor_id,
                    "START_PROSPECTIVE_RUN",
                ),
            )
        elif trace.run_state not in {"RUNNING", "SUCCEEDED"}:
            raise ProspectiveRuntimeIntegrityError(
                f"prospective Runtime Run {run.run_id} is {trace.run_state}"
            )

    def _execute_predeclare(
        self,
        plan: ProspectiveArchiveRuntimePlan,
        manifest: ArchiveOperatorManifest,
        *,
        actor_id: str,
        lease_duration: timedelta,
    ) -> None:
        trace = self._runtime.inspect_run(plan.predeclare.run_id)
        _verify_trace(plan, plan.predeclare, trace)
        if trace.run_state == "SUCCEEDED":
            return
        ready = next((item for item in trace.steps if item.state == "READY"), None)
        if ready is None:
            raise ProspectiveRuntimeIntegrityError(
                "prospective predeclaration has no claimable Runtime Step"
            )
        claim = self._runtime.claim_next(
            run_id=plan.predeclare.run_id,
            worker_id=f"prospective-predeclare:{actor_id}",
            lease_duration=lease_duration,
            context=_context(
                f"prospective:{plan.predeclare.run_id}:{ready.step_id}:claim:"
                f"{len(ready.attempt_states) + 1}",
                actor_id,
                "CLAIM_PROSPECTIVE_PREDECLARE",
                actor_type=ActorType.WORKER,
            ),
        )
        if claim is None:
            raise ProspectiveRuntimeIntegrityError(
                "prospective predeclaration claim was not acquired"
            )
        self._runtime.start_attempt(
            claim,
            _context(
                f"prospective:{claim.attempt_id}:start",
                actor_id,
                "START_PROSPECTIVE_PREDECLARE",
                actor_type=ActorType.WORKER,
            ),
        )
        existing_result_hash = self._reconcile_existing_archive(manifest)
        if existing_result_hash is None:
            self._archives.start(
                manifest.start_request,
                _context(
                    f"archive:{plan.market_archive_id}:start",
                    actor_id,
                    "PREDECLARE_PROSPECTIVE_ARCHIVE",
                ),
                runtime_claim=claim,
            )
        else:
            self._runtime.succeed_attempt(
                claim,
                result_hash=existing_result_hash,
                context=_context(
                    f"prospective:{claim.attempt_id}:reconcile-archive",
                    actor_id,
                    "RECONCILE_PROSPECTIVE_ARCHIVE",
                    actor_type=ActorType.WORKER,
                ),
            )
        _require_step_succeeded(self._runtime, claim)

    def _reconcile_existing_archive(
        self,
        manifest: ArchiveOperatorManifest,
    ) -> str | None:
        if self._archive_inspection is None or self._archive_verification is None:
            return None
        try:
            actual = self._archive_inspection.inspect(
                manifest.start_request.market_archive_id
            )
        except RuntimeNotFoundError:
            return None
        verified = self._archive_verification.verify(actual.market_archive_id)
        request = manifest.start_request
        root_matches = (
            verified.matched
            and actual.request_identity == f"archive:{request.market_archive_id}:start"
            and actual.archive_code == request.archive_code
            and actual.lane == request.lane.value
            and actual.provider_product_id == request.provider_product_id
            and actual.exchange_code == request.exchange_code
            and actual.timeframe == request.timeframe.value
            and actual.price_basis == request.price_basis.value
            and actual.instrument_scope == request.instrument_scope
            and actual.instrument_scope_sha256 == request.instrument_scope_sha256
            and actual.event_window_start == request.event_window_start
            and actual.event_window_end == request.event_window_end
            and actual.reserved_free_bytes == request.reserved_free_bytes
            and actual.maximum_archive_bytes == request.maximum_archive_bytes
            and actual.maximum_slice_bytes == request.maximum_slice_bytes
            and actual.code_artifact_id == request.code_artifact_id
            and actual.config_artifact_id == request.config_artifact_id
            and actual.provenance_sha256 == request.provenance_sha256
            and actual.slice_count == len(request.slices)
        )
        expected_slices = tuple(
            MarketArchiveSlice(
                market_archive_slice_id=item.market_archive_slice_id,
                market_archive_id=request.market_archive_id,
                ordinal=item.ordinal,
                scope_key=item.scope_key,
                event_window_start=item.event_window_start,
                event_window_end=item.event_window_end,
                request_sha256=item.request_sha256,
                expected_fact_kind=item.expected_fact_kind,
                status=ArchiveSliceStatus.PLANNED,
            )
            for item in request.slices
        )
        slice_matches = len(actual.slices) == len(expected_slices) and all(
            observed.market_archive_slice_id == expected.market_archive_slice_id
            and observed.ordinal == expected.ordinal
            and observed.scope_key == expected.scope_key
            and observed.expected_fact_kind == expected.expected_fact_kind
            and observed.event_window_start == expected.event_window_start
            and observed.event_window_end == expected.event_window_end
            and observed.request_sha256 == str(expected.request_sha256)
            and observed.content_sha256 == str(expected.content_sha256)
            for observed, expected in zip(actual.slices, expected_slices, strict=True)
        )
        expected_archive = MarketArchive(
            market_archive_id=request.market_archive_id,
            lane=request.lane,
            provider_product_id=request.provider_product_id,
            exchange_code=request.exchange_code,
            timeframe=request.timeframe,
            price_basis=request.price_basis,
            instrument_scope=request.instrument_scope,
            instrument_scope_sha256=request.instrument_scope_sha256,
            event_window_start=request.event_window_start,
            event_window_end=request.event_window_end,
            archive_start_at=actual.archive_start_at,
            reserved_free_bytes=request.reserved_free_bytes,
            maximum_archive_bytes=request.maximum_archive_bytes,
            maximum_slice_bytes=request.maximum_slice_bytes,
            code_artifact_id=request.code_artifact_id,
            config_artifact_id=request.config_artifact_id,
            provenance_sha256=request.provenance_sha256,
            slices=expected_slices,
        )
        if (
            not root_matches
            or not slice_matches
            or actual.content_sha256 != str(expected_archive.content_sha256)
        ):
            mismatch = ", ".join(verified.mismatches) or "structural mismatch"
            raise ProspectiveRuntimeIntegrityError(
                f"existing MarketArchive differs from manifest: {mismatch}"
            )
        return actual.command_result_hash

    def _fail_integrity(
        self,
        claim: AttemptClaim,
        actor_id: str,
        detail: str,
    ) -> None:
        self._runtime.fail_attempt(
            claim,
            error_class="INTEGRITY",
            error_code="INTEGRITY_ERROR",
            context=_context(
                f"prospective:{claim.attempt_id}:unknown-step",
                actor_id,
                "FAIL_PROSPECTIVE_INTEGRITY",
                actor_type=ActorType.WORKER,
            ),
        )
        raise ProspectiveRuntimeIntegrityError(detail)


def _verify_trace(
    plan: ProspectiveArchiveRuntimePlan,
    expected: ProspectiveRuntimeRunPlan,
    trace: RunTrace,
) -> None:
    if (
        trace.run_id != expected.run_id
        or trace.schedule_id != plan.schedule.schedule_id
        or trace.fire_key != expected.fire_key
        or trace.runtime_mode != RuntimeMode.PROSPECTIVE.value
        or trace.code_sha != plan.code_sha
        or trace.config_hash != plan.config_sha256
        or len(trace.steps) != len(expected.steps)
    ):
        raise ProspectiveRuntimeIntegrityError(
            f"prospective Runtime Run {expected.run_id} differs from frozen intent"
        )
    for actual, frozen in zip(trace.steps, expected.steps, strict=True):
        if (
            actual.step_key != frozen.step_key
            or actual.step_kind != frozen.step_kind
            or actual.implementation != frozen.implementation
            or actual.implementation_version != frozen.implementation_version
            or actual.request_hash != frozen.request_hash
            or actual.input_evidence_hash != frozen.input_evidence_hash
            or actual.deadline_at != frozen.retry_policy.deadline
        ):
            raise ProspectiveRuntimeIntegrityError(
                f"prospective Runtime Step {actual.step_id} differs from frozen intent"
            )


def _require_step_succeeded(runtime: RuntimeApplication, claim: AttemptClaim) -> None:
    trace = runtime.inspect_run(claim.run_id)
    step = next(item for item in trace.steps if item.step_id == claim.step_id)
    if step.state != "SUCCEEDED":
        raise ProspectiveRuntimeIntegrityError(
            f"Market command did not atomically terminalize Runtime Step {claim.step_id}"
        )


def _step_is_live(runtime: RuntimeApplication, claim: AttemptClaim) -> bool:
    trace = runtime.inspect_run(claim.run_id)
    step = next(item for item in trace.steps if item.step_id == claim.step_id)
    return step.state in {"CLAIMED", "RUNNING"}


def _context(
    key: str,
    actor_id: str,
    reason_code: str,
    *,
    actor_type: ActorType = ActorType.OPERATOR,
) -> CommandContext:
    return CommandContext(
        idempotency_key=key,
        actor_type=actor_type,
        actor_id=actor_id,
        reason_code=reason_code,
    )


def _id(key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"mra:prospective-runtime:v1:{key}")


__all__ = [
    "ProspectiveArchiveRuntimeApplication",
    "ProspectiveArchiveRuntimePlan",
    "ProspectiveRuntimeExecution",
    "ProspectiveRuntimeFailure",
    "ProspectiveRuntimeIntegrityError",
    "ProspectiveRuntimeRegistration",
    "ProspectiveRuntimeRunPlan",
    "compile_prospective_runtime_plan",
]
