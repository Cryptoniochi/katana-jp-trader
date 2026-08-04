"""Dynamic Watchlist銘柄名Cache連携のテスト。"""

import json
from pathlib import Path

from app.runtime.dynamic_watchlist_scheduler import (
    DynamicWatchlistScheduler,
)


class FakeResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def resolve(
        self,
        codes,
    ) -> dict[str, str]:
        normalized = tuple(codes)
        self.calls.append(normalized)
        return {
            code: f"name-{code}"
            for code in normalized
        }


def create_scheduler(
    tmp_path: Path,
    resolver: FakeResolver,
) -> DynamicWatchlistScheduler:
    report = tmp_path / "reports" / "watchlist" / "latest.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "selected": [
                    {"code": "7203"},
                    {"code": "8306"},
                    {"code": "7203"},
                ]
            }
        ),
        encoding="utf-8",
    )

    return DynamicWatchlistScheduler(
        enabled=True,
        database_path=tmp_path / "data" / "katana.db",
        latest_report_path=report,
        marker_directory=tmp_path / "markers",
        status_path=tmp_path / "status.json",
        symbol_name_resolver=resolver,
    )


def test_refresh_symbol_names_uses_selected_unique_codes(
    tmp_path: Path,
) -> None:
    resolver = FakeResolver()
    scheduler = create_scheduler(
        tmp_path,
        resolver,
    )

    assert scheduler._refresh_symbol_names() == 2
    assert resolver.calls == [
        ("7203", "8306")
    ]


def test_refresh_symbol_names_once_updates_old_marker(
    tmp_path: Path,
) -> None:
    resolver = FakeResolver()
    scheduler = create_scheduler(
        tmp_path,
        resolver,
    )
    marker = tmp_path / "markers" / "2026-08-04.applied.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(
        '{"target_date":"2026-08-04"}',
        encoding="utf-8",
    )

    assert scheduler._refresh_symbol_names_once(
        marker_path=marker
    ) == 2
    assert scheduler._refresh_symbol_names_once(
        marker_path=marker
    ) is None
    assert len(resolver.calls) == 1

    payload = json.loads(
        marker.read_text(encoding="utf-8")
    )
    assert payload["symbol_names_refreshed"] is True
    assert payload["resolved_symbol_name_count"] == 2
