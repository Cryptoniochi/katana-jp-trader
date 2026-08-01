"""OperationalReadinessServiceのテスト。"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.runtime.operational_readiness_service import (
    OperationalReadinessService,
)


NOW = datetime(
    2026,
    8,
    1,
    tzinfo=timezone.utc,
)


class FakeStatusReader:
    def __init__(
        self,
        *,
        service_state="healthy",
        stale=False,
        kabu_state="connected",
    ) -> None:
        self.payload = {
            "service_state": service_state,
            "stale": stale,
            "status_age_seconds": 5,
            "kabu_station_readiness": kabu_state,
        }

    def read(self):
        return self.payload


def create_database(
    tmp_path: Path,
) -> Path:
    path = tmp_path / "katana.db"

    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE sample (id INTEGER)"
        )
        connection.commit()

    return path


def test_readiness_is_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    watchlist = tmp_path / "watchlist.txt"
    watchlist.write_text(
        "7203\n6758\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.runtime.operational_readiness_service.shutil.which",
        lambda _name: "tailscale",
    )

    payload = OperationalReadinessService(
        database_path=create_database(tmp_path),
        watchlist_path=watchlist,
        service_status_reader=FakeStatusReader(),
        project_directory=tmp_path,
        minimum_free_bytes=0,
        now_provider=lambda: NOW,
        tailscale_runner=lambda *_args, **_kwargs: (
            SimpleNamespace(
                returncode=0,
                stdout="100.64.14.23\n",
                stderr="",
            )
        ),
    ).evaluate()

    assert payload.overall_state == "ready"
    assert payload.ready_for_paper_trading


def test_disconnected_kabu_requires_attention(
    tmp_path: Path,
    monkeypatch,
) -> None:
    watchlist = tmp_path / "watchlist.txt"
    watchlist.write_text(
        "7203\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.runtime.operational_readiness_service.shutil.which",
        lambda _name: None,
    )

    payload = OperationalReadinessService(
        database_path=create_database(tmp_path),
        watchlist_path=watchlist,
        service_status_reader=FakeStatusReader(
            kabu_state="disconnected"
        ),
        project_directory=tmp_path,
        minimum_free_bytes=0,
        now_provider=lambda: NOW,
    ).evaluate()

    assert payload.overall_state == "attention"
    assert not payload.ready_for_paper_trading
