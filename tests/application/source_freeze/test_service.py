from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from market_regime_alpha.application.source_freeze import SourceFreezeService


class _Executor:
    def prepare_history(self, command):
        return ("history", command)

    def freeze_security_status(self, command):
        return ("status", command)

    def freeze_supplemental(self, command):
        return ("supplemental", command)

    def freeze_decision_quote(self, command):
        return ("quote", command)

    def freeze_sources(self, command, *, replay_archive_path=None):
        return SimpleNamespace(
            record=command,
            source_archive_path=Path("archive"),
            acquired="acquired",
        )


def test_source_freeze_service_exposes_only_source_operations() -> None:
    executor = _Executor()
    service = SourceFreezeService(executor)  # type: ignore[arg-type]

    assert service.prepare_history("command") == ("history", "command")
    assert service.freeze("command").source_archive_path == Path("archive")
    assert not hasattr(service, "finalize_run")
    assert not hasattr(service, "run")


def test_canonical_free_data_composition_does_not_import_daily_loop_runner() -> None:
    source = Path(
        "src/market_regime_alpha/application/free_data_operation/service.py"
    ).read_text(encoding="utf-8")

    assert "DailyLoopRunner" not in source
    assert "freeze_sources(" not in source
