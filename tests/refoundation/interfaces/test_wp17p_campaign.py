from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from market_regime_alpha.interfaces.wp17p_campaign import Wp17pCampaignOperations
from market_regime_alpha.research_qualification.domain.exploratory_backtest import (
    BacktestArmKind,
    BacktestSessionRole,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)


def test_campaign_orders_preaccess_freeze_before_fit_and_validation_outcomes() -> None:
    calls: list[str] = []
    baseline = SimpleNamespace(
        exploratory_backtest_arm_id=uuid4(), kind=BacktestArmKind.RULE_BASELINE
    )
    challenger = SimpleNamespace(
        exploratory_backtest_arm_id=uuid4(), kind=BacktestArmKind.MODEL_CHALLENGER
    )
    fit_session = SimpleNamespace(
        exploratory_backtest_fold_session_id=uuid4(),
        role=BacktestSessionRole.FIT_INPUT,
    )
    validation_session = SimpleNamespace(
        exploratory_backtest_fold_session_id=uuid4(),
        role=BacktestSessionRole.EVALUATION,
    )
    fit_fold = SimpleNamespace(
        exploratory_backtest_fold_id=uuid4(),
        purpose=PartitionPurpose.FIT,
        sessions=(fit_session,),
    )
    validation_fold = SimpleNamespace(
        exploratory_backtest_fold_id=uuid4(),
        purpose=PartitionPurpose.VALIDATION,
        sessions=(validation_session,),
    )
    catalog = SimpleNamespace(
        backtest=SimpleNamespace(
            arms=(baseline, challenger), folds=(fit_fold, validation_fold)
        )
    )

    class Research:
        def register_catalog(self, catalog) -> None:
            calls.append("register")

        def materialize_dataset(self, **kwargs):
            arm_id = kwargs["exploratory_backtest_arm_id"]
            label = "baseline" if arm_id == baseline.exploratory_backtest_arm_id else "model"
            session_id = kwargs["exploratory_backtest_fold_session_id"]
            phase = "fit" if session_id == fit_session.exploratory_backtest_fold_session_id else "validation"
            calls.append(f"dataset:{phase}:{label}")
            return SimpleNamespace(dataset_id=uuid4())

    class Decisions:
        def execute(self, *, dataset, complete_decision_support, model_version_id=None, **kwargs):
            phase = "validation" if complete_decision_support else "fit"
            calls.append(f"decision:{phase}:{'model' if model_version_id else 'baseline'}")
            return SimpleNamespace(dataset_id=dataset.dataset_id, decision_run_id=uuid4())

    class Evaluations:
        def open(self, *, datasets, **kwargs):
            phase = "fit" if len(datasets) == 1 else "validation"
            calls.append(f"open:{phase}")
            return SimpleNamespace(evaluation_run_id=uuid4())

        def complete(self, *, opened, **kwargs):
            phase = "fit" if calls.count("open:validation") == 0 else "validation"
            calls.append(f"complete:{phase}")
            return SimpleNamespace(evaluation_run_id=opened.evaluation_run_id)

    class Outcomes:
        def settle(self, *, decision, **kwargs):
            phase = "fit" if calls.count("open:validation") == 0 else "validation"
            calls.append(f"outcome:{phase}")
            return SimpleNamespace(decision_run_id=decision.dataset_id)

    class Models:
        def train(self, **kwargs):
            calls.append("model")
            return SimpleNamespace(model_version_id=uuid4())

    operations = Wp17pCampaignOperations(
        SimpleNamespace(),
        code_sha="a" * 40,
        research=Research(),
        decisions=Decisions(),
        evaluations=Evaluations(),
        outcomes=Outcomes(),
        models=Models(),
    )

    operations.run(catalog=catalog, pilot_instrument_ids=tuple(uuid4() for _ in range(32)))

    assert calls.index("open:fit") < calls.index("outcome:fit")
    assert calls.index("complete:fit") < calls.index("model")
    assert calls.index("model") < calls.index("decision:validation:model")
    assert calls.index("open:validation") < calls.index("outcome:validation")
