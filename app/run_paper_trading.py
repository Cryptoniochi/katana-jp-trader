"""Project KATANAの本番Paper Tradingを起動する。"""

from __future__ import annotations

import argparse
import os
import signal
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4
from collections.abc import Mapping, Sequence
from pathlib import Path
from threading import Event
from typing import Protocol, TextIO

from app.notifications.notification_composition import (
    NotificationComposition,
)
from app.notifications.notification_gateway import (
    NotificationGateway,
)
from app.notifications.notification_gateway_models import (
    NotificationGatewayRequest,
)
from app.notifications.notification_models import (
    NotificationSeverity,
)
from app.notifications.notification_rule_models import (
    NotificationRulePolicy,
)
from app.notifications.notification_template import (
    NotificationTemplateName,
)
from app.runtime.paper_trading_composition import (
    PaperTradingComposition,
    PaperTradingProductionSettings,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDayResult,
    PaperTradingDayStopReason,
)
from app.runtime.production_readiness import (
    ProductionReadinessChecker,
    ProductionReadinessReport,
)
from app.settings import ROOT_DIR, Settings
from app.watchlist import load_watchlist


DEFAULT_DATABASE_PATH = Path("data/katana.db")
DEFAULT_WATCHLIST_PATH = Path("watchlist.txt")
DEFAULT_INITIAL_CASH = 10_000_000.0
DEFAULT_CYCLE_INTERVAL_SECONDS = 30.0
DEFAULT_JQUANTS_TIMEOUT_SECONDS = 30.0


class PaperTradingApplicationBundle(Protocol):
    """ランチャーが利用する本番Application Bundle。"""

    def run(self) -> PaperTradingDayResult:
        """終日Paper Tradingを実行する。"""


class PaperTradingCompositionFactory(Protocol):
    """本番Compositionを生成するFactory。"""

    @staticmethod
    def create(
        *,
        settings: PaperTradingProductionSettings,
        now_provider=None,
        stop_requested=None,
    ) -> PaperTradingApplicationBundle:
        """本番Application Bundleを生成する。"""





RuntimeNotificationGatewayFactory = Callable[
    [Mapping[str, str] | None],
    NotificationGateway | None,
]

class StopController:
    """OSシグナルから安全停止要求を管理する。"""

    def __init__(self) -> None:
        """停止要求がない状態で作成する。"""

        self._event = Event()

    @property
    def is_stop_requested(self) -> bool:
        """停止要求済みか返す。"""

        return self._event.is_set()

    def request_stop(self) -> None:
        """安全停止を要求する。"""

        self._event.set()

    def __call__(self) -> bool:
        """停止判定関数として利用する。"""

        return self.is_stop_requested


def build_argument_parser() -> argparse.ArgumentParser:
    """本番ランチャーのコマンドライン引数を定義する。"""

    parser = argparse.ArgumentParser(
        prog="python -m app.run_paper_trading",
        description=(
            "Project KATANAのPaper Tradingを"
            "東京市場の取引時間に従って実行します。"
        ),
    )

    parser.add_argument(
        "--database-path",
        type=Path,
        default=None,
        help=(
            "SQLiteデータベースのパス。"
            "未指定時は環境変数KATANA_DATABASE_PATH、"
            "またはdata/katana.dbを使用します。"
        ),
    )

    parser.add_argument(
        "--watchlist",
        type=Path,
        default=None,
        help=(
            "監視銘柄を記載したWatch Listファイル。"
            "未指定時は環境変数KATANA_WATCHLIST_PATH、"
            "またはwatchlist.txtを使用します。"
        ),
    )

    parser.add_argument(
        "--code",
        action="append",
        default=[],
        help=(
            "監視対象の銘柄コード。複数指定できます。"
            "指定した場合はWatch Listより優先されます。"
        ),
    )

    parser.add_argument(
        "--initial-cash",
        type=float,
        default=None,
        help=(
            "Paper Brokerの初期資金。"
            "未指定時は環境変数KATANA_INITIAL_CASH、"
            "または10000000を使用します。"
        ),
    )

    parser.add_argument(
        "--cycle-interval",
        type=float,
        default=None,
        help=(
            "Trading Cycleの実行間隔秒数。"
            "未指定時は環境変数KATANA_CYCLE_INTERVAL_SECONDS、"
            "または30秒を使用します。"
        ),
    )

    parser.add_argument(
        "--maximum-cycles",
        type=int,
        default=None,
        help=(
            "最大Trading Cycle数。"
            "未指定時は市場終了まで継続します。"
        ),
    )

    parser.add_argument(
        "--jquants-api-key",
        default=None,
        help=(
            "J-Quants APIキー。"
            "通常は環境変数JQUANTS_API_KEYを使用してください。"
        ),
    )

    parser.add_argument(
        "--jquants-timeout",
        type=float,
        default=None,
        help=(
            "J-Quants APIのタイムアウト秒数。"
            "未指定時は環境変数KATANA_JQUANTS_TIMEOUT_SECONDS、"
            "または30秒を使用します。"
        ),
    )

    parser.add_argument(
        "--commission-per-order",
        type=float,
        default=None,
        help=(
            "Paper Brokerの1注文当たり手数料。"
            "未指定時は環境変数KATANA_COMMISSION_PER_ORDER、"
            "または0を使用します。"
        ),
    )

    parser.add_argument(
        "--slippage-rate",
        type=float,
        default=None,
        help=(
            "Paper Brokerのスリッページ率。"
            "未指定時は環境変数KATANA_SLIPPAGE_RATE、"
            "または0を使用します。"
        ),
    )

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help=(
            "Trading Cycleで例外が発生した場合に"
            "継続せず停止します。"
        ),
    )

    parser.add_argument(
        "--stop-on-cycle-failure",
        action="store_true",
        help=(
            "FAILEDのTrading Cycleを検出した時点で"
            "終日運用を停止します。"
        ),
    )

    parser.add_argument(
        "--ignore-resource-critical",
        action="store_true",
        help=(
            "Runtime ResourceがCRITICALでも"
            "終日運用を継続します。"
        ),
    )

    parser.add_argument(
        "--check",
        "--validate-only",
        "--dry-run",
        dest="readiness_check",
        action="store_true",
        help=(
            "Paper Tradingを開始せず、"
            "本番運転前の総合診断だけを実行します。"
        ),
    )

    return parser


