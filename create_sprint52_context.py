from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_OUTPUT = "sprint52_context.txt"

TARGET_FILES: tuple[str, ...] = (
    "app/backtest/run_backtest.py",
    "app/backtest/historical_models.py",
    "app/backtest/market_replay.py",
    "app/backtest/orb_signal_strategy.py",
    "app/backtest/event_driven_backtest_runner.py",
    "app/backtest/walk_forward_models.py",
    "app/backtest/walk_forward_window_service.py",
    "app/backtest/walk_forward_result_models.py",
    "app/backtest/walk_forward_runner.py",
    "app/backtest/walk_forward_summary_models.py",
    "app/backtest/walk_forward_analyzer.py",
    "app/backtest/walk_forward_report_writer.py",
    "app/market/bar_repository.py",
    "app/market/trading_calendar.py",
    "app/market/history_state.py",
    "app/market/jquants_downloader.py",
    "app/market/jquants_batch_import.py",
    "app/trading/signal_models.py",
    "app/trading/order_models.py",
    "app/trading/order_repository.py",
    "app/trading/order_service.py",
    "app/trading/position_repository.py",
    "app/trading/position_service.py",
    "app/trading/portfolio_repository.py",
    "app/trading/portfolio_service.py",
    "app/trading/paper_broker.py",
    "app/trading/trade_execution_repository.py",
    "app/settings.py",
    "tests/test_run_backtest.py",
    "tests/test_walk_forward_cli.py",
    "tests/test_market_bar_repository.py",
    "tests/test_trading_calendar.py",
    "tests/test_orb_signal_strategy.py",
    "tests/test_event_driven_backtest_runner.py",
)


@dataclass(frozen=True, slots=True)
class CollectedFile:
    relative_path: str
    absolute_path: Path
    content: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Project KATANA Sprint52用の最新コンテキストを生成します。"
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project KATANAのルート。既定値は現在のディレクトリです。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT),
        help=f"出力先。既定値は {DEFAULT_OUTPUT} です。",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="不足ファイルがあっても存在するファイルだけで出力します。",
    )
    return parser.parse_args()


def resolve_output_path(root: Path, output: Path) -> Path:
    return output if output.is_absolute() else root / output


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue

    raise UnicodeError(f"文字コードを判定できませんでした: {path}")


def collect_files(
    root: Path,
    relative_paths: Iterable[str],
) -> tuple[list[CollectedFile], list[str]]:
    collected: list[CollectedFile] = []
    missing: list[str] = []

    for relative_path in relative_paths:
        absolute_path = root / relative_path

        if not absolute_path.is_file():
            missing.append(relative_path)
            continue

        collected.append(
            CollectedFile(
                relative_path=relative_path,
                absolute_path=absolute_path,
                content=read_text_file(absolute_path),
            )
        )

    return collected, missing


def render_context(
    root: Path,
    collected_files: Iterable[CollectedFile],
    missing_files: Iterable[str],
) -> str:
    collected = list(collected_files)
    missing = list(missing_files)

    lines: list[str] = [
        "# Project KATANA Sprint52 Context",
        "",
        f"Project root: {root}",
        f"Collected files: {len(collected)}",
        f"Missing files: {len(missing)}",
        "",
        "## Current verified state",
        "",
        "- Sprint51 completed",
        "- 911 tests passed",
        "- Walk-Forward Optimization CLI integrated",
        "- CSV/JSON Walk-Forward reports implemented",
        "",
        "## Proposed Sprint52-1 target",
        "",
        "Realtime market data monitoring foundation",
        "- Market session state model",
        "- Trading-day and market-hours decision service",
        "- New 5-minute bar detection",
        "- Duplicate-bar prevention",
        "- Poll-cycle result model",
        "- Safe idle behavior outside market hours",
        "- Focused unit tests",
        "- No broker live-order submission yet",
        "- Preserve all existing behavior and tests",
        "",
    ]

    if missing:
        lines.extend(
            [
                "## Missing files",
                "",
                *[f"- {path}" for path in missing],
                "",
            ]
        )

    lines.extend(["## Collected source files", ""])

    for item in collected:
        language = "python" if item.absolute_path.suffix == ".py" else "text"
        lines.extend(
            [
                "=" * 100,
                f"FILE: {item.relative_path}",
                "=" * 100,
                f"```{language}",
                item.content.rstrip(),
                "```",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    output_path = resolve_output_path(
        root,
        args.output.expanduser(),
    ).resolve()

    if not root.is_dir():
        print(
            f"ERROR: プロジェクトルートが存在しません: {root}",
            file=sys.stderr,
        )
        return 1

    try:
        collected, missing = collect_files(root, TARGET_FILES)
    except (OSError, UnicodeError) as error:
        print(
            f"ERROR: ファイル読み込みに失敗しました: {error}",
            file=sys.stderr,
        )
        return 1

    if missing and not args.allow_missing:
        print(
            "ERROR: 次の対象ファイルが見つかりません:",
            file=sys.stderr,
        )

        for relative_path in missing:
            print(f"  - {relative_path}", file=sys.stderr)

        print(
            "\n不足ファイルを確認するか、--allow-missing を指定してください。",
            file=sys.stderr,
        )
        return 1

    if not collected:
        print(
            "ERROR: 収集できる対象ファイルがありません。",
            file=sys.stderr,
        )
        return 1

    context = render_context(root, collected, missing)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            context,
            encoding="utf-8",
            newline="\n",
        )
    except OSError as error:
        print(
            f"ERROR: 出力に失敗しました: {error}",
            file=sys.stderr,
        )
        return 1

    print("Sprint52コンテキストを生成しました。")
    print(f"出力先: {output_path}")
    print(f"収集済み: {len(collected)} ファイル")
    print(f"不足: {len(missing)} ファイル")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
