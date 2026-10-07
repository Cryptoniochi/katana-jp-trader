"""Phase 6-E Step 4: one-shot read-only activation review CLI boundary.

The CLI accepts an already-composed operator review object through ``run_once``.
It only evaluates once and prints JSON. It cannot compose/start Paper runtime,
unlock Live execution, recover state, access a broker, or submit an order.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Protocol, TextIO
import sys

from app.live.live_activation_operator_review import (
    LiveActivationOperatorReview,
)


class LiveActivationOperatorReviewLike(Protocol):
    def evaluate(self): ...


def run_once(
    *,
    review: LiveActivationOperatorReviewLike,
    output: TextIO,
) -> int:
    """Evaluate exactly once, print the read-only review, and return status."""

    report = review.evaluate()
    output.write(LiveActivationOperatorReview.to_json(report))
    output.write("\n")
    return 0 if report.authorization_ready else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render one read-only Project KATANA Live activation review. "
            "This command does not enable Live trading."
        )
    )
    parser.add_argument(
        "--stdin-composition-only",
        action="store_true",
        help=(
            "Reserved marker for Phase 6-E: the CLI has no production "
            "composition root yet and cannot activate Live trading."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.error(
        "Phase 6-E Step 4 is a dependency-injected read-only CLI boundary. "
        "Production composition is intentionally not attached yet."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
