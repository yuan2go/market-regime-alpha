"""Bounded read-only accounting over frozen Backtest members and owner facts."""

from collections import defaultdict
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.domain.backtest_diagnostics import (
    FunnelArm, FunnelCell, FunnelMember, FunnelMetricInput, FunnelOutcomeGap, FunnelSnapshot, FunnelTraining,
)


_CELLS_SQL = """
SELECT af.exploratory_backtest_arm_id AS arm_id,
       fs.exploratory_backtest_fold_id AS fold_id,
       fs.exploratory_backtest_fold_session_id AS session_id,
       fs.session_date, fs.session_role,
       b.dataset_id, decision.decision_run_id,
       d.available_cell_count, d.missing_cell_count, d.unknown_cell_count,
       d.stale_cell_count, d.conflict_cell_count
FROM mra.backtest_arm_fold af
JOIN mra.exploratory_backtest_fold_session fs
  ON fs.exploratory_backtest_fold_id=af.exploratory_backtest_fold_id
LEFT JOIN mra.exploratory_backtest_dataset b
  ON b.exploratory_backtest_run_id=af.exploratory_backtest_run_id
 AND b.exploratory_backtest_arm_id=af.exploratory_backtest_arm_id
 AND b.exploratory_backtest_fold_session_id=fs.exploratory_backtest_fold_session_id
LEFT JOIN mra.dataset d USING(dataset_id)
LEFT JOIN mra.exploratory_retrospective_decision_run decision
  ON decision.dataset_id=b.dataset_id
WHERE af.exploratory_backtest_run_id=%s AND fs.session_role IN ('FIT_INPUT','EVALUATION')
ORDER BY af.ordinal,fs.ordinal
"""

_MEMBERS_SQL = """
SELECT b.exploratory_backtest_arm_id AS arm_id,
       b.exploratory_backtest_fold_session_id AS session_id,
       sample.instrument_id, um.membership_status,
       ea.eligibility_assessment_id,ea.result,
       ca.candidate_id,ca.disposition,ca.reason_code,dr.decision_run_id
FROM mra.exploratory_backtest_dataset b
JOIN mra.dataset d USING(dataset_id)
JOIN mra.backtest_sample_member sample
 ON sample.exploratory_backtest_run_id=b.exploratory_backtest_run_id
LEFT JOIN mra.universe_member um
 ON um.universe_revision_id=d.universe_revision_id AND um.instrument_id=sample.instrument_id
LEFT JOIN mra.eligibility_assessment ea
 ON ea.universe_member_id=um.universe_member_id AND ea.eligibility_policy_id=d.eligibility_policy_id
LEFT JOIN mra.decision_run dr ON dr.dataset_id=d.dataset_id
LEFT JOIN mra.candidate ca ON ca.candidate_set_id=dr.candidate_set_id AND ca.instrument_id=sample.instrument_id
WHERE b.exploratory_backtest_run_id=%s
ORDER BY b.exploratory_backtest_arm_id,b.exploratory_backtest_fold_session_id,sample.ordinal
"""

# Each relation is read independently: no multiplicative joins between stages.
_MEMBER_FACTS_SQL = """
SELECT 'Feature' kind, c.candidate_id owner, c.raw_status state,c.raw_reason_code reason
FROM mra.candidate_score_component c WHERE c.dataset_id=ANY(%s::uuid[])
UNION ALL
SELECT 'Signal',candidate_id,status,reason_code FROM mra.signal WHERE decision_run_id=ANY(%s::uuid[])
UNION ALL
SELECT 'Forecast',candidate_id,status,reason_code FROM mra.forecast WHERE decision_run_id=ANY(%s::uuid[])
UNION ALL
SELECT 'Opportunity',candidate_id,status,reason_code FROM mra.opportunity WHERE decision_run_id=ANY(%s::uuid[])
UNION ALL
SELECT 'Portfolio',candidate_id,status,reason_code FROM mra.portfolio_line WHERE decision_run_id=ANY(%s::uuid[])
UNION ALL
SELECT 'Outcome',c.candidate_id,r.outcome_status,r.availability_status
FROM mra.decision_target_commitment c
LEFT JOIN LATERAL (
 SELECT outcome_status,availability_status FROM mra.market_target_outcome_revision r
 WHERE r.commitment_id=c.commitment_id ORDER BY revision_ordinal DESC LIMIT 1
) r ON true WHERE c.decision_run_id=ANY(%s::uuid[])
"""

