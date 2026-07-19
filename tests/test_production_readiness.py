"""Production Readiness Checkのテスト。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.database import initialize_database
from app.runtime.paper_trading_composition import (
    PaperTradingProductionSettings,
)
from app.runtime.production_readiness import (
    ProductionReadinessChecker,
    ProductionReadinessStatus,
)


class FakeBundle:
    """主要Componentを保持する診断用Bundle。"""

    day_service = object()
    trading_loop_component = object()
    runtime_bundle = object()
    market_monitor = object()
    paper_broker = object()
    portfolio_service = object()


class MissingComponentBundle:
    """一部Componentが欠けた診断用Bundle。"""

    day_service = object()
    trading_loop_component = None
    runtime_bundle = object()
    market_monitor = object()
    paper_broker = object()
    portfolio_service = object()


class FakeCompositionFactory:
    """DBを初期化してFake Bundleを返す。"""

    bundle = FakeBundle()
    error: Exception | None = None
    call_count = 0

    @classmethod
    def reset(
        cls,
        *,
        bundle=None,
        error: Exception | None = None,
    ) -> None:
        cls.bundle = (
            bundle
            if bundle is not None
            else FakeBundle()
        )
        cls.error = error
        cls.call_count = 0

    @classmethod
    def create(
        cls,
        *,
        settings,
        now_provider=None,
        stop_requested=None,
    ):
        cls.call_count += 1

        if cls.error is not None:
            raise cls.error

        settings.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        initialize_database(
            settings.database_path
        )

        return cls.bundle


def create_settings(
    tmp_path: Path,
    *,
    api_key: str | None = "test-key",
) -> PaperTradingProductionSettings:
    """診断用の正常設定を作成する。"""

    return PaperTradingProductionSettings(
        database_path=(
            tmp_path / "data" / "katana.db"
        ),
        codes=("7203", "6758"),
        jquants_api_key=api_key,
    )


def test_readiness_report_is_ready(
    tmp_path: Path,
) -> None:
    """すべて正常ならREADYを返す。"""

    FakeCompositionFactory.reset()

    report = ProductionReadinessChecker(
        composition_factory=(
            FakeCompositionFactory
        ),
        python_version_provider=lambda: (
            3,
            14,
            0,
        ),
    ).check(
        settings=create_settings(tmp_path)
    )

    assert report.is_ready
    assert report.failure_count == 0
    assert report.ok_count == len(
        report.items
    )
    assert FakeCompositionFactory.call_count == 1


def test_missing_api_key_is_not_ready(
    tmp_path: Path,
) -> None:
    """APIキーがなければCompositionを生成しない。"""

    FakeCompositionFactory.reset()

    report = ProductionReadinessChecker(
        composition_factory=(
            FakeCompositionFactory
        ),
        python_version_provider=lambda: (
            3,
            14,
            0,
        ),
    ).check(
        settings=create_settings(
            tmp_path,
            api_key=None,
        )
    )

    assert report.is_ready is False
    assert report.failure_count == 1
    assert FakeCompositionFactory.call_count == 0

    failed = next(
        item
        for item in report.items
        if item.is_failed
    )

    assert failed.name == "J-Quants API Key"


def test_old_python_is_not_ready(
    tmp_path: Path,
) -> None:
    """非対応Pythonでは診断を停止する。"""

    FakeCompositionFactory.reset()

    report = ProductionReadinessChecker(
        composition_factory=(
            FakeCompositionFactory
        ),
        python_version_provider=lambda: (
            3,
            10,
            9,
        ),
    ).check(
        settings=create_settings(tmp_path)
    )

    assert report.is_ready is False
    assert FakeCompositionFactory.call_count == 0
    assert report.items[0].status is (
        ProductionReadinessStatus.FAILED
    )
    assert report.items[0].name == "Python"


def test_composition_error_is_reported(
    tmp_path: Path,
) -> None:
    """Composition生成例外を診断失敗へ変換する。"""

    FakeCompositionFactory.reset(
        error=RuntimeError(
            "composition failed"
        )
    )

    report = ProductionReadinessChecker(
        composition_factory=(
            FakeCompositionFactory
        ),
        python_version_provider=lambda: (
            3,
            14,
            0,
        ),
    ).check(
        settings=create_settings(tmp_path)
    )

    assert report.is_ready is False
    assert report.failure_count == 1
    assert report.items[-1].name == "Composition"
    assert (
        "composition failed"
        in report.items[-1].message
    )


def test_missing_component_is_reported(
    tmp_path: Path,
) -> None:
    """Composition内のComponent欠落を検出する。"""

    FakeCompositionFactory.reset(
        bundle=MissingComponentBundle()
    )

    report = ProductionReadinessChecker(
        composition_factory=(
            FakeCompositionFactory
        ),
        python_version_provider=lambda: (
            3,
            14,
            0,
        ),
    ).check(
        settings=create_settings(tmp_path)
    )

    assert report.is_ready is False

    failed_names = {
        item.name
        for item in report.items
        if item.is_failed
    }

    assert failed_names == {
        "Trading Loop"
    }


def test_database_check_uses_temporary_write(
    tmp_path: Path,
) -> None:
    """DB診断後も永続テーブルを追加しない。"""

    FakeCompositionFactory.reset()
    settings = create_settings(tmp_path)

    report = ProductionReadinessChecker(
        composition_factory=(
            FakeCompositionFactory
        ),
        python_version_provider=lambda: (
            3,
            14,
            0,
        ),
    ).check(
        settings=settings
    )

    assert report.is_ready
    assert settings.database_path.exists()

    import sqlite3

    with sqlite3.connect(
        settings.database_path
    ) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'katana_readiness_check'
            """
        ).fetchone()

    assert row is not None
    assert int(row[0]) == 0


