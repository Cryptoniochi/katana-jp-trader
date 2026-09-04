"""Sprint 131-3: Universe Bootstrap chunk size regression tests。"""

from pathlib import Path

from app.runtime.universe_daily_scheduler import UniverseDailyScheduler


def test_default_bootstrap_chunk_size_is_50(tmp_path: Path) -> None:
    scheduler = UniverseDailyScheduler(
        enabled=False,
        database_path=tmp_path / "katana.db",
    )

    assert scheduler.maximum_symbols_per_run == 50


def test_bootstrap_command_uses_configured_chunk_size(
    tmp_path: Path,
) -> None:
    captured: list[list[str]] = []

    class Completed:
        returncode = 0

    def runner(command, **_kwargs):
        captured.append(command)
        return Completed()

    scheduler = UniverseDailyScheduler(
        enabled=False,
        database_path=tmp_path / "katana.db",
        maximum_symbols_per_run=50,
        command_runner=runner,
    )

    scheduler._run_bootstrap(
        target_date=__import__("datetime").date(2026, 9, 3)
    )

    command = captured[0]
    index = command.index("--maximum-symbols-per-run")
    assert command[index + 1] == "50"
