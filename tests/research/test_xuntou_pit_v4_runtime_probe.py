from market_regime_alpha.research.xuntou_pit_v4_runtime import probe_xtquant_pit_capabilities


def test_runtime_probe_never_infers_semantics_from_method_presence() -> None:
    probe = probe_xtquant_pit_capabilities(importer=lambda _: object())
    assert probe["historical_membership_capability"]["status"] == "UNVERIFIED"
    assert probe["historical_quote_capability"]["status"] == "UNVERIFIED"
    assert probe["research_evidence_produced"] is False
