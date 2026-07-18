"""Sprint70-4F-1 schema version expectation updater.

対象テスト関数の中にある、Schema Versionの期待値
「== 10」を「== SCHEMA_VERSION」へ更新します。
各ファイルのバックアップも作成します。
"""

from __future__ import annotations

import re
from pathlib import Path


TARGETS = {
    Path("tests/test_order_repository.py"):
        "test_initialize_database_creates_trade_orders_table",
    Path("tests/test_portfolio_repository.py"):
        "test_initialize_database_creates_portfolio_tables",
    Path("tests/test_position_repository.py"):
        "test_initialize_database_creates_positions_table",
    Path("tests/test_scheduled_run_state_repository.py"):
        "test_initialize_database_creates_scheduled_run_states_table",
    Path("tests/test_signal_repository.py"):
        "test_initialize_database_creates_trade_signals_table",
    Path("tests/test_trade_execution_repository.py"):
        "test_initialize_database_creates_trade_executions_table",
    Path("tests/test_update_run_repository.py"):
        "test_initialize_database_creates_update_runs_table",
}


def function_span(
    source: str,
    function_name: str,
) -> tuple[int, int]:
    """指定したトップレベルテスト関数の範囲を返す。"""

    pattern = re.compile(
        rf"(?m)^def {re.escape(function_name)}\s*\("
    )
    match = pattern.search(source)

    if match is None:
        raise RuntimeError(
            f"対象テスト関数が見つかりません: {function_name}"
        )

    start = match.start()
    next_function = re.search(
        r"(?m)^def test_",
        source[match.end():],
    )
    end = (
        len(source)
        if next_function is None
        else match.end() + next_function.start()
    )
    return start, end


def update_file(
    path: Path,
    function_name: str,
) -> None:
    """対象関数内のSchema Version固定期待値を更新する。"""

    if not path.exists():
        raise FileNotFoundError(
            f"対象ファイルが見つかりません: {path}"
        )

    original = path.read_text(encoding="utf-8")
    start, end = function_span(original, function_name)
    function_source = original[start:end]

    matches = list(
        re.finditer(r"==\s*10\b", function_source)
    )

    if len(matches) != 1:
        raise RuntimeError(
            f"{path}: {function_name} 内の "
            f"'== 10' が{len(matches)}件です。"
            "安全のため自動変更を中止しました。"
        )

    updated_function = re.sub(
        r"==\s*10\b",
        "== SCHEMA_VERSION",
        function_source,
        count=1,
    )
    updated = (
        original[:start]
        + updated_function
        + original[end:]
    )

    if "SCHEMA_VERSION" not in original:
        import_match = re.search(
            r"(?m)^from app\.database import \((?P<body>.*?)^\)",
            updated,
            flags=re.DOTALL,
        )

        if import_match is not None:
            body = import_match.group("body")
            replacement = (
                "from app.database import (\n"
                "    SCHEMA_VERSION,\n"
                f"{body}"
                ")"
            )
            updated = (
                updated[:import_match.start()]
                + replacement
                + updated[import_match.end():]
            )
        else:
            single_import = re.search(
                r"(?m)^from app\.database import "
                r"initialize_database\s*$",
                updated,
            )
            if single_import is not None:
                updated = (
                    updated[:single_import.start()]
                    + "from app.database import (\n"
                    + "    SCHEMA_VERSION,\n"
                    + "    initialize_database,\n"
                    + ")"
                    + updated[single_import.end():]
                )
            else:
                raise RuntimeError(
                    f"{path}: app.database importを"
                    "自動更新できませんでした。"
                )

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        backup.write_text(
            original,
            encoding="utf-8",
            newline="\n",
        )

    path.write_text(
        updated,
        encoding="utf-8",
        newline="\n",
    )
    print(f"updated: {path}")


def main() -> int:
    for path, function_name in TARGETS.items():
        update_file(path, function_name)

    print("complete: 7 files updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
