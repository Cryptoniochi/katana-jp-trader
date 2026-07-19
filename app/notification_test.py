"""Discord・LINEへの実送信を確認するCLI。"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO
from uuid import uuid4

from app.notifications.notification_composition import (
    NotificationComposition,
    NotificationCompositionBundle,
    NotificationConfigurationError,
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
from app.settings import ROOT_DIR, Settings


def build_argument_parser() -> argparse.ArgumentParser:
    """CLI引数を定義する。"""

    parser = argparse.ArgumentParser(
        description=(
            "Project KATANAのDiscord・LINE通知を"
            "実際に送信して接続を確認します。"
        )
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ROOT_DIR / ".env",
        help="通知認証情報を読み込む.envファイル",
    )
    parser.add_argument(
        "--message",
        default=(
            "Project KATANAの外部通知接続は正常です。"
        ),
        help="テスト通知本文",
    )
    parser.add_argument(
        "--title",
        default="Notification Test",
        help="テスト通知タイトル",
    )

    return parser


def create_test_policy(
    channel_names: tuple[str, ...],
) -> NotificationRulePolicy:
    """すべての有効チャネルへ確実に配信する方針を返す。"""

    return NotificationRulePolicy(
        info_channels=channel_names,
        warning_channels=channel_names,
        error_channels=channel_names,
        critical_channels=channel_names,
        duplicate_cooldown_seconds=0,
    )


def send_test_notification(
    *,
    bundle: NotificationCompositionBundle,
    title: str,
    message: str,
    created_at: datetime | None = None,
):
    """Notification Gateway経由でテスト通知を送る。"""

    now = (
        created_at
        if created_at is not None
        else datetime.now(timezone.utc)
    )

    return bundle.gateway.send(
        NotificationGatewayRequest(
            notification_id=(
                f"notification-test-{uuid4().hex}"
            ),
            template_name=NotificationTemplateName.GENERIC,
            created_at=now,
            source="notification-test-cli",
            context={
                "title": title,
                "message": message,
            },
            severity=NotificationSeverity.CRITICAL,
            metadata={
                "event_type": "connection_test",
                "current_status": "operational",
            },
        ),
        continue_on_error=True,
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    output: TextIO = sys.stdout,
    error_output: TextIO = sys.stderr,
) -> int:
    """設定を読み込み、実送信結果を終了コードへ変換する。"""

    arguments = build_argument_parser().parse_args(argv)

    try:
        app_settings = Settings.from_environment(
            environment=environ,
            env_file=arguments.env_file,
        )

        provisional = NotificationComposition.create(
            settings=app_settings.notifications,
            require_channel=True,
        )
        policy = create_test_policy(
            provisional.channel_names
        )
        bundle = NotificationComposition.create(
            settings=app_settings.notifications,
            policy=policy,
            require_channel=True,
        )

        print(
            "Project KATANA Notification Test",
            file=output,
        )
        print(
            "channels="
            + ",".join(bundle.channel_names),
            file=output,
        )

        result = send_test_notification(
            bundle=bundle,
            title=arguments.title,
            message=arguments.message,
        )

        delivery = result.routing_result.delivery

        if delivery is None:
            print(
                "通知がルールにより抑止されました。",
                file=error_output,
            )
            return 2

        failed_channels = [
            channel.channel_name
            for channel in delivery.channels
            if not channel.delivered
        ]

        for channel in delivery.channels:
            mark = "OK" if channel.delivered else "FAILED"
            print(
                f"{channel.channel_name}: {mark}",
                file=output,
            )

        if failed_channels:
            print(
                "送信に失敗したチャネル: "
                + ",".join(failed_channels),
                file=error_output,
            )
            return 1

        print(
            "すべての通知チャネルへの送信に成功しました。",
            file=output,
        )
        return 0

    except NotificationConfigurationError as error:
        print(
            f"設定エラー: {error}",
            file=error_output,
        )
        return 2
    except Exception as error:
        print(
            "通知テストに失敗しました。 "
            f"{type(error).__name__}: {error}",
            file=error_output,
        )
        return 1


def main() -> None:
    """CLIエントリーポイント。"""

    raise SystemExit(run())


if __name__ == "__main__":
    main()
