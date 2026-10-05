"""Operator CLI for the durable manual Live Kill Switch.

This command only reads or writes the local manual Kill Switch state file.
It does not connect to kabu Station, submit orders, or enable Live execution.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from app.live.live_manual_kill_switch_state import ManualKillSwitchState
from app.live.live_manual_kill_switch_state_reader import ManualKillSwitchStateReader
from app.live.live_manual_kill_switch_state_writer import ManualKillSwitchStateWriter
from app.settings import ROOT_DIR


DEFAULT_MANUAL_KILL_SWITCH_STATE_PATH = (
    ROOT_DIR / "reports/live/manual_kill_switch_state.json"
).resolve()
RELEASE_CONFIRMATION_TOKEN = "RELEASE"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or explicitly change the manual Live Kill Switch.",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=DEFAULT_MANUAL_KILL_SWITCH_STATE_PATH,
        help="Override the durable manual Kill Switch state path.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "status",
        help="Read the current state without changing it.",
    )

    engage_parser = subparsers.add_parser(
        "engage",
        help="Block Live new-entry eligibility immediately.",
    )
    engage_parser.add_argument(
        "--reason",
        required=True,
        help="Non-empty operator reason recorded in the durable state.",
    )

    release_parser = subparsers.add_parser(
        "release",
        help="Release only the manual block; all other Live locks remain unchanged.",
    )
    release_parser.add_argument(
        "--reason",
        required=True,
        help="Non-empty operator reason recorded in the durable state.",
    )
    release_parser.add_argument(
        "--confirm",
        required=True,
        help=f"Must be exactly {RELEASE_CONFIRMATION_TOKEN}.",
    )

    return parser


def _validated_reason(parser: argparse.ArgumentParser, reason: str) -> str:
    normalized = reason.strip()
    if not normalized:
        parser.error("--reason must not be empty.")
    return normalized


def _print_state(state: ManualKillSwitchState) -> None:
    status = "BLOCKED" if state.manual_blocked else "RELEASED"
    print(f"manual_kill_switch={status}")
    print(f"manual_blocked={str(state.manual_blocked).lower()}")
    print(f"updated_at={state.updated_at.isoformat()}")
    print(f"reason={state.reason}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    state_path = Path(args.state_path).resolve()

    if args.command == "status":
        state = ManualKillSwitchStateReader(state_path).read_state()
        _print_state(state)
        return 0

    reason = _validated_reason(parser, args.reason)

    if args.command == "engage":
        state = ManualKillSwitchStateWriter(state_path).engage(reason=reason)
        _print_state(state)
        return 0

    if args.command == "release":
        if args.confirm != RELEASE_CONFIRMATION_TOKEN:
            parser.error(
                "--confirm must be exactly "
                f"{RELEASE_CONFIRMATION_TOKEN}; manual release was not written."
            )
        state = ManualKillSwitchStateWriter(state_path).release(reason=reason)
        _print_state(state)
        return 0

    parser.error("Unsupported command.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
