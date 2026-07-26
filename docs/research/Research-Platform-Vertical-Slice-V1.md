# Research Platform Multi-Model Candidate Slice V1

> **Status:** CURRENT_RESEARCH_PROGRAM  
> **Authority:** Current implementation evidence and research boundary for the first Platform Multi-model Candidate Slice  
> **Owner:** Candidate Discovery domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-Research-Program.md, Candidate-Research.md, ../roadmap/work-packages/WP-D0-Platform-Governance-Kernel.md, ../status/Capability-Matrix.md  
> **Code Evidence:** `src/market_regime_alpha/platform/multi_model_slice.py`; `tests/platform/test_research_platform_kernel.py`

## 目标

在同一个 `CandidateResearchDataset` 上运行三个固定 Candidate 模型，验证Model定义、多模型统一编排、完整结果保留和横向重叠分析。

该切片是已合并的机械运行能力，不是持久化Daily Prediction Ledger，也不证明任一模型存在Alpha。

## 模型

- `platform-b0-momentum-v1`
- `platform-b1-balanced-v1`
- `platform-b2-volume-momentum-v1`

### 命名限制

当前第三个模型在代码中沿用了`B2`名称，但其实现仍是固定权重`TransparentCompositeSpec`，不等同于正式模型梯队中的“B2正则化统计基线”。WP-D0必须通过显式迁移处理该命名冲突，不能静默复用或改写历史Model ID。

## Python入口

```python
from market_regime_alpha.platform import (
    build_default_candidate_slice_specs,
    run_multi_model_candidate_slice,
)

specs = build_default_candidate_slice_specs(
    momentum_feature_id=momentum_feature_id,
    volume_feature_id=volume_feature_id,
    volatility_feature_id=volatility_feature_id,
)

run = run_multi_model_candidate_slice(
    candidate_dataset,
    model_specs=specs,
    code_revision=git_commit_sha,
    top_k_values=(5, 10, 20),
)
```

## 输入约束

- 输入必须是现有权威`CandidateResearchDataset`；
- 三个Feature ID必须存在于该数据集；
- 所有模型共享数据集中的Universe、Decision Time和Target；
- 当前模型使用固定透明权重，不执行自动调参；
- 当前Runner尚未强制绑定持久化Model Registry、Target/Evaluation Protocol和Frozen Experiment Protocol。

## 输出

每个模型输出：

- `model_id`；
- `experiment_id`；
- `config_hash`；
- `ranking_coverage`；
- 完整`CandidatePrediction`；
- 完整`CandidateRankingRejection`。

跨模型输出：

- Top-K overlap；
- Top-K union；
- Jaccard。

## 当前缺口

- 缺少内容寻址的`PredictionRun` Aggregate；
- 缺少Target/Evaluation/Experiment Protocol引用；
- 缺少持久化、恢复、幂等和Supersession语义；
- 缺少Outcome与滚动Evaluation；
- 缺少对DataEligibility和Model EvidenceLevel的独立兼容检查。

这些缺口由[WP-D0 Platform Governance Kernel Hardening](../roadmap/work-packages/WP-D0-Platform-Governance-Kernel.md)和后续WP-D4负责。

## 证据边界

该切片证明多模型平台合同和运行逻辑可用，不证明：

- 任一模型存在Alpha；
- B1或当前透明复合challenger优于B0；
- 共识股票更可能上涨；
- 免费数据具有正式PIT资格；
- 任何模型可以进入实盘。
