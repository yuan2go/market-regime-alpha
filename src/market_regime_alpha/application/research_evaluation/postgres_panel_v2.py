"""PostgreSQL registry for immutable Research Panel V2 Artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_evaluation.panel_v2 import (
    FrozenResearchPanelV2,
    load_research_panel_v2,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class ResearchPanelConflict(ValueError):
    """Research Panel identity, Artifact, or owner-lineage conflict."""


class ResearchPanelIntegrityError(ValueError):
    """Stored Research Panel failed canonical restoration."""


class PostgresResearchPanelRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def register(self, panel: FrozenResearchPanelV2, *, artifact_path: Path) -> FrozenResearchPanelV2:
        if load_research_panel_v2(artifact_path) != panel:
            raise ResearchPanelConflict("Research Panel Artifact does not match content")
        if artifact_path.name != f"{panel.panel_id}.json":
            raise ResearchPanelConflict("Research Panel locator is not content-addressed")

        def operation(connection: Any) -> None:
            protocol = connection.execute(
                "SELECT protocol_hash FROM outcome_target_protocol WHERE protocol_id = %s",
                (str(panel.target_protocol_id),),
            ).fetchone()
            if protocol is None or str(protocol[0]) != panel.target_protocol_hash:
                raise ResearchPanelConflict("Research Panel Target Protocol lineage mismatch")
            connection.execute(
                """
                INSERT INTO research_evaluation_panel_v2(
                    panel_id, panel_hash, target_protocol_id, target_protocol_hash,
                    slice_count, row_count, payload_json, artifact_locator, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (panel_id) DO NOTHING
                """,
                (
                    str(panel.panel_id),
                    panel.panel_hash,
                    str(panel.target_protocol_id),
                    panel.target_protocol_hash,
                    len(panel.slices),
                    panel.row_count,
                    Jsonb(panel.to_canonical_dict()),
                    str(artifact_path.resolve()),
                    panel.created_at,
                ),
            )
            stored = connection.execute(
                "SELECT panel_hash, artifact_locator FROM research_evaluation_panel_v2 WHERE panel_id = %s",
                (str(panel.panel_id),),
            ).fetchone()
            if stored is None or (str(stored[0]) != panel.panel_hash or str(stored[1]) != str(artifact_path.resolve())):
                raise ResearchPanelConflict("Research Panel identity conflict")
            for value in panel.slices:
                decision = connection.execute(
                    "SELECT decision_hash FROM shadow_research_decision WHERE decision_id = %s",
                    (str(value.shadow_decision.artifact_id),),
                ).fetchone()
                outcome = connection.execute(
                    "SELECT settlement_hash, shadow_decision_id FROM targeted_shadow_outcome WHERE settlement_id = %s",
                    (str(value.targeted_outcome.artifact_id),),
                ).fetchone()
                if decision is None or str(decision[0]) != value.shadow_decision.content_hash:
                    raise ResearchPanelConflict("Research Panel Decision lineage mismatch")
                if outcome is None or (
                    str(outcome[0]) != value.targeted_outcome.content_hash or str(outcome[1]) != str(value.shadow_decision.artifact_id)
                ):
                    raise ResearchPanelConflict("Research Panel Outcome lineage mismatch")
                connection.execute(
                    """
                    INSERT INTO research_evaluation_panel_slice_v2(
                        panel_id, slice_id, slice_hash, shadow_decision_id,
                        targeted_outcome_id, run_id, tick_id, trading_date,
                        row_count, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (panel_id, slice_id) DO NOTHING
                    """,
                    (
                        str(panel.panel_id),
                        str(value.slice_id),
                        value.slice_hash,
                        str(value.shadow_decision.artifact_id),
                        str(value.targeted_outcome.artifact_id),
                        str(value.run_id),
                        str(value.tick_id),
                        value.trading_date,
                        len(value.rows),
                        Jsonb(value.to_canonical_dict()),
                    ),
                )
                for row in value.rows:
                    connection.execute(
                        """
                        INSERT INTO research_evaluation_panel_row_v2(
                            panel_id, slice_id, row_id, row_hash, symbol,
                            universe_eligible, pool_included, candidate_status,
                            candidate_rank, target_label_count, payload_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (panel_id, slice_id, row_id) DO NOTHING
                        """,
                        (
                            str(panel.panel_id),
                            str(value.slice_id),
                            str(row.row_id),
                            row.row_hash,
                            row.symbol,
                            row.universe_eligible,
                            row.pool_included,
                            row.candidate_status,
                            row.candidate_rank,
                            len(row.target_labels),
                            Jsonb(row.to_canonical_dict()),
                        ),
                    )

        self._factory.run_transaction(operation)
        return self.get(panel.panel_id)

    def get(self, panel_id: ArtifactId) -> FrozenResearchPanelV2:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT payload_json, panel_hash, artifact_locator FROM research_evaluation_panel_v2 WHERE panel_id = %s",
                (str(panel_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(panel_id))
        try:
            panel = FrozenResearchPanelV2.from_canonical_dict(_object(row[0]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchPanelIntegrityError("Research Panel restoration failed") from exc
        if panel.panel_hash != str(row[1]):
            raise ResearchPanelIntegrityError("Research Panel owner hash drift")
        if load_research_panel_v2(Path(str(row[2]))) != panel:
            raise ResearchPanelIntegrityError("Research Panel Artifact drift")
        return panel

    def replay(self, panel_id: ArtifactId) -> FrozenResearchPanelV2:
        stored = self.get(panel_id)
        rebuilt_hash = canonical_hash(stored.identity_payload())
        if rebuilt_hash != stored.panel_hash:
            raise ResearchPanelIntegrityError("Research Panel replay mismatch")
        return stored


def _object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ResearchPanelIntegrityError("Research Panel payload is not an object")
    return value


__all__ = [
    "PostgresResearchPanelRepository",
    "ResearchPanelConflict",
    "ResearchPanelIntegrityError",
]
