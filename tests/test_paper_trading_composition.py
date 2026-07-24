"""本番Paper Trading Composition Rootのテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.runtime.paper_trading_composition import (
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
    assert settings.commission_per_order == 100.0
    assert settings.slippage_rate == 0.001