_METRICS_SQL = """
WITH scoped AS MATERIALIZED (
 SELECT m.evaluation_metric_id,m.evaluation_protocol_metric_id,m.evaluation_run_id,
        e.expected_member_count,e.observation_count
 FROM mra.backtest_evaluation_execution x
 JOIN mra.evaluation_run e USING(evaluation_run_id)
 JOIN mra.evaluation_metric m USING(evaluation_run_id)
 WHERE x.exploratory_backtest_run_id=%s
), params AS (
 SELECT p.evaluation_protocol_metric_id,
 max(p.integer_value) FILTER(WHERE p.parameter_code='expected_roster_size') expected_roster_size,
 max(p.integer_value) FILTER(WHERE p.parameter_code='minimum_observations') minimum_observations
 FROM mra.evaluation_formula_parameter p
 WHERE p.evaluation_protocol_metric_id=ANY(ARRAY(SELECT evaluation_protocol_metric_id FROM scoped))
 GROUP BY p.evaluation_protocol_metric_id
), observations AS (
 SELECT o.evaluation_metric_id,o.input_state,count(*) count
 FROM mra.evaluation_metric_observation o
 WHERE o.evaluation_run_id=ANY(ARRAY(SELECT DISTINCT evaluation_run_id FROM scoped))
 GROUP BY o.evaluation_metric_id,o.input_state
)
SELECT s.*,p.expected_roster_size,p.minimum_observations,
       o.input_state,o.count
FROM scoped s LEFT JOIN params p USING(evaluation_protocol_metric_id)
LEFT JOIN observations o USING(evaluation_metric_id)
ORDER BY s.evaluation_metric_id,o.input_state
"""


