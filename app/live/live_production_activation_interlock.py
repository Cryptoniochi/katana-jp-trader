"""Final static interlock for concrete Live production activation."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LiveProductionInterlockState:
    runtime_integration_enabled: bool
    broker_transport_enabled: bool
    order_transmission_enabled: bool

    @property
    def released(self) -> bool:
        return (
            self.runtime_integration_enabled
            and self.broker_transport_enabled
            and self.order_transmission_enabled
        )


class LiveProductionActivationInterlock:
    """Require all three reviewed static hard locks before concrete Live starts."""

    @staticmethod
    def state() -> LiveProductionInterlockState:
        from app.live.locked_live_runtime_integration import (
            LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
        )
        from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
        from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
        return LiveProductionInterlockState(
            runtime_integration_enabled=bool(
                LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED
            ),
            broker_transport_enabled=bool(LIVE_BROKER_TRANSPORT_ENABLED),
            order_transmission_enabled=bool(LIVE_ORDER_TRANSMISSION_ENABLED),
        )

    @classmethod
    def require_released(cls) -> LiveProductionInterlockState:
        state=cls.state()
        if not state.released:
            raise RuntimeError(
                "Concrete Live production remains hard-locked. "
                "Runtime integration, broker transport, and order transmission "
                "must all be explicitly enabled after activation review."
            )
        return state
