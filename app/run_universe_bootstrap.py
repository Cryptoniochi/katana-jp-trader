"""全市場Universe Bootstrap CLI。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

from app.market.kabu_station_client import (
    KabuStationClient,
    KabuStationClientSettings,
)
from app.universe.kabu_station_universe_daily_collector import (
    KabuStationUniverseDailyBarCollector,
)
from app.universe.universe_bootstrap_service import UniverseBootstrapService


TOKYO = ZoneInfo("Asia/Tokyo")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "listed_symbolsを起点に全市場の日足を段階的にBootstrapします。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
    )
    parser.add_argument(
        "--trading-date",
        type=lambda value: datetime.fromisoformat(value).date(),
        default=None,
    )
    parser.add_argument(
        "--maximum-symbols-per-run",
        type=int,
        default=300,
    )
    parser.add_argument(
        "--minimum-completion-ratio",
        type=float,
        default=0.99,
    )
    parser.add_argument(
        "--unavailable-path",
        type=Path,
        default=Path(
            "reports/universe/bootstrap_unavailable.json"
        ),
    )
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=0.30,
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=4.0,
    )
    parser.add_argument(
        "--maximum-attempts",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--retry-backoff-seconds",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--minimum-success-ratio",
        type=float,
        default=0.70,
    )
    parser.add_argument(
        "--exchange",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path(
            "reports/universe/bootstrap_latest.json"
        ),
    )
    return parser


def read_setting(key: str, *, env_file: Path) -> str | None:
    value = os.environ.get(key)
    if value:
        return value.strip()

    if not env_file.exists():
        return None

    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or "=" not in stripped
        ):
            continue
        name, raw_value = stripped.split("=", 1)
        if name.strip() != key:
            continue
        normalized = raw_value.strip().strip('"').strip("'")
        return normalized or None

    return None


def write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def run(arguments: Sequence[str] | None = None) -> int:
    parsed = build_argument_parser().parse_args(arguments)

    password = (
        read_setting(
            "KABU_STATION_API_PASSWORD",
            env_file=parsed.env_file,
        )
        or read_setting(
            "KABUSTATION_API_PASSWORD",
            env_file=parsed.env_file,
        )
    )
    if not password:
        raise RuntimeError(
            "KABU_STATION_API_PASSWORDを環境変数または.envに設定してください。"
        )

    base_url = (
        read_setting(
            "KABU_STATION_BASE_URL",
            env_file=parsed.env_file,
        )
        or read_setting(
            "KABU_STATION_API_BASE_URL",
            env_file=parsed.env_file,
        )
        or "http://localhost:18080/kabusapi"
    )

    trading_date = (
        parsed.trading_date
        if parsed.trading_date is not None
        else datetime.now(TOKYO).date()
    )

    client = KabuStationClient(
        settings=KabuStationClientSettings(
            api_password=password,
            base_url=base_url,
            timeout_seconds=parsed.request_timeout_seconds,
        )
    )
    collector = KabuStationUniverseDailyBarCollector(
        client=client,
        database_path=parsed.database_path,
        exchange=parsed.exchange,
        request_interval_seconds=parsed.request_interval_seconds,
        minimum_success_ratio=parsed.minimum_success_ratio,
        maximum_attempts=parsed.maximum_attempts,
        retry_backoff_seconds=parsed.retry_backoff_seconds,
        progress_reporter=lambda message: print(message, flush=True),
    )

    service = UniverseBootstrapService(
        database_path=parsed.database_path,
        collector=collector,
        maximum_symbols_per_run=parsed.maximum_symbols_per_run,
        minimum_completion_ratio=parsed.minimum_completion_ratio,
        unavailable_path=parsed.unavailable_path,
    )

    result = service.run_once(trading_date=trading_date)
    write_report(parsed.report_path, result.to_dict())

    print("Project KATANA Universe Bootstrap")
    print("=" * 48)
    print(f"trading_date={result.trading_date}")
    print(f"universe={result.universe_count}")
    print(f"already_collected={result.already_collected_count}")
    print(f"attempted={result.attempted_count}")
    print(f"collected={result.collected_count}")
    print(f"remaining={result.remaining_count}")
    print(f"retryable_remaining={result.retryable_remaining_count}")
    print(f"terminal_skipped={result.terminal_skipped_count}")
    print(f"coverage_ratio={result.coverage_ratio:.4f}")
    print(f"completed={result.completed}")

    if result.failed_codes:
        print("Failed/Skipped codes (first 20)")
        for code in result.failed_codes[:20]:
            print(f"  {code}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
