"""Phase 6-E Step 5: production E2E activation-review safety boundary.

This boundary connects the already-existing Final Live Readiness gate from the
production bundle to the Phase 6-E authorization and operator-review layers.
It is deliberately read-only: no Paper runtime start, recovery, unlock, broker
transport, network call, or live-order submission is exposed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.live.execution_mode import ExecutionModeSettings
from app.live.final_live_readiness import FinalLiveReadinessGate
from app.live.live_activation_authorization_composition import (
    ProductionLiveActivationAuthorizationFactory,
    ProductionLiveActivationReadOnlyProvidersLike,
)
from app.live.live_activation_operator_review import (
    LiveActivationOperatorReview,
)


class ProductionLiveActivationBundleLike(Protocol):
    final_live_readiness_gate: FinalLiveReadinessGate | None


@dataclass(frozen=True, slots=True)
class ProductionLiveActivationE2EReview:
    review: LiveActivationOperatorReview

    def evaluate(self):
        return self.review.evaluate()


class ProductionLiveActivationE2EFactory:
    """Compose Final Readiness -> Authorization -> Operator Review only."""

    @staticmethod
    def create(
        *,
        production_bundle: ProductionLiveActivationBundleLike,
        read_only_providers: ProductionLiveActivationReadOnlyProvidersLike,
        execution_settings: ExecutionModeSettings,
        trading_date: date,
    ) -> ProductionLiveActivationE2EReview:
        readiness_gate = production_bundle.final_live_readiness_gate
        if readiness_gate is None:
            raise ValueError(
                "Production bundle has no Final Live Readiness gate."
            )

        def final_readiness_activation_ready() -> bool:
            report = readiness_gate.check(
                execution_settings=execution_settings,
                trading_date=trading_date,
            )
            return report.activation_ready is True

        authorization_gate = (
            ProductionLiveActivationAuthorizationFactory.create(
                read_only_providers=read_only_providers,
                final_readiness_activation_ready_provider=(
                    final_readiness_activation_ready
                ),
            )
        )
        return ProductionLiveActivationE2EReview(
            review=LiveActivationOperatorReview(gate=authorization_gate)
        )
