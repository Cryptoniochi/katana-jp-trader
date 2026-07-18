"""Sprint70-4F-1: schema version assertions updater.

7つの既存テストファイルにある
    assert SCHEMA_VERSION == 10
を
    assert SCHEMA_VERSION == 11
へ置換します。
"""

from __future__ import annotations

from pathlib import Path


TARGETS = (
    Path("tests/test_order_repository.py"),
    Path("tests/test_portfolio_repository.py"),
    Path("tests/test_position_repository.py"),
    Path("tests/test_scheduled_run_state_repository.py"),
    Path("tests/test_signal_repository.py"),
    Path("tests/test_trade_execution_repository.py"),
    Path("tests/test_update_run_repository.py"),
)

OLD = "assert SCHEMA_VERSION == 10"
NEW = "assert SCHEMA_VERSION == 11"


def main() -> int:
    for path in TARGETS:
        if not path.exists():
            raise FileNotFoundError(
                f"対象ファイルが見つかりません: {path}"
            )

        original = path.read_text(encoding="utf-8")
        count = original.count(OLD)

        if count != 1:
            raise RuntimeError(
                f"{path}: '{OLD}' が {count} 件です。"
            )

        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            backup.write_text(
                original,
                encoding="utf-8",
                newline="\n",
            )

        path.write_text(
            original.replace(OLD, NEW, 1),
            encoding="utf-8",
            newline="\n",
        )
        print(f"updated: {path}")

    print("complete: 7 files updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
