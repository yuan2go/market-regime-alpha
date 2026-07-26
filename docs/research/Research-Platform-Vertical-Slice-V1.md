# Research Platform Multi-Model Candidate Slice V1

## 目标

在同一个 `CandidateResearchDataset` 上运行三个固定 Candidate 模型，验证 Model Registry 前置定义、多模型统一编排、完整结果保留和横向重叠分析。

## 模型

- `platform-b0-momentum-v1`
- `platform-b1-balanced-v1`
- `platform-b2-volume-momentum-v1`

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

- 输入必须是现有权威 `CandidateResearchDataset`；
- 三个 Feature ID 必须存在于该数据集；
- 所有模型共享数据集中的 Universe、Decision Time和Target；
- 当前模型使用固定透明权重，不执行自动调参。

## 输出

每个模型输出：

- `model_id`；
- `experiment_id`；
- `config_hash`；
- `ranking_coverage`；
- 完整 `CandidatePrediction`；
- 完整 `CandidateRankingRejection`。

跨模型输出：

- Top-K overlap；
- Top-K union；
- Jaccard。

## 证据边界

该切片证明多模型平台合同和运行逻辑可用，不证明：

- 任一模型存在Alpha；
- B1或B2优于B0；
- 共识股票更可能上涨；
- 免费数据具有正式PIT资格；
- 任何模型可以进入实盘。