def create_production_settings(
    arguments: argparse.Namespace,
    *,
    environ: Mapping[str, str] | None = None,
) -> PaperTradingProductionSettings:
    """CLI引数と環境変数から本番設定を作成する。"""

    resolved_environ = (
        environ
        if environ is not None
        else os.environ
    )

    database_path = _resolve_path(
        argument_value=arguments.database_path,
        environment_value=resolved_environ.get(
            "KATANA_DATABASE_PATH"
        ),
        default_value=DEFAULT_DATABASE_PATH,
    )

    watchlist_path = _resolve_path(
        argument_value=arguments.watchlist,
        environment_value=resolved_environ.get(
            "KATANA_WATCHLIST_PATH"
        ),
        default_value=DEFAULT_WATCHLIST_PATH,
    )

    codes = _resolve_codes(
        direct_codes=tuple(arguments.code),
        watchlist_path=watchlist_path,
    )

    initial_cash = _resolve_float(
        argument_value=arguments.initial_cash,
        environment_value=resolved_environ.get(
            "KATANA_INITIAL_CASH"
        ),
        default_value=DEFAULT_INITIAL_CASH,
        environment_name="KATANA_INITIAL_CASH",
    )

    cycle_interval_seconds = _resolve_float(
        argument_value=arguments.cycle_interval,
        environment_value=resolved_environ.get(
            "KATANA_CYCLE_INTERVAL_SECONDS"
        ),
        default_value=DEFAULT_CYCLE_INTERVAL_SECONDS,
        environment_name=(
            "KATANA_CYCLE_INTERVAL_SECONDS"
        ),
    )

    jquants_timeout_seconds = _resolve_float(
        argument_value=arguments.jquants_timeout,
        environment_value=resolved_environ.get(
            "KATANA_JQUANTS_TIMEOUT_SECONDS"
        ),
        default_value=DEFAULT_JQUANTS_TIMEOUT_SECONDS,
        environment_name=(
            "KATANA_JQUANTS_TIMEOUT_SECONDS"
        ),
    )

    commission_per_order = _resolve_float(
        argument_value=arguments.commission_per_order,
        environment_value=resolved_environ.get(
            "KATANA_COMMISSION_PER_ORDER"
        ),
        default_value=0.0,
        environment_name=(
            "KATANA_COMMISSION_PER_ORDER"
        ),
    )

    slippage_rate = _resolve_float(
        argument_value=arguments.slippage_rate,
        environment_value=resolved_environ.get(
            "KATANA_SLIPPAGE_RATE"
        ),
        default_value=0.0,
        environment_name="KATANA_SLIPPAGE_RATE",
    )

    api_key = (
        arguments.jquants_api_key
        if arguments.jquants_api_key is not None
        else resolved_environ.get("JQUANTS_API_KEY")
    )

    return PaperTradingProductionSettings(
        database_path=database_path,
        codes=codes,
        initial_cash=initial_cash,
        cycle_interval_seconds=(
            cycle_interval_seconds
        ),
        maximum_cycles=arguments.maximum_cycles,
        jquants_api_key=api_key,
        jquants_timeout_seconds=(
            jquants_timeout_seconds
        ),
        commission_per_order=commission_per_order,
        slippage_rate=slippage_rate,
        continue_on_cycle_error=(
            not arguments.fail_fast
        ),
        stop_on_cycle_failure=(
            arguments.stop_on_cycle_failure
        ),
        stop_on_resource_critical=(
            not arguments.ignore_resource_critical
        ),
    )



