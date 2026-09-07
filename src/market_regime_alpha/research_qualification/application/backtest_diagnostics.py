"""Canonical report plus complete member accounting; no new metric computation."""

from collections import Counter
from dataclasses import asdict
import json
from typing import Protocol, Any
from uuid import UUID

from market_regime_alpha.research_qualification.application.backtest_reports import BacktestReportApplication
from market_regime_alpha.research_qualification.domain.backtest_diagnostics import FunnelSnapshot, summarize_funnel
from market_regime_alpha.research_qualification.errors import BacktestReportIntegrityError
from market_regime_alpha.shared.hashing import canonical_json_sha256


class BacktestDiagnosticsSourcePort(Protocol):
    def load(self, run_id: UUID) -> FunnelSnapshot: ...


class BacktestDiagnosticsApplication:
    def __init__(self, source: BacktestDiagnosticsSourcePort, reports: BacktestReportApplication) -> None:
        self._source = source
        self._reports = reports

    def project(self, run_id: UUID) -> dict[str, object]:
        report = self._reports.project(run_id)
        snapshot = self._source.load(run_id)
        summary = summarize_funnel(snapshot)
        if snapshot.run_id != run_id or snapshot.specification_sha256 != _mapping(report['executive_summary'])['specification_sha256']:
            raise BacktestReportIntegrityError('diagnostic source differs from reconciled Backtest identity')
        # A changed input/result roster during the read cannot borrow the earlier PASS.
        if report != self._reports.project(run_id):
            raise BacktestReportIntegrityError('canonical report changed during diagnostics')
        metrics = [m for section in ('data_coverage', 'candidate_metrics', 'context_attribution', 'signal_forecast_metrics',
            'portfolio_risk_metrics', 'gross_net_economics', 'fold_time_stability') for m in _sequence(report[section])]
        inputs = {m.metric_id: m for m in snapshot.metric_inputs}
        if set(inputs) != {str(m['evaluation_metric_id']) for m in metrics}:
            raise BacktestReportIntegrityError('diagnostic metric input roster differs from reconciled Evaluation')
        diagnoses = []
        for metric in metrics:
            if metric['result_state'] != 'NOT_ESTIMABLE':
                continue
            facts = inputs[str(metric['evaluation_metric_id'])]
            diagnosis = 'NOT_DETERMINED'
            cells = [c for c in snapshot.cells if c.arm_id == metric['arm_id'] and
                (c.fold_id == metric['fold_id'] if metric['fold_id'] else c.role == 'EVALUATION')]
            cell_ids = {(c.arm_id, c.session_id) for c in cells}
            members = [m for m in snapshot.members if (m.arm_id, m.session_id) in cell_ids]
            legal = sum(m.candidate_id is None and m.eligibility == 'INELIGIBLE' and bool(m.eligibility_reasons) for m in members)
            unexplained = sum(m.candidate_id is None and not (m.eligibility == 'INELIGIBLE' and m.eligibility_reasons) for m in members)
            if (metric['reason_code'] == 'EXPECTED_ROSTER_MISMATCH' and metric['scope_kind'] in ('FOLD', 'AGGREGATE')
                and facts.expected_roster_size == len(members) and unexplained == 0
                and len(members) - legal == facts.parent_member_count == facts.parent_observation_count == facts.observation_count):
                diagnosis = 'DECLARED_PRE_ELIGIBILITY_DENOMINATOR_WITH_LEGAL_EXCLUSIONS'
            elif metric['reason_code'] == 'INSUFFICIENT_OBSERVATIONS' and facts.observation_count == 0 and facts.parent_member_count == 0:
                diagnosis = 'EMPTY_CANONICAL_PARTITION_SLICE'
            elif (metric['reason_code'] == 'INSUFFICIENT_OBSERVATIONS' and facts.observation_count > 0
                and facts.included_observation_count == 0 and all(state == 'NOT_ESTIMABLE' for state, _ in facts.input_states)):
                diagnosis = 'NO_ESTIMABLE_CANONICAL_METRIC_INPUTS'
            diagnoses.append({'metric': metric, 'canonical_input_counts': asdict(facts), 'diagnosis': diagnosis,
                'arm_fold_member_count_before_metric_slice': len(members), 'arm_fold_legal_exclusion_count_before_metric_slice': legal,
                'arm_fold_unexplained_loss_count_before_metric_slice': unexplained})
        arm_scopes = {(a.candidate_policy_sha256, a.portfolio_policy_sha256, a.risk_policy_sha256, a.cost_roster_sha256) for a in snapshot.arms}
        fingerprints: dict[str, str] = {}
        for arm in snapshot.arms:
            roster = [(c.fold_id, str(c.session_date), c.role) for c in snapshot.cells if c.arm_id == arm.arm_id]
            fingerprints[arm.arm_id] = canonical_json_sha256(sorted(roster))
        comparable = bool(snapshot.arms) and len(arm_scopes) == 1 and len(set(fingerprints.values())) == 1
        # Match the exact formula identity, scope and code before presenting arm values together.
        groups: dict[tuple[object, ...], list[dict[str, Any]]] = {}
        for metric in metrics:
            key = (metric['scope_kind'], metric['fold_id'], metric['slice_key'], metric['metric_code'], metric['formula_code'], metric['formula_version'], metric['formula_content_sha256'])
            groups.setdefault(key, []).append(metric)
        comparison = [{
            'mode': 'COMMON_SCOPE_CANONICAL_VALUES' if comparable and len(rows) == len(snapshot.arms) and len({r['arm_id'] for r in rows}) == len(snapshot.arms) else 'NOT_COMPARABLE_COMPLETE_ARM_ROSTER',
            'metrics': rows,
            'winner': None,
        } for rows in groups.values()]
        cell_by_key = {(c.arm_id, c.session_id): c for c in snapshot.cells}
        payload: dict[str, object] = {
            'schema': 'mra-backtest-diagnostics-v1', 'authority': 'READ_ONLY_PROJECTION',
            'database_scope': {'name': snapshot.database_name, 'oid': snapshot.database_oid, 'cluster_identity': snapshot.cluster_identity},
            'summary': summary, 'canonical_report': report,
            'cells': tuple(asdict(c) for c in snapshot.cells),
            'member_roster': tuple(asdict(m) for m in snapshot.members),
            'training_units': tuple(asdict(t) for t in snapshot.training),
            'eligibility_exclusions': tuple({'cell': asdict(cell_by_key[(m.arm_id,m.session_id)]), 'instrument_id': m.instrument_id, 'reasons': m.eligibility_reasons}
                for m in snapshot.members if m.eligibility=='INELIGIBLE'),
            'outcome_gap_facts': tuple(asdict(g) for g in snapshot.outcome_gaps),
            'not_estimable_diagnoses': diagnoses,
            'diagnosis_counts': dict(sorted(Counter(str(d['diagnosis']) for d in diagnoses).items())),
            'arm_comparison': {'shared_sample_feature_target': report['feature_target_definitions'],
                'shared_universe_sample': report['universe_sample'], 'policy_bindings': tuple(asdict(a) for a in snapshot.arms),
                'fold_session_fingerprints': fingerprints, 'groups': comparison},
            'alpha_bottleneck': 'NOT_DETERMINED', 'model_superiority': 'NOT_DETERMINED',
            'next_experiment_boundaries': (
                'New protocol must explicitly distinguish sampled population, eligible population and Outcome availability denominators; do not rewrite frozen results.',
                'Collect real prospective Target-aligned inputs and outcomes before daily Model Shadow; historical Validation is not untouched OOS.',
                'Bind ModelVersion, feature lineage, knowledge cutoff and canonical prospective Decision/Target; do not fabricate retrospective folds for daily inference.',
                'V1 economics remains excluded from V2 episode correctness; Target horizon is not a tradable holding period.',
            ),
        }
        payload['projection_sha256'] = canonical_json_sha256(payload)
        return payload

    def render_json(self, run_id: UUID) -> bytes:
        return (json.dumps(self.project(run_id), sort_keys=True, indent=2, default=str, ensure_ascii=False, allow_nan=False) + '\n').encode()

    def render_markdown(self, run_id: UUID) -> bytes:
        payload = self.project(run_id)
        lines = ['# Canonical research funnel diagnosis', '',
            'Read-only exploratory projection; member counts are not independent days, episodes or Alpha evidence.', '',
            '## Database scope', '', json.dumps(payload['database_scope'], sort_keys=True), '', '## Complete member accounting', '']
        summary = _mapping(payload['summary'])
        for key, value in summary.items():
            if key != 'stages':
                lines.append(f'- {key}: {value}')
        lines.extend(['', '## Stage states', '', '| Stage | Canonical state | Member/fact count |', '|---|---|---:|'])
        for stage, states in _mapping(summary['stages']).items():
            for state, count in _mapping(states).items():
                lines.append(f'| {stage} | {state} | {count} |')
        lines.extend(['', '## Not-estimable diagnoses', ''])
        for reason, count in _mapping(payload['diagnosis_counts']).items():
            lines.append(f'- {reason}: {count}')
        lines.extend(['', '## Eligibility exclusions', '', '| Session | Arm | Instrument | Canonical reason |', '|---|---|---|---|'])
        for excluded in _sequence(payload['eligibility_exclusions']):
            cell = _mapping(excluded['cell'])
            lines.append(f"| {cell['session_date']} | {cell['arm_id']} | {excluded['instrument_id']} | {excluded['reasons']} |")
        lines.extend(['', '## Canonical Outcome gaps', ''])
        for gap in _sequence(payload['outcome_gap_facts']):
            lines.append(f"- Commitment {gap['commitment_id']}; revision {gap['revision_id']}; {gap['outcome_status']}; {gap['reason_codes']}")
        lines.extend(['', '## Canonical arm metrics', '', 'Values below are existing Evaluation projections; no metric is recalculated and no winner is inferred.', '',
            '| Comparability | Scope | Fold/slice | Metric | Formula/version | Arm | State | Value | Reason |', '|---|---|---|---|---|---|---|---|---|'])
        for group in _sequence(_mapping(payload['arm_comparison'])['groups']):
            for m in _sequence(group['metrics']):
                value = m['decimal_value'] if m['decimal_value'] is not None else 'NOT_ESTIMABLE'
                lines.append(f"| {group['mode']} | {m['scope_kind']} | {m['fold_id'] or m['slice_key'] or 'ALL'} | {m['metric_code']} | {m['formula_code']}/{m['formula_version']} | {m['arm_id']} | {m['result_state']} | {value} | {m['reason_code']} |")
        lines.extend(['', '## Next experiment boundary', '', 'Alpha bottleneck: NOT_DETERMINED. Model superiority: NOT_DETERMINED.', ''])
        boundaries = payload['next_experiment_boundaries']
        assert isinstance(boundaries, tuple)
        for item in boundaries:
            lines.append(f'- {item}')
        lines.extend(['', f"Projection SHA256: {payload['projection_sha256']}", ''])
        return '\n'.join(lines).encode()


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BacktestReportIntegrityError('expected canonical report object')
    return value


def _sequence(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, (tuple, list)) or any(not isinstance(item, dict) for item in value):
        raise BacktestReportIntegrityError('expected canonical report metric roster')
    return list(value)
