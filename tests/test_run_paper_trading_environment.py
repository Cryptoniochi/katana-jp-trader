"""run_paper_tradingの`.env`読込テスト。"""

from pathlib import Path

from app.run_paper_trading import (
    build_argument_parser,
    create_production_settings,
    load_runtime_environment,
)


def test_env_file_fills_missing_values(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "KABU_STATION_API_PASSWORD=secret",
                "KATANA_MARKET_DATA_MODE=kabu-station-realtime",
                (
                    "KATANA_ENABLED_STRATEGIES="
                    "orb,pullback,high-breakout"
                ),
            ]
        ),
        encoding="utf-8",
    )

    environment = load_runtime_environment(
        {},
        env_file=env_file,
    )

    assert environment["KABU_STATION_API_PASSWORD"] == "secret"
    assert (
        environment["KATANA_MARKET_DATA_MODE"]
        == "kabu-station-realtime"
    )
    assert (
        environment["KATANA_ENABLED_STRATEGIES"]
        == "orb,pullback,high-breakout"
    )


def test_explicit_environment_overrides_env_file(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "KABU_STATION_API_PASSWORD=from-file\n",
        encoding="utf-8",
    )

    environment = load_runtime_environment(
        {
            "KABU_STATION_API_PASSWORD": (
                "from-process"
            )
        },
        env_file=env_file,
    )

    assert (
        environment["KABU_STATION_API_PASSWORD"]
        == "from-process"
    )


def test_merged_environment_builds_settings(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    watchlist = tmp_path / "watchlist.txt"
    watchlist.write_text("7203\n", encoding="utf-8")
    env_file.write_text(
        "\n".join(
            [
                "KABU_STATION_API_PASSWORD=secret",
                "KATANA_MARKET_DATA_MODE=kabu-station-realtime",
                (
                    "KATANA_ENABLED_STRATEGIES="
                    "orb,pullback,high-breakout"
                ),
                f"KATANA_WATCHLIST_PATH={watchlist}",
            ]
        ),
        encoding="utf-8",
    )

    environment = load_runtime_environment(
        {},
        env_file=env_file,
    )
    arguments = build_argument_parser().parse_args([])
    settings = create_production_settings(
        arguments,
        environ=environment,
    )

    assert settings.kabu_station_api_password == "secret"
    assert settings.enabled_strategy_names == (
        "orb",
        "pullback",
        "high-breakout",
    )
