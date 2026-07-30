"""kabuステーション実接続とリアルタイム受信を確認する。"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from app.database import initialize_database
from app.market.bar_repository import MarketBarRepository
from app.market.kabu_station_bar_sink import (
    KabuStationBarRepositorySink,
)
from app.market.kabu_station_client import (
    KabuStationClient,
    KabuStationClientSettings,
)
from app.market.kabu_station_realtime_provider import (
    KabuStationRealtimeProvider,
)
from app.market.kabu_station_realtime_service import (
    KabuStationRealtimeService,
)
from app.market.kabu_station_tick_monitor import (
    KabuStationTickMonitor,
)


DEFAULT_DATABASE_PATH = Path("data/katana.db")
DEFAULT_DURATION_SECONDS = 60.0
DEFAULT_BASE_URL = "http://localhost:18080/kabusapi"
DEFAULT_WEBSOCKET_URL = (
    "ws://localhost:18080/kabusapi/websocket"
)


def build_argument_parser() -> argparse.ArgumentParser:
    """CLI引数を定義する。"""

    parser = argparse.ArgumentParser(
        prog=(
            "python -m "
            "app.run_kabu_station_realtime_check"
        ),
        description=(
            "kabuステーションAPIへ接続し、"
            "リアルタイムPUSHと5分足保存を確認します。"
        ),
    )
    parser.add_argument(
        "--code",
        action="append",
        default=[],
        help=(
            "受信対象銘柄コード。複数指定できます。"
            "例: --code 7203 --code 9984"
        ),
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION_SECONDS,
        help="受信を継続する秒数。既定値は60秒です。",
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=(
            "完成した5分足の保存先。"
            "既定値はdata/katana.dbです。"
        ),
    )
    parser.add_argument(
        "--token-only",
        action="store_true",
        help=(
            "トークン取得だけを確認し、"
            "WebSocketへ接続せず終了します。"
        ),
    )
    parser.add_argument(
        "--quiet-ticks",
        action="store_true",
        help="受信Tickを1件ずつ表示しません。",
    )
    return parser


def resolve_api_password(
    environ: Mapping[str, str] | None = None,
) -> str:
    """環境変数からAPIパスワードを取得する。"""

    resolved = (
        os.environ
        if environ is None
        else environ
    )
    password = (
        resolved.get("KABU_STATION_API_PASSWORD")
        or resolved.get("KABUSTATION_API_PASSWORD")
        or ""
    ).strip()

    if not password:
        raise ValueError(
            "環境変数KABU_STATION_API_PASSWORDを"
            "設定してください。"
        )

    return password


def normalize_codes(
    raw_codes: Sequence[str],
) -> tuple[str, ...]:
    """銘柄コードを重複なしで検証する。"""

    codes = tuple(
        dict.fromkeys(
            value.strip()
            for value in raw_codes
            if value.strip()
        )
    )

    for code in codes:
        if not code.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。 "
                f"value={code}"
            )

        if len(code) not in {4, 5}:
            raise ValueError(
                "銘柄コードは4桁または5桁で"
                "指定してください。 "
                f"value={code}"
            )

    if len(codes) > 50:
        raise ValueError(
            "kabuステーションAPIの登録上限は"
            "50銘柄です。"
        )

    return codes


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    """実接続確認を実行する。"""

    arguments = build_argument_parser().parse_args(argv)

    try:
        password = resolve_api_password(environ)
        codes = normalize_codes(arguments.code)

        if arguments.duration <= 0:
            raise ValueError(
                "受信時間は0秒より大きい必要があります。"
            )

        client = KabuStationClient(
            settings=KabuStationClientSettings(
                api_password=password,
                base_url=DEFAULT_BASE_URL,
            )
        )
        provider = KabuStationRealtimeProvider(
            client=client
        )

        print("kabuステーションAPIへ接続します。")
        token = provider.connect()
        print(
            "トークン取得成功:"
            f" token_length={len(token)}"
        )

        if arguments.token_only:
            print("トークン確認を正常終了しました。")
            return 0

        if not codes:
            raise ValueError(
                "WebSocket確認には--codeを"
                "1件以上指定してください。"
            )

        database_path = Path(arguments.database_path)
        database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        initialize_database(database_path)

        sink = KabuStationBarRepositorySink(
            repository=MarketBarRepository(
                database_path
            )
        )
        monitor = KabuStationTickMonitor(
            print_ticks=not arguments.quiet_ticks
        )

        def websocket_factory(**kwargs):
            from app.market.kabu_station_websocket import (
                KabuStationWebSocketClient,
            )

            return KabuStationWebSocketClient(
                url=DEFAULT_WEBSOCKET_URL,
                **kwargs,
            )

        service = KabuStationRealtimeService(
            provider=provider,
            websocket_client_factory=websocket_factory,
            on_tick=monitor,
            on_completed_bar=sink,
            interval_minutes=5,
        )

        registered = service.start(codes)
        print(
            "リアルタイム受信を開始しました:"
            f" codes={','.join(registered)}"
        )
        print(
            f"{arguments.duration:g}秒間待機します。"
            " Ctrl+Cで安全に停止できます。"
        )

        deadline = time.monotonic() + arguments.duration

        try:
            while time.monotonic() < deadline:
                time.sleep(0.25)
        except KeyboardInterrupt:
            print("停止要求を受け付けました。")
        finally:
            flushed = service.stop()

        provider_status = provider.status()
        sink_status = sink.status()
        monitor_status = monitor.status()

        print("実接続確認結果")
        print(
            "  登録銘柄:"
            f" {','.join(provider_status.registered_codes)}"
        )
        print(
            "  受信Tick数:"
            f" {monitor_status.received_tick_count}"
        )
        print(
            "  Tick受信銘柄:"
            f" {','.join(monitor_status.received_codes)}"
        )
        print(
            "  最終Tick日時:"
            f" {monitor_status.last_received_at}"
        )
        print(
            "  完成バー保存数:"
            f" {sink_status.saved_bar_count}"
        )
        print(
            "  停止時フラッシュ数:"
            f" {len(flushed)}"
        )
        print(
            "  最終エラー:"
            f" {provider_status.last_error}"
        )

        if monitor_status.received_tick_count == 0:
            print(
                "注意: Tickを受信しませんでした。"
                " 市場時間中か、登録銘柄に価格更新が"
                "あったか確認してください。"
            )
            return 2

        print(
            "リアルタイムPUSH受信を確認しました。"
        )
        return 0

    except Exception as error:
        detail = (
            str(error).strip()
            or type(error).__name__
        )
        print(
            f"実接続確認に失敗しました: {detail}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
