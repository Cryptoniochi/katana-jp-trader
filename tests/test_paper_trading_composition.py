"""本番Paper Trading Composition Rootのテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.runtime.paper_trading_composition import (
    PaperTradingComposition,
    PaperTradingProductionBundle,
    PaperTradingProductionSettings,
)


def test_settings_normalizes_codes_and_database_path(
    tmp_path: Path,
) -> None:
    """銘柄コードの空白・重複とDB Pathを正規化する。"""

    database_path = tmp_path / "data" / "katana.db"

    settings = PaperTradingProductionSettings(
        database_path=database_path,
        codes=(
            " 7203 ",
            "6758",
            "7203",
        ),
    )

    assert settings.database_path == database_path
    assert settings.codes == (
        "7203",
        "6758",
    )


@pytest.mark.parametrize(
    "codes",
    [
        (),
        ("",),
        ("720A",),
        ("123",),
        ("123456",),
    ],
)
def test_settings_rejects_invalid_codes(
    tmp_path: Path,
    codes: tuple[str, ...],
) -> None:
    """空または不正な銘柄コードを拒否する。"""

    with pytest.raises(ValueError):
        PaperTradingProductionSettings(
            database_path=tmp_path / "katana.db",
            codes=codes,
        )


@pytest.mark.parametrize(
    (
        "field_name",
        "field_value",
    ),
    [
        ("initial_cash", -1.0),
        ("cycle_interval_seconds", -1.0),
        ("maximum_cycles", 0),
        ("jquants_timeout_seconds", 0.0),
        ("maximum_codes_per_poll", 0),
        ("rate_limit_cooldown_seconds", -1.0),
        ("replay_maximum_lookback_days", 0),
        ("commission_per_order", -1.0),
        ("slippage_rate", -0.01),
    ],
)
def test_settings_rejects_invalid_numeric_values(
    tmp_path: Path,
    field_name: str,
    field_value: object,
) -> None:
    """不正な数値設定を拒否する。"""

    arguments: dict[str, object] = {
        "database_path": tmp_path / "katana.db",
        "codes": ("7203",),
    }
    arguments[field_name] = field_value

    with pytest.raises(ValueError):
        PaperTradingProductionSettings(
            **arguments,
        )


def test_settings_accepts_safe_production_values(
    tmp_path: Path,
) -> None:
    """本番運転向けの正常な設定を保持する。"""

    settings = PaperTradingProductionSettings(
        database_path=tmp_path / "katana.db",
        codes=("7203", "6758"),
        initial_cash=5_000_000.0,
        cycle_interval_seconds=30.0,
        maximum_cycles=10,
        jquants_timeout_seconds=20.0,
        maximum_codes_per_poll=8,
        rate_limit_cooldown_seconds=90.0,
        market_data_mode=" JQUANTS-CURRENT-DAY ",
        replay_maximum_lookback_days=10,
        commission_per_order=100.0,
        slippage_rate=0.001,
        continue_on_cycle_error=True,
        stop_on_cycle_failure=False,
        stop_on_resource_critical=True,
    )

    assert settings.initial_cash == 5_000_000.0
    assert settings.cycle_interval_seconds == 30.0
    assert settings.maximum_cycles == 10
    assert settings.jquants_timeout_seconds == 20.0
    assert settings.maximum_codes_per_poll == 8
    assert settings.rate_limit_cooldown_seconds == 90.0
    assert settings.market_data_mode == "jquants-current-day"
    assert settings.replay_maximum_lookback_days == 10
    assert settings.commission_per_order == 100.0
    assert settings.slippage_rate == 0.001

def test_settings_uses_safe_polling_defaults(
    tmp_path: Path,
) -> None:
    """本番既定値が100銘柄向けの安全な取得制御を保持する。"""

    settings = PaperTradingProductionSettings(
        database_path=tmp_path / "katana.db",
        codes=("7203",),
    )

    assert settings.maximum_codes_per_poll == 10
    assert settings.rate_limit_cooldown_seconds == 60.0


def test_production_bundle_exposes_diagnostic_components() -> None:
    """本番Bundleがデータフロー診断対象を公開する。"""

    field_names = {
        field.name
        for field in PaperTradingProductionBundle.__dataclass_fields__.values()
    }

    assert "replay_provider" in field_names
    assert "live_orchestrator" in field_names
    assert "realtime_paper_trading_service" in field_names
    assert "signal_engine" in field_names


def test_settings_uses_previous_day_replay_by_default(
    tmp_path: Path,
) -> None:
    """Paper Trading既定値は前営業日リプレイを使う。"""

    settings = PaperTradingProductionSettings(
        database_path=tmp_path / "katana.db",
        codes=("7203",),
    )

    assert settings.market_data_mode == "previous-day-replay"
    assert settings.replay_maximum_lookback_days == 14


def test_settings_rejects_unknown_market_data_mode(
    tmp_path: Path,
) -> None:
    """未対応の市場データモードを拒否する。"""

    with pytest.raises(ValueError, match="市場データモード"):
        PaperTradingProductionSettings(
            database_path=tmp_path / "katana.db",
            codes=("7203",),
            market_data_mode="unknown",
        )


def test_settings_accepts_kabu_station_realtime(
    tmp_path: Path,
) -> None:
    settings = PaperTradingProductionSettings(
        database_path=tmp_path / "katana.db",
        codes=("7203",),
        market_data_mode="kabu-station-realtime",
        kabu_station_api_password="secret",
    )

    assert settings.market_data_mode == (
        "kabu-station-realtime"
    )


def test_kabu_station_realtime_requires_password(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="KABU_STATION_API_PASSWORD",
    ):
        PaperTradingProductionSettings(
            database_path=tmp_path / "katana.db",
            codes=("7203",),
            market_data_mode="kabu-station-realtime",
        )


def test_kabu_station_realtime_rejects_more_than_50_codes(
    tmp_path: Path,
) -> None:
    codes = tuple(
        str(1000 + index)
        for index in range(51)
    )

    with pytest.raises(ValueError, match="50銘柄"):
        PaperTradingProductionSettings(
            database_path=tmp_path / "katana.db",
            codes=codes,
            market_data_mode="kabu-station-realtime",
            kabu_station_api_password="secret",
        )