def create_runtime_notification_gateway(
    environ: Mapping[str, str] | None = None,
) -> NotificationGateway | None:
    """有効な外部通知チャネルからRuntime用Gatewayを作成する。"""

    app_settings = Settings.from_environment(
        environment=environ,
        env_file=ROOT_DIR / ".env",
    )
    provisional = NotificationComposition.create(
        settings=app_settings.notifications,
        require_channel=False,
    )

    if not provisional.channels:
        return None

    channel_names = provisional.channel_names
    policy = NotificationRulePolicy(
        info_channels=channel_names,
        warning_channels=channel_names,
        error_channels=channel_names,
        critical_channels=channel_names,
        duplicate_cooldown_seconds=0,
    )
    bundle = NotificationComposition.create(
        settings=app_settings.notifications,
        policy=policy,
        require_channel=True,
    )

    return bundle.gateway


def _send_runtime_notification(
    gateway: NotificationGateway | None,
    *,
    title: str,
    message: str,
    severity: NotificationSeverity,
    event_type: str,
    error_output: TextIO,
) -> None:
    """Runtime通知を送り、通知障害を取引処理から隔離する。"""

    if gateway is None:
        return

    try:
        gateway.send(
            NotificationGatewayRequest(
                notification_id=(
                    f"paper-runtime-{uuid4().hex}"
                ),
                template_name=(
                    NotificationTemplateName.GENERIC
                ),
                created_at=datetime.now(timezone.utc),
                source="paper-trading-runtime",
                context={
                    "title": title,
                    "message": message,
                },
                severity=severity,
                metadata={
                    "event_type": event_type,
                },
            ),
            continue_on_error=True,
        )
    except Exception as error:
        detail = (
            str(error).strip()
            or type(error).__name__
        )
        print(
            "外部通知の送信に失敗しました。"
            f" event_type={event_type}"
            f" error={detail}",
            file=error_output,
        )


def _startup_notification_message(
    settings: PaperTradingProductionSettings,
) -> str:
    """開始通知本文を生成する。"""

    return (
        "Paper Tradingを開始します。\\n"
        f"監視銘柄数: {len(settings.codes)}\\n"
        f"監視銘柄: {','.join(settings.codes)}\\n"
        f"初期資金: {settings.initial_cash:,.0f}円\\n"
        "実行間隔: "
        f"{settings.cycle_interval_seconds:g}秒\\n"
        f"最大サイクル数: {settings.maximum_cycles}"
    )


