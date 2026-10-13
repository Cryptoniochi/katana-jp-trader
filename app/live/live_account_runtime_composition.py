"""Compose authoritative read-only account state for the dedicated Live runtime.

This module is intentionally separate from ``PaperTradingComposition``.  It
constructs broker-backed Live account/risk/position providers, but construction
itself performs no network access and cannot submit or cancel orders.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.live.kabu_station_read_only import (
    KabuStationReadOnlyReportWriter,
    KabuStationReadOnlyService,
)
from app.live.live_account_risk_portfolio import (
    KabuStationLivePositionProvider,
    KabuStationLiveRiskPortfolioProvider,
)
from app.live.live_account_state_service import KabuStationLiveAccountStateService
from app.live.live_daily_loss_state import (
    DailyClosedTradeRepository,
    LiveDailyLossStateProvider,
)
from app.live.live_equity_peak_state import LiveEquityPeakStore
from app.market.kabu_station_client import KabuStationClient


NowProvider = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class LiveAccountRuntimeProviders:
    """Authoritative broker-backed inputs reserved for the Live runtime."""

    account_state_service: KabuStationLiveAccountStateService
    risk_portfolio_provider: KabuStationLiveRiskPortfolioProvider
    position_provider: KabuStationLivePositionProvider


class LiveAccountRuntimeProviderFactory:
    """Build dedicated Live providers without touching PaperBroker.

    Network reads happen only when a returned provider is evaluated.  This
    keeps composition safe to construct while ensuring each Live risk/position
    decision refreshes the real kabu Station account and fails closed on an
    incomplete broker snapshot.
    """

    @staticmethod
    def create(
        *,
        kabu_client: KabuStationClient,
        daily_trade_repository: DailyClosedTradeRepository,
        kabu_station_report_path: Path,
        live_equity_peak_path: Path,
        now_provider: NowProvider | None = None,
    ) -> LiveAccountRuntimeProviders:
        effective_now_provider = now_provider or (
            lambda: datetime.now(timezone.utc)
        )

        read_only_service = KabuStationReadOnlyService(
            client=kabu_client,
            now_provider=effective_now_provider,
        )
        account_state_service = KabuStationLiveAccountStateService(
            read_only_service=read_only_service,
            report_writer=KabuStationReadOnlyReportWriter(
                Path(kabu_station_report_path)
            ),
        )
        daily_loss_state = LiveDailyLossStateProvider(
            repository=daily_trade_repository,
            now_provider=effective_now_provider,
        )
        peak_store = LiveEquityPeakStore(
            Path(live_equity_peak_path),
            now_provider=effective_now_provider,
        )
        risk_portfolio_provider = KabuStationLiveRiskPortfolioProvider(
            account_state_service=account_state_service,
            daily_profit_loss_provider=(
                daily_loss_state.daily_realized_profit_loss
            ),
            consecutive_loss_count_provider=(
                daily_loss_state.consecutive_loss_count
            ),
            peak_equity_provider=peak_store.peak_equity,
            now_provider=effective_now_provider,
        )
        position_provider = KabuStationLivePositionProvider(
            account_state_service=account_state_service,
        )
        return LiveAccountRuntimeProviders(
            account_state_service=account_state_service,
            risk_portfolio_provider=risk_portfolio_provider,
            position_provider=position_provider,
        )
