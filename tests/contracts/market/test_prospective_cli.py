from __future__ import annotations

import pytest

from market_regime_alpha.interfaces.cli.main import _parser


def test_generic_prospective_operator_commands_are_explicit() -> None:
    parser = _parser()
    common = [
        "--manifest",
        "manifest.json",
        "--code-sha",
        "1" * 40,
        "--expected-database-name",
        "mra_operational",
    ]

    planned = parser.parse_args(["archive", "prospective", "plan-next", *common])
    predeclared = parser.parse_args(
        [
            "archive",
            "prospective",
            "predeclare",
            *common,
            "--actor-id",
            "operator",
        ]
    )
    due = parser.parse_args(
        [
            "archive",
            "prospective",
            "run-due",
            *common,
            "--actor-id",
            "operator",
            "--worker-id",
            "worker",
        ]
    )

    assert planned.prospective_command == "plan-next"
    assert predeclared.prospective_command == "predeclare"
    assert due.prospective_command == "run-due"


@pytest.mark.parametrize('command', ('continue', 'predeclare', 'run-due', 'resume'))
def test_unguarded_prospective_write_commands_stop_before_any_database_or_provider_access(monkeypatch, command):
    from importlib import import_module
    from io import StringIO
    module = import_module('market_regime_alpha.interfaces.cli.main')
    def forbidden(*_, **__):
        pytest.fail('unguarded command reached database or Provider composition')
    monkeypatch.setattr(module, 'require_isolated_operational_target', forbidden)
    monkeypatch.setattr(module, 'bootstrap_application', forbidden)
    options = ['--code-sha', '1'*40, '--expected-database-name', 'mra_operational', '--actor-id', 'operator']
    if command == 'continue':
        options += ['--series-code', 'series']
    else:
        options += ['--manifest', 'unread-frozen-manifest.json']
    if command != 'predeclare':
        options += ['--worker-id', 'worker']
    output, errors = StringIO(), StringIO()
    code = module.main(['archive', 'prospective', command, *options],
        environ={'MRA_DATABASE_URL': 'postgresql://localhost/mra_operational', 'MRA_ARTIFACT_ROOT': '/evidence/artifacts'},
        stdout=output, stderr=errors)
    assert code == 2
    assert 'OPERATION_GUARDED_PROSPECTIVE_ENTRY_REQUIRED' in errors.getvalue()
    assert output.getvalue() == ''


@pytest.mark.parametrize('command', ('start', 'resume', 'retry'))
def test_generic_archive_mutation_cannot_bypass_prospective_guard(monkeypatch, command):
    from importlib import import_module
    from io import StringIO
    from types import SimpleNamespace
    from market_regime_alpha.market.domain import ArchiveLane
    module = import_module('market_regime_alpha.interfaces.cli.main')
    def forbidden(*_, **__):
        pytest.fail('prospective manifest reached unguarded database composition')
    monkeypatch.setattr(module, 'require_isolated_operational_target', forbidden)
    monkeypatch.setattr(module, 'bootstrap_application', forbidden)
    monkeypatch.setattr(module, 'load_archive_manifest', lambda _: SimpleNamespace(
        start_request=SimpleNamespace(lane=ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS)))
    options = ['--manifest', 'frozen-prospective-manifest.json', '--expected-database-name', 'mra_operational', '--actor-id', 'operator']
    if command != 'start':
        options += ['--operation-key', 'exact-operation']
    output, errors = StringIO(), StringIO()
    code = module.main(['archive', command, *options],
        environ={'MRA_DATABASE_URL': 'postgresql://localhost/mra_operational', 'MRA_ARTIFACT_ROOT': '/evidence/artifacts'},
        stdout=output, stderr=errors)
    assert code == 2
    assert 'OPERATION_GUARDED_PROSPECTIVE_ENTRY_REQUIRED' in errors.getvalue()
    assert output.getvalue() == ''


def test_retrospective_archive_entry_retains_its_existing_explicit_scope_check(monkeypatch):
    from contextlib import contextmanager
    from importlib import import_module
    from io import StringIO
    from types import SimpleNamespace
    from market_regime_alpha.market.domain import ArchiveLane
    module = import_module('market_regime_alpha.interfaces.cli.main')
    manifest = SimpleNamespace(start_request=SimpleNamespace(lane=ArchiveLane.RETROSPECTIVE_BACKFILL))
    events = []
    def load(path):
        events.append('manifest')
        return manifest
    def scope(settings, **kwargs):
        assert kwargs['expected_database_name'] == 'mra_operational'
        events.append('scope')
    @contextmanager
    def bootstrap(settings):
        events.append('composition')
        yield object()
    def start(app, actual, **kwargs):
        assert actual is manifest and kwargs['actor_id'] == 'operator'
        events.append('canonical-start')
        return {'state': 'RETROSPECTIVE_FIXTURE'}
    monkeypatch.setattr(module, 'load_archive_manifest', load)
    monkeypatch.setattr(module, 'require_isolated_operational_target', scope)
    monkeypatch.setattr(module, 'bootstrap_application', bootstrap)
    monkeypatch.setattr(module, 'start_archive', start)
    output, errors = StringIO(), StringIO()
    assert module.main(['archive', 'start', '--manifest', 'retrospective.json',
        '--expected-database-name', 'mra_operational', '--actor-id', 'operator'],
        environ={'MRA_DATABASE_URL': 'postgresql://localhost/mra_operational', 'MRA_ARTIFACT_ROOT': '/evidence/artifacts'},
        stdout=output, stderr=errors) == 0
    assert events == ['manifest', 'scope', 'composition', 'canonical-start']
    assert 'RETROSPECTIVE_FIXTURE' in output.getvalue()
    assert errors.getvalue() == ''