def _finished_notification_message(
    result: PaperTradingDayResult,
) -> str:
    """終了通知本文を生成する。"""

    return (
        "Paper Tradingが終了しました。\\n"
        f"取引日: {result.trading_date.isoformat()}\\n"
        f"終了理由: {result.stop_reason.value}\\n"
        f"サイクル数: {result.cycle_count}\\n"
        f"損益: {result.net_profit_loss}\\n"
        f"収益率: {result.return_rate}\\n"
        f"エラー: {result.error_message}"
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    composition_factory: (
        PaperTradingCompositionFactory
    ) = PaperTradingComposition,
    environ: Mapping[str, str] | None = None,
    output: TextIO | None = None,
    error_output: TextIO | None = None,
    install_signals: bool = True,
    notification_gateway_factory: (
        RuntimeNotificationGatewayFactory
    ) = create_runtime_notification_gateway,
) -> int:
    """本番Paper Tradingを起動して終了コードを返す。"""

    resolved_output = (
        output
        if output is not None
        else sys.stdout
    )
    resolved_error_output = (
        error_output
        if error_output is not None
        else sys.stderr
    )

    parser = build_argument_parser()
    arguments = parser.parse_args(argv)
    stop_controller = StopController()
    notification_gateway: NotificationGateway | None = None
    previous_signal_handlers: dict[
        signal.Signals,
        signal.Handlers,
    ] = {}

    try:
        settings = create_production_settings(
            arguments,
            environ=environ,
        )

        if arguments.readiness_check:
            checker = ProductionReadinessChecker(
                composition_factory=composition_factory,
            )
            report = checker.check(
                settings=settings
            )
            _print_readiness_report(
                report,
                output=resolved_output,
            )
            return 0 if report.is_ready else 1

        try:
            notification_gateway = (
                notification_gateway_factory(environ)
            )
        except Exception as error:
            detail = (
                str(error).strip()
                or type(error).__name__
            )
            print(
                "外部通知の初期化に失敗しました。"
                f" error={detail}",
                file=resolved_error_output,
            )
            notification_gateway = None

        if install_signals:
            previous_signal_handlers = (
                _install_signal_handlers(
                    stop_controller
                )
            )

        _print_startup_information(
            settings,
            output=resolved_output,
        )

        bundle = composition_factory.create(
            settings=settings,
            stop_requested=stop_controller,
        )

        _send_runtime_notification(
            notification_gateway,
            title="Paper Trading Started",
            message=_startup_notification_message(
                settings
            ),
            severity=NotificationSeverity.INFO,
            event_type="paper_trading_started",
            error_output=resolved_error_output,
        )

        result = bundle.run()

        _print_result(
            result,
            output=resolved_output,
        )

        exit_code = _resolve_exit_code(result)
        _send_runtime_notification(
            notification_gateway,
            title=(
                "Paper Trading Finished"
                if exit_code == 0
                else "Paper Trading Stopped"
            ),
            message=_finished_notification_message(
                result
            ),
            severity=(
                NotificationSeverity.INFO
                if exit_code == 0
                else NotificationSeverity.ERROR
            ),
            event_type=(
                "paper_trading_finished"
                if exit_code == 0
                else "paper_trading_stopped"
            ),
            error_output=resolved_error_output,
        )

        return exit_code

    except KeyboardInterrupt:
        stop_controller.request_stop()

        print(
            "KeyboardInterruptを受信しました。"
            "Paper Tradingを停止します。",
            file=resolved_error_output,
        )
        _send_runtime_notification(
            notification_gateway,
            title="Paper Trading Interrupted",
            message=(
                "KeyboardInterruptを受信したため、"
                "Paper Tradingを停止します。"
            ),
            severity=NotificationSeverity.WARNING,
            event_type="paper_trading_interrupted",
            error_output=resolved_error_output,
        )

        return 130

    except Exception as error:
        message = (
            str(error).strip()
            or type(error).__name__
        )

        print(
            "Paper Tradingを起動または実行できませんでした。"
            f" error={message}",
            file=resolved_error_output,
        )
        _send_runtime_notification(
            notification_gateway,
            title="Paper Trading Failed",
            message=(
                "Paper Tradingで例外が発生しました。\n"
                f"例外種別: {type(error).__name__}\n"
                f"詳細: {message}"
            ),
            severity=NotificationSeverity.CRITICAL,
            event_type="paper_trading_failed",
            error_output=resolved_error_output,
        )

        return 1

    finally:
        if previous_signal_handlers:
            _restore_signal_handlers(
                previous_signal_handlers
            )


def main() -> None:
    """コマンドライン起動時のエントリーポイント。"""

    raise SystemExit(run())


def _resolve_codes(
    *,
    direct_codes: tuple[str, ...],
    watchlist_path: Path,
) -> tuple[str, ...]:
    """直接指定またはWatch Listから銘柄を読み込む。"""

    normalized_direct_codes = tuple(
        dict.fromkeys(
            code.strip()
            for code in direct_codes
            if code.strip()
        )
    )

    if normalized_direct_codes:
        return normalized_direct_codes

    return tuple(
        load_watchlist(watchlist_path)
    )


def _resolve_path(
    *,
    argument_value: Path | None,
    environment_value: str | None,
    default_value: Path,
) -> Path:
    """CLI・環境変数・既定値の順でPathを決定する。"""

    if argument_value is not None:
        return Path(argument_value)

    if environment_value is not None:
        normalized = environment_value.strip()

        if normalized:
            return Path(normalized)

    return Path(default_value)


def _resolve_float(
    *,
    argument_value: float | None,
    environment_value: str | None,
    default_value: float,
    environment_name: str,
) -> float:
    """CLI・環境変数・既定値の順で数値を決定する。"""

    if argument_value is not None:
        return float(argument_value)

    if environment_value is None:
        return default_value

    normalized = environment_value.strip()

    if not normalized:
        return default_value

    try:
        return float(normalized)
    except ValueError as error:
        raise ValueError(
            "環境変数を数値へ変換できません。 "
            f"name={environment_name} "
            f"value={normalized}"
        ) from error


