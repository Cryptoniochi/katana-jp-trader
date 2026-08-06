"""候補ユニバースの日足をkabuステーションから収集するCLI。"""

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


TOKYO = ZoneInfo("Asia/Tokyo")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "DB内の候補ユニバースをBoard APIで照会し、"
            "当日OHLCVをmarket_barsへ保存します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path(
            "reports/universe/"
            "kabu_station_daily_latest.json"
        ),
    )
    parser.add_argument(
        "--exchange",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=0.12,
    )
    parser.add_argument(
        "--minimum-success-ratio",
        type=float,
        default=0.80,
    )
    parser.add_argument(
        "--trading-date",
        type=lambda value: datetime.fromisoformat(
            value
        ).date(),
        default=None,
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    password = str(
        os.environ.get(
            "KABU_STATION_API_PASSWORD",
            "",
        )
    ).strip()

    if not password:
        raise RuntimeError(
            "環境変数KABU_STATION_API_PASSWORDが必要です。"
        )

    trading_date = (
        parsed.trading_date
        if parsed.trading_date is not None
        else datetime.now(TOKYO).date()
    )
    client = KabuStationClient(
        settings=KabuStationClientSettings(
            api_password=password,
        )
    )
    result = KabuStationUniverseDailyBarCollector(
        client=client,
        database_path=parsed.database_path,
        exchange=parsed.exchange,
        request_interval_seconds=(
            parsed.request_interval_seconds
        ),
        minimum_success_ratio=(
            parsed.minimum_success_ratio
        ),
    ).collect(
        trading_date=trading_date
    )

    parsed.report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    parsed.report_path.write_text(
        json.dumps(
            result.to_dict(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Project KATANA Universe Daily Collection")
    print("=" * 48)
    print(f"trading_date={result.trading_date}")
    print(f"requested={result.requested_count}")
    print(f"collected={result.collected_count}")
    print(f"saved={result.saved_count}")
    print(f"skipped={result.skipped_count}")
    print(f"failures={len(result.failures)}")
    print(f"success_ratio={result.success_ratio:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
