"""本番Paper Trading開始前の総合診断を行う。"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from app.runtime.paper_trading_composition import (
    PaperTradingProductionSettings,
)


class ProductionReadinessStatus(StrEnum):
    """個別診断項目の状態。"""

    OK = "ok"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ProductionReadinessItem:
    """本番運転前の個別診断結果。"""

    name: str
    status: ProductionReadinessStatus
    message: str

    def __post_init__(self) -> None:
        """診断項目を検証して正規化する。"""

        normalized_name = self.name.strip()
        normalized_message = self.message.strip()

        if not normalized_name:
            raise ValueError(
                "診断項目名を指定してください。"
            )

        if not normalized_message:
            raise ValueError(
                "診断結果メッセージを指定してください。"
            )

        object.__setattr__(
            self,
            "name",
            normalized_name,
        )
        object.__setattr__(
            self,
            "message",
            normalized_message,
        )

    @property
    def is_ok(self) -> bool:
        """診断項目が正常か返す。"""

        return self.status is ProductionReadinessStatus.OK

    @property
    def is_failed(self) -> bool:
        """診断項目が失敗か返す。"""

        return (
            self.status
            is ProductionReadinessStatus.FAILED
        )


@dataclass(frozen=True, slots=True)
class ProductionReadinessReport:
    """本番運転前診断の総合結果。"""

    items: tuple[ProductionReadinessItem, ...]

    @property
    def is_ready(self) -> bool:
        """すべての診断項目が正常か返す。"""

        return all(
            item.is_ok
            for item in self.items
        )

    @property
    def failure_count(self) -> int:
        """失敗した診断項目数を返す。"""

        return sum(
            item.is_failed
            for item in self.items
        )

    @property
    def ok_count(self) -> int:
        """正常な診断項目数を返す。"""

        return sum(
            item.is_ok
            for item in self.items
        )


class ProductionReadinessBundle(Protocol):
    """診断対象となる本番Composition Bundle。"""

    day_service: object
    trading_loop_component: object
    runtime_bundle: object
    market_monitor: object
    paper_broker: object
    portfolio_service: object


class ProductionReadinessCompositionFactory(Protocol):
    """本番Compositionを生成するFactory。"""

    @staticmethod
    def create(
        *,
        settings: PaperTradingProductionSettings,
        now_provider=None,
        stop_requested=None,
    ) -> ProductionReadinessBundle:
        """本番Composition Bundleを返す。"""


NotificationChannelProvider = Callable[
    [],
    tuple[str, ...],
]
TradingDayProvider = Callable[
    [date],
    bool,
]
TodayProvider = Callable[
    [],
    date,
]


PythonVersionProvider = Callable[
    [],
    tuple[int, int, int],
]


class ProductionReadinessChecker:
    """本番Paper Tradingの起動条件を診断する。"""

    MINIMUM_PYTHON_VERSION = (
        3,
        11,
        0,
    )

    def __init__(
        self,
        *,
        composition_factory: (
            ProductionReadinessCompositionFactory
        ),
        python_version_provider: (
            PythonVersionProvider | None
        ) = None,
        notification_channel_provider: (
            NotificationChannelProvider | None
        ) = None,
        trading_day_provider: (
            TradingDayProvider | None
        ) = None,
        today_provider: TodayProvider | None = None,
    ) -> None:
        """Composition Factoryと運用診断用Providerを設定する。"""

        self.composition_factory = composition_factory
        self.python_version_provider = (
            python_version_provider
            if python_version_provider is not None
            else self._current_python_version
        )
        self.notification_channel_provider = (
            notification_channel_provider
        )
        self.trading_day_provider = trading_day_provider
        self.today_provider = (
            today_provider
            if today_provider is not None
            else date.today
        )

    def check(
        self,
        *,
        settings: PaperTradingProductionSettings,
    ) -> ProductionReadinessReport:
        """本番運転に必要な条件を順番に診断する。"""

        items: list[ProductionReadinessItem] = []

        python_item = self._check_python_version()
        items.append(python_item)

        settings_item = self._check_settings(
            settings
        )
        items.append(settings_item)

        runtime_settings_item = (
            self._check_runtime_settings(
                settings
            )
        )
        items.append(runtime_settings_item)

        if self.notification_channel_provider is not None:
            items.append(
                self._check_notification_channels()
            )

        if self.trading_day_provider is not None:
            items.append(
                self._check_trading_day()
            )

        api_key_item = self._check_api_key(
            settings
        )
        items.append(api_key_item)

        database_parent_item = (
            self._check_database_parent(
                settings.database_path
            )
        )
        items.append(database_parent_item)

        if any(
            item.is_failed
            for item in items
        ):
            return ProductionReadinessReport(
                items=tuple(items)
            )

        try:
            bundle = (
                self.composition_factory.create(
                    settings=settings,
                    stop_requested=lambda: False,
                )
            )
        except Exception as error:
            items.append(
                self._failed(
                    "Composition",
                    (
                        "本番Compositionを生成できませんでした。 "
                        f"error={self._error_message(error)}"
                    ),
                )
            )

            return ProductionReadinessReport(
                items=tuple(items)
            )

        items.append(
            self._ok(
                "Composition",
                "本番Compositionを生成できました。",
            )
        )

        items.append(
            self._check_database(
                settings.database_path
            )
        )

        items.extend(
            self._check_bundle_components(
                bundle
            )
        )

        return ProductionReadinessReport(
            items=tuple(items)
        )

    def _check_python_version(
        self,
    ) -> ProductionReadinessItem:
        """Pythonバージョンを診断する。"""

        current = (
            self.python_version_provider()
        )

        if current < self.MINIMUM_PYTHON_VERSION:
            return self._failed(
                "Python",
                (
                    "Python 3.11以上が必要です。 "
                    "current="
                    f"{current[0]}.{current[1]}.{current[2]}"
                ),
            )

        return self._ok(
            "Python",
            (
                "対応Pythonバージョンです。 "
                "current="
                f"{current[0]}.{current[1]}.{current[2]}"
            ),
        )

    @staticmethod
    def _check_settings(
        settings: PaperTradingProductionSettings,
    ) -> ProductionReadinessItem:
        """監視対象などの本番設定を診断する。"""

        if not settings.codes:
            return ProductionReadinessChecker._failed(
                "Settings",
                "監視対象銘柄がありません。",
            )

        return ProductionReadinessChecker._ok(
            "Settings",
            (
                "本番設定を読み込めました。 "
                f"code_count={len(settings.codes)}"
            ),
        )

    @staticmethod
    def _check_runtime_settings(
        settings: PaperTradingProductionSettings,
    ) -> ProductionReadinessItem:
        """Paper Tradingの主要Runtime設定を診断する。"""

        if settings.initial_cash <= 0:
            return ProductionReadinessChecker._failed(
                "Runtime Settings",
                "初期資金は0より大きい必要があります。",
            )

        if settings.cycle_interval_seconds < 0:
            return ProductionReadinessChecker._failed(
                "Runtime Settings",
                "サイクル間隔は0秒以上である必要があります。",
            )

        if (
            settings.maximum_cycles is not None
            and settings.maximum_cycles <= 0
        ):
            return ProductionReadinessChecker._failed(
                "Runtime Settings",
                "最大サイクル数は0より大きい必要があります。",
            )

        return ProductionReadinessChecker._ok(
            "Runtime Settings",
            (
                "Runtime設定を確認しました。 "
                f"initial_cash={settings.initial_cash:.2f} "
                "cycle_interval_seconds="
                f"{settings.cycle_interval_seconds} "
                f"maximum_cycles={settings.maximum_cycles}"
            ),
        )

    def _check_notification_channels(
        self,
    ) -> ProductionReadinessItem:
        """外部通知チャネルが1件以上有効か診断する。"""

        assert self.notification_channel_provider is not None

        try:
            raw_channels = (
                self.notification_channel_provider()
            )
            channels = tuple(
                dict.fromkeys(
                    channel.strip()
                    for channel in raw_channels
                    if channel.strip()
                )
            )
        except Exception as error:
            return self._failed(
                "Notification Channels",
                (
                    "通知設定を読み込めませんでした。 "
                    f"error={self._error_message(error)}"
                ),
            )

        if not channels:
            return self._failed(
                "Notification Channels",
                (
                    "DiscordまたはLINEの通知チャネルが"
                    "設定されていません。"
                ),
            )

        return self._ok(
            "Notification Channels",
            (
                "外部通知チャネルが有効です。 "
                f"channels={','.join(channels)}"
            ),
        )

    def _check_trading_day(
        self,
    ) -> ProductionReadinessItem:
        """診断日が東京市場の営業日か確認する。"""

        assert self.trading_day_provider is not None
        target_date = self.today_provider()

        try:
            is_trading_day = self.trading_day_provider(
                target_date
            )
        except Exception as error:
            return self._failed(
                "Trading Day",
                (
                    "営業日判定に失敗しました。 "
                    f"date={target_date.isoformat()} "
                    f"error={self._error_message(error)}"
                ),
            )

        if not is_trading_day:
            return self._ok(
                "Trading Day",
                (
                    "診断日は東京市場の非営業日です。 "
                    "診断は有効ですが、取引は開始されません。 "
                    f"date={target_date.isoformat()}"
                ),
            )

        return self._ok(
            "Trading Day",
            (
                "診断日は東京市場の営業日です。 "
                f"date={target_date.isoformat()}"
            ),
        )

    @staticmethod
    def _check_api_key(
        settings: PaperTradingProductionSettings,
    ) -> ProductionReadinessItem:
        """J-Quants APIキーの有無を診断する。"""

        api_key = (
            ""
            if settings.jquants_api_key is None
            else settings.jquants_api_key.strip()
        )

        if not api_key:
            return ProductionReadinessChecker._failed(
                "J-Quants API Key",
                (
                    "J-Quants APIキーが設定されていません。 "
                    "環境変数JQUANTS_API_KEYを設定してください。"
                ),
            )

        return ProductionReadinessChecker._ok(
            "J-Quants API Key",
            "J-Quants APIキーが設定されています。",
        )

    @staticmethod
    def _check_database_parent(
        database_path: Path,
    ) -> ProductionReadinessItem:
        """DB保存先ディレクトリを診断する。"""

        parent = Path(database_path).parent

        try:
            parent.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as error:
            return ProductionReadinessChecker._failed(
                "Database Directory",
                (
                    "DB保存先ディレクトリを準備できません。 "
                    f"path={parent} "
                    f"error={ProductionReadinessChecker._error_message(error)}"
                ),
            )

        if not parent.is_dir():
            return ProductionReadinessChecker._failed(
                "Database Directory",
                (
                    "DB保存先がディレクトリではありません。 "
                    f"path={parent}"
                ),
            )

        return ProductionReadinessChecker._ok(
            "Database Directory",
            (
                "DB保存先ディレクトリを使用できます。 "
                f"path={parent}"
            ),
        )

    @staticmethod
    def _check_database(
        database_path: Path,
    ) -> ProductionReadinessItem:
        """SQLite接続と一時書込みを診断する。"""

        resolved_path = Path(database_path)

        if not resolved_path.exists():
            return ProductionReadinessChecker._failed(
                "Database",
                (
                    "Composition生成後もDBが存在しません。 "
                    f"path={resolved_path}"
                ),
            )

        if not resolved_path.is_file():
            return ProductionReadinessChecker._failed(
                "Database",
                (
                    "DBパスがファイルではありません。 "
                    f"path={resolved_path}"
                ),
            )

        try:
            with sqlite3.connect(
                resolved_path
            ) as connection:
                connection.execute(
                    """
                    CREATE TEMP TABLE
                    katana_readiness_check (
                        id INTEGER PRIMARY KEY,
                        checked INTEGER NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO katana_readiness_check (
                        checked
                    )
                    VALUES (1)
                    """
                )
                row = connection.execute(
                    """
                    SELECT checked
                    FROM katana_readiness_check
                    WHERE id = 1
                    """
                ).fetchone()

            if row is None or int(row[0]) != 1:
                raise RuntimeError(
                    "SQLite一時書込み結果を確認できません。"
                )

        except Exception as error:
            return ProductionReadinessChecker._failed(
                "Database",
                (
                    "SQLite DBへ接続または一時書込みできません。 "
                    f"path={resolved_path} "
                    f"error={ProductionReadinessChecker._error_message(error)}"
                ),
            )

        return ProductionReadinessChecker._ok(
            "Database",
            (
                "SQLite接続と一時書込みを確認しました。 "
                f"path={resolved_path}"
            ),
        )

    @classmethod
    def _check_bundle_components(
        cls,
        bundle: ProductionReadinessBundle,
    ) -> tuple[ProductionReadinessItem, ...]:
        """Composition内の主要Componentを確認する。"""

        components = (
            (
                "Paper Trading Day Service",
                "day_service",
            ),
            (
                "Trading Loop",
                "trading_loop_component",
            ),
            (
                "Paper Trading Runtime",
                "runtime_bundle",
            ),
            (
                "Market Monitor",
                "market_monitor",
            ),
            (
                "Paper Broker",
                "paper_broker",
            ),
            (
                "Portfolio",
                "portfolio_service",
            ),
        )

        items: list[
            ProductionReadinessItem
        ] = []

        for name, attribute_name in components:
            component = getattr(
                bundle,
                attribute_name,
                None,
            )

            if component is None:
                items.append(
                    cls._failed(
                        name,
                        (
                            "Composition内にComponentが"
                            "生成されていません。 "
                            f"attribute={attribute_name}"
                        ),
                    )
                )
                continue

            items.append(
                cls._ok(
                    name,
                    "Componentを生成できました。",
                )
            )

        return tuple(items)

    @staticmethod
    def _current_python_version(
    ) -> tuple[int, int, int]:
        """実行中のPythonバージョンを返す。"""

        return (
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro,
        )

    @staticmethod
    def _ok(
        name: str,
        message: str,
    ) -> ProductionReadinessItem:
        """正常な診断項目を作成する。"""

        return ProductionReadinessItem(
            name=name,
            status=ProductionReadinessStatus.OK,
            message=message,
        )

    @staticmethod
    def _failed(
        name: str,
        message: str,
    ) -> ProductionReadinessItem:
        """失敗した診断項目を作成する。"""

        return ProductionReadinessItem(
            name=name,
            status=ProductionReadinessStatus.FAILED,
            message=message,
        )

    @staticmethod
    def _error_message(
        error: Exception,
    ) -> str:
        """例外を表示可能な文字列へ変換する。"""

        return (
            str(error).strip()
            or type(error).__name__
        )