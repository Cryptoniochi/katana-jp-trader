"""Phase 6-E Step 3: read-only operator review/report boundary.

Formats a Live activation authorization result for human review. This module
has no capability to unlock, arm, execute, recover, transmit, or submit orders.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Protocol

from app.live.live_activation_authorization import (
    LiveActivationAuthorizationReport,
)


class LiveActivationAuthorizationGateLike(Protocol):
    def check(self) -> LiveActivationAuthorizationReport: ...


class LiveActivationOperatorReview:
    """Evaluate the authorization gate once and render a read-only report."""

    def __init__(self, *, gate: LiveActivationAuthorizationGateLike) -> None:
        self.gate = gate

    def evaluate(self) -> LiveActivationAuthorizationReport:
        return self.gate.check()

    @staticmethod
    def to_dict(report: LiveActivationAuthorizationReport) -> dict[str, object]:
        return {
            "generated_at": report.generated_at.isoformat(),
            "authorization_ready": report.authorization_ready,
            "state": report.state.value,
            "items": [
                {
                    "key": item.key,
                    "passed": item.passed,
                    "message": item.message,
                }
                for item in report.items
            ],
            "operator_notice": (
                "READ-ONLY REVIEW ONLY. AUTHORIZATION_READY does not enable "
                "Live runtime integration, broker transport, or order transmission."
            ),
        }

    @classmethod
    def to_json(
        cls,
        report: LiveActivationAuthorizationReport,
        *,
        indent: int = 2,
    ) -> str:
        return json.dumps(
            cls.to_dict(report),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )
