"""全市場ユニバースを一次スクリーニングする。"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from app.universe.listed_symbol_repository import (
    ListedSymbolRepository,
)
from app.universe.universe_models import (
    UniverseScreeningCandidate,
    UniverseScreeningReport,
    UniverseScreeningSettings,
)


class UniversePrimaryScreener:
    """約4,000銘柄から最大300銘柄へ絞り込む。"""

    def __init__(
        self,
        *,
        database_path: Path,
        settings: UniverseScreeningSettings | None = None,
        now_provider: Callable[
            [],
            datetime,
        ] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.settings = (
            settings
            if settings is not None
            else UniverseScreeningSettings()
        )
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(
                timezone.utc
            )
        )

    def screen(self) -> UniverseScreeningReport:
        now = self._current_time()
        symbols = ListedSymbolRepository(
            self.database_path
        ).load_active(
            allowed_markets=(
                self.settings.allowed_markets
            ),
            allowed_security_types=(
                self.settings
                .allowed_security_types
            ),
        )
        metrics = self._load_latest_metrics()

        evaluated = []

        for symbol in symbols:
            metric = metrics.get(symbol.code)

            if metric is None:
                continue

            exclusions: list[str] = []
            latest_price = metric["latest_price"]
            purchase_amount = (
                latest_price
                * symbol.trading_unit
            )

            if latest_price < (
                self.settings.minimum_latest_price
            ):
                exclusions.append(
                    "below_minimum_price"
                )

            if latest_price > (
                self.settings.maximum_latest_price
            ):
                exclusions.append(
                    "above_maximum_price"
                )

            if purchase_amount > (
                self.settings.maximum_purchase_amount
            ):
                exclusions.append(
                    "over_purchase_budget"
                )

            if metric["average_volume"] < (
                self.settings.minimum_average_volume
            ):
                exclusions.append(
                    "insufficient_volume"
                )

            if metric["average_turnover"] < (
                self.settings.minimum_average_turnover
            ):
                exclusions.append(
                    "insufficient_turnover"
                )

            age_days = (
                now.date()
                - metric["latest_trading_date"]
            ).days

            if age_days > (
                self.settings.maximum_data_age_days
            ):
                exclusions.append(
                    "stale_data"
                )

            score = self._score(
                average_turnover=(
                    metric["average_turnover"]
                ),
                average_volume=(
                    metric["average_volume"]
                ),
                purchase_amount=purchase_amount,
            )

            evaluated.append(
                UniverseScreeningCandidate(
                    code=symbol.code,
                    name=symbol.name,
                    market=symbol.market,
                    security_type=(
                        symbol.security_type
                    ),
                    trading_unit=(
                        symbol.trading_unit
                    ),
                    latest_price=latest_price,
                    purchase_amount=(
                        purchase_amount
                    ),
                    average_volume=(
                        metric["average_volume"]
                    ),
                    average_turnover=(
                        metric["average_turnover"]
                    ),
                    latest_trading_date=(
                        metric[
                            "latest_trading_date"
                        ]
                    ),
                    score=score,
                    exclusion_reasons=tuple(
                        exclusions
                    ),
                    selected=False,
                )
            )

        eligible = sorted(
            (
                item
                for item in evaluated
                if not item.exclusion_reasons
            ),
            key=lambda item: (
                -item.score,
                -item.average_turnover,
                item.code,
            ),
        )
        selected_codes = {
            item.code
            for item in eligible[
                : self.settings.maximum_symbols
            ]
        }

        selected = tuple(
            self._mark_selected(item)
            for item in eligible
            if item.code in selected_codes
        )
        excluded = tuple(
            item
            for item in evaluated
            if item.code not in selected_codes
        )

        return UniverseScreeningReport(
            generated_at=now,
            universe_count=len(symbols),
            evaluated_count=len(evaluated),
            eligible_count=len(eligible),
            selected_count=len(selected),
            settings=self.settings,
            selected=selected,
            excluded=excluded,
        )

    def _load_latest_metrics(
        self,
    ) -> dict[str, dict[str, object]]:
        if not self.database_path.exists():
            return {}

        with sqlite3.connect(
            self.database_path
        ) as connection:
            if not self._table_exists(
                connection,
                "market_bars",
            ):
                return {}

            rows = connection.execute(
                """
                SELECT
                    code,
                    traded_at,
                    close,
                    volume
                FROM market_bars
                WHERE interval_minutes = 1440
                ORDER BY code ASC,
                         traded_at DESC
                """
            ).fetchall()

        grouped: dict[
            str,
            list[tuple[datetime, float, float]],
        ] = defaultdict(list)

        for code, traded_at, close, volume in rows:
            if len(grouped[str(code)]) >= 20:
                continue

            parsed = datetime.fromisoformat(
                str(traded_at)
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            grouped[str(code)].append(
                (
                    parsed,
                    float(close),
                    float(volume),
                )
            )

        return {
            code: {
                "latest_price": values[0][1],
                "average_volume": (
                    sum(
                        item[2]
                        for item in values
                    )
                    / len(values)
                ),
                "average_turnover": (
                    sum(
                        item[1] * item[2]
                        for item in values
                    )
                    / len(values)
                ),
                "latest_trading_date": (
                    values[0][0].date()
                ),
            }
            for code, values in grouped.items()
            if values
        }

    @staticmethod
    def _score(
        *,
        average_turnover: float,
        average_volume: float,
        purchase_amount: float,
    ) -> float:
        turnover_score = min(
            60.0,
            max(
                0.0,
                (
                    math.log10(
                        max(
                            average_turnover,
                            1.0,
                        )
                    )
                    - 6.0
                )
                / 4.0
                * 60.0,
            ),
        )
        volume_score = min(
            25.0,
            max(
                0.0,
                (
                    math.log10(
                        max(
                            average_volume,
                            1.0,
                        )
                    )
                    - 3.0
                )
                / 4.0
                * 25.0,
            ),
        )
        affordability_score = max(
            0.0,
            15.0
            * (
                1.0
                - min(
                    1.0,
                    purchase_amount
                    / 950_000.0,
                )
            ),
        )

        return round(
            turnover_score
            + volume_score
            + affordability_score,
            4,
        )

    @staticmethod
    def _mark_selected(
        item: UniverseScreeningCandidate,
    ) -> UniverseScreeningCandidate:
        return UniverseScreeningCandidate(
            code=item.code,
            name=item.name,
            market=item.market,
            security_type=item.security_type,
            trading_unit=item.trading_unit,
            latest_price=item.latest_price,
            purchase_amount=item.purchase_amount,
            average_volume=item.average_volume,
            average_turnover=item.average_turnover,
            latest_trading_date=(
                item.latest_trading_date
            ),
            score=item.score,
            exclusion_reasons=(
                item.exclusion_reasons
            ),
            selected=True,
        )

    @staticmethod
    def _table_exists(
        connection: sqlite3.Connection,
        table_name: str,
    ) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            """,
            (table_name,),
        ).fetchone()

        return row is not None

    def _current_time(self) -> datetime:
        value = self.now_provider()

        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(
            timezone.utc
        )
