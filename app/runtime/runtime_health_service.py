"""Trading Runtimeの自己診断を実行する。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from app.runtime.paper_trading_runtime_models import (
    PaperTradingRuntimeStatus,
)
from app.runtime.runtime_health_models import (
    RuntimeHealthCheck,
    RuntimeHealthReport,
    RuntimeHealthStatus,
)


class RuntimeStatusReader(Protocol):
    """Runtime状態を取得できるオブジェクト。"""

    @property
    def status(self) -> PaperTradingRuntimeStatus | None:
        """現在のRuntime状態を返す。"""


class PortfolioHealthReader(Protocol):
    """Portfolio Snapshotを取得できるオブジェクト。"""

    def create_snapshot(
        self,
        *,
        generated_at: datetime | None = None,
    ) -> Any:
        """現在のPortfolio Snapshotを返す。"""


class RuntimeHealthService:
    """Trading Runtimeの主要コンポーネントを自己診断する。"""

    RUNTIME_CHECK_NAME = "runtime"
    PORTFOLIO_CHECK_NAME = "portfolio"
    BROKER_CHECK_NAME = "broker"
    REPOSITORY_CHECK_NAME = "repository"
    MARKET_DATA_CHECK_NAME = "market_data"

    def __init__(
        self,
        *,
        runtime: RuntimeStatusReader | None = None,
        portfolio_reader: PortfolioHealthReader | None = None,
        broker_probe: Callable[[], Any] | None = None,
        repository_probes: Iterable[
            tuple[str, Callable[[], Any]]
        ] = (),
        market_data_time_provider: (
            Callable[[], datetime | None] | None
        ) = None,
        market_data_warning_after: timedelta = timedelta(
            minutes=5
        ),
        market_data_error_after: timedelta = timedelta(
            minutes=15
        ),
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """診断対象、閾値、時計を設定する。"""

        if market_data_warning_after <= timedelta(0):
            raise ValueError(
                "Market Data警告閾値は0より大きい必要があります。"
            )

        if market_data_error_after <= (
            market_data_warning_after
        ):
            raise ValueError(
                "Market Dataエラー閾値は警告閾値より"
                "大きい必要があります。"
            )

        normalized_repository_probes = tuple(
            repository_probes
        )
        probe_names: set[str] = set()

        for name, probe in normalized_repository_probes:
            normalized_name = name.strip()

            if not normalized_name:
                raise ValueError(
                    "Repository診断名を指定してください。"
                )

            if normalized_name in probe_names:
                raise ValueError(
                    "Repository診断名が重複しています。 "
                    f"name={normalized_name}"
                )

            if not callable(probe):
                raise TypeError(
                    "Repository診断処理は呼び出し可能である"
                    "必要があります。"
                )

            probe_names.add(normalized_name)

        self.runtime = runtime
        self.portfolio_reader = portfolio_reader
        self.broker_probe = broker_probe
        self.repository_probes = tuple(
            (
                name.strip(),
                probe,
            )
            for name, probe in normalized_repository_probes
        )
        self.market_data_time_provider = (
            market_data_time_provider
        )
        self.market_data_warning_after = (
            market_data_warning_after
        )
        self.market_data_error_after = (
            market_data_error_after
        )
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def check(self) -> RuntimeHealthReport:
        """設定済みの全診断を実行してレポートを返す。"""

        checked_at = self._current_time()
        checks: list[RuntimeHealthCheck] = []

        if self.runtime is not None:
            checks.append(
                self._check_runtime(
                    checked_at=checked_at
                )
            )

        if self.portfolio_reader is not None:
            checks.append(
                self._check_portfolio(
                    checked_at=checked_at
                )
            )

        if self.broker_probe is not None:
            checks.append(
                self._run_probe(
                    name=self.BROKER_CHECK_NAME,
                    success_message="Brokerは応答しています。",
                    failure_prefix="Broker診断に失敗しました。",
                    probe=self.broker_probe,
                    checked_at=checked_at,
                )
            )

        if self.repository_probes:
            checks.append(
                self._check_repositories(
                    checked_at=checked_at
                )
            )

        if self.market_data_time_provider is not None:
            checks.append(
                self._check_market_data(
                    checked_at=checked_at
                )
            )

        return RuntimeHealthReport.create(
            checks=checks,
            generated_at=checked_at,
        )

    def _check_runtime(
        self,
        *,
        checked_at: datetime,
    ) -> RuntimeHealthCheck:
        """Runtime状態を診断する。"""

        try:
            status = self.runtime.status
        except Exception as error:
            return self._error_check(
                name=self.RUNTIME_CHECK_NAME,
                message="Runtime状態の取得に失敗しました。",
                error=error,
                checked_at=checked_at,
            )

        if status is PaperTradingRuntimeStatus.RUNNING:
            return RuntimeHealthCheck(
                name=self.RUNTIME_CHECK_NAME,
                status=RuntimeHealthStatus.OK,
                message="Runtimeは稼働中です。",
                checked_at=checked_at,
                details={
                    "runtime_status": status.value,
                },
            )

        if status is None:
            return RuntimeHealthCheck(
                name=self.RUNTIME_CHECK_NAME,
                status=RuntimeHealthStatus.WARNING,
                message="Runtimeはまだ開始されていません。",
                checked_at=checked_at,
                details={
                    "runtime_status": None,
                },
            )

        if status is PaperTradingRuntimeStatus.COMPLETED:
            return RuntimeHealthCheck(
                name=self.RUNTIME_CHECK_NAME,
                status=RuntimeHealthStatus.WARNING,
                message="Runtimeは正常終了済みです。",
                checked_at=checked_at,
                details={
                    "runtime_status": status.value,
                },
            )

        return RuntimeHealthCheck(
            name=self.RUNTIME_CHECK_NAME,
            status=RuntimeHealthStatus.ERROR,
            message="Runtimeは異常終了しています。",
            checked_at=checked_at,
            details={
                "runtime_status": status.value,
            },
        )

    def _check_portfolio(
        self,
        *,
        checked_at: datetime,
    ) -> RuntimeHealthCheck:
        """Portfolio Snapshot取得と主要数値を診断する。"""

        try:
            snapshot = self.portfolio_reader.create_snapshot(
                generated_at=checked_at
            )
            equity = float(snapshot.broker_equity)
            cash_balance = float(snapshot.cash_balance)
            buying_power = float(snapshot.buying_power)
        except Exception as error:
            return self._error_check(
                name=self.PORTFOLIO_CHECK_NAME,
                message="Portfolio診断に失敗しました。",
                error=error,
                checked_at=checked_at,
            )

        values = {
            "broker_equity": equity,
            "cash_balance": cash_balance,
            "buying_power": buying_power,
        }

        if any(
            not self._is_finite_number(value)
            for value in values.values()
        ):
            return RuntimeHealthCheck(
                name=self.PORTFOLIO_CHECK_NAME,
                status=RuntimeHealthStatus.ERROR,
                message="Portfolioに不正な数値があります。",
                checked_at=checked_at,
                details=values,
            )

        if equity < 0 or cash_balance < 0 or buying_power < 0:
            return RuntimeHealthCheck(
                name=self.PORTFOLIO_CHECK_NAME,
                status=RuntimeHealthStatus.ERROR,
                message="Portfolioに負の残高があります。",
                checked_at=checked_at,
                details=values,
            )

        return RuntimeHealthCheck(
            name=self.PORTFOLIO_CHECK_NAME,
            status=RuntimeHealthStatus.OK,
            message="Portfolioは正常に取得できました。",
            checked_at=checked_at,
            details=values,
        )

    def _check_repositories(
        self,
        *,
        checked_at: datetime,
    ) -> RuntimeHealthCheck:
        """設定済みRepositoryをまとめて診断する。"""

        failures: dict[str, str] = {}
        successful_names: list[str] = []

        for name, probe in self.repository_probes:
            try:
                probe()
            except Exception as error:
                failures[name] = (
                    f"{type(error).__name__}: {error}"
                )
            else:
                successful_names.append(name)

        details = {
            "successful": tuple(successful_names),
            "failed": failures,
        }

        if failures:
            return RuntimeHealthCheck(
                name=self.REPOSITORY_CHECK_NAME,
                status=RuntimeHealthStatus.ERROR,
                message=(
                    "一部のRepository診断に失敗しました。"
                ),
                checked_at=checked_at,
                details=details,
            )

        return RuntimeHealthCheck(
            name=self.REPOSITORY_CHECK_NAME,
            status=RuntimeHealthStatus.OK,
            message="Repositoryは正常に応答しています。",
            checked_at=checked_at,
            details=details,
        )

    def _check_market_data(
        self,
        *,
        checked_at: datetime,
    ) -> RuntimeHealthCheck:
        """最終Market Data更新日時を診断する。"""

        try:
            last_updated_at = (
                self.market_data_time_provider()
            )
        except Exception as error:
            return self._error_check(
                name=self.MARKET_DATA_CHECK_NAME,
                message="Market Data更新日時の取得に失敗しました。",
                error=error,
                checked_at=checked_at,
            )

        if last_updated_at is None:
            return RuntimeHealthCheck(
                name=self.MARKET_DATA_CHECK_NAME,
                status=RuntimeHealthStatus.WARNING,
                message="Market Dataはまだ受信されていません。",
                checked_at=checked_at,
                details={
                    "last_updated_at": None,
                },
            )

        if last_updated_at.tzinfo is None:
            return RuntimeHealthCheck(
                name=self.MARKET_DATA_CHECK_NAME,
                status=RuntimeHealthStatus.ERROR,
                message=(
                    "Market Data更新日時にタイムゾーンが"
                    "ありません。"
                ),
                checked_at=checked_at,
                details={
                    "last_updated_at": (
                        last_updated_at.isoformat()
                    ),
                },
            )

        normalized_updated_at = (
            last_updated_at.astimezone(timezone.utc)
        )
        age = checked_at - normalized_updated_at

        if age < timedelta(0):
            return RuntimeHealthCheck(
                name=self.MARKET_DATA_CHECK_NAME,
                status=RuntimeHealthStatus.WARNING,
                message=(
                    "Market Data更新日時が現在時刻より"
                    "未来です。"
                ),
                checked_at=checked_at,
                details=self._market_data_details(
                    last_updated_at=normalized_updated_at,
                    age=age,
                ),
            )

        if age >= self.market_data_error_after:
            status = RuntimeHealthStatus.ERROR
            message = (
                "Market Dataの更新が停止している可能性が"
                "あります。"
            )
        elif age >= self.market_data_warning_after:
            status = RuntimeHealthStatus.WARNING
            message = (
                "Market Dataの更新が遅延しています。"
            )
        else:
            status = RuntimeHealthStatus.OK
            message = (
                "Market Dataは正常に更新されています。"
            )

        return RuntimeHealthCheck(
            name=self.MARKET_DATA_CHECK_NAME,
            status=status,
            message=message,
            checked_at=checked_at,
            details=self._market_data_details(
                last_updated_at=normalized_updated_at,
                age=age,
            ),
        )

    def _run_probe(
        self,
        *,
        name: str,
        success_message: str,
        failure_prefix: str,
        probe: Callable[[], Any],
        checked_at: datetime,
    ) -> RuntimeHealthCheck:
        """任意の疎通確認処理を実行する。"""

        try:
            result = probe()
        except Exception as error:
            return self._error_check(
                name=name,
                message=failure_prefix,
                error=error,
                checked_at=checked_at,
            )

        return RuntimeHealthCheck(
            name=name,
            status=RuntimeHealthStatus.OK,
            message=success_message,
            checked_at=checked_at,
            details={
                "result_type": type(result).__name__,
            },
        )

    @staticmethod
    def _error_check(
        *,
        name: str,
        message: str,
        error: Exception,
        checked_at: datetime,
    ) -> RuntimeHealthCheck:
        """例外情報を含むERROR診断結果を生成する。"""

        return RuntimeHealthCheck(
            name=name,
            status=RuntimeHealthStatus.ERROR,
            message=message,
            checked_at=checked_at,
            details={
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        )

    def _current_time(self) -> datetime:
        """現在時刻をUTCへ正規化して返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)

    @staticmethod
    def _is_finite_number(
        value: float,
    ) -> bool:
        """有限の数値か返す。"""

        return value == value and value not in {
            float("inf"),
            float("-inf"),
        }

    @staticmethod
    def _market_data_details(
        *,
        last_updated_at: datetime,
        age: timedelta,
    ) -> dict[str, Any]:
        """Market Data診断の詳細情報を生成する。"""

        return {
            "last_updated_at": (
                last_updated_at.isoformat()
            ),
            "age_seconds": age.total_seconds(),
        }
