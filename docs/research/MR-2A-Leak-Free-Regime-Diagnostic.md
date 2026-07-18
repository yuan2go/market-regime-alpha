# MR-2A Leak-Free Market Regime Diagnostic

MR-2A supersedes the historical MR-2 regime conclusion. It constructs each Decision Time Context
from normalized bars at or before 14:50 Asia/Shanghai; it does not read Decision Date full-session
high, low, close, or amount. The current run is `mr2a-ffb5cc8e8c086092d338`, using Dataset
`prr-dataset-fa40337727427b2f1ff63548` and corrected MR-1 run `mr1-aa92832aed92f3d1ae82`.

The context had 60 available dates at complete 20-symbol coverage. Feature diagnostics use an
explicit direction registry and genuine Spearman rank IC. Regime comparisons disclose 36 tests,
500-draw seeded bootstrap/permutation diagnostics, and use an exploratory 0.001 daily-effect
hypothesis threshold. ETF/sector context is unavailable.

Historical result: `C1. REGIME_HETEROGENEITY_HYPOTHESIS`. MR-2A is now
`SUPERSEDED_FOR_CURRENT_RESEARCH_AUTHORITY`: it repaired raw-bar leakage, but its absolute-return
conditionality and non-model-specific comparator cannot establish Candidate excess Alpha. The
historical output remains descriptive evidence only, not C2 replication, Formal OOS Alpha, a
winner selection, or a production Regime Gate. MR-2B is still incomplete.
