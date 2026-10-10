"""Phase 6-F explicit activated-live composition.

No existing locked-live composition is modified by this module.
Construction requires the caller to explicitly supply the kabu Station sender
and activation/runtime flags. Defaults are fail-closed.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.live.activated_live_broker_transport import ActivatedKabuStationLiveTransport
from app.live.activated_live_submission_coordinator import (
    ActivatedLiveSubmissionCoordinator,
)
from app.live.execution_mode import ExecutionModeSettings
from app.live.kabu_station_cash_order_sender import KabuStationCashOrderSender
from app.live.live_execution_journal_repository import SQLiteLiveExecutionJournal
from app.live.live_submission_boundary import LockedLiveSubmissionBoundary


NowProvider = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class ActivatedLiveRuntimeBundle:
    journal: SQLiteLiveExecutionJournal
    submission_boundary: LockedLiveSubmissionBoundary
    transport: ActivatedKabuStationLiveTransport
    submission_coordinator: ActivatedLiveSubmissionCoordinator


class ActivatedLiveRuntimeFactory:
    @staticmethod
    def create(
        *,
        database_path: Path,
        sender: KabuStationCashOrderSender,
        execution_settings: ExecutionModeSettings,
        activation_enabled: bool = False,
        runtime_armed: bool = False,
        now_provider: NowProvider | None = None,
    ) -> ActivatedLiveRuntimeBundle:
        journal = SQLiteLiveExecutionJournal(
            Path(database_path),
            now_provider=now_provider,
        )
        boundary = LockedLiveSubmissionBoundary(
            journal=journal,
            now_provider=now_provider,
        )
        transport = ActivatedKabuStationLiveTransport(
            sender=sender,
            execution_settings=execution_settings,
            activation_enabled=activation_enabled,
            runtime_armed=runtime_armed,
            now_provider=now_provider,
        )
        coordinator = ActivatedLiveSubmissionCoordinator(
            journal=journal,
            submission_boundary=boundary,
            transport=transport,
            now_provider=now_provider,
        )
        return ActivatedLiveRuntimeBundle(
            journal=journal,
            submission_boundary=boundary,
            transport=transport,
            submission_coordinator=coordinator,
        )
