"""Compile prospective archive intent into the one canonical Runtime model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from market_regime_alpha.market.application.archive import StartMarketArchiveRequest, RecordProspectivePlanningGapRequest
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
    CaptureRequest,
    ProviderResponse,
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
from market_regime_alpha.shared.identity import TradingSessionId
from market_regime_alpha.market.ports.prospective_continuity import ProspectiveContinuityReadPort
from market_regime_alpha.market.ports.session_roster import ArchiveTradingSessionReadPort
from market_regime_alpha.market.ports.target_archive_schedule import TargetArchiveScheduleReadPort
from market_regime_alpha.market.application.prospective_continuity import plan_continuation
from market_regime_alpha.market.application.prospective_archive import (
    ProspectiveArchiveInstrument, build_target_aligned_prospective_manifest,
)
from market_regime_alpha.market.domain import ProspectiveArchiveSession
from market_regime_alpha.infrastructure.providers.baostock_archive import BaoStockArchiveQuery


_IMPLEMENTATION = "market.prospective_archive"
_SCHEDULE_CODE = "prospective-archive"


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
    attempt_ids: tuple[UUID, ...] = ()


class ProspectiveRuntimeIntegrityError(RuntimeError):
    """Frozen Runtime and Market intent no longer reconcile."""


class ProspectiveExternalEffectUnknown(ProspectiveRuntimeIntegrityError):
    """A prior Provider effect has no canonical Capture receipt to reconcile."""


class _ReconciledCaptureProvider:
    """Only the first Attempt may start I/O; retries must find Capture receipts."""

    def __init__(self, provider: MarketProvider, *, attempt_no: int,
                 before_effect: Callable[[], None] | None = None) -> None:
        self._provider = provider
        self._may_start = attempt_no == 1
        self._before_effect = before_effect

    def capture(self, request: CaptureRequest) -> ProviderResponse:
        if not self._may_start:
            raise ProspectiveExternalEffectUnknown(
                "EXTERNAL_EFFECT_UNKNOWN: prior Attempt has no reconciled Capture; "
                "Provider I/O cannot be repeated"
            )
        self._may_start = False
        if self._before_effect is not None:
            self._before_effect()
        return self._provider.capture(request)


class _ArchiveCommands(Protocol):
    def start(
        self,
        request: StartMarketArchiveRequest,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> object: ...


    def finalize_overdue(self, *, market_archive_id: UUID, context: CommandContext,
                         runtime_claim: AttemptClaim | None = None) -> object: ...

    def record_prospective_planning_gap(self, request: RecordProspectivePlanningGapRequest,
                                      context: CommandContext, *, runtime_claim: AttemptClaim | None = None) -> object: ...


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
    runtime_revision: int = 2,
) -> ProspectiveArchiveRuntimePlan:
    """Build stable Run/Step intent; it performs no I/O or Authority writes."""

    if type(runtime_revision) is not int or runtime_revision not in {1, 2}:
        raise ValueError("Unknown prospective Runtime revision")
    implementation_version = str(runtime_revision)
    catalog_hash = canonical_json_sha256({
        "implementation": _IMPLEMENTATION,
        "implementation_version": implementation_version,
        "step_kinds": ("RECORD_EVIDENCE", "CAPTURE"),
    })
    config_bytes = manifest.to_bytes()
    config_hash = sha256_bytes(config_bytes)
    archive_id = manifest.start_request.market_archive_id
    schedule_id = _id(f"schedule:{runtime_revision}:{catalog_hash}")
    schedule = ScheduleSpec(
        schedule_id=schedule_id,
        schedule_code=_SCHEDULE_CODE,
        revision=runtime_revision,
        runtime_mode=RuntimeMode.PROSPECTIVE,
        schedule_expression="POSTGRESQL_DUE_QUERY",
        timezone_name="Asia/Shanghai",
        step_catalog_hash=catalog_hash,
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
                implementation_version=implementation_version,
                ordinal=1,
                required=True,
                request_hash=canonical_json_sha256(manifest.start_request),
                input_evidence_hash=config_hash,
                retry_policy=RetryPolicy(
                    max_attempts=1 if runtime_revision == 1 else 3,
                    backoff=() if runtime_revision == 1 else (timedelta(0), timedelta(0)),
                    retryable_codes=frozenset() if runtime_revision == 1 else frozenset({"LEASE_EXPIRED"}),
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
                    implementation_version=implementation_version,
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
        due_query: Callable[[UUID], tuple[UUID, ...]],
        archive_inspection: ArchiveInspectionPort | None = None,
        archive_verification: ArchiveVerificationPort | None = None,
        continuity: ProspectiveContinuityReadPort | None = None,
        trading_sessions: ArchiveTradingSessionReadPort | None = None,
        target_schedules: TargetArchiveScheduleReadPort | None = None,
        manifest_reader: Callable[[str, int], bytes] | None = None,
    ) -> None:
        self._runtime = runtime
        self._artifacts = artifacts
        self._archives = archives
        self._operations = operations
        self._database_clock = database_clock
        self._due_query = due_query
        self._archive_inspection = archive_inspection
        self._archive_verification = archive_verification
        self._continuity = continuity
        self._trading_sessions = trading_sessions
        self._target_schedules = target_schedules
        self._manifest_reader = manifest_reader

    def predeclare(
        self,
        manifest: ArchiveOperatorManifest,
        *,
        code_sha: str,
        actor_id: str,
        lease_duration: timedelta,
        runtime_revision: int = 2,
        before_action: Callable[[], None] | None = None,
    ) -> ProspectiveRuntimeRegistration:
        if before_action is not None:
            before_action()
        plan = compile_prospective_runtime_plan(manifest, code_sha=code_sha, runtime_revision=runtime_revision)
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
        self._runtime.recover_expired(
            actor_id=actor_id, reason_code="PROSPECTIVE_LEASE_RECOVERY",
            run_id=plan.predeclare.run_id,
        )
        self._execute_predeclare(
            plan,
            manifest,
            actor_id=actor_id,
            lease_duration=lease_duration,
            before_action=before_action,
        )
        for run in plan.capture_runs:
            if before_action is not None:
                before_action()
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
        runtime_revision: int = 2,
        maximum_attempts: int | None = None,
        before_action: Callable[[], None] | None = None,
    ) -> ProspectiveRuntimeExecution:
        if maximum_attempts is not None and (type(maximum_attempts) is not int or maximum_attempts < 0):
            raise ValueError("Prospective attempt budget must be a non-negative integer")
        plan = compile_prospective_runtime_plan(manifest, code_sha=code_sha, runtime_revision=runtime_revision)
        recovered_ids: list[UUID] = []
        for recovery_run in plan.runs:
            if before_action is not None:
                before_action()
            recovered_ids.extend(self._runtime.recover_expired(
                actor_id=actor_id,
                reason_code="PROSPECTIVE_LEASE_RECOVERY",
                run_id=recovery_run.run_id,
            ))
        recovered = tuple(recovered_ids)
        observed_at = self._database_clock.now()
        due_slice_ids = frozenset(self._due_query(plan.market_archive_id))
        planned_ids = {item.plan.market_archive_slice_id for item in manifest.slices}
        if not due_slice_ids <= planned_ids:
            raise ProspectiveRuntimeIntegrityError("Due query returned a slice outside the frozen manifest")
        due = tuple(
            run
            for run in plan.capture_runs
            if run.window_start is not None
            and run.window_end is not None
            and run.window_start <= observed_at <= run.window_end
            and any(item.plan.market_archive_slice_id in due_slice_ids for item in run.slices)
        )
        results: list[ArchiveSliceExecutionResult] = []
        failures: list[ProspectiveRuntimeFailure] = []
        attempt_ids: list[UUID] = []
        for run in due:
            trace = self._runtime.inspect_run(run.run_id)
            _verify_trace(plan, run, trace)
            by_key = {
                f"capture-{item.plan.ordinal:04d}": item for item in run.slices
            }
            while trace.run_state == "RUNNING":
                if maximum_attempts is not None and len(attempt_ids) >= maximum_attempts:
                    break
                ready = next((item for item in trace.steps if item.state == "READY"
                              and by_key[item.step_key].plan.market_archive_slice_id in due_slice_ids), None)
                if ready is None:
                    break
                if before_action is not None:
                    before_action()
                claim = self._runtime.claim_next(
                    run_id=run.run_id,
                    step_id=ready.step_id,
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
                attempt_ids.append(claim.attempt_id)
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
                        provider=_ReconciledCaptureProvider(
                            provider, attempt_no=claim.attempt_no, before_effect=before_action,
                        ),
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
                except (ValueError, ProspectiveRuntimeIntegrityError) as exc:
                    if _step_is_live(self._runtime, claim):
                        self._runtime.fail_attempt(
                            claim,
                            error_class="INTEGRITY",
                            error_code=("EXTERNAL_EFFECT_UNKNOWN"
                                        if isinstance(exc, ProspectiveExternalEffectUnknown)
                                        else "INTEGRITY_ERROR"),
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
            attempt_ids=tuple(attempt_ids),
        )

    def continue_series(
        self, *, series_code: str, code_sha: str, actor_id: str, worker_id: str,
        lease_duration: timedelta, provider: MarketProvider,
        normalizer_for: Callable[[ArchiveManifestSlice], MarketNormalizer],
        maximum_attempts: int | None = None,
        before_action: Callable[[], None] | None = None,
    ) -> dict[str, object]:
        """One bounded continuity tick; scheduling remains the existing Runtime."""
        if len(code_sha) != 40 or any(character not in "0123456789abcdef" for character in code_sha):
            raise ValueError("Continuity requires an exact implementation SHA")
        if maximum_attempts is not None and (type(maximum_attempts) is not int or maximum_attempts < 1):
            raise ValueError("Continuity attempt budget must be a positive integer")
        if (self._continuity is None or self._trading_sessions is None
                or self._target_schedules is None or self._manifest_reader is None
                or self._archive_verification is None):
            raise ProspectiveRuntimeIntegrityError("Continuity owner read ports are required")
        references = self._continuity.generations(series_code)
        if not references:
            raise ProspectiveRuntimeIntegrityError("Series requires an exact initial predeclared generation")
        executions: list[ProspectiveRuntimeExecution] = []
        manifests: list[ArchiveOperatorManifest] = []
        for reference in references:
            if before_action is not None:
                before_action()
            content = self._manifest_reader(reference.config_sha256, reference.config_size_bytes)
            if len(content) != reference.config_size_bytes or sha256_bytes(content) != reference.config_sha256:
                raise ProspectiveRuntimeIntegrityError("Generation manifest Artifact bytes differ")
            manifest = ArchiveOperatorManifest.from_json(content.decode("utf-8"))
            generation = manifest.start_request.prospective_generation
            if generation is None or (
                generation.series_code, generation.market_archive_id, generation.generation,
                generation.predecessor_market_archive_id,
            ) != (series_code, reference.market_archive_id, reference.generation,
                  reference.predecessor_market_archive_id):
                raise ProspectiveRuntimeIntegrityError("Generation manifest differs from canonical chain")
            verification = self._archive_verification.verify(reference.market_archive_id)
            if not verification.matched:
                raise ProspectiveRuntimeIntegrityError("Previous generation does not reconcile")
            # Repairs an interrupted registration using its original code/config;
            # completed commands resolve through exact receipt replay.
            self.predeclare(manifest, code_sha=reference.code_sha, actor_id=actor_id,
                            lease_duration=lease_duration, runtime_revision=reference.runtime_revision,
                            before_action=before_action)
            overdue = self._continuity.overdue_slice_ids(reference.market_archive_id)
            if overdue:
                def finalize(claim: AttemptClaim, context: CommandContext,
                             archive_id: UUID = reference.market_archive_id) -> object:
                    return self._archives.finalize_overdue(market_archive_id=archive_id,
                                                          context=context, runtime_claim=claim)

                self._run_maintenance(
                    manifest, code_sha=reference.code_sha,
                    config_artifact_id=reference.config_artifact_id,
                    operation="finalize_overdue", payload={"slice_ids": overdue},
                    actor_id=actor_id, worker_id=worker_id, lease_duration=lease_duration,
                    command=finalize,
                    runtime_revision=reference.runtime_revision,
                    before_action=before_action,
                )
            executions.append(self.run_due(
                manifest, code_sha=reference.code_sha, actor_id=actor_id, worker_id=worker_id,
                lease_duration=lease_duration, provider=provider, normalizer_for=normalizer_for,
                runtime_revision=reference.runtime_revision,
                before_action=before_action,
                maximum_attempts=None if maximum_attempts is None else max(
                    0, maximum_attempts - sum(len(item.attempt_ids) for item in executions),
                ),
            ))
            manifests.append(manifest)
        head = manifests[-1]
        generation = head.start_request.prospective_generation
        assert generation is not None
        contract = self._target_schedules.exact_contract(generation.target_definition_id)
        known_sessions = self._trading_sessions.available_from(
            exchange=generation.exchange, session_id=TradingSessionId(generation.decision_session_id), limit=512,
        )
        sessions = tuple(ProspectiveArchiveSession(
            item.session_id.value, item.exchange, item.session_date, item.open_at, item.close_at,
        ) for item in known_sessions)
        observed_at = self._database_clock.now()
        continuation = plan_continuation(head, contract=contract, sessions=sessions, observed_at=observed_at)
        gaps = [(session_id, "GENERATION_NOT_PREDECLARED")
                for session_id in continuation.missed_decision_session_ids]
        scan_limited = len(known_sessions) == 512 and continuation.blocked_reason is not None
        if continuation.blocked_decision_session_id is not None and not scan_limited:
            gaps.append((continuation.blocked_decision_session_id, "CALENDAR_INCOMPLETE"))
        for session_id, reason in gaps:
            request = RecordProspectivePlanningGapRequest(
                series_code=series_code, expected_generation=generation.generation + 1,
                predecessor_market_archive_id=generation.market_archive_id,
                target_definition_id=generation.target_definition_id,
                target_version=generation.target_version,
                target_definition_sha256=str(generation.target_definition_sha256),
                expected_decision_session_id=session_id, reason_code=reason,
            )
            def record_gap(claim: AttemptClaim, context: CommandContext,
                           gap_request: RecordProspectivePlanningGapRequest = request) -> object:
                return self._archives.record_prospective_planning_gap(gap_request, context, runtime_claim=claim)

            self._run_maintenance(
                head, code_sha=references[-1].code_sha,
                config_artifact_id=references[-1].config_artifact_id,
                operation="record_planning_gap", payload={"request": request},
                actor_id=actor_id, worker_id=worker_id, lease_duration=lease_duration,
                command=record_gap,
                runtime_revision=references[-1].runtime_revision,
                before_action=before_action,
            )
        new_generation_id = None
        if continuation.next_sessions is not None:
            if before_action is not None:
                before_action()
            codes: dict[UUID, str] = {}
            for item in head.slices:
                schedule = next(row for row in generation.schedules
                                if row.market_archive_slice_id == item.plan.market_archive_slice_id)
                code = BaoStockArchiveQuery.from_resource(item.capture_request.resource).code
                if code is None or (schedule.instrument_id in codes and codes[schedule.instrument_id] != code):
                    raise ProspectiveRuntimeIntegrityError("Frozen instrument Provider codes are inconsistent")
                codes[schedule.instrument_id] = code
            instruments = tuple(ProspectiveArchiveInstrument(
                member.instrument_id, member.instrument_identifier_id, codes[member.instrument_id],
            ) for member in generation.members)
            provenance = canonical_json_sha256({
                "predecessor": generation.market_archive_id,
                "predecessor_sha256": str(generation.content_sha256),
                "next_decision_session": continuation.next_sessions.decision.session_id,
                "code_sha": code_sha,
            })
            code_artifact = self._artifacts.publish(
                ('{"application":"market.prospective_continuity","code_sha":"' + code_sha + '"}').encode(),
                media_type="application/json",
                context=_context(f"prospective-continuity:code:{code_sha}", actor_id, "REGISTER_PROSPECTIVE_CODE"),
            )
            next_manifest = build_target_aligned_prospective_manifest(
                provider_product_id=head.start_request.provider_product_id,
                code_artifact_id=code_artifact.artifact_id, config_artifact_id=head.start_request.config_artifact_id,
                contract=contract, resolved_sessions=continuation.next_sessions, instruments=instruments,
                series_code=series_code, generation=generation.generation + 1,
                predecessor_market_archive_id=generation.market_archive_id,
                planned_not_before=self._database_clock.now(), provenance_sha256=provenance,
                reserved_free_bytes=head.start_request.reserved_free_bytes,
                maximum_archive_bytes=head.start_request.maximum_archive_bytes,
                maximum_slice_bytes=head.start_request.maximum_slice_bytes,
            )
            registration = self.predeclare(next_manifest, code_sha=code_sha, actor_id=actor_id,
                                           lease_duration=lease_duration, before_action=before_action,
                                           # Continuation is not an implicit Schedule upgrade.
                                           runtime_revision=references[-1].runtime_revision)
            new_generation_id = registration.market_archive_id
        return {"series_code": series_code, "observed_at": observed_at,
                "generation_ids": tuple(item.market_archive_id for item in references),
                "new_generation_id": new_generation_id, "planning_gaps": tuple(gaps),
                "blocked_reason": "CALENDAR_SCAN_LIMIT" if scan_limited else continuation.blocked_reason,
                "due_attempt_count": sum(len(item.attempt_ids) for item in executions),
                "executions": tuple(executions)}

    def _run_maintenance(
        self, manifest: ArchiveOperatorManifest, *, code_sha: str, config_artifact_id: UUID,
        operation: str, payload: dict[str, object], actor_id: str, worker_id: str,
        lease_duration: timedelta, command: Callable[[AttemptClaim, CommandContext], object],
        runtime_revision: int,
        before_action: Callable[[], None] | None = None,
    ) -> None:
        if before_action is not None:
            before_action()
        plan = compile_prospective_runtime_plan(manifest, code_sha=code_sha, runtime_revision=runtime_revision)
        request_hash = canonical_json_sha256({"archive_id": plan.market_archive_id,
                                             "operation": operation, "payload": payload})
        key = f"archive:{plan.market_archive_id}:maintenance:{operation}:{request_hash}"
        run_id = _id(f"run:{key}")
        run = ProspectiveRuntimeRunPlan(
            run_id=run_id, fire_key=key, requested_at=self._database_clock.now(),
            decision_time=None, window_start=None, window_end=None, schedule_slot=None,
            steps=(StepSpec(
                step_key=operation, step_kind="RECORD_EVIDENCE",
                implementation=f"{_IMPLEMENTATION}.{operation}", implementation_version="1",
                ordinal=1, required=True, request_hash=request_hash,
                input_evidence_hash=plan.config_sha256,
                retry_policy=RetryPolicy(max_attempts=3, backoff=(timedelta(0), timedelta(0)),
                                         retryable_codes=frozenset({"LEASE_EXPIRED"})),
                external_effect_class=ExternalEffectClass.NONE,
            ),), slices=(),
        )
        try:
            trace = self._runtime.inspect_run(run_id)
        except RuntimeNotFoundError:
            self._register_run(plan, run, config_artifact_id, actor_id)
        else:
            _verify_trace(plan, run, trace)
            if trace.run_state == "QUEUED":
                self._runtime.start_run(run_id, _context(f"prospective:{run_id}:start", actor_id,
                                                        "START_PROSPECTIVE_RUN"))
        if before_action is not None:
            before_action()
        self._runtime.recover_expired(actor_id=actor_id, reason_code="PROSPECTIVE_LEASE_RECOVERY", run_id=run_id)
        trace = self._runtime.inspect_run(run_id)
        if trace.run_state == "SUCCEEDED":
            return
        if before_action is not None:
            before_action()
        claim = self._runtime.claim_next(
            run_id=run_id, worker_id=worker_id, lease_duration=lease_duration,
            context=_context(f"{key}:claim:{len(trace.steps[0].attempt_states) + 1}", actor_id,
                             "CLAIM_PROSPECTIVE_MAINTENANCE", actor_type=ActorType.WORKER),
        )
        if claim is None:
            raise ProspectiveRuntimeIntegrityError("Prospective maintenance is not claimable")
        self._runtime.start_attempt(claim, _context(f"{key}:start:{claim.attempt_id}", actor_id,
                                                   "START_PROSPECTIVE_MAINTENANCE", actor_type=ActorType.WORKER))
        command(claim, _context(key, actor_id, "PROSPECTIVE_MAINTENANCE", actor_type=ActorType.WORKER))
        _require_step_succeeded(self._runtime, claim)

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
        elif (trace.run_state == "FAILED" and run in plan.capture_runs
              and any(step.state == "FAILED" for step in trace.steps)
              and all(
                  step.state == "SUCCEEDED"
                  or (step.state == "BLOCKED" and not step.attempt_states)
                  or (step.state == "READY" and not step.attempt_states
                      and step.deadline_at is not None
                      and step.deadline_at < self._database_clock.now())
                  or (step.state == "FAILED"
                      and step.attempt_states == ("FAILED_TERMINAL",)
                      and step.latest_attempt_error_code == "DEADLINE_EXHAUSTED")
                  for step in trace.steps
              )):
            # Read-only registration reconciliation after a missed window.
            # Never reopen the failed Run, retry a Provider, or hide an earlier
            # unknown effect behind a subsequent deadline failure.
            return
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
        before_action: Callable[[], None] | None = None,
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
        if before_action is not None:
            before_action()
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
