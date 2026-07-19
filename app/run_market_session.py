"""東京市場の営業日・時間帯に応じてPaper Tradingを起動する。"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from threading import Event
from typing import TextIO

from app.notifications.notification_models import (
    NotificationSeverity,
)
from app.run_paper_trading import (
    RuntimeNotificationGatewayFactory,
    _send_runtime_notification,
    create_runtime_notification_gateway,
    run as run_paper_trading,
)
from app.runtime.session_runner import (
    MarketSessionRunDecision,
    MarketSessionRunner,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """運用ランナー固有のCLI引数を定義する。"""

    parser = argparse.ArgumentParser(
        prog="python -m app.run_market_session",
        description=(
            "東京市場の営業日と時間帯を確認し、"
            "取引可能時刻にPaper Tradingを起動します。"
        ),
        add_help=True,
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help=(
            "市場開始前・昼休みに待機せず終了します。"
        ),
    )
    parser.add_argument(
        "--maximum-sleep-seconds",
        type=float,
        default=30.0,
        help=(
            "市場開始待機中に1回でsleepする最大秒数。"
        ),
    )

    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    output: TextIO = sys.stdout,
    error_output: TextIO = sys.stderr,
    now_provider=None,
    sleeper=None,
    market_clock=None,
    paper_trading_runner=run_paper_trading,
    notification_gateway_factory: (
        RuntimeNotificationGatewayFactory
    ) = create_runtime_notification_gateway,
) -> int:
    """市場状態を確認してPaper Tradingを実行する。"""

    parser = build_argument_parser()
    arguments, paper_arguments = (
        parser.parse_known_args(argv)
    )
    stop_event = Event()

    try:
        gateway = notification_gateway_factory(
            environ
        )
    except Exception as error:
        print(
            "外部通知の初期化に失敗しました。 "
            f"error={error}",
            file=error_output,
        )
        gateway = None

    notified_wait_target = None

    def observe(status, snapshot) -> None:
        nonlocal notified_wait_target

        if status == "waiting_for_open":
            target = snapshot.next_trading_at

            if notified_wait_target == target:
                return

            notified_wait_target = target
            message = (
                "市場開始まで待機します。\n"
                f"現在セッション: {snapshot.session.value}\n"
                "次回取引可能時刻: "
                f"{target.isoformat()}\n"
                f"待機秒数: {snapshot.wait_seconds:.1f}"
            )
            print(
                message.replace("\n", " "),
                file=output,
            )
            _send_runtime_notification(
                gateway,
                title="Market Session Waiting",
                message=message,
                severity=NotificationSeverity.INFO,
                event_type="market_session_waiting",
                error_output=error_output,
            )

        elif status == "non_business_day":
            message = (
                "本日は東京市場の非営業日です。\n"
                f"日付: {snapshot.local_at.date().isoformat()}\n"
                "次回取引可能時刻: "
                f"{snapshot.next_trading_at.isoformat()}"
            )
            print(
                message.replace("\n", " "),
                file=output,
            )
            _send_runtime_notification(
                gateway,
                title="Paper Trading Skipped",
                message=message,
                severity=NotificationSeverity.INFO,
                event_type=(
                    "paper_trading_skipped_non_business_day"
                ),
                error_output=error_output,
            )

        elif status == "after_close":
            message = (
                "本日の東京市場は終了しています。\n"
                f"現在時刻: {snapshot.local_at.isoformat()}\n"
                "次回取引可能時刻: "
                f"{snapshot.next_trading_at.isoformat()}"
            )
            print(
                message.replace("\n", " "),
                file=output,
            )
            _send_runtime_notification(
                gateway,
                title="Paper Trading Skipped",
                message=message,
                severity=NotificationSeverity.INFO,
                event_type=(
                    "paper_trading_skipped_after_close"
                ),
                error_output=error_output,
            )

        elif status == "market_open":
            print(
                "東京市場は取引時間中です。"
                "Paper Tradingを起動します。",
                file=output,
            )

    runner_kwargs = {
        "maximum_sleep_seconds": (
            arguments.maximum_sleep_seconds
        ),
        "wait_for_open": not arguments.no_wait,
        "stop_requested": stop_event.is_set,
        "status_observer": observe,
    }

    if now_provider is not None:
        runner_kwargs["now_provider"] = now_provider
    if sleeper is not None:
        runner_kwargs["sleeper"] = sleeper
    if market_clock is not None:
        runner_kwargs["market_clock"] = market_clock

    runner = MarketSessionRunner(
        **runner_kwargs
    )

    try:
        result = runner.run(
            lambda: paper_trading_runner(
                paper_arguments,
                environ=environ,
                output=output,
                error_output=error_output,
            )
        )
    except KeyboardInterrupt:
        stop_event.set()
        print(
            "KeyboardInterruptを受信しました。"
            "市場セッション運用を停止します。",
            file=error_output,
        )
        return 130
    except Exception as error:
        print(
            "市場セッション運用に失敗しました。 "
            f"error={error}",
            file=error_output,
        )
        _send_runtime_notification(
            gateway,
            title="Market Session Runner Failed",
            message=(
                "市場セッション運用で例外が発生しました。\n"
                f"例外種別: {type(error).__name__}\n"
                f"詳細: {error}"
            ),
            severity=NotificationSeverity.CRITICAL,
            event_type="market_session_runner_failed",
            error_output=error_output,
        )
        return 1

    if (
        result.decision
        is MarketSessionRunDecision.EXECUTED
    ):
        assert result.application_exit_code is not None
        return result.application_exit_code

    if (
        result.decision
        is MarketSessionRunDecision.STOP_REQUESTED
    ):
        return 130

    return 0


def main() -> None:
    """CLIエントリーポイント。"""

    raise SystemExit(run())


if __name__ == "__main__":
    main()
