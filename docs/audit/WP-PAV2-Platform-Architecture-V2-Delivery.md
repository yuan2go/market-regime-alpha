# WP-PAV2 Platform Architecture V2 Delivery

> **Status:** CURRENT_STATUS
> **Authority:** Verified engineering delivery evidence for WP-PAV2
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-07-30
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../architecture/09-Platform-Architecture-V2.md, ../architecture/decisions/ADR-003-Platform-V2-Research-Artifact-Boundary.md, ../roadmap/work-packages/WP-PAV2-Platform-Architecture-V2-and-Research-Layer-MVP.md, ../status/Current-State.md
> **Code Evidence:** `feat/platform-architecture-v2-research-layer@64cacd2`; documentation commit is recorded in Git history

## Conclusion

```text
PLATFORM_ARCHITECTURE_V2_COMPLETE
RESEARCH_LAYER_MVP_COMPLETE
```

This is an engineering and deterministic Replay conclusion. It is not a real
market, formal PIT, OOS Alpha or trading conclusion.

## Baseline

```text
starting_branch = feat/wp-d3-1-real-decision-evidence
starting_head = fc05a3fe782a2e5095a362d1ef892b71fca4a7c5
delivery_branch = feat/platform-architecture-v2-research-layer
```

The actual starting HEAD matched the requested baseline. No remote increment
or user worktree modification had to be reconciled.

## Code-first diagnosis

| Concern | State before WP-PAV2 |
|---|---|
| Data and Evidence | Canonical SourceManifest, staged public acquisition, Runtime Journal, Artifact verification and Replay already implemented |
| Market Regime | MR2A/MR2B existed as focused exploratory research, not a platform snapshot or daily gate |
| Theme Rotation | Research documents and mappings existed; no canonical runnable snapshot in the daily flow |
| Capital Evolution | Legacy capital-flow code and research prose existed; no typed proxy-based state artifact |
| Candidate Discovery | CandidateDataset and B0/B1 PredictionRuns were mature; they ranked a population and did not own Theme, Capital or trade action |
| Signal and Forecast | Scattered research concepts; no stable Platform V2 ownership contract |
| Entry | Phase D plumbing emitted WAIT/REJECT only; historical V1 had separate frozen ENTER semantics |
| Position and Exit | Legacy or designed-only; no canonical Platform V2 executable authority |
| Evaluation | Target/Evaluation Protocol and DailyReview existed; no layer-scoped EvaluationReport |

`DailyLoopRunner` already orchestrated acquisition recovery, Source quality,
Universe, Feature, B0/B1, Recommendation, Entry, daily Artifact and settlement.
Adding four more research stages there would deepen an overloaded Application
service, so WP-PAV2 uses a separate `PlatformResearchRunner`.

## Delivered call chain

```text
scripts/run_research_layer.py
→ PlatformResearchRunner.run
→ run_research_pipeline_v2
→ evaluate_market_regime_v0
→ evaluate_theme_rotation_v0
→ evaluate_capital_evolution_v0
→ discover_candidates_v2
→ publish_research_layer_artifact
→ load_verified_research_artifact
```

Replay verifies the exact package, reconstructs all typed objects, reruns the
same pipeline and rejects any semantic difference.

## Reuse and adapters

- MR2A metrics are projected by `adapt_mr2a_to_market_observation`;
- B0/B1 PredictionRuns are consumed by
  `adapt_b0_b1_candidate_factors`;
- existing SourceManifest, Universe, Eligibility, Decision Time, Decision
  Price, Feature IDs, Model IDs and Target IDs remain authoritative;
- no existing Feature formula, B0/B1 score, rank, target or Reader changed.

## Model assumptions

Observed facts are the typed values and times in `ResearchInputBundle`.
Market, Theme and Capital scores are deterministic transformations of those
facts. Thresholds and weights are model assumptions, all stored in versioned
configuration identities.

Capital Evolution states are proxy-based inferences. They do not assert that
an institution, controlling actor or dealer has a particular intent.

## Test and runtime evidence

```text
pytest = PASS, 1164 passed, 0 failed, 0 skipped
mypy = PASS, 224 source files
ruff = PASS
pip_check = PASS
git_diff_check = PASS
```

The full pytest run emitted six existing Pandas DataFrame fragmentation
warnings in unrelated top-1000 backtest tests.

Fixture execution published a nine-file ResearchLayerArtifact, reconstructed
its report and then replayed to the same Artifact ID, content hash, layer
states and CandidateSet. Tampering and unsupported Reader schemas fail closed.
Real LIVE was deliberately not executed.

The explicit post-test CLI fixture run recorded:

```text
evidence_kind = SYNTHETIC_FIXTURE
research_status = RESEARCH_RESTRICTED
market_state = RISK_NEUTRAL
trade_permission = RESTRICT
theme_count = 1
capital_symbol_count = 6
candidate_reconciliation_count = 6
selected_candidate_count = 5
artifact_id = research-layer-artifact-08430638860f4f5fc209738f
content_hash = sha256:08430638860f4f5fc209738f1af4efca631f0e2218dd1ea4fd5bf526fe63562f
checksum_manifest_hash = sha256:2cf4eec6abd617397b318ade27554cb888e13574f245629b4e53a0238e9762db
```

Two consecutive CLI Replay commands returned the same Artifact ID and content
hash. The CLI report was reconstructed from the verified semantic objects.
The temporary package was written outside the repository and is not delivery
source or real market evidence.

## Compatibility evidence

A focused 320-test suite covering daily acquisition, SourceManifest,
Universe, Features, Platform PredictionRuns, Phase D decision artifacts,
historical `daily_research` V1, Candidates and Platform V2 passed before the
full suite.

The historical `daily_research` V1 package remains six files with its existing
Schema, IDs, Reader and ENTER semantics. Platform V2 has a separate package,
schema and Reader Registry.

## Authority and limitations

```text
data_eligibility = EXPLORATORY
formal_pit = NOT_ESTABLISHED
formal_oos_alpha = NOT_ESTABLISHED
trading_authority = NOT_GRANTED
```

The implemented V0 models are not empirically validated. The repository does
not yet build a real historical archive with complete Theme and Capital
observations, and the new Research Pipeline is not wired into public LIVE or
DailyLoop.

## Remaining ordered work

1. Signal Engine MVP;
2. Next-session Forecast implementation and calibration;
3. Trade Decision research boundary;
4. Position, Execution and Exit models;
5. layer-specific evaluation materialization;
6. operational Research Runtime orchestration;
7. qualified historical and real-data validation.
