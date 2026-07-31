"""実行経路監査の最小テスト。"""

from pathlib import Path

from app.runtime.paper_trading_composition import (
    PaperTradingProductionSettings,
)


def test_trace_path_is_resolved_under_project_root(
    tmp_path: Path,
) -> None:
    settings = PaperTradingProductionSettings(
        database_path=tmp_path / "katana.db",
        codes=("7203",),
        market_data_mode="kabu-station-realtime",
        kabu_station_api_password="secret",
        risk_trace_path=Path(
            "logs/risk/paper_trading_trace.jsonl"
        ),
    )

    assert settings.risk_trace_path.is_absolute()
    assert settings.risk_trace_path.name == (
        "paper_trading_trace.jsonl"
    )
