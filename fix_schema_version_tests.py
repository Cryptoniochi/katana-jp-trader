"""Project KATANA schema version test expectations updater.

Sprint70-4F-1でSCHEMA_VERSIONを10から11へ更新したことに伴い、
対象テスト7ファイルの固定値比較だけを安全に更新します。
"""

from __future__ import annotations

import re
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

ASSERT_PATTERN = re.compile(
    r"^(?P<indent>\s*)assert(?P<body>.+?)==\s*10\s*$"
)


def update_file(path: Path) -> int:
    """Schema versionを固定値10と比較するassertだけを更新する。"""

    if not path.exists():
        raise FileNotFoundError(
            f"対象ファイルが見つかりません: {path}"
        )

    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    updated_lines: list[str] = []
    replacement_count = 0
    schema_context_remaining = 0

    for line in lines:
        stripped = line.strip().lower()

        if "schema_version" in stripped:
            schema_context_remaining = 12

        match = ASSERT_PATTERN.match(line)
        if (
            match is not None
            and schema_context_remaining > 0
        ):
            updated_lines.append(
                f"{match.group('indent')}assert"
                f"{match.group('body')}== SCHEMA_VERSION"
            )
            replacement_count += 1
        else:
            updated_lines.append(line)

        if schema_context_remaining > 0:
            schema_context_remaining -= 1

    if replacement_count == 0:
        raise RuntimeError(
            "Schema Version 10の固定assertを検出できませんでした: "
            f"{path}"
        )

    updated = "\n".join(updated_lines) + (
        "\n" if original.endswith("\n") else ""
    )

    backup_path = path.with_suffix(path.suffix + ".bak")
    backup_path.write_text(
        original,
        encoding="utf-8",
        newline="\n",
    )
    path.write_text(
        updated,
        encoding="utf-8",
        newline="\n",
    )

    return replacement_count


def main() -> int:
    total = 0

    for path in TARGETS:
        count = update_file(path)
        total += count
        print(f"updated: {path} ({count} replacement)")

    print(f"complete: {total} assertions updated")
    print("backup files were created with the .py.bak suffix")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
