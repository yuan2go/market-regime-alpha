from datetime import timedelta
import json
from uuid import uuid4

import psycopg
import pytest

from market_regime_alpha.bootstrap import TargetSettings, bootstrap_application, bootstrap_database
from market_regime_alpha.selection.domain import UniverseDefinition, UniverseScopeSpecification, ExploratoryRetrospectiveSelectionScope
from market_regime_alpha.shared.time import DecisionTime
from tests.contracts.research_qualification.archive_campaign_fixture import seed_complete_archive, _context


def test_static_roster_is_explicit_retrospective_only_and_idempotent(target_database_url, tmp_path):
    settings = TargetSettings(target_database_url, tmp_path / "artifacts")
    bootstrap_database(settings)
    with bootstrap_application(settings) as app:
        product, instruments, sessions, _, _, archive_id, seal = seed_complete_archive(app, daily_bars=True)
        universe = UniverseDefinition(uuid4(), "static_research", "STATIC_UNIVERSE/SURVIVORSHIP_LIMITED")
        app.selection.register_universe(universe, _context("static-register"))
        instruments = tuple(sorted(instruments, key=str))
        content = json.dumps({"schema": "selection-universe-scope-v1", "classification_scheme": "STATIC_RESEARCH_ROSTER",
            "classification_code": "SURVIVORSHIP_LIMITED_V1", "market_provider_product_id": str(product.provider_product_id),
            "instrument_ids": [str(x) for x in instruments]}, sort_keys=True, separators=(",", ":")).encode()
        artifact = app.artifacts.publish(content, media_type="application/json", context=_context("static-scope"))
        scope = UniverseScopeSpecification(artifact.artifact_id, artifact.content_sha256, artifact.size_bytes,
            product.provider_product_id, "STATIC_RESEARCH_ROSTER", "SURVIVORSHIP_LIMITED_V1", instruments)
        retrospective = ExploratoryRetrospectiveSelectionScope(archive_id, seal.market_archive_seal_id, seal.knowledge_cutoff, sessions[1].close_at)
        kwargs = dict(universe_id=universe.universe_id, scope=scope, retrospective_scope=retrospective, context=_context("static-freeze"))
        frozen = app.selection.freeze_exploratory_retrospective_universe(**kwargs)
        assert len(frozen.members) == 32
        assert all(m.membership_status.value == "INCLUDED" and m.evidence_status.value == "MISSING"
                   and m.reason_code == "STATIC_RESEARCH_ROSTER" and m.observed_membership_status is None
                   and m.membership_revision_id is None and m.classification_id is None and m.market_capture_id is None
                   and m.market_decision_visible_at is None for m in frozen.members)
        replay = app.selection.freeze_exploratory_retrospective_universe(**kwargs)
        assert replay.replayed and replay.universe_revision_id == frozen.universe_revision_id
        with pytest.raises(ValueError, match="cannot enter prospective"):
            app.selection.freeze_universe(universe_id=universe.universe_id, scope=scope,
                decision_time=DecisionTime(seal.knowledge_cutoff), context=_context("static-prospective-refused"))
        from dataclasses import replace
        from market_regime_alpha.runtime.errors import RuntimeStateConflictError
        from tests.contracts.research_qualification import _historical_backtest_catalog as C
        from market_regime_alpha.selection.domain import EligibilityRuleKind
        original = C._eligibility(product.provider_product_id)
        policy = replace(original, eligibility_policy_id=uuid4(), policy_code="static_eligibility",
                         rules=(original.rules[0], replace(original.rules[1], rule_kind=EligibilityRuleKind.LAST_COMPLETED_SESSION_ACTIVE)))
        app.selection.register_eligibility_policy(policy, _context("static-policy"))
        with pytest.raises(RuntimeStateConflictError, match="requires retrospective Eligibility"):
            app.selection.assess_eligibility(universe_revision_id=frozen.universe_revision_id,
                eligibility_policy_id=policy.eligibility_policy_id, decision_time=frozen.decision_time,
                context=_context("ordinary-static-eligibility-refused"))
        from market_regime_alpha.infrastructure.postgres.queries.research_sources import PostgresResearchSourceQueries
        with psycopg.connect(target_database_url) as connection:
            with pytest.raises(RuntimeStateConflictError, match="both exact scope bindings"):
                PostgresResearchSourceQueries(connection).expected_population(
                    universe_revision_id=frozen.universe_revision_id, eligibility_policy_id=policy.eligibility_policy_id,
                    decision_time=frozen.decision_time, lock=False)
        with pytest.raises(psycopg.errors.CheckViolation, match="STATIC_RESEARCH_REQUIRES_EXACT_RETROSPECTIVE_ELIGIBILITY"):
            with psycopg.connect(target_database_url) as connection:
                connection.execute("""INSERT INTO mra.eligibility_assessment
                  (eligibility_assessment_id,universe_revision_id,universe_member_id,eligibility_policy_id,instrument_id,
                   decision_time,result,rule_count,pass_count,fail_count,unknown_count)
                  VALUES(%s,%s,%s,%s,%s,%s,'ELIGIBLE',1,1,0,0)""",
                  (uuid4(),frozen.universe_revision_id,frozen.members[0].universe_member_id,policy.eligibility_policy_id,
                   frozen.members[0].instrument_id.value,frozen.decision_time.value))
        assessed = app.selection.assess_exploratory_retrospective_eligibility(
            universe_revision_id=frozen.universe_revision_id, eligibility_policy_id=policy.eligibility_policy_id,
            retrospective_scope=retrospective, context=_context("static-eligibility"))
        assert assessed.eligible_count == 32
        # Database-level refusal also applies to a malformed writer that omits
        # the retrospective binding. This connection is the disposable fixture.
        with pytest.raises(psycopg.errors.CheckViolation, match="STATIC_RESEARCH_REQUIRES_EXACT_RETROSPECTIVE_SCOPE"):
            with psycopg.connect(target_database_url) as connection:
                invalid_id = uuid4()
                connection.execute("""INSERT INTO mra.universe_revision
                    (universe_revision_id,universe_id,revision,decision_time,scope_artifact_id,scope_content_sha256,scope_size_bytes,
                     market_provider_product_id,classification_scheme,classification_code,total_count,included_count,excluded_count,unknown_count)
                    SELECT %s,universe_id,999,%s,scope_artifact_id,scope_content_sha256,scope_size_bytes,
                     market_provider_product_id,classification_scheme,classification_code,1,1,0,0
                    FROM mra.universe_revision WHERE universe_revision_id=%s""",
                    (invalid_id, sessions[1].close_at + timedelta(seconds=1), frozen.universe_revision_id))
                connection.execute("""INSERT INTO mra.universe_member
                    (universe_member_id,universe_revision_id,instrument_id,membership_status,evidence_status,reason_code,lineage_hash)
                    VALUES(%s,%s,%s,'INCLUDED','MISSING','STATIC_RESEARCH_ROSTER',%s)""",
                    (uuid4(), invalid_id, instruments[0].value, "a" * 64))
