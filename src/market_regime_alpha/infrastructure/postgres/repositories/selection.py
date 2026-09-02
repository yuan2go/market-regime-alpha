"""PostgreSQL Authority adapter for Selection Core aggregates."""

from __future__ import annotations

from decimal import Decimal
from collections.abc import Iterable
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)
from market_regime_alpha.selection.domain import (
    CriterionOperator,
    CriterionResult,
    CriterionValueKind,
    EligibilityAssessmentDecision,
    EligibilityBatch,
    EligibilityPolicy,
    EligibilityReasonDecision,
    EligibilityRule,
    EligibilityRuleKind,
    EligibilityStatus,
    ExploratoryRetrospectiveSelectionScope,
    FrozenUniverse,
    MarketEvidenceStatus,
    MarketLineage,
    UniverseDefinition,
    UniverseMemberDecision,
    UniverseMembershipStatus,
    UniverseScopeSpecification,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash, InstrumentId
from market_regime_alpha.shared.time import DecisionTime


class PostgresSelectionRepository:
    """Persist exactly Universe and Eligibility; transaction stays in the UoW."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def register_universe(self, definition: UniverseDefinition) -> int:
        self._connection.execute(
            """
            INSERT INTO mra.universe (universe_id, universe_code, purpose)
            VALUES (%s, %s, %s)
            """,
            (
                definition.universe_id,
                definition.universe_code,
                definition.purpose,
            ),
        )
        return 1

    def register_eligibility_policy(self, policy: EligibilityPolicy) -> int:
        product = self._provider_product(policy.market_provider_product_id)
        self._validate_policy_capabilities(policy, product)
        self._connection.execute(
            """
            INSERT INTO mra.eligibility_policy (
                eligibility_policy_id, market_provider_product_id,
                policy_code, version, content_sha256, rule_count
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                policy.eligibility_policy_id,
                policy.market_provider_product_id,
                policy.policy_code,
                policy.version,
                policy.content_sha256,
                len(policy.rules),
            ),
        )
        self._execute_many(
            """
            INSERT INTO mra.eligibility_rule (
                eligibility_rule_id, eligibility_policy_id, rule_code,
                ordinal, rule_kind, measure_code, aggregation, window_value,
                window_unit, value_kind, operator, threshold_decimal,
                threshold_status, threshold_count, value_unit, missing_result
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, 'UNKNOWN'
            )
            """,
            (
                (
                    rule.eligibility_rule_id,
                    policy.eligibility_policy_id,
                    rule.rule_code,
                    rule.ordinal,
                    rule.rule_kind.value,
                    rule.measure_code,
                    rule.aggregation,
                    rule.window_value,
                    rule.window_unit,
                    rule.value_kind.value,
                    rule.operator.value,
                    rule.threshold_decimal,
                    rule.threshold_status,
                    rule.threshold_count,
                    rule.value_unit,
                )
                for rule in policy.rules
            ),
        )
        return policy.version

    def load_eligibility_policy(self, policy_id: UUID) -> EligibilityPolicy:
        row = self._connection.execute(
            """
            SELECT eligibility_policy_id, market_provider_product_id,
                   policy_code, version, content_sha256, rule_count
            FROM mra.eligibility_policy
            WHERE eligibility_policy_id = %s
            FOR SHARE
            """,
            (policy_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Eligibility policy {policy_id} does not exist")
        rules = tuple(
            _eligibility_rule(item)
            for item in self._connection.execute(
                """
                SELECT eligibility_rule_id, rule_code, ordinal, rule_kind,
                       measure_code, aggregation, window_value, window_unit,
                       value_kind, operator, threshold_decimal,
                       threshold_status, threshold_count, value_unit
                FROM mra.eligibility_rule
                WHERE eligibility_policy_id = %s
                ORDER BY ordinal
                """,
                (policy_id,),
            ).fetchall()
        )
        if len(rules) != int(row[5]):
            raise ArtifactIntegrityError("Eligibility policy rule count does not reconcile")
        policy = EligibilityPolicy(
            eligibility_policy_id=UUID(str(row[0])),
            market_provider_product_id=UUID(str(row[1])),
            policy_code=str(row[2]),
            version=int(row[3]),
            rules=rules,
        )
        if policy.content_sha256 != str(row[4]):
            raise ArtifactIntegrityError("Eligibility policy content hash does not match its rules")
        return policy

    def validate_and_lock_scope(
        self,
        *,
        universe_id: UUID,
        scope: UniverseScopeSpecification,
    ) -> int:
        universe = self._connection.execute(
            "SELECT universe_id FROM mra.universe WHERE universe_id = %s FOR UPDATE",
            (universe_id,),
        ).fetchone()
        if universe is None:
            raise RuntimeNotFoundError(f"Universe {universe_id} does not exist")
        product = self._provider_product(scope.market_provider_product_id)
        fact_kinds = set(product[0])
        required = {"INSTRUMENT", "CLASSIFICATION", "CLASSIFICATION_MEMBERSHIP"}
        if not required.issubset(fact_kinds):
            raise RuntimeStateConflictError("Universe scope provider product lacks canonical classification capabilities")
        artifact = self._connection.execute(
            """
            SELECT content_sha256, size_bytes,
                   mra.artifact_has_verified_integrity(
                       integrity_state, last_verified_at
                   )
            FROM mra.artifact
            WHERE artifact_id = %s
            FOR SHARE
            """,
            (scope.artifact_id,),
        ).fetchone()
        expected_hash = _content_hash_value(scope.content_sha256)
        if artifact is None:
            raise RuntimeNotFoundError(f"Universe scope Artifact {scope.artifact_id} does not exist")
        if str(artifact[0]) != expected_hash or int(artifact[1]) != scope.size_bytes or artifact[2] is not True:
            raise ArtifactIntegrityError("Universe scope Artifact identity or Foundation integrity does not match")
        expected_ids = tuple(item.value for item in scope.instrument_ids)
        if expected_ids:
            rows = self._connection.execute(
                """
                SELECT instrument_id
                FROM mra.instrument
                WHERE instrument_id = ANY(%s)
                FOR SHARE
                """,
                (list(expected_ids),),
            ).fetchall()
            if {UUID(str(row[0])) for row in rows} != set(expected_ids):
                raise RuntimeStateConflictError("Universe scope must contain existing canonical Instrument identities")
        row = self._connection.execute(
            """
            SELECT COALESCE(max(revision), 0) + 1
            FROM mra.universe_revision
            WHERE universe_id = %s
            """,
            (universe_id,),
        ).fetchone()
        if row is None:
            raise AssertionError("Universe revision query must return one row")
        return int(row[0])

    def insert_frozen_universe(
        self,
        *,
        universe_revision_id: UUID,
        universe_id: UUID,
        revision: int,
        decision_time: DecisionTime,
        scope: UniverseScopeSpecification,
        members: tuple[UniverseMemberDecision, ...],
    ) -> None:
        valid_time = self._connection.execute(
            "SELECT %s <= transaction_timestamp()",
            (decision_time.value,),
        ).fetchone()
        if valid_time is None or valid_time[0] is not True:
            raise RuntimeStateConflictError("Universe DecisionTime cannot be in the future")
        included = sum(member.membership_status is UniverseMembershipStatus.INCLUDED for member in members)
        excluded = sum(member.membership_status is UniverseMembershipStatus.EXCLUDED for member in members)
        unknown = sum(member.membership_status is UniverseMembershipStatus.UNKNOWN for member in members)
        if len(members) != included + excluded + unknown:
            raise AssertionError("Universe counts do not reconcile before persistence")
        self._connection.execute(
            """
            INSERT INTO mra.universe_revision (
                universe_revision_id, universe_id, revision, decision_time,
                scope_artifact_id, scope_content_sha256, scope_size_bytes,
                market_provider_product_id, classification_scheme,
                classification_code, total_count, included_count,
                excluded_count, unknown_count
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                universe_revision_id,
                universe_id,
                revision,
                decision_time.value,
                scope.artifact_id,
                _content_hash_value(scope.content_sha256),
                scope.size_bytes,
                scope.market_provider_product_id,
                scope.classification_scheme,
                scope.classification_code,
                len(members),
                included,
                excluded,
                unknown,
            ),
        )
        self._execute_many(
            """
            INSERT INTO mra.universe_member (
                universe_member_id, universe_revision_id, instrument_id,
                membership_status, evidence_status,
                observed_membership_status, classification_id,
                classification_membership_revision_id, source_gap_id,
                market_capture_id, market_decision_visible_at,
                reason_code, lineage_hash
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                (
                    member.universe_member_id,
                    universe_revision_id,
                    member.instrument_id.value,
                    member.membership_status.value,
                    member.evidence_status.value,
                    member.observed_membership_status,
                    member.classification_id,
                    member.membership_revision_id,
                    member.source_gap_id,
                    member.market_capture_id,
                    member.market_decision_visible_at,
                    member.reason_code,
                    member.lineage_hash,
                )
                for member in members
            ),
        )

    def bind_exploratory_retrospective_universe(
        self,
        universe_revision_id: UUID,
        scope: ExploratoryRetrospectiveSelectionScope,
    ) -> None:
        content_hash = canonical_json_sha256(
            {
                "evidence_lane": scope.evidence_lane,
                "knowledge_cutoff": scope.knowledge_cutoff,
                "market_archive_id": scope.market_archive_id,
                "market_archive_seal_id": scope.market_archive_seal_id,
                "scope_content_sha256": str(scope.content_sha256),
                "simulated_event_cutoff": scope.simulated_event_cutoff,
                "universe_revision_id": universe_revision_id,
            }
        )
        self._connection.execute(
            """
            INSERT INTO mra.exploratory_retrospective_universe_revision (
                universe_revision_id, market_archive_id,
                market_archive_seal_id, evidence_lane, knowledge_cutoff,
                simulated_event_cutoff, scope_content_sha256, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                universe_revision_id,
                scope.market_archive_id,
                scope.market_archive_seal_id,
                scope.evidence_lane,
                scope.knowledge_cutoff,
                scope.simulated_event_cutoff,
                str(scope.content_sha256),
                content_hash,
            ),
        )

    def bind_exploratory_retrospective_eligibility(
        self,
        *,
        universe: FrozenUniverse,
        eligibility_policy_id: UUID,
        scope: ExploratoryRetrospectiveSelectionScope,
        assessment_count: int,
    ) -> None:
        content_hash = canonical_json_sha256(
            {
                "assessment_count": assessment_count,
                "eligibility_policy_id": eligibility_policy_id,
                "evidence_lane": scope.evidence_lane,
                "knowledge_cutoff": scope.knowledge_cutoff,
                "market_archive_id": scope.market_archive_id,
                "market_archive_seal_id": scope.market_archive_seal_id,
                "scope_content_sha256": str(scope.content_sha256),
                "simulated_event_cutoff": scope.simulated_event_cutoff,
                "universe_revision_id": universe.universe_revision_id,
            }
        )
        self._connection.execute(
            """
            INSERT INTO mra.exploratory_retrospective_eligibility_batch (
                universe_revision_id, eligibility_policy_id,
                market_archive_id, market_archive_seal_id, evidence_lane,
                knowledge_cutoff, simulated_event_cutoff,
                scope_content_sha256, assessment_count, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                universe.universe_revision_id,
                eligibility_policy_id,
                scope.market_archive_id,
                scope.market_archive_seal_id,
                scope.evidence_lane,
                scope.knowledge_cutoff,
                scope.simulated_event_cutoff,
                str(scope.content_sha256),
                assessment_count,
                content_hash,
            ),
        )

    def require_exploratory_retrospective_universe_scope(
        self,
        universe_revision_id: UUID,
        scope: ExploratoryRetrospectiveSelectionScope,
    ) -> None:
        row = self._connection.execute(
            """
            SELECT market_archive_id, market_archive_seal_id, evidence_lane,
                   knowledge_cutoff, simulated_event_cutoff,
                   scope_content_sha256
            FROM mra.exploratory_retrospective_universe_revision
            WHERE universe_revision_id = %s
            FOR SHARE
            """,
            (universe_revision_id,),
        ).fetchone()
        expected = (
            scope.market_archive_id,
            scope.market_archive_seal_id,
            scope.evidence_lane,
            scope.knowledge_cutoff,
            scope.simulated_event_cutoff,
            str(scope.content_sha256),
        )
        if row is None or tuple(row) != expected:
            raise RuntimeStateConflictError(
                "retrospective Eligibility requires the exact Universe archive scope"
            )

    def require_exploratory_retrospective_eligibility_scope(
        self,
        *,
        universe_revision_id: UUID,
        eligibility_policy_id: UUID,
        scope: ExploratoryRetrospectiveSelectionScope,
    ) -> None:
        row = self._connection.execute(
            """
            SELECT market_archive_id, market_archive_seal_id, evidence_lane,
                   knowledge_cutoff, simulated_event_cutoff,
                   scope_content_sha256
            FROM mra.exploratory_retrospective_eligibility_batch
            WHERE universe_revision_id = %s
              AND eligibility_policy_id = %s
            FOR SHARE
            """,
            (universe_revision_id, eligibility_policy_id),
        ).fetchone()
        expected = (
            scope.market_archive_id,
            scope.market_archive_seal_id,
            scope.evidence_lane,
            scope.knowledge_cutoff,
            scope.simulated_event_cutoff,
            str(scope.content_sha256),
        )
        if row is None or tuple(row) != expected:
            raise RuntimeStateConflictError(
                "retrospective Eligibility archive scope does not reconcile"
            )

    def load_frozen_universe(
        self,
        universe_revision_id: UUID,
        *,
        result_hash: str,
        receipt_id: UUID,
        replayed: bool,
    ) -> FrozenUniverse:
        self._assert_receipt(
            receipt_id=receipt_id,
            aggregate_kind="UNIVERSE_REVISION",
            aggregate_id=str(universe_revision_id),
            result_hash=result_hash,
        )
        return self._load_frozen_universe(
            universe_revision_id,
            result_hash=result_hash,
            receipt_id=receipt_id,
            replayed=replayed,
            lock=False,
        )

    def lock_frozen_universe(self, universe_revision_id: UUID) -> FrozenUniverse:
        receipt = self._receipt_for(
            aggregate_kind="UNIVERSE_REVISION",
            aggregate_id=str(universe_revision_id),
        )
        return self._load_frozen_universe(
            universe_revision_id,
            result_hash=str(receipt[1]),
            receipt_id=UUID(str(receipt[0])),
            replayed=False,
            lock=True,
        )

    def insert_eligibility_assessments(
        self,
        *,
        universe: FrozenUniverse,
        policy: EligibilityPolicy,
        decision_time: DecisionTime,
        assessments: tuple[EligibilityAssessmentDecision, ...],
    ) -> None:
        member_identity = {(member.universe_member_id, member.instrument_id.value) for member in universe.members}
        assessment_identity = {(assessment.universe_member_id, assessment.instrument_id.value) for assessment in assessments}
        if member_identity != assessment_identity or len(assessments) != len(universe.members):
            raise RuntimeStateConflictError("Eligibility must assess every scoped Universe member exactly once")
        expected_rule_ids = {rule.eligibility_rule_id for rule in policy.rules}
        for assessment in assessments:
            if {reason.rule.eligibility_rule_id for reason in assessment.reasons} != expected_rule_ids:
                raise RuntimeStateConflictError("Eligibility assessment must persist every policy rule exactly once")
        self._validate_lineage(policy, assessments)
        for assessment in assessments:
            pass_count = sum(reason.criterion_result is CriterionResult.PASS for reason in assessment.reasons)
            fail_count = sum(reason.criterion_result is CriterionResult.FAIL for reason in assessment.reasons)
            unknown_count = sum(reason.criterion_result is CriterionResult.UNKNOWN for reason in assessment.reasons)
            self._connection.execute(
                """
                INSERT INTO mra.eligibility_assessment (
                    eligibility_assessment_id, universe_revision_id,
                    universe_member_id, eligibility_policy_id, instrument_id,
                    decision_time, result, rule_count, pass_count,
                    fail_count, unknown_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    assessment.eligibility_assessment_id,
                    universe.universe_revision_id,
                    assessment.universe_member_id,
                    policy.eligibility_policy_id,
                    assessment.instrument_id.value,
                    decision_time.value,
                    assessment.result.value,
                    len(assessment.reasons),
                    pass_count,
                    fail_count,
                    unknown_count,
                ),
            )
            self._execute_many(
                """
                INSERT INTO mra.eligibility_reason (
                    eligibility_reason_id, eligibility_assessment_id,
                    eligibility_policy_id, eligibility_rule_id,
                    criterion_result, observed_value_kind,
                    observed_decimal, observed_status, observed_count,
                    measure_code, aggregation, window_value, window_unit,
                    operator, threshold_decimal, threshold_status,
                    threshold_count, value_unit, reason_code,
                    market_fact_revision_ids, market_bar_revision_ids,
                    market_gap_ids, market_session_ids, market_capture_ids,
                    lineage_hash
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    _reason_insert_row(
                        assessment.eligibility_assessment_id,
                        policy.eligibility_policy_id,
                        reason,
                    )
                    for reason in assessment.reasons
                ),
            )

    def load_eligibility_batch(
        self,
        *,
        universe_revision_id: UUID,
        eligibility_policy_id: UUID,
        decision_time: DecisionTime,
        result_hash: str,
        receipt_id: UUID,
        replayed: bool,
    ) -> EligibilityBatch:
        aggregate_id = f"{universe_revision_id}:{eligibility_policy_id}"
        self._assert_receipt(
            receipt_id=receipt_id,
            aggregate_kind="ELIGIBILITY_BATCH",
            aggregate_id=aggregate_id,
            result_hash=result_hash,
        )
        policy = self.load_eligibility_policy(eligibility_policy_id)
        rows = self._connection.execute(
            """
            SELECT eligibility_assessment_id, universe_member_id,
                   instrument_id, result, rule_count, pass_count,
                   fail_count, unknown_count
            FROM mra.eligibility_assessment
            WHERE universe_revision_id = %s
              AND eligibility_policy_id = %s
              AND decision_time = %s
            ORDER BY instrument_id
            """,
            (universe_revision_id, eligibility_policy_id, decision_time.value),
        ).fetchall()
        assessments = tuple(self._assessment_from_row(row, policy) for row in rows)
        revision = self._connection.execute(
            """
            SELECT decision_time, total_count
            FROM mra.universe_revision
            WHERE universe_revision_id = %s
            """,
            (universe_revision_id,),
        ).fetchone()
        if revision is None:
            raise RuntimeNotFoundError(f"Universe revision {universe_revision_id} does not exist")
        if revision[0] != decision_time.value or len(assessments) != int(revision[1]):
            raise ArtifactIntegrityError("Eligibility batch does not cover its exact Universe DecisionTime scope")
        expected_hash = canonical_json_sha256(
            {
                "assessments": assessments,
                "decision_time": decision_time,
                "eligibility_policy_id": eligibility_policy_id,
                "universe_revision_id": universe_revision_id,
            }
        )
        if expected_hash != result_hash:
            raise ArtifactIntegrityError("Eligibility replay result hash does not reconcile")
        eligible = sum(item.result is EligibilityStatus.ELIGIBLE for item in assessments)
        ineligible = sum(item.result is EligibilityStatus.INELIGIBLE for item in assessments)
        unknown = sum(item.result is EligibilityStatus.UNKNOWN for item in assessments)
        return EligibilityBatch(
            universe_revision_id=universe_revision_id,
            eligibility_policy_id=eligibility_policy_id,
            decision_time=decision_time,
            assessments=assessments,
            total_count=len(assessments),
            eligible_count=eligible,
            ineligible_count=ineligible,
            unknown_count=unknown,
            result_hash=result_hash,
            receipt_id=receipt_id,
            replayed=replayed,
        )

    def _load_frozen_universe(
        self,
        universe_revision_id: UUID,
        *,
        result_hash: str,
        receipt_id: UUID,
        replayed: bool,
        lock: bool,
    ) -> FrozenUniverse:
        suffix = " FOR SHARE" if lock else ""
        row = self._connection.execute(
            """
            SELECT universe_revision_id, universe_id, revision, decision_time,
                   scope_content_sha256, total_count, included_count,
                   excluded_count, unknown_count
            FROM mra.universe_revision
            WHERE universe_revision_id = %s
            """
            + suffix,
            (universe_revision_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Universe revision {universe_revision_id} does not exist")
        members = tuple(
            _universe_member(item)
            for item in self._connection.execute(
                """
                SELECT universe_member_id, instrument_id, membership_status,
                       evidence_status, observed_membership_status,
                       classification_id,
                       classification_membership_revision_id, source_gap_id,
                       market_capture_id, market_decision_visible_at,
                       reason_code, lineage_hash
                FROM mra.universe_member
                WHERE universe_revision_id = %s
                ORDER BY instrument_id
                """,
                (universe_revision_id,),
            ).fetchall()
        )
        counts = (
            len(members),
            sum(member.membership_status is UniverseMembershipStatus.INCLUDED for member in members),
            sum(member.membership_status is UniverseMembershipStatus.EXCLUDED for member in members),
            sum(member.membership_status is UniverseMembershipStatus.UNKNOWN for member in members),
        )
        if counts != tuple(int(item) for item in row[5:9]):
            raise ArtifactIntegrityError("Persisted Universe counts do not reconcile")
        decision_time = DecisionTime(row[3])
        expected_hash = canonical_json_sha256(
            {
                "decision_time": decision_time,
                "members": members,
                "revision": int(row[2]),
                "scope_content_sha256": ContentHash(str(row[4])),
                "universe_id": UUID(str(row[1])),
                "universe_revision_id": UUID(str(row[0])),
            }
        )
        if expected_hash != result_hash:
            raise ArtifactIntegrityError("Frozen Universe replay result hash does not reconcile")
        return FrozenUniverse(
            universe_revision_id=UUID(str(row[0])),
            universe_id=UUID(str(row[1])),
            revision=int(row[2]),
            decision_time=decision_time,
            members=members,
            total_count=counts[0],
            included_count=counts[1],
            excluded_count=counts[2],
            unknown_count=counts[3],
            result_hash=result_hash,
            receipt_id=receipt_id,
            replayed=replayed,
        )

    def _assessment_from_row(
        self,
        row: tuple[Any, ...],
        policy: EligibilityPolicy,
    ) -> EligibilityAssessmentDecision:
        rules = {rule.eligibility_rule_id: rule for rule in policy.rules}
        reason_rows = self._connection.execute(
            """
            SELECT reason.eligibility_reason_id, reason.eligibility_rule_id,
                   reason.criterion_result, reason.observed_value_kind,
                   reason.observed_decimal, reason.observed_status,
                   reason.observed_count, reason.reason_code,
                   reason.market_fact_revision_ids,
                   reason.market_bar_revision_ids,
                   reason.market_gap_ids, reason.market_session_ids,
                   reason.market_capture_ids, reason.lineage_hash
            FROM mra.eligibility_reason AS reason
            JOIN mra.eligibility_rule AS rule
              ON rule.eligibility_policy_id = reason.eligibility_policy_id
             AND rule.eligibility_rule_id = reason.eligibility_rule_id
            WHERE reason.eligibility_assessment_id = %s
            ORDER BY rule.ordinal
            """,
            (row[0],),
        ).fetchall()
        reasons = tuple(_eligibility_reason(item, rules) for item in reason_rows)
        persisted_counts = (int(row[4]), int(row[5]), int(row[6]), int(row[7]))
        actual_counts = (
            len(reasons),
            sum(item.criterion_result is CriterionResult.PASS for item in reasons),
            sum(item.criterion_result is CriterionResult.FAIL for item in reasons),
            sum(item.criterion_result is CriterionResult.UNKNOWN for item in reasons),
        )
        if persisted_counts != actual_counts or len(reasons) != len(policy.rules):
            raise ArtifactIntegrityError("Eligibility reason counts do not reconcile")
        return EligibilityAssessmentDecision(
            eligibility_assessment_id=UUID(str(row[0])),
            universe_member_id=UUID(str(row[1])),
            instrument_id=InstrumentId.parse(row[2]),
            result=EligibilityStatus(str(row[3])),
            reasons=reasons,
        )

    def _validate_lineage(
        self,
        policy: EligibilityPolicy,
        assessments: tuple[EligibilityAssessmentDecision, ...],
    ) -> None:
        lineages = tuple(reason.lineage for assessment in assessments for reason in assessment.reasons)
        expected = {
            "mra.instrument_fact_revision": {value for lineage in lineages for value in lineage.fact_revision_ids},
            "mra.market_bar_revision": {value for lineage in lineages for value in lineage.bar_revision_ids},
            "mra.source_gap": {value for lineage in lineages for value in lineage.gap_ids},
        }
        for table, values in expected.items():
            if not values:
                continue
            identity_column = {
                "mra.instrument_fact_revision": "fact_revision_id",
                "mra.market_bar_revision": "bar_revision_id",
                "mra.source_gap": "gap_id",
            }[table]
            rows = self._connection.execute(
                f"""
                SELECT {identity_column}
                FROM {table}
                WHERE {identity_column} = ANY(%s)
                  AND provider_product_id = %s
                FOR SHARE
                """,
                (list(values), policy.market_provider_product_id),
            ).fetchall()
            if {UUID(str(row[0])) for row in rows} != values:
                raise ArtifactIntegrityError("Eligibility Market lineage does not match its provider product")
        sessions = {value for lineage in lineages for value in lineage.session_ids}
        if sessions:
            rows = self._connection.execute(
                """
                SELECT session.session_id
                FROM mra.trading_session AS session
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = session.source_capture_id
                WHERE session.session_id = ANY(%s)
                  AND capture.provider_product_id = %s
                FOR SHARE OF session
                """,
                (list(sessions), policy.market_provider_product_id),
            ).fetchall()
            if {UUID(str(row[0])) for row in rows} != sessions:
                raise ArtifactIntegrityError("Eligibility session lineage does not match its provider product")
        captures = {value for lineage in lineages for value in lineage.capture_ids}
        if captures:
            rows = self._connection.execute(
                """
                SELECT capture_id
                FROM mra.data_capture
                WHERE capture_id = ANY(%s)
                  AND provider_product_id = %s
                FOR SHARE
                """,
                (list(captures), policy.market_provider_product_id),
            ).fetchall()
            if {UUID(str(row[0])) for row in rows} != captures:
                raise ArtifactIntegrityError("Eligibility capture lineage does not match its provider product")

    def _provider_product(self, provider_product_id: UUID) -> tuple[Any, ...]:
        row = self._connection.execute(
            """
            SELECT fact_kinds, instrument_fact_kinds,
                   bar_timeframes, price_bases
            FROM mra.provider_product
            WHERE provider_product_id = %s
            FOR SHARE
            """,
            (provider_product_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Market provider product {provider_product_id} does not exist")
        return tuple(row)

    def _execute_many(
        self,
        query: str,
        params: Iterable[tuple[object, ...]],
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.executemany(query, params)

    @staticmethod
    def _validate_policy_capabilities(
        policy: EligibilityPolicy,
        product: tuple[Any, ...],
    ) -> None:
        fact_kinds = set(product[0])
        instrument_fact_kinds = set(product[1])
        required_fact_kinds = {"INSTRUMENT", "INSTRUMENT_FACT"}
        required_instrument_facts = {
            {
                EligibilityRuleKind.NOT_SUSPENDED: "SECURITY_STATUS",
                EligibilityRuleKind.NOT_SPECIAL_TREATMENT: "SPECIAL_TREATMENT_STATUS",
                EligibilityRuleKind.MIN_LISTING_AGE: "LISTING_STATUS",
                EligibilityRuleKind.MIN_LIQUIDITY: None,
                EligibilityRuleKind.LIMIT_METADATA_PRESENT: "LIMIT_UP_PRICE",
            }[rule.rule_kind]
            for rule in policy.rules
        }
        required_instrument_facts.discard(None)
        if any(rule.rule_kind is EligibilityRuleKind.LIMIT_METADATA_PRESENT for rule in policy.rules):
            required_instrument_facts.update({"LIMIT_UP_PRICE", "LIMIT_DOWN_PRICE", "REFERENCE_PRICE"})
        if any(
            rule.rule_kind
            in {
                EligibilityRuleKind.NOT_SUSPENDED,
                EligibilityRuleKind.LIMIT_METADATA_PRESENT,
                EligibilityRuleKind.MIN_LIQUIDITY,
            }
            for rule in policy.rules
        ):
            required_fact_kinds.add("TRADING_SESSION")
        if any(rule.rule_kind is EligibilityRuleKind.MIN_LIQUIDITY for rule in policy.rules):
            required_fact_kinds.add("MARKET_BAR")
            if "DAILY" not in set(product[2]) or "RAW_UNADJUSTED" not in set(product[3]):
                raise RuntimeStateConflictError("Liquidity policy requires canonical DAILY RAW_UNADJUSTED bars")
        if not required_fact_kinds.issubset(fact_kinds) or not required_instrument_facts.issubset(instrument_fact_kinds):
            raise RuntimeStateConflictError("Eligibility policy requires unavailable canonical Market facts")

    def _receipt_for(self, *, aggregate_kind: str, aggregate_id: str):
        row = self._connection.execute(
            """
            SELECT receipt_id, result_hash
            FROM mra.command_receipt
            WHERE status = 'SUCCEEDED'
              AND result_aggregate_kind = %s
              AND result_aggregate_id = %s
            ORDER BY completed_at, receipt_id
            LIMIT 1
            """,
            (aggregate_kind, aggregate_id),
        ).fetchone()
        if row is None:
            raise ArtifactIntegrityError(f"{aggregate_kind} {aggregate_id} has no successful receipt")
        return row

    def _assert_receipt(
        self,
        *,
        receipt_id: UUID,
        aggregate_kind: str,
        aggregate_id: str,
        result_hash: str,
    ) -> None:
        row = self._connection.execute(
            """
            SELECT 1
            FROM mra.command_receipt
            WHERE receipt_id = %s
              AND status = 'SUCCEEDED'
              AND result_aggregate_kind = %s
              AND result_aggregate_id = %s
              AND result_hash = %s
            """,
            (receipt_id, aggregate_kind, aggregate_id, result_hash),
        ).fetchone()
        if row is None:
            raise ArtifactIntegrityError("Selection replay receipt identity does not match")


def _eligibility_rule(row: tuple[Any, ...]) -> EligibilityRule:
    return EligibilityRule(
        eligibility_rule_id=UUID(str(row[0])),
        rule_code=str(row[1]),
        ordinal=int(row[2]),
        rule_kind=EligibilityRuleKind(str(row[3])),
        measure_code=str(row[4]),
        aggregation=str(row[5]),
        window_value=int(row[6]),
        window_unit=str(row[7]),
        value_kind=CriterionValueKind(str(row[8])),
        operator=CriterionOperator(str(row[9])),
        threshold_decimal=Decimal(row[10]) if row[10] is not None else None,
        threshold_status=str(row[11]) if row[11] is not None else None,
        threshold_count=int(row[12]) if row[12] is not None else None,
        value_unit=str(row[13]),
    )


def _universe_member(row: tuple[Any, ...]) -> UniverseMemberDecision:
    return UniverseMemberDecision(
        universe_member_id=UUID(str(row[0])),
        instrument_id=InstrumentId.parse(row[1]),
        membership_status=UniverseMembershipStatus(str(row[2])),
        evidence_status=MarketEvidenceStatus(str(row[3])),
        observed_membership_status=str(row[4]) if row[4] is not None else None,
        classification_id=UUID(str(row[5])) if row[5] is not None else None,
        membership_revision_id=UUID(str(row[6])) if row[6] is not None else None,
        source_gap_id=UUID(str(row[7])) if row[7] is not None else None,
        market_capture_id=UUID(str(row[8])) if row[8] is not None else None,
        market_decision_visible_at=row[9],
        reason_code=str(row[10]),
        lineage_hash=str(row[11]),
    )


def _eligibility_reason(
    row: tuple[Any, ...],
    rules: dict[UUID, EligibilityRule],
) -> EligibilityReasonDecision:
    rule_id = UUID(str(row[1]))
    try:
        rule = rules[rule_id]
    except KeyError as error:
        raise ArtifactIntegrityError("Eligibility reason references an unknown rule") from error
    lineage = MarketLineage(
        fact_revision_ids=tuple(UUID(str(item)) for item in row[8]),
        bar_revision_ids=tuple(UUID(str(item)) for item in row[9]),
        gap_ids=tuple(UUID(str(item)) for item in row[10]),
        session_ids=tuple(UUID(str(item)) for item in row[11]),
        capture_ids=tuple(UUID(str(item)) for item in row[12]),
    )
    if lineage.content_sha256 != str(row[13]):
        raise ArtifactIntegrityError("Eligibility reason lineage hash does not match")
    return EligibilityReasonDecision(
        eligibility_reason_id=UUID(str(row[0])),
        rule=rule,
        criterion_result=CriterionResult(str(row[2])),
        observed_value_kind=CriterionValueKind(str(row[3])),
        observed_decimal=Decimal(row[4]) if row[4] is not None else None,
        observed_status=str(row[5]) if row[5] is not None else None,
        observed_count=int(row[6]) if row[6] is not None else None,
        reason_code=str(row[7]),
        lineage=lineage,
    )


def _reason_insert_row(
    assessment_id: UUID,
    policy_id: UUID,
    reason: EligibilityReasonDecision,
) -> tuple[object, ...]:
    rule = reason.rule
    lineage = reason.lineage
    return (
        reason.eligibility_reason_id,
        assessment_id,
        policy_id,
        rule.eligibility_rule_id,
        reason.criterion_result.value,
        reason.observed_value_kind.value,
        reason.observed_decimal,
        reason.observed_status,
        reason.observed_count,
        rule.measure_code,
        rule.aggregation,
        rule.window_value,
        rule.window_unit,
        rule.operator.value,
        rule.threshold_decimal,
        rule.threshold_status,
        rule.threshold_count,
        rule.value_unit,
        reason.reason_code,
        list(lineage.fact_revision_ids),
        list(lineage.bar_revision_ids),
        list(lineage.gap_ids),
        list(lineage.session_ids),
        list(lineage.capture_ids),
        lineage.content_sha256,
    )


def _content_hash_value(value: ContentHash | str) -> str:
    return value.value if isinstance(value, ContentHash) else value


__all__ = ["PostgresSelectionRepository"]
