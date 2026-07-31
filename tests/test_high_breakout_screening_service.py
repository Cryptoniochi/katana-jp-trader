"""HighBreakoutScreeningServiceのテスト。"""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.database import initialize_database
from app.strategy.high_breakout_candidate_repository import (
    HighBreakoutCandidateRepository,
)
from app.strategy.high_breakout_models import (
    HighBreakoutScreenerSettings,
)
from app.strategy.high_breakout_screener import (
    HighBreakoutScreener,
)
from app.strategy.high_breakout_screening_service import (
    HighBreakoutScreeningService,
)


JST = ZoneInfo("Asia/Tokyo")


def write_csv(
    path: Path,
    *,
    code: str = "7203",
    breakout: bool = True,
) -> None:
    start = datetime(
        2026,
        1,
        5,
        tzinfo=JST,
    )

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "code",
                "traded_at",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

        for index in range(64):
            close = 1000.0 + index
            writer.writerow(
                [
                    code,
                    (
                        start
                        + timedelta(days=index)
                    ).isoformat(),
                    close - 5,
                    close + 5,
                    close - 10,
                    close,
                    100000,
                ]
            )

        previous_high = 1000.0 + 63 + 5

        if breakout:
            open_price = previous_high + 5
            high_price = previous_high + 15
            low_price = previous_high
            close_price = previous_high + 10
        else:
            open_price = previous_high - 8
            high_price = previous_high
            low_price = previous_high - 18
            close_price = previous_high - 1

        writer.writerow(
            [
                code,
                (
                    start
                    + timedelta(days=64)
                ).isoformat(),
                open_price,
                high_price,
                low_price,
                close_price,
                300000,
            ]
        )


def create_service(
    tmp_path: Path,
) -> tuple[
    HighBreakoutScreeningService,
    HighBreakoutCandidateRepository,
]:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)
    repository = HighBreakoutCandidateRepository(
        database_path
    )

    service = HighBreakoutScreeningService(
        screener=HighBreakoutScreener(
            settings=HighBreakoutScreenerSettings(
                minimum_turnover=0,
                minimum_atr_rate=None,
                maximum_atr_rate=None,
            )
        ),
        candidate_repository=repository,
    )

    return service, repository


def test_service_reads_csv_and_saves_candidates(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "daily.csv"
    write_csv(csv_path)
    service, repository = create_service(
        tmp_path
    )

    candidates = service.run_from_csv(
        csv_path
    )

    assert len(candidates) == 1
    assert candidates[0].code == "7203"
    assert repository.count() == 1


def test_service_returns_empty_for_non_breakout(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "daily.csv"
    write_csv(
        csv_path,
        breakout=False,
    )

    service, repository = create_service(
        tmp_path
    )
    candidates = service.run_from_csv(
        csv_path
    )

    assert candidates == ()
    assert repository.count() == 0