def _install_signal_handlers(
    stop_controller: StopController,
) -> dict[
    signal.Signals,
    signal.Handlers,
]:
    """SIGINT・SIGTERMを安全停止要求へ変換する。"""

    previous_handlers: dict[
        signal.Signals,
        signal.Handlers,
    ] = {}

    supported_signals = [
        signal.SIGINT,
    ]

    if hasattr(signal, "SIGTERM"):
        supported_signals.append(
            signal.SIGTERM
        )

    def handle_signal(
        _signal_number: int,
        _frame,
    ) -> None:
        stop_controller.request_stop()

    for signal_value in supported_signals:
        previous_handlers[signal_value] = (
            signal.getsignal(signal_value)
        )
        signal.signal(
            signal_value,
            handle_signal,
        )

    return previous_handlers


def _restore_signal_handlers(
    previous_handlers: Mapping[
        signal.Signals,
        signal.Handlers,
    ],
) -> None:
    """変更前のOSシグナルハンドラーへ戻す。"""

    for (
        signal_value,
        previous_handler,
    ) in previous_handlers.items():
        signal.signal(
            signal_value,
            previous_handler,
        )


def _print_startup_information(
    settings: PaperTradingProductionSettings,
    *,
    output: TextIO,
) -> None:
    """起動設定を標準出力へ表示する。"""

    print(
        "Project KATANA Paper Trading",
        file=output,
    )
    print(
        f"database={settings.database_path}",
        file=output,
    )
    print(
        "codes="
        + ",".join(settings.codes),
        file=output,
    )
    print(
        f"initial_cash={settings.initial_cash:.2f}",
        file=output,
    )
    print(
        "cycle_interval_seconds="
        f"{settings.cycle_interval_seconds}",
        file=output,
    )
    print(
        "maximum_cycles="
        f"{settings.maximum_cycles}",
        file=output,
    )
    print(
        "Ctrl+Cで安全停止を要求できます。",
        file=output,
    )


def _print_readiness_report(
    report: ProductionReadinessReport,
    *,
    output: TextIO,
) -> None:
    """本番運転前診断を表示する。"""

    print(
        "=========================================",
        file=output,
    )
    print(
        "Project KATANA Production Readiness",
        file=output,
    )
    print(
        "=========================================",
        file=output,
    )

    for item in report.items:
        marker = (
            "OK"
            if item.is_ok
            else "FAILED"
        )

        print(
            f"[{marker}] {item.name}",
            file=output,
        )
        print(
            f"       {item.message}",
            file=output,
        )

    print(
        "",
        file=output,
    )
    print(
        "Overall",
        file=output,
    )
    print(
        "READY"
        if report.is_ready
        else "NOT READY",
        file=output,
    )
    print(
        "ok="
        f"{report.ok_count} "
        "failed="
        f"{report.failure_count}",
        file=output,
    )


def _print_result(
    result: PaperTradingDayResult,
    *,
    output: TextIO,
) -> None:
    """終日運用結果を標準出力へ表示する。"""

    print(
        "Paper Trading finished.",
        file=output,
    )
    print(
        f"trading_date={result.trading_date.isoformat()}",
        file=output,
    )
    print(
        f"stop_reason={result.stop_reason.value}",
        file=output,
    )
    print(
        f"cycle_count={result.cycle_count}",
        file=output,
    )
    print(
        f"net_profit_loss={result.net_profit_loss}",
        file=output,
    )
    print(
        f"return_rate={result.return_rate}",
        file=output,
    )

    if result.error_message is not None:
        print(
            f"error={result.error_message}",
            file=output,
        )

    if result.dashboard_error_message is not None:
        print(
            "dashboard_error="
            f"{result.dashboard_error_message}",
            file=output,
        )

    for hook_error in (
        result.post_run_hook_error_messages
    ):
        print(
            f"post_run_hook_error={hook_error}",
            file=output,
        )


def _resolve_exit_code(
    result: PaperTradingDayResult,
) -> int:
    """運用終了理由をプロセス終了コードへ変換する。"""

    if (
        result.stop_reason
        is PaperTradingDayStopReason.ERROR
    ):
        return 1

    if (
        result.stop_reason
        is PaperTradingDayStopReason.CYCLE_FAILED
    ):
        return 2

    if (
        result.stop_reason
        is PaperTradingDayStopReason.RESOURCE_CRITICAL
    ):
        return 3

    return 0


if __name__ == "__main__":
    main()