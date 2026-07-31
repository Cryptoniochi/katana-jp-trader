"""Project KATANA Sprint90-2統合用コンテキストを収集する。"""

from __future__ import annotations

import argparse
import zipfile
from dataclasses import dataclass
from pathlib import Path


DEFAULT_OUTPUT = Path("katana_sprint90_2_context.zip")

TARGET_FILES = (
    "pyproject.toml",
    "app/database.py",
    "app/run_paper_trading.py",
    "app/run_market_session.py",
    "app/scheduler.py",
    "app/runtime/paper_trading_composition.py",
    "app/market/models.py",
    "app/market/bar_repository.py",
    "app/market/realtime_market_service.py",
    "app/market/market_data_provider.py",
    "app/market/kabu_station_models.py",
    "app/market/kabu_station_client.py",
    "app/market/kabu_station_websocket.py",
    "app/market/kabu_station_realtime_provider.py",
    "app/market/kabu_station_realtime_service.py",
    "app/market/kabu_station_tick_monitor.py",
    "app/market/kabu_station_bar_sink.py",
    "app/market/realtime_bar_aggregator.py",
    "app/trading/paper_trading_runner.py",
    "app/trading/paper_trading_runtime.py",
    "app/strategy/opening_range_breakout_strategy.py",
    "app/strategy/signal_engine.py",
    "app/notifications/notification_composition.py",
    "tests/test_run_paper_trading.py",
    "tests/test_paper_trading_composition.py",
    "tests/test_realtime_market_service.py",
    "tests/test_market_bar_repository.py",
    "tests/test_kabu_station_realtime_service.py",
    "tests/test_kabu_station_bar_sink.py",
    "tests/test_run_kabu_station_realtime_check.py",
)


@dataclass(frozen=True, slots=True)
class CollectionResult:
    """収集結果。"""

    collected: tuple[str, ...]
    missing: tuple[str, ...]
    output_path: Path


def parse_arguments() -> argparse.Namespace:
    """CLI引数を解析する。"""

    parser = argparse.ArgumentParser(
        description=(
            "Sprint90-2でkabuステーションAPIを"
            "Paper Tradingへ統合するための最新ファイルを収集します。"
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help=(
            "Project KATANAのルート。"
            "既定値は現在のフォルダです。"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "出力ZIP。相対パスはプロジェクトルート基準です。"
        ),
    )
    return parser.parse_args()


def collect_context(
    *,
    root: Path,
    output: Path,
) -> CollectionResult:
    """対象ファイルをZIPへ格納する。"""

    resolved_root = root.resolve()

    if not resolved_root.is_dir():
        raise FileNotFoundError(
            f"プロジェクトルートが見つかりません: {resolved_root}"
        )

    output_path = (
        output.resolve()
        if output.is_absolute()
        else (resolved_root / output).resolve()
    )
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    collected: list[str] = []
    missing: list[str] = []

    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for relative_path in TARGET_FILES:
            source = resolved_root / relative_path

            if not source.is_file():
                missing.append(relative_path)
                continue

            archive.write(
                source,
                arcname=relative_path,
            )
            collected.append(relative_path)

        manifest = _render_manifest(
            root=resolved_root,
            collected=collected,
            missing=missing,
        )
        archive.writestr(
            "SPRINT90_2_CONTEXT_MANIFEST.txt",
            manifest,
        )

    return CollectionResult(
        collected=tuple(collected),
        missing=tuple(missing),
        output_path=output_path,
    )


def _render_manifest(
    *,
    root: Path,
    collected: list[str],
    missing: list[str],
) -> str:
    """収集内容の一覧を生成する。"""

    lines = [
        "Project KATANA Sprint90-2 Context",
        f"Project root: {root}",
        f"Collected: {len(collected)}",
        f"Missing: {len(missing)}",
        "",
        "[Collected]",
        *collected,
        "",
        "[Missing]",
        *(missing or ["なし"]),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    """収集処理を実行する。"""

    arguments = parse_arguments()
    result = collect_context(
        root=arguments.root,
        output=arguments.output,
    )

    print("Sprint90-2統合用ファイルを収集しました。")
    print(f"出力先: {result.output_path}")
    print(f"収集数: {len(result.collected)}")
    print(f"不足数: {len(result.missing)}")

    if result.missing:
        print("不足ファイル:")
        for relative_path in result.missing:
            print(f"  - {relative_path}")

    print(
        "生成されたZIPをこのチャットへアップロードしてください。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
