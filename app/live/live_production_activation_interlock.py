"""Production activation interlock for the concrete Live runtime.

The legacy Phase 6-C hard locks are intentionally kept False forever.  They
protect the historical locked pipeline and must never be opened merely to run
the reviewed activated production transport.

Concrete production instead requires an independent explicit environment gate:
KATANA_LIVE_PRODUCTION_ENABLED=YES.

Daily LIVE arming and the date-specific confirmation remain separate gates in
ExecutionModeSettings / LiveArmingPolicy and are rechecked by the activated
broker transport.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


LIVE_PRODUCTION_ENABLE_VARIABLE = "KATANA_LIVE_PRODUCTION_ENABLED"
LIVE_PRODUCTION_ENABLE_VALUE = "YES"


@dataclass(frozen=True, slots=True)
class LiveProductionInterlockState:
    legacy_runtime_integration_enabled: bool
    legacy_broker_transport_enabled: bool
    legacy_order_transmission_enabled: bool
    production_activation_enabled: bool

    @property
    def legacy_locks_sealed(self) -> bool:
        return not (
            self.legacy_runtime_integration_enabled
            or self.legacy_broker_transport_enabled
            or self.legacy_order_transmission_enabled
        )

    @property
    def released(self) -> bool:
        return self.legacy_locks_sealed and self.production_activation_enabled


class LiveProductionActivationInterlock:
    """Open only the reviewed activated path; keep all legacy paths sealed."""

    @staticmethod
    def state(
        environment: Mapping[str, str] | None = None,
    ) -> LiveProductionInterlockState:
        from app.live.locked_live_runtime_integration import (
            LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
        )
        from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
        from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED

        env = environment or {}
        production_activation_enabled = (
            str(env.get(LIVE_PRODUCTION_ENABLE_VARIABLE, ""))
            .strip()
            .upper()
            == LIVE_PRODUCTION_ENABLE_VALUE
        )

        return LiveProductionInterlockState(
            legacy_runtime_integration_enabled=bool(
                LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED
            ),
            legacy_broker_transport_enabled=bool(
                LIVE_BROKER_TRANSPORT_ENABLED
            ),
            legacy_order_transmission_enabled=bool(
                LIVE_ORDER_TRANSMISSION_ENABLED
            ),
            production_activation_enabled=production_activation_enabled,
        )

    @classmethod
    def require_released(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> LiveProductionInterlockState:
        state = cls.state(environment)

        if not state.legacy_locks_sealed:
            raise RuntimeError(
                "Legacy Live hard locks must remain sealed. "
                "Do not enable the Phase 6-C runtime integration, broker "
                "transport, or order transmission constants."
            )

        if not state.production_activation_enabled:
            raise RuntimeError(
                f"Concrete Live production is disabled. "
                f"Set {LIVE_PRODUCTION_ENABLE_VARIABLE}="
                f"{LIVE_PRODUCTION_ENABLE_VALUE} only after the final "
                "production activation review."
            )

        return state
