"""Project KATANA設定管理のテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.settings import (
    BrokerSettings,
    RuntimeEnvironment,
    Settings,
    SettingsError,
    load_env_file,
)


def test_existing_default_paths_are_preserved() -> None:
    settings = Settings()

    assert settings.watchlist_path.name == "watchlist.txt"
    assert settings.database_path.name == "katana.db"
    assert settings.csv_dir.name == "csv"
    assert settings.historical_csv_dir.name == "historical"


def test_from_environment_reads_nested_settings() -> None:
    settings = Settings.from_environment(
        environment={
            "KATANA_ENVIRONMENT": "paper",
            "KATANA_DISCORD_WEBHOOK_URL": (
                "https://discord.test/hook"
            ),
            "KATANA_SLACK_WEBHOOK_URL": (
                "https://slack.test/hook"
            ),
            "KATANA_BROKER_NAME": "paper",
            "KATANA_JQUANTS_REFRESH_TOKEN": "secret-token",
            "KATANA_MAX_POSITION_COUNT": "8",
            "KATANA_MAX_POSITION_VALUE": "2500000",
            "KATANA_DATABASE_PATH": "data/custom.db",
        }
    )

    assert settings.environment is RuntimeEnvironment.PAPER
    assert settings.notifications.discord_enabled
    assert settings.notifications.slack_enabled
    assert settings.broker.broker_name == "paper"
    assert settings.jquants.refresh_token == "secret-token"
    assert settings.risk.max_position_count == 8
    assert settings.risk.max_position_value == 2_500_000.0
    assert settings.database_path == Path("data/custom.db")


def test_explicit_environment_overrides_env_file(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "KATANA_BROKER_NAME=file-broker\n"
        "KATANA_MAX_POSITION_COUNT=3\n",
        encoding="utf-8",
    )

    settings = Settings.from_environment(
        environment={
            "KATANA_BROKER_NAME": "explicit-broker",
            "KATANA_MAX_POSITION_COUNT": "9",
        },
        env_file=env_file,
    )

    assert settings.broker.broker_name == "explicit-broker"
    assert settings.risk.max_position_count == 9


def test_load_env_file_supports_comments_and_quotes(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\n"
        "\n"
        "A=plain\n"
        "B=\"double quoted\"\n"
        "C='single quoted'\n",
        encoding="utf-8",
    )

    assert load_env_file(env_file) == {
        "A": "plain",
        "B": "double quoted",
        "C": "single quoted",
    }


def test_missing_env_file_returns_empty_mapping(
    tmp_path: Path,
) -> None:
    assert load_env_file(
        tmp_path / "missing.env"
    ) == {}


def test_invalid_env_file_is_rejected(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "INVALID LINE\n",
        encoding="utf-8",
    )

    with pytest.raises(
        SettingsError,
        match="形式が不正",
    ):
        load_env_file(env_file)


def test_invalid_numeric_environment_value_is_rejected() -> None:
    with pytest.raises(
        SettingsError,
        match="整数",
    ):
        Settings.from_environment(
            environment={
                "KATANA_MAX_POSITION_COUNT": "many",
            }
        )


def test_production_rejects_paper_broker() -> None:
    with pytest.raises(
        SettingsError,
        match="paper Broker",
    ):
        Settings(
            environment=RuntimeEnvironment.PRODUCTION,
            broker=BrokerSettings(
                broker_name="paper"
            ),
        )


def test_masked_summary_hides_secrets() -> None:
    settings = Settings.from_environment(
        environment={
            "KATANA_BROKER_API_KEY": "abcdefghij",
            "KATANA_BROKER_API_SECRET": "secret-value",
            "KATANA_JQUANTS_REFRESH_TOKEN": "refresh-token",
            "KATANA_DISCORD_WEBHOOK_URL": (
                "https://discord.test/secret"
            ),
        }
    )

    summary_text = str(settings.masked_summary())

    assert "abcdefghij" not in summary_text
    assert "secret-value" not in summary_text
    assert "refresh-token" not in summary_text
    assert "https://discord.test/secret" not in summary_text


def test_create_directories_creates_required_paths(
    tmp_path: Path,
) -> None:
    settings = Settings(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        logs_dir=tmp_path / "logs",
        reports_dir=tmp_path / "reports",
        csv_dir=tmp_path / "data" / "csv",
        historical_csv_dir=(
            tmp_path / "data" / "historical"
        ),
    )

    settings.create_directories()

    assert settings.config_dir.is_dir()
    assert settings.data_dir.is_dir()
    assert settings.logs_dir.is_dir()
    assert settings.reports_dir.is_dir()
    assert settings.csv_dir.is_dir()
    assert settings.historical_csv_dir.is_dir()
