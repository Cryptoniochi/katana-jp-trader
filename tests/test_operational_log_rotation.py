"""運用ログローテーションのテスト。"""

from pathlib import Path

from app.runtime.operational_log_rotation import (
    rotate_log_file,
    rotate_operational_logs,
)


def test_small_log_is_not_rotated(
    tmp_path: Path,
) -> None:
    path = tmp_path / "katana.log"
    path.write_text(
        "small",
        encoding="utf-8",
    )

    result = rotate_log_file(
        path,
        maximum_bytes=100,
        backup_count=3,
    )

    assert not result.rotated
    assert path.read_text(
        encoding="utf-8"
    ) == "small"


def test_large_log_is_rotated(
    tmp_path: Path,
) -> None:
    path = tmp_path / "katana.log"
    path.write_bytes(b"x" * 20)

    result = rotate_log_file(
        path,
        maximum_bytes=10,
        backup_count=3,
    )

    assert result.rotated
    assert path.exists()
    assert path.stat().st_size == 0
    assert (
        tmp_path / "katana.log.1"
    ).stat().st_size == 20


def test_operational_targets_are_supported(
    tmp_path: Path,
) -> None:
    results = rotate_operational_logs(
        project_directory=tmp_path,
        maximum_bytes=10,
        backup_count=2,
    )

    assert len(results) == 3


def test_locked_log_falls_back_to_copy_and_truncate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "katana_service.log"
    path.write_bytes(b"x" * 20)

    original_replace = Path.replace

    def locked_replace(self, target):
        if self == path:
            raise PermissionError("simulated Windows file lock")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", locked_replace)

    result = rotate_log_file(
        path,
        maximum_bytes=10,
        backup_count=3,
    )

    assert result.rotated
    assert result.original_size == 20
    assert path.exists()
    assert path.stat().st_size == 0
    assert (
        tmp_path / "katana_service.log.1"
    ).read_bytes() == b"x" * 20


def test_locked_log_fallback_preserves_backup_generations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "katana_service.log"
    path.write_bytes(b"current-current")
    (tmp_path / "katana_service.log.1").write_bytes(b"previous-1")
    (tmp_path / "katana_service.log.2").write_bytes(b"previous-2")

    original_replace = Path.replace

    def locked_replace(self, target):
        if self == path:
            raise PermissionError("simulated Windows file lock")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", locked_replace)

    result = rotate_log_file(
        path,
        maximum_bytes=10,
        backup_count=3,
    )

    assert result.rotated
    assert path.stat().st_size == 0
    assert (
        tmp_path / "katana_service.log.1"
    ).read_bytes() == b"current-current"
    assert (
        tmp_path / "katana_service.log.2"
    ).read_bytes() == b"previous-1"
    assert (
        tmp_path / "katana_service.log.3"
    ).read_bytes() == b"previous-2"
