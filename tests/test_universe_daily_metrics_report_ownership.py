from pathlib import Path

from app.run_universe_bootstrap import build_argument_parser
from app.universe.kabu_station_universe_daily_collector import (
    KabuStationUniverseDailyBarCollector,
)


class FakeClient:
    class Settings:
        maximum_registered_symbols = 50
        timeout_seconds = 4.0

    settings = Settings()

    def register_symbols(self, symbols):
        return tuple(symbols)

    def unregister_all(self):
        return None


class FakeRepository:
    def upsert_many(self, bars):
        return len(tuple(bars))


def test_collector_default_does_not_target_production_metrics():
    collector = KabuStationUniverseDailyBarCollector(
        client=FakeClient(),
        database_path=Path("unused.db"),
        repository=FakeRepository(),
    )
    assert collector.metrics_report_path is None


def test_bootstrap_cli_explicitly_owns_production_metrics_path():
    parsed = build_argument_parser().parse_args([])
    assert parsed.board_metrics_report_path == Path(
        "reports/universe/board_metrics_latest.json"
    )


def test_bootstrap_cli_allows_metrics_path_override(tmp_path):
    target = tmp_path / "board.json"
    parsed = build_argument_parser().parse_args(
        ["--board-metrics-report-path", str(target)]
    )
    assert parsed.board_metrics_report_path == target
