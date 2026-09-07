"""One repeatable-read operational view of explicit prospective Authority rows."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import fields
from typing import Any

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.market.domain.archive import (
    ArchiveCaptureObservation, ArchiveLane, ArchiveObservationRelation,
    ArchiveObservationTimeliness, ArchiveSliceStatus, MarketArchive, MarketArchiveSlice,
)
from market_regime_alpha.market.domain import BarTimeframe, PriceBasis
from market_regime_alpha.market.domain.prospective_archive import (
    ProspectiveArchiveGenerationPlan, ProspectiveArchiveMemberPlan,
    ProspectiveArchivePlanningGap, ProspectiveArchiveScheduleSlot, ProspectiveArchiveSliceSchedulePlan,
)
from market_regime_alpha.market.domain.prospective_health import ProspectiveHealthSlice, project_prospective_health
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.hashing import canonical_json_sha256


def _arguments(model: Any, row: dict[str, Any]) -> dict[str, Any]:
    """Use existing concrete dataclass contracts, including their content hashes."""
    return {field.name: row[field.name] for field in fields(model) if field.init}


def _group(rows: list[dict[str, Any]], key: str) -> dict[Any, list[dict[str, Any]]]:
    result: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        result[row[key]].append(row)
    return result


def _bounded_rows(cursor: Any, statement: str, parameters: tuple[Any, ...], maximum_rows: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = cursor.execute(statement + " LIMIT %s", (*parameters, maximum_rows + 1)).fetchall()
    if len(rows) > maximum_rows:
        raise ValueError("health canonical child roster exceeds the explicit row budget; no truncation is permitted")
    return rows


class PostgresProspectiveHealthReadPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def inspect(self, series_code: str, *, maximum_slices: int = 100_000) -> dict[str, Any]:
        if not series_code or len(series_code) > 100:
            raise ValueError("health series_code is invalid")
        if type(maximum_slices) is not int or not 1 <= maximum_slices <= 100_000:
            raise ValueError("health slice budget must be an integer from 1 to 100000")
        with self._pool.connection(read_only=True) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            with connection.cursor(row_factory=dict_row) as cursor:
                identity = cursor.execute("""
                    SELECT current_database() AS name, oid::bigint AS oid,
                           (pg_control_system()).system_identifier::text AS cluster_identity,
                           pg_get_userbyid(datdba) AS owner, clock_timestamp() AS observed_at
                    FROM pg_database WHERE datname=current_database()
                """).fetchone()
                assert identity is not None
                clock = identity.pop("observed_at")
                generations = _bounded_rows(cursor, "SELECT * FROM mra.prospective_archive_generation WHERE series_code=%s ORDER BY generation", (series_code,), maximum_slices)
                if not generations:
                    raise ValueError("health series has no canonical prospective generation")
                if sum(g["schedule_count"] for g in generations) > maximum_slices:
                    raise ValueError("health expected slice roster exceeds the explicit budget")
                ids = [g["market_archive_id"] for g in generations]
                roots = _bounded_rows(cursor, "SELECT * FROM mra.market_archive WHERE market_archive_id=ANY(%s::uuid[])", (ids,), maximum_slices)
                members = _bounded_rows(cursor, "SELECT * FROM mra.prospective_archive_generation_member WHERE market_archive_id=ANY(%s::uuid[]) ORDER BY market_archive_id,ordinal", (ids,), maximum_slices)
                schedules = _bounded_rows(cursor, "SELECT * FROM mra.prospective_archive_slice_schedule WHERE market_archive_id=ANY(%s::uuid[]) ORDER BY market_archive_id,ordinal", (ids,), maximum_slices)
                slices = _bounded_rows(cursor, "SELECT * FROM mra.market_archive_slice WHERE market_archive_id=ANY(%s::uuid[]) ORDER BY market_archive_id,ordinal", (ids,), maximum_slices)
                observations = _bounded_rows(cursor, """
                    SELECT observation.*, capture.status AS capture_status,
                           artifact.artifact_id, artifact.content_sha256 AS physical_reference_sha256,
                           artifact.size_bytes AS physical_reference_size, artifact.integrity_state
                    FROM mra.market_archive_capture_observation observation
                    LEFT JOIN mra.data_capture capture USING(capture_id)
                    LEFT JOIN mra.artifact artifact ON artifact.artifact_id=capture.artifact_id
                    WHERE observation.market_archive_id=ANY(%s::uuid[])
                    ORDER BY observation.market_archive_slice_id, observation.observation_ordinal
                """, (ids,), maximum_slices * 3)
                terminals = _bounded_rows(cursor, "SELECT * FROM mra.prospective_archive_slice_terminal WHERE market_archive_id=ANY(%s::uuid[])", (ids,), maximum_slices)
                revisions = _bounded_rows(cursor, "SELECT * FROM mra.prospective_archive_revision_observation WHERE market_archive_id=ANY(%s::uuid[]) ORDER BY comparison_ordinal", (ids,), maximum_slices * 3)
                gaps = _bounded_rows(cursor, """
                    SELECT binding.*, gap.gap_kind, gap.reason_code, gap.recorded_at AS source_gap_recorded_at
                    FROM mra.market_archive_slice_gap binding LEFT JOIN mra.source_gap gap USING(gap_id)
                    WHERE binding.market_archive_id=ANY(%s::uuid[])
                """, (ids,), maximum_slices)
                resources = _bounded_rows(cursor, "SELECT * FROM mra.market_archive_resource_stop WHERE market_archive_id=ANY(%s::uuid[])", (ids,), maximum_slices)
                planning_gaps = _bounded_rows(cursor, "SELECT * FROM mra.prospective_archive_planning_gap WHERE series_code=%s ORDER BY expected_generation,detected_at", (series_code,), maximum_slices)
                runs = _bounded_rows(cursor, """
                    SELECT run.*, artifact.content_sha256 AS config_artifact_sha256
                    FROM mra.runtime_run run LEFT JOIN mra.artifact artifact ON artifact.artifact_id=run.config_artifact_id
                    WHERE run.fire_key LIKE ANY(%s::text[])
                """, ([f"archive:{archive_id}:%" for archive_id in ids],), maximum_slices * 2)
                run_ids = [run["run_id"] for run in runs]
                steps = _bounded_rows(cursor, "SELECT * FROM mra.runtime_step WHERE run_id=ANY(%s::uuid[]) ORDER BY ordinal", (run_ids,), maximum_slices * 2)
                attempts = _bounded_rows(cursor, "SELECT * FROM mra.runtime_attempt WHERE step_id=ANY(%s::uuid[]) ORDER BY step_id,attempt_no", ([s["step_id"] for s in steps],), maximum_slices * 6)
        try:
            return self._project(identity, clock, series_code, generations, roots, members, schedules, slices,
                                 observations, terminals, revisions, gaps, resources, planning_gaps, runs, steps, attempts)
        except (KeyError, TypeError, ValueError) as exc:
            raise ArtifactIntegrityError("prospective health canonical root/roster does not reconcile") from exc

    @staticmethod
    def _project(database: dict[str, Any], clock: Any, series_code: str, generations: list[dict[str, Any]],
                 roots: list[dict[str, Any]], members: list[dict[str, Any]], schedules: list[dict[str, Any]],
                 slices: list[dict[str, Any]], observations: list[dict[str, Any]], terminals: list[dict[str, Any]],
                 revisions: list[dict[str, Any]], gaps: list[dict[str, Any]], resources: list[dict[str, Any]],
                 planning_gaps: list[dict[str, Any]], runs: list[dict[str, Any]], steps: list[dict[str, Any]],
                 attempts: list[dict[str, Any]]) -> dict[str, Any]:
        root_by_id = {r["market_archive_id"]: r for r in roots}
        members_by_archive = _group(members, "market_archive_id")
        schedules_by_archive = _group(schedules, "market_archive_id")
        slices_by_archive = _group(slices, "market_archive_id")
        schedule_by_slice = {s["market_archive_slice_id"]: s for s in schedules}
        predecessor = None
        for ordinal, g in enumerate(generations, 1):
            archive_id = g["market_archive_id"]
            if g["generation"] != ordinal or g["predecessor_market_archive_id"] != predecessor:
                raise ValueError("generation chain is incomplete")
            predecessor = archive_id
            root = root_by_id[archive_id]
            typed_members = tuple(ProspectiveArchiveMemberPlan(**_arguments(ProspectiveArchiveMemberPlan, r)) for r in members_by_archive[archive_id])
            typed_schedule = tuple(ProspectiveArchiveSliceSchedulePlan(**_arguments(ProspectiveArchiveSliceSchedulePlan, {**r, "slot": ProspectiveArchiveScheduleSlot(r["schedule_slot"])})) for r in schedules_by_archive[archive_id])
            typed_generation = ProspectiveArchiveGenerationPlan(**_arguments(ProspectiveArchiveGenerationPlan, {
                **g, "exchange": g["exchange_code"], "members": typed_members, "schedules": typed_schedule,
            }))
            for key in ("content_sha256", "member_roster_sha256", "schedule_roster_sha256"):
                if str(getattr(typed_generation, key)) != g[key]:
                    raise ValueError("generation content hash differs")
            if len(typed_members) != g["member_count"] or len(typed_schedule) != g["schedule_count"]:
                raise ValueError("generation roster count differs")
            for typed_member, saved in zip(typed_members, members_by_archive[archive_id], strict=True):
                if str(typed_member.content_sha256) != saved["content_sha256"]:
                    raise ValueError("member content differs")
            for typed_slot, saved in zip(typed_schedule, schedules_by_archive[archive_id], strict=True):
                if str(typed_slot.content_sha256) != saved["content_sha256"]:
                    raise ValueError("schedule content differs")
            typed_slices = tuple(MarketArchiveSlice(**_arguments(MarketArchiveSlice, {**s, "status": ArchiveSliceStatus.PLANNED})) for s in slices_by_archive[archive_id])
            if {s.market_archive_slice_id for s in typed_slices} != {s.market_archive_slice_id for s in typed_schedule}:
                raise ValueError("scheduled slice roster differs")
            archive = MarketArchive(**_arguments(MarketArchive, {
                **root, "lane": ArchiveLane(root["lane"]), "timeframe": BarTimeframe(root["timeframe"]),
                "price_basis": PriceBasis(root["price_basis"]), "slices": typed_slices,
            }))
            if archive.lane is not ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS or archive.slice_count != root["slice_count"]:
                raise ValueError("root prospective scope differs")
            for key in ("content_sha256", "slice_roster_sha256"):
                if str(getattr(archive, key)) != root[key]:
                    raise ValueError("archive root hash differs")
            if any(str(typed.content_sha256) != saved["content_sha256"] for typed, saved in zip(typed_slices, slices_by_archive[archive_id], strict=True)):
                raise ValueError("slice hash differs")
        run_by_key = {r["fire_key"]: r for r in runs}
        if len(run_by_key) != len(runs):
            raise ValueError("ambiguous Runtime scope")
        for g in generations:
            predeclare = run_by_key[f"archive:{g['market_archive_id']}:predeclare"]
            if predeclare["runtime_mode"] != "PROSPECTIVE" or predeclare["config_hash"] != predeclare["config_artifact_sha256"]:
                raise ValueError("generation Runtime binding differs")
        slice_archive = {s["market_archive_slice_id"]: s["market_archive_id"] for s in slices}
        for child in (*observations, *terminals, *revisions, *gaps, *resources):
            if slice_archive.get(child["market_archive_slice_id"]) != child["market_archive_id"]:
                raise ValueError("health child belongs to a foreign or missing expected slice")
        for gap in gaps:
            if gap["gap_kind"] is None or gap["reason_code"] is None:
                raise ValueError("health SourceGap binding is unresolved")
        for gap in planning_gaps:
            typed_gap = ProspectiveArchivePlanningGap(**_arguments(ProspectiveArchivePlanningGap, gap))
            if str(typed_gap.content_sha256) != gap["content_sha256"]:
                raise ValueError("planning gap hash differs")
        observations_by_slice = _group(observations, "market_archive_slice_id")
        revisions_by_slice = _group(revisions, "market_archive_slice_id")
        terminal_by_slice = {t["market_archive_slice_id"]: t for t in terminals}
        gaps_by_slice = _group(gaps, "market_archive_slice_id")
        resources_by_slice = _group(resources, "market_archive_slice_id")
        attempts_by_step = _group(attempts, "step_id")
        step_by_key = {(s["run_id"], s["step_key"]): s for s in steps}
        facts = []
        projected_slices = []
        for s in slices:
            slice_id = s["market_archive_slice_id"]
            schedule = schedule_by_slice[slice_id]
            fire_key = (f"archive:{s['market_archive_id']}:capture:{schedule['schedule_slot'].lower()}:"
                        f"{s['event_window_start'].isoformat()}:{s['event_window_end'].isoformat()}")
            run = run_by_key[fire_key]
            predeclare = run_by_key[f"archive:{s['market_archive_id']}:predeclare"]
            step = step_by_key[(run["run_id"], f"capture-{s['ordinal']:04d}")]
            if (run["runtime_mode"] != "PROSPECTIVE" or run["config_hash"] != run["config_artifact_sha256"]
                or step["input_evidence_hash"] != run["config_hash"] or step["step_kind"] != "CAPTURE"
                or any(run[key] != predeclare[key] for key in ("code_sha", "config_artifact_id", "config_hash", "schedule_id"))):
                raise ValueError("slice Runtime binding differs")
            observed = observations_by_slice[slice_id]
            for index, observation in enumerate(observed, 1):
                typed_observation = ArchiveCaptureObservation(**_arguments(ArchiveCaptureObservation, {
                    **observation, "relation": ArchiveObservationRelation(observation["relation"]),
                    "timeliness": ArchiveObservationTimeliness(observation["timeliness"]),
                }))
                if str(typed_observation.content_sha256) != observation["content_sha256"] or observation["observation_ordinal"] != index:
                    raise ValueError("observation content/roster differs")
                if observation["previous_observation_id"] != (observed[index-2]["market_archive_capture_observation_id"] if index > 1 else None):
                    raise ValueError("observation previous identity differs")
                if observation["capture_status"] != "CAPTURED" or observation["artifact_sha256"] != observation["physical_reference_sha256"] or observation["artifact_size_bytes"] != observation["physical_reference_size"]:
                    raise ValueError("Capture/Artifact references differ")
            terminal = terminal_by_slice.get(slice_id)
            state = terminal["terminal_state"] if terminal else None
            if terminal and canonical_json_sha256({k: terminal[k] for k in ("market_archive_id", "market_archive_slice_id", "terminal_state", "reason_code", "terminal_at")}) != terminal["content_sha256"]:
                raise ValueError("terminal hash differs")
            if state in {"CAPTURED_ON_TIME", "CAPTURED_LATE"} and not observed:
                raise ValueError("successful terminal lacks observation")
            if state in {"CAPTURED_ON_TIME", "CAPTURED_LATE"} and observed[0]["timeliness"] != ("ON_TIME" if state == "CAPTURED_ON_TIME" else "LATE"):
                raise ValueError("terminal timeliness differs from canonical observation")
            if terminal is None and (observed or gaps_by_slice[slice_id] or resources_by_slice[slice_id]):
                raise ValueError("completed slice effect lacks its atomic terminal fact")
            if state in {"PROVIDER_GAP", "FAILED"} and not gaps_by_slice[slice_id]:
                raise ValueError("failed terminal lacks gap")
            if state == "RESOURCE_STOP" and not resources_by_slice[slice_id]:
                raise ValueError("resource terminal lacks stop")
            scoped_revisions = revisions_by_slice[slice_id]
            if {r["market_archive_capture_observation_id"] for r in scoped_revisions} != {o["market_archive_capture_observation_id"] for o in observed}:
                raise ValueError("prospective observation/revision roster differs")
            for revision in scoped_revisions:
                payload = {k: revision[k] for k in (
                    "artifact_sha256", "comparison_ordinal", "instrument_id", "market_archive_capture_observation_id",
                    "market_archive_id", "market_archive_slice_id", "target_checkpoint_id", "normalized_revision_roster_sha256",
                    "predecessor_observation_id", "relation",
                )}
                if canonical_json_sha256(payload) != revision["content_sha256"]:
                    raise ValueError("revision content differs")
            scoped_attempts = attempts_by_step[step["step_id"]]
            latest = scoped_attempts[-1] if scoped_attempts else {}
            fact = ProspectiveHealthSlice(
                market_archive_id=s["market_archive_id"], market_archive_slice_id=slice_id,
                window_start=s["event_window_start"], window_end=s["event_window_end"], terminal_state=state,
                observation_count=len(observed), first_observed_at=observed[0]["observed_at"] if observed else None,
                latest_observed_at=observed[-1]["observed_at"] if observed else None,
                latest_known_at=observed[-1]["known_at"] if observed else None,
                latest_revision_observed_at=max((r["observed_at"] for r in revisions_by_slice[slice_id]), default=None),
                latest_attempt_state=latest.get("state"), latest_attempt_error_code=latest.get("error_code"),
                latest_attempt_lease_until=latest.get("lease_until"), runtime_state=run["state"],
            )
            facts.append(fact)
            projected_slices.append({
                **s, "schedule": schedule, "terminal": terminal, "observations": observed,
                "revisions": revisions_by_slice[slice_id], "source_gaps": gaps_by_slice[slice_id],
                "resource_stops": resources_by_slice[slice_id], "runtime_run_id": run["run_id"],
                "runtime_state": run["state"], "runtime_step_id": step["step_id"], "step_state": step["state"],
                "attempts": scoped_attempts,
            })
        return {
            "database": database, "observed_at": clock, "series_code": series_code,
            "authority": "NON_AUTHORITATIVE_OPERATIONAL_HEALTH_PROJECTION",
            "owner_reconciliation": "NOT_PERFORMED", "artifact_physical_verification": "NOT_PERFORMED",
            "root_and_roster_integrity": "MATCHED", "generations": generations,
            "slices": projected_slices, "planning_gaps": planning_gaps,
            "summary": project_prospective_health(observed_at=clock, slices=tuple(facts), planning_gap_count=len(planning_gaps)),
            "rate_scope": "ALL_OPENED_EXPECTED_WINDOWS_IN_THE_EXPLICIT_SERIES",
            "research_maturity": "NOT_ASSESSED",
        }
