"""Project KATANA運用ログの世代管理。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LogRotationResult:
    """1ファイルのローテーション結果。"""

    path: Path
    existed: bool
    original_size: int
    rotated: bool


def rotate_log_file(
    path: Path,
    *,
    maximum_bytes: int,
    backup_count: int,
) -> LogRotationResult:
    """指定サイズを超えたログを世代管理する。"""

    if maximum_bytes <= 0:
        raise ValueError(
            "最大ログサイズは0より大きい必要があります。"
        )

    if backup_count <= 0:
        raise ValueError(
            "バックアップ世代数は0より大きい必要があります。"
        )

    target = Path(path)

    if not target.exists():
        return LogRotationResult(
            path=target,
            existed=False,
            original_size=0,
            rotated=False,
        )

    original_size = target.stat().st_size

    if original_size < maximum_bytes:
        return LogRotationResult(
            path=target,
            existed=True,
            original_size=original_size,
            rotated=False,
        )

    oldest = target.with_name(
        f"{target.name}.{backup_count}"
    )

    if oldest.exists():
        oldest.unlink()

    for index in range(
        backup_count - 1,
        0,
        -1,
    ):
        source = target.with_name(
            f"{target.name}.{index}"
        )

        if source.exists():
            destination = target.with_name(
                f"{target.name}.{index + 1}"
            )
            source.replace(destination)

    target.replace(
        target.with_name(
            f"{target.name}.1"
        )
    )
    target.touch()

    return LogRotationResult(
        path=target,
        existed=True,
        original_size=original_size,
        rotated=True,
    )


def rotate_operational_logs(
    *,
    project_directory: Path,
    maximum_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> tuple[LogRotationResult, ...]:
    """主要な運用ログをまとめてローテーションする。"""

    project = Path(project_directory)
    targets = (
        project
        / "logs"
        / "service"
        / "katana_service.log",
        project
        / "logs"
        / "dashboard"
        / "dashboard_resident.log",
        project
        / "katana.log",
    )

    return tuple(
        rotate_log_file(
            target,
            maximum_bytes=maximum_bytes,
            backup_count=backup_count,
        )
        for target in targets
    )
