"""Phase 6-F Step 1: read-only Live activation transition contract.

Models the ordered readiness transition after Phase 6-E operator review.
This module is deliberately side-effect free: it cannot unlock runtime
integration, broker transport, or live order transmission.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.live.live_activation_authorization import (
    LiveActivationAuthorizationReport,
)


class LiveActivationTransitionState(StrEnum):
    LOCKED = "locked"
    AUTHORIZATION_READY = "authorization_ready"
    RUNTIME_ACTIVATION_READY = "runtime_activation_ready"
    TRANSPORT_ACTIVATION_READY = "transport_activation_ready"
    ORDER_TRANSMISSION_ACTIVATION_READY = "order_transmission_activation_ready"


@dataclass(frozen=True, slots=True)
class LiveActivationTransitionReport:
    generated_at: datetime
    state: LiveActivationTransitionState
    authorization_ready: bool
    runtime_activation_ready: bool
    transport_activation_ready: bool
    order_transmission_activation_ready: bool
    message: str

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware.")

        if self.transport_activation_ready and not self.runtime_activation_ready:
            raise ValueError(
                "transport activation cannot be ready before runtime activation."
            )
        if (
            self.order_transmission_activation_ready
            and not self.transport_activation_ready
        ):
            raise ValueError(
                "order transmission cannot be ready before transport activation."
            )


class LiveActivationTransition:
    """Evaluate the future activation sequence without performing activation."""

    @staticmethod
    def evaluate(
        *,
        authorization_report: LiveActivationAuthorizationReport,
        runtime_prerequisites_ready: bool = False,
        transport_prerequisites_ready: bool = False,
        order_transmission_prerequisites_ready: bool = False,
    ) -> LiveActivationTransitionReport:
        authorization_ready = authorization_report.authorization_ready is True

        runtime_ready = (
            authorization_ready
            and runtime_prerequisites_ready is True
        )
        transport_ready = (
            runtime_ready
            and transport_prerequisites_ready is True
        )
        order_ready = (
            transport_ready
            and order_transmission_prerequisites_ready is True
        )

        if order_ready:
            state = (
                LiveActivationTransitionState.ORDER_TRANSMISSION_ACTIVATION_READY
            )
            message = (
                "All modeled activation prerequisites are ready. "
                "No Live execution lock has been changed."
            )
        elif transport_ready:
            state = LiveActivationTransitionState.TRANSPORT_ACTIVATION_READY
            message = (
                "Transport activation prerequisites are ready; "
                "order transmission remains not ready."
            )
        elif runtime_ready:
            state = LiveActivationTransitionState.RUNTIME_ACTIVATION_READY
            message = (
                "Runtime activation prerequisites are ready; "
                "transport and order transmission remain not ready."
            )
        elif authorization_ready:
            state = LiveActivationTransitionState.AUTHORIZATION_READY
            message = (
                "Authorization is ready; all execution activation stages "
                "remain not ready."
            )
        else:
            state = LiveActivationTransitionState.LOCKED
            message = "Live activation remains locked."

        return LiveActivationTransitionReport(
            generated_at=authorization_report.generated_at,
            state=state,
            authorization_ready=authorization_ready,
            runtime_activation_ready=runtime_ready,
            transport_activation_ready=transport_ready,
            order_transmission_activation_ready=order_ready,
            message=message,
        )
