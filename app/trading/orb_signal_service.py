"""5分足からORBシグナルを生成してSQLiteへ保存する。"""

from dataclasses import dataclass
from typing import Protocol

from app.market.models import StockPrice
from app.strategy.orb_diagnostics import (
    OrbDiagnosticReport,
    OrbDiagnosticService,
)
from app.trading.orb_signal_factory import (
    OrbSignalFactory,
)
from app.trading.signal_models import (
    TradeSignal,
    TradeSignalRecord,
)
from app.trading.signal_repository import (
    DuplicateSignalError,
)


class TradeSignalWriter(Protocol):
    """売買シグナル保存処理のインターフェース。"""

    def save(
        self,
        signal: TradeSignal,
    ) -> TradeSignalRecord:
        """シグナルを保存する。"""


@dataclass(frozen=True, slots=True)
class OrbSignalGenerationFailure:
    """ORBシグナル保存失敗。"""

    signal_id: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class OrbSignalGenerationResult:
    """ORBシグナル生成処理の結果。"""

    diagnostic_report: OrbDiagnosticReport
    generated_signals: tuple[
        TradeSignal,
        ...
    ]
    saved_records: tuple[
        TradeSignalRecord,
        ...
    ]
    duplicate_signals: tuple[
        TradeSignal,
        ...
    ]
    failures: tuple[
        OrbSignalGenerationFailure,
        ...
    ]

    @property
    def diagnostic_count(self) -> int:
        """診断した銘柄・営業日数を返す。"""

        return (
            self.diagnostic_report
            .trading_day_count
        )

    @property
    def candidate_count(self) -> int:
        """ORB候補件数を返す。"""

        return (
            self.diagnostic_report
            .trade_candidate_count
        )

    @property
    def generated_count(self) -> int:
        """生成したシグナル件数を返す。"""

        return len(
            self.generated_signals
        )

    @property
    def saved_count(self) -> int:
        """新規保存した件数を返す。"""

        return len(
            self.saved_records
        )

    @property
    def duplicate_count(self) -> int:
        """重複としてスキップした件数を返す。"""

        return len(
            self.duplicate_signals
        )

    @property
    def failed_count(self) -> int:
        """保存に失敗した件数を返す。"""

        return len(
            self.failures
        )

    @property
    def is_successful(self) -> bool:
        """重複以外の保存失敗がないか返す。"""

        return self.failed_count == 0


class OrbSignalGenerationService:
    """ORB診断・シグナル生成・永続化を実行する。"""

    def __init__(
        self,
        *,
        diagnostic_service: OrbDiagnosticService,
        signal_factory: OrbSignalFactory,
        signal_repository: TradeSignalWriter,
    ) -> None:
        """必要な診断・生成・保存処理を設定する。"""

        self.diagnostic_service = (
            diagnostic_service
        )
        self.signal_factory = (
            signal_factory
        )
        self.signal_repository = (
            signal_repository
        )

    def run(
        self,
        prices: list[StockPrice],
        *,
        continue_on_error: bool = True,
    ) -> OrbSignalGenerationResult:
        """5分足からORBシグナルを生成して保存する。"""

        diagnostic_report = (
            self.diagnostic_service.run(
                prices
            )
        )

        generated_signals = (
            self.signal_factory.create_many(
                diagnostic_report.daily_results
            )
        )

        saved_records: list[
            TradeSignalRecord
        ] = []
        duplicate_signals: list[
            TradeSignal
        ] = []
        failures: list[
            OrbSignalGenerationFailure
        ] = []

        for signal in generated_signals:
            try:
                record = (
                    self.signal_repository.save(
                        signal
                    )
                )

            except DuplicateSignalError:
                duplicate_signals.append(
                    signal
                )
                continue

            except Exception as error:
                if not continue_on_error:
                    raise

                failures.append(
                    OrbSignalGenerationFailure(
                        signal_id=(
                            signal.signal_id
                        ),
                        code=signal.code,
                        message=str(error),
                    )
                )
                continue

            saved_records.append(
                record
            )

        return OrbSignalGenerationResult(
            diagnostic_report=(
                diagnostic_report
            ),
            generated_signals=tuple(
                generated_signals
            ),
            saved_records=tuple(
                saved_records
            ),
            duplicate_signals=tuple(
                duplicate_signals
            ),
            failures=tuple(
                failures
            ),
        )