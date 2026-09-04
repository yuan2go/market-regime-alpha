from __future__ import annotations

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
