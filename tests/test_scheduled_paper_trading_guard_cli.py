"""Scheduled Paper Trading CLIのGuard設定テスト。"""

from app.run_scheduled_paper_trading import (
    build_argument_parser,
)


def test_guard_is_enabled_by_default() -> None:
    parsed = build_argument_parser().parse_args([])

    assert not parsed.skip_autonomous_guard


def test_guard_can_be_skipped_explicitly() -> None:
    parsed = build_argument_parser().parse_args(
        ["--skip-autonomous-guard"]
    )

    assert parsed.skip_autonomous_guard
