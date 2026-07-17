"""Project KATANAの設定管理。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Mapping


ROOT_DIR = Path(__file__).resolve().parent.parent


class RuntimeEnvironment(StrEnum):
    """Project KATANAの実行環境。"""

    DEVELOPMENT = "development"
    PAPER = "paper"
    PRODUCTION = "production"


class SettingsError(ValueError):
    """設定値が不正であることを表す。"""


@dataclass(frozen=True, slots=True)
class NotificationSettings:
    """外部通知設定。"""

    discord_webhook_url: str | None = None
    slack_webhook_url: str | None = None
    line_channel_access_token: str | None = None
    line_destination_id: str | None = None

    def __post_init__(self) -> None:
        """通知設定を正規化する。"""

        object.__setattr__(
            self,
            "discord_webhook_url",
            _normalize_optional(self.discord_webhook_url),
        )
        object.__setattr__(
            self,
            "slack_webhook_url",
            _normalize_optional(self.slack_webhook_url),
        )
        object.__setattr__(
            self,
            "line_channel_access_token",
            _normalize_optional(self.line_channel_access_token),
        )
        object.__setattr__(
            self,
            "line_destination_id",
            _normalize_optional(self.line_destination_id),
        )

    @property
    def discord_enabled(self) -> bool:
        return self.discord_webhook_url is not None

    @property
    def slack_enabled(self) -> bool:
        return self.slack_webhook_url is not None

    @property
    def line_enabled(self) -> bool:
        return (
            self.line_channel_access_token is not None
            and self.line_destination_id is not None
        )


@dataclass(frozen=True, slots=True)
class BrokerSettings:
    """Broker接続設定。"""

    broker_name: str = "paper"
    account_id: str | None = None
    api_key: str | None = None
    api_secret: str | None = None

    def __post_init__(self) -> None:
        broker_name = self.broker_name.strip()

        if not broker_name:
            raise SettingsError(
                "Broker名を指定してください。"
            )

        object.__setattr__(self, "broker_name", broker_name)
        object.__setattr__(
            self,
            "account_id",
            _normalize_optional(self.account_id),
        )
        object.__setattr__(
            self,
            "api_key",
            _normalize_optional(self.api_key),
        )
        object.__setattr__(
            self,
            "api_secret",
            _normalize_optional(self.api_secret),
        )


@dataclass(frozen=True, slots=True)
class JQuantsSettings:
    """J-Quants接続設定。"""

    refresh_token: str | None = None
    base_url: str = "https://api.jquants.com"

    def __post_init__(self) -> None:
        base_url = self.base_url.strip()

        if not base_url:
            raise SettingsError(
                "J-Quants Base URLを指定してください。"
            )

        object.__setattr__(
            self,
            "refresh_token",
            _normalize_optional(self.refresh_token),
        )
        object.__setattr__(
            self,
            "base_url",
            base_url.rstrip("/"),
        )


@dataclass(frozen=True, slots=True)
class RiskSettings:
    """主要リスク設定。"""

    max_position_count: int = 5
    max_position_value: float = 1_000_000.0
    max_total_exposure: float = 5_000_000.0
    minimum_cash_balance: float = 500_000.0
    max_daily_loss: float = 100_000.0

    def __post_init__(self) -> None:
        if self.max_position_count <= 0:
            raise SettingsError(
                "最大保有銘柄数は0より大きい必要があります。"
            )

        for name, value in {
            "1銘柄最大投資額": self.max_position_value,
            "最大総投資額": self.max_total_exposure,
            "最低現金残高": self.minimum_cash_balance,
            "日次損失上限": self.max_daily_loss,
        }.items():
            if value < 0:
                raise SettingsError(
                    f"{name}は0以上である必要があります。"
                )


@dataclass(frozen=True, slots=True)
class Settings:
    """アプリケーション全体の設定。"""

    app_name: str = "Project KATANA"
    version: str = "0.35.0"
    environment: RuntimeEnvironment = (
        RuntimeEnvironment.DEVELOPMENT
    )

    config_dir: Path = ROOT_DIR / "config"
    data_dir: Path = ROOT_DIR / "data"
    logs_dir: Path = ROOT_DIR / "logs"
    reports_dir: Path = ROOT_DIR / "reports"

    watchlist_path: Path = ROOT_DIR / "config" / "watchlist.txt"

    csv_dir: Path = ROOT_DIR / "data" / "csv"
    historical_csv_dir: Path = ROOT_DIR / "data" / "historical"
    database_path: Path = ROOT_DIR / "data" / "katana.db"

    notifications: NotificationSettings = field(
        default_factory=NotificationSettings
    )
    broker: BrokerSettings = field(
        default_factory=BrokerSettings
    )
    jquants: JQuantsSettings = field(
        default_factory=JQuantsSettings
    )
    risk: RiskSettings = field(
        default_factory=RiskSettings
    )

    def __post_init__(self) -> None:
        if not self.app_name.strip():
            raise SettingsError(
                "アプリケーション名を指定してください。"
            )

        if not self.version.strip():
            raise SettingsError(
                "バージョンを指定してください。"
            )

        if (
            self.environment is RuntimeEnvironment.PRODUCTION
            and self.broker.broker_name == "paper"
        ):
            raise SettingsError(
                "本番環境ではpaper Brokerを使用できません。"
            )

    def create_directories(self) -> None:
        """必要なフォルダを作成する。"""

        for path in (
            self.config_dir,
            self.data_dir,
            self.logs_dir,
            self.reports_dir,
            self.csv_dir,
            self.historical_csv_dir,
        ):
            path.mkdir(
                parents=True,
                exist_ok=True,
            )

    def masked_summary(self) -> dict[str, object]:
        """機密情報を隠した設定サマリーを返す。"""

        return {
            "app_name": self.app_name,
            "version": self.version,
            "environment": self.environment.value,
            "database_path": str(self.database_path),
            "broker": {
                "broker_name": self.broker.broker_name,
                "account_id": _mask_secret(
                    self.broker.account_id
                ),
                "api_key": _mask_secret(
                    self.broker.api_key
                ),
                "api_secret": _mask_secret(
                    self.broker.api_secret
                ),
            },
            "jquants": {
                "base_url": self.jquants.base_url,
                "refresh_token": _mask_secret(
                    self.jquants.refresh_token
                ),
            },
            "notifications": {
                "discord_webhook_url": _mask_secret(
                    self.notifications.discord_webhook_url
                ),
                "slack_webhook_url": _mask_secret(
                    self.notifications.slack_webhook_url
                ),
                "line_channel_access_token": _mask_secret(
                    self.notifications.line_channel_access_token
                ),
                "line_destination_id": _mask_secret(
                    self.notifications.line_destination_id
                ),
            },
        }

    @classmethod
    def from_environment(
        cls,
        *,
        environment: Mapping[str, str] | None = None,
        env_file: Path | None = None,
    ) -> "Settings":
        """環境変数と.envから設定を作成する。

        優先順位:
        1. ``environment`` 引数またはOS環境変数
        2. ``env_file`` の値
        3. 既定値
        """

        file_values = (
            load_env_file(env_file)
            if env_file is not None
            else {}
        )
        source = dict(file_values)
        source.update(
            dict(os.environ)
            if environment is None
            else dict(environment)
        )

        runtime_environment = RuntimeEnvironment(
            source.get(
                "KATANA_ENVIRONMENT",
                RuntimeEnvironment.DEVELOPMENT.value,
            ).strip().lower()
        )

        notifications = NotificationSettings(
            discord_webhook_url=source.get(
                "KATANA_DISCORD_WEBHOOK_URL"
            ),
            slack_webhook_url=source.get(
                "KATANA_SLACK_WEBHOOK_URL"
            ),
            line_channel_access_token=source.get(
                "KATANA_LINE_CHANNEL_ACCESS_TOKEN"
            ),
            line_destination_id=source.get(
                "KATANA_LINE_DESTINATION_ID"
            ),
        )

        broker = BrokerSettings(
            broker_name=source.get(
                "KATANA_BROKER_NAME",
                "paper",
            ),
            account_id=source.get(
                "KATANA_BROKER_ACCOUNT_ID"
            ),
            api_key=source.get(
                "KATANA_BROKER_API_KEY"
            ),
            api_secret=source.get(
                "KATANA_BROKER_API_SECRET"
            ),
        )

        jquants = JQuantsSettings(
            refresh_token=source.get(
                "KATANA_JQUANTS_REFRESH_TOKEN"
            ),
            base_url=source.get(
                "KATANA_JQUANTS_BASE_URL",
                "https://api.jquants.com",
            ),
        )

        risk = RiskSettings(
            max_position_count=_read_int(
                source,
                "KATANA_MAX_POSITION_COUNT",
                5,
            ),
            max_position_value=_read_float(
                source,
                "KATANA_MAX_POSITION_VALUE",
                1_000_000.0,
            ),
            max_total_exposure=_read_float(
                source,
                "KATANA_MAX_TOTAL_EXPOSURE",
                5_000_000.0,
            ),
            minimum_cash_balance=_read_float(
                source,
                "KATANA_MINIMUM_CASH_BALANCE",
                500_000.0,
            ),
            max_daily_loss=_read_float(
                source,
                "KATANA_MAX_DAILY_LOSS",
                100_000.0,
            ),
        )

        database_path = Path(
            source.get(
                "KATANA_DATABASE_PATH",
                str(ROOT_DIR / "data" / "katana.db"),
            )
        )

        return cls(
            environment=runtime_environment,
            database_path=database_path,
            notifications=notifications,
            broker=broker,
            jquants=jquants,
            risk=risk,
        )


def load_env_file(
    path: Path,
) -> dict[str, str]:
    """単純なKEY=VALUE形式の.envファイルを読み込む。"""

    if not path.exists():
        return {}

    if not path.is_file():
        raise SettingsError(
            ".envのパスがファイルではありません。 "
            f"path={path}"
        )

    values: dict[str, str] = {}

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            raise SettingsError(
                ".envの形式が不正です。 "
                f"path={path} line={line_number}"
            )

        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()

        if not key:
            raise SettingsError(
                ".envのキーが空です。 "
                f"path={path} line={line_number}"
            )

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]

        values[key] = value

    return values


def _normalize_optional(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def _mask_secret(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    if len(value) <= 4:
        return "*" * len(value)

    return (
        value[:2]
        + "*" * (len(value) - 4)
        + value[-2:]
    )


def _read_int(
    source: Mapping[str, str],
    key: str,
    default: int,
) -> int:
    raw_value = source.get(key)

    if raw_value is None:
        return default

    try:
        return int(raw_value)
    except ValueError as error:
        raise SettingsError(
            f"{key}は整数で指定してください。"
        ) from error


def _read_float(
    source: Mapping[str, str],
    key: str,
    default: float,
) -> float:
    raw_value = source.get(key)

    if raw_value is None:
        return default

    try:
        return float(raw_value)
    except ValueError as error:
        raise SettingsError(
            f"{key}は数値で指定してください。"
        ) from error


settings = Settings()