def test_optional_operational_checks_are_reported(
    tmp_path: Path,
) -> None:
    """通知・営業日・Runtime設定を診断へ追加できる。"""

    FakeCompositionFactory.reset()

    report = ProductionReadinessChecker(
        composition_factory=FakeCompositionFactory,
        python_version_provider=lambda: (
            3,
            14,
            0,
        ),
        notification_channel_provider=lambda: (
            "discord",
            "line",
        ),
        trading_day_provider=lambda target_date: (
            target_date == date(2026, 7, 21)
        ),
        today_provider=lambda: date(
            2026,
            7,
            21,
        ),
    ).check(
        settings=create_settings(tmp_path)
    )

    assert report.is_ready

    item_map = {
        item.name: item
        for item in report.items
    }

    assert item_map[
        "Runtime Settings"
    ].is_ok
    assert (
        "discord,line"
        in item_map[
            "Notification Channels"
        ].message
    )
    assert (
        "営業日です"
        in item_map["Trading Day"].message
    )


def test_missing_notification_channel_is_not_ready(
    tmp_path: Path,
) -> None:
    """運用診断で通知チャネル未設定を検出する。"""

    FakeCompositionFactory.reset()

    report = ProductionReadinessChecker(
        composition_factory=FakeCompositionFactory,
        python_version_provider=lambda: (
            3,
            14,
            0,
        ),
        notification_channel_provider=lambda: (),
    ).check(
        settings=create_settings(tmp_path)
    )

    assert report.is_ready is False

    failed = next(
        item
        for item in report.items
        if item.name == "Notification Channels"
    )

    assert failed.is_failed
    assert FakeCompositionFactory.call_count == 0


def test_non_trading_day_is_informational(
    tmp_path: Path,
) -> None:
    """非営業日でもシステム自体のREADY判定を妨げない。"""

    FakeCompositionFactory.reset()

    report = ProductionReadinessChecker(
        composition_factory=FakeCompositionFactory,
        python_version_provider=lambda: (
            3,
            14,
            0,
        ),
        trading_day_provider=lambda _date: False,
        today_provider=lambda: date(
            2026,
            7,
            19,
        ),
    ).check(
        settings=create_settings(tmp_path)
    )

    assert report.is_ready

    trading_day = next(
        item
        for item in report.items
        if item.name == "Trading Day"
    )

    assert trading_day.is_ok
    assert "非営業日" in trading_day.message