class PostgresBacktestDiagnosticsSourcePort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def load(self, run_id: UUID) -> FunnelSnapshot:
        with self._pool.connection(read_only=True) as connection:
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            with connection.cursor(row_factory=dict_row) as c:
                identity = c.execute("""SELECT current_database() name,d.oid,
                    (SELECT system_identifier::text FROM pg_control_system()) cluster
                    FROM pg_database d WHERE datname=current_database()""").fetchone()
                root = c.execute('SELECT specification_sha256 FROM mra.backtest_specification WHERE exploratory_backtest_run_id=%s', (run_id,)).fetchone()
                if root is None or identity is None:
                    raise ValueError('diagnostics require exact current Backtest specification')
                arms = c.execute("""SELECT exploratory_backtest_arm_id,candidate_policy_sha256,
                    portfolio_policy_sha256,risk_policy_sha256,effective_cost_roster_sha256
                    FROM mra.backtest_arm_specification WHERE exploratory_backtest_run_id=%s ORDER BY exploratory_backtest_arm_id""", (run_id,)).fetchall()
                sample = c.execute('SELECT instrument_id FROM mra.backtest_sample_member WHERE exploratory_backtest_run_id=%s ORDER BY ordinal', (run_id,)).fetchall()
                cells = c.execute(_CELLS_SQL, (run_id,)).fetchall()
                if any(row['dataset_id'] is None or row['decision_run_id'] is None for row in cells):
                    raise ValueError('diagnostics require complete Dataset/Decision cell roster')
                rows = c.execute(_MEMBERS_SQL, (run_id,)).fetchall()
                dataset_ids = sorted({row['dataset_id'] for row in cells}, key=str)
                decision_ids = sorted({row['decision_run_id'] for row in cells}, key=str)
                member_facts: dict[tuple[str, str], list[str]] = defaultdict(list)
                for fact in c.execute(_MEMBER_FACTS_SQL, (dataset_ids, *(decision_ids for _ in range(5)))).fetchall():
                    member_facts[(str(fact['owner']), fact['kind'])].append(f"{fact['state'] or 'ABSENT'}:{fact['reason'] or 'NO_OWNER_FACT'}")
                decision_facts: dict[tuple[str, str], list[str]] = defaultdict(list)
                for fact in c.execute("""
                    SELECT 'Context' kind,decision_run_id owner,context_kind||':'||assessment_state state
                    FROM mra.context_assessment WHERE decision_run_id=ANY(%s::uuid[])
                    UNION ALL SELECT 'Risk',decision_run_id,status FROM mra.risk_decision WHERE decision_run_id=ANY(%s::uuid[])
                    """, (decision_ids, decision_ids)).fetchall():
                    decision_facts[(str(fact['owner']), fact['kind'])].append(fact['state'])
                assessment_ids = sorted({row['eligibility_assessment_id'] for row in rows if row['eligibility_assessment_id']}, key=str)
                reasons: dict[str, list[str]] = defaultdict(list)
                for fact in c.execute("""SELECT eligibility_assessment_id,criterion_result,reason_code,measure_code,
                    coalesce(observed_status,observed_decimal::text,observed_count::text,'UNKNOWN') observed
                    FROM mra.eligibility_reason WHERE eligibility_assessment_id=ANY(%s::uuid[])
                    AND criterion_result<>'PASS' ORDER BY eligibility_reason_id""", (assessment_ids,)).fetchall():
                    reasons[str(fact['eligibility_assessment_id'])].append(':'.join(str(fact[k]) for k in ('criterion_result', 'reason_code', 'measure_code', 'observed')))
                gaps = c.execute("""
                    SELECT cm.decision_run_id,cm.commitment_id,cm.instrument_id,r.market_target_outcome_revision_id,
                           r.outcome_status,r.availability_status,
                           array_agg(reason.reason_code ORDER BY reason.reason_ordinal) FILTER(WHERE reason.reason_code IS NOT NULL) reasons
                    FROM mra.decision_target_commitment cm
                    JOIN LATERAL (SELECT * FROM mra.market_target_outcome_revision r WHERE r.commitment_id=cm.commitment_id
                                  ORDER BY revision_ordinal DESC LIMIT 1) r ON r.outcome_status<>'COMPLETE'
                    LEFT JOIN mra.market_target_outcome_reason reason USING(market_target_outcome_revision_id)
                    WHERE cm.decision_run_id=ANY(%s::uuid[])
                    GROUP BY cm.decision_run_id,cm.commitment_id,cm.instrument_id,r.market_target_outcome_revision_id,r.outcome_status,r.availability_status
                    ORDER BY cm.decision_run_id,cm.commitment_id
                    """, (decision_ids,)).fetchall()
                metric_rows = c.execute(_METRICS_SQL, (run_id,)).fetchall()
                training = c.execute("""
                    SELECT t.model_training_run_id,v.model_version_id,t.sample_count,t.estimable_count,
                           count(DISTINCT p.decision_session_date) sessions,count(DISTINCT s.decision_run_id) decisions
                    FROM mra.model_training_run t LEFT JOIN mra.model_version v USING(model_training_run_id)
                    LEFT JOIN mra.model_training_sample s USING(model_training_run_id)
                    LEFT JOIN mra.research_partition_member p USING(research_partition_member_id)
                    WHERE t.exploratory_backtest_run_id=%s
                    GROUP BY t.model_training_run_id,v.model_version_id ORDER BY t.model_training_run_id
                    """, (run_id,)).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in metric_rows:
            grouped[str(row['evaluation_metric_id'])].append(row)
        inputs = []
        for metric_id, items in grouped.items():
            first = items[0]
            input_states = tuple((r['input_state'], int(r['count'])) for r in items if r['input_state'] is not None)
            inputs.append(FunnelMetricInput(metric_id, first['expected_roster_size'], first['minimum_observations'],
                sum(n for _, n in input_states), sum(n for state, n in input_states if state == 'INCLUDED'),
                first['expected_member_count'], first['observation_count'], input_states))
        members = []
        for row in rows:
            key = str(row['candidate_id'])
            decision = str(row['decision_run_id'])
            def states(kind: str) -> tuple[str, ...]:
                return tuple(sorted(member_facts.get((key, kind), ())))
            members.append(FunnelMember(str(row['arm_id']), str(row['session_id']), str(row['instrument_id']),
                row['membership_status'], row['result'], tuple(sorted(reasons.get(str(row['eligibility_assessment_id']), ()))),
                _text(row['candidate_id']), row['disposition'], row['reason_code'], states('Feature'),
                tuple(sorted(decision_facts.get((decision, 'Context'), ()))), states('Signal'), states('Forecast'),
                states('Opportunity'), states('Portfolio'), tuple(sorted(decision_facts.get((decision, 'Risk'), ()))), states('Outcome')))
        return FunnelSnapshot(run_id, root['specification_sha256'], identity['name'], identity['oid'], identity['cluster'],
            tuple(str(row['instrument_id']) for row in sample),
            tuple(FunnelCell(str(row['arm_id']), str(row['fold_id']), str(row['session_id']), row['session_date'], row['session_role'],
                _text(row['dataset_id']), _text(row['decision_run_id']), *(int(row[k]) for k in ('available_cell_count', 'missing_cell_count', 'unknown_cell_count', 'stale_cell_count', 'conflict_cell_count'))) for row in cells),
            tuple(members), tuple(inputs), tuple(FunnelTraining(str(t['model_training_run_id']), _text(t['model_version_id']),
                t['sample_count'], t['estimable_count'], t['sessions'], t['decisions']) for t in training),
            tuple(FunnelArm(str(a['exploratory_backtest_arm_id']), a['candidate_policy_sha256'], a['portfolio_policy_sha256'], a['risk_policy_sha256'], a['effective_cost_roster_sha256']) for a in arms),
            tuple(FunnelOutcomeGap(str(g['decision_run_id']), str(g['commitment_id']), str(g['market_target_outcome_revision_id']),
                str(g['instrument_id']), g['outcome_status'], g['availability_status'], tuple(g['reasons'] or ())) for g in gaps))


def _text(value: object) -> str | None:
    return None if value is None else str(value)
