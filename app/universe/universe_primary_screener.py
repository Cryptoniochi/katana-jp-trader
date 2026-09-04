"""全市場からデイトレード機会の高い候補を一次選抜する。"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.universe.listed_symbol_repository import ListedSymbolRepository
from app.universe.universe_models import (
    UniverseScreeningCandidate,
    UniverseScreeningReport,
    UniverseScreeningSettings,
)


class UniversePrimaryScreener:
    """全市場から最大300銘柄のDay-Trade Opportunity Universeを作る。"""

    def __init__(
        self,
        *,
        database_path: Path,
        settings: UniverseScreeningSettings | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.settings = settings or UniverseScreeningSettings()
        self.now_provider = now_provider or (
            lambda: datetime.now(timezone.utc)
        )

    def screen(self) -> UniverseScreeningReport:
        now = self._current_time()
        symbols = ListedSymbolRepository(self.database_path).load_active(
            allowed_markets=self.settings.allowed_markets,
            allowed_security_types=self.settings.allowed_security_types,
        )
        metrics = self._load_latest_metrics()
        evaluated: list[UniverseScreeningCandidate] = []

        for symbol in symbols:
            metric = metrics.get(symbol.code)
            if metric is None:
                continue

            exclusions: list[str] = []
            latest_price = float(metric["latest_price"])
            purchase_amount = latest_price * symbol.trading_unit

            if latest_price < self.settings.minimum_latest_price:
                exclusions.append("below_minimum_price")
            if latest_price > self.settings.maximum_latest_price:
                exclusions.append("above_maximum_price")
            if purchase_amount > self.settings.maximum_purchase_amount:
                exclusions.append("over_purchase_budget")
            if float(metric["average_volume"]) < self.settings.minimum_average_volume:
                exclusions.append("insufficient_volume")
            if float(metric["average_turnover"]) < self.settings.minimum_average_turnover:
                exclusions.append("insufficient_turnover")

            age_days = (now.date() - metric["latest_trading_date"]).days
            if age_days > self.settings.maximum_data_age_days:
                exclusions.append("stale_data")

            opportunity_score, liquidity_score = self._score(metric, purchase_amount)

            evaluated.append(
                UniverseScreeningCandidate(
                    code=symbol.code,
                    name=symbol.name,
                    market=symbol.market,
                    security_type=symbol.security_type,
                    trading_unit=symbol.trading_unit,
                    latest_price=latest_price,
                    purchase_amount=purchase_amount,
                    average_volume=float(metric["average_volume"]),
                    average_turnover=float(metric["average_turnover"]),
                    latest_trading_date=metric["latest_trading_date"],
                    score=opportunity_score,
                    exclusion_reasons=tuple(exclusions),
                    selected=False,
                    atr_ratio=float(metric["atr_ratio"]),
                    volume_ratio=float(metric["volume_ratio"]),
                    return_5d=float(metric["return_5d"]),
                    breakout_ratio=float(metric["breakout_ratio"]),
                    range_expansion_ratio=float(metric["range_expansion_ratio"]),
                    gap_ratio=float(metric["gap_ratio"]),
                    close_position_ratio=float(metric["close_position_ratio"]),
                    opportunity_score=opportunity_score,
                    liquidity_score=liquidity_score,
                )
            )

        eligible = sorted(
            (item for item in evaluated if not item.exclusion_reasons),
            key=lambda item: (
                -item.opportunity_score,
                -item.volume_ratio,
                -item.atr_ratio,
                -item.average_turnover,
                item.code,
            ),
        )
        selected_codes = {
            item.code for item in eligible[: self.settings.maximum_symbols]
        }
        selected = tuple(
            self._mark_selected(item)
            for item in eligible
            if item.code in selected_codes
        )
        excluded = tuple(
            item for item in evaluated if item.code not in selected_codes
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

    def _load_latest_metrics(self) -> dict[str, dict[str, object]]:
        if not self.database_path.exists():
            return {}

        with sqlite3.connect(self.database_path) as connection:
            if not self._table_exists(connection, "market_bars"):
                return {}
            rows = connection.execute(
                """
                SELECT code, traded_at, open, high, low, close, volume
                FROM market_bars
                WHERE interval_minutes = 1440
                ORDER BY code ASC, traded_at DESC
                """
            ).fetchall()

        grouped: dict[str, list[tuple[datetime, float, float, float, float, float]]] = defaultdict(list)
        for code, traded_at, open_, high, low, close, volume in rows:
            key = str(code)
            if len(grouped[key]) >= self.settings.lookback_days:
                continue
            parsed = datetime.fromisoformat(str(traded_at))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            grouped[key].append(
                (
                    parsed,
                    float(open_),
                    float(high),
                    float(low),
                    float(close),
                    float(volume),
                )
            )

        result: dict[str, dict[str, object]] = {}
        for code, values in grouped.items():
            if not values:
                continue
            latest = values[0]
            previous = values[1:]
            reference = previous if previous else values

            average_volume = sum(item[5] for item in values) / len(values)
            average_turnover = sum(item[4] * item[5] for item in values) / len(values)
            reference_volume = sum(item[5] for item in reference) / len(reference)
            volume_ratio = latest[5] / reference_volume if reference_volume > 0 else 0.0

            true_ranges: list[float] = []
            for index, item in enumerate(values):
                high = item[2]
                low = item[3]
                previous_close = (
                    values[index + 1][4]
                    if index + 1 < len(values)
                    else item[4]
                )
                true_ranges.append(
                    max(high - low, abs(high - previous_close), abs(low - previous_close))
                )
            atr = sum(true_ranges) / len(true_ranges)
            atr_ratio = atr / latest[4] if latest[4] > 0 else 0.0

            latest_range = max(0.0, latest[2] - latest[3])
            prior_ranges = [max(0.0, item[2] - item[3]) for item in reference]
            average_prior_range = (
                sum(prior_ranges) / len(prior_ranges) if prior_ranges else latest_range
            )
            range_expansion_ratio = (
                latest_range / average_prior_range
                if average_prior_range > 0 else 1.0
            )

            if len(values) >= 5:
                oldest_5 = values[4][4]
                return_5d = (
                    latest[4] / oldest_5 - 1.0 if oldest_5 > 0 else 0.0
                )
            else:
                return_5d = 0.0

            prior_high = max((item[2] for item in reference), default=latest[2])
            breakout_ratio = (
                latest[4] / prior_high - 1.0 if prior_high > 0 else 0.0
            )

            previous_close = values[1][4] if len(values) > 1 else latest[1]
            gap_ratio = (
                latest[1] / previous_close - 1.0
                if previous_close > 0 else 0.0
            )

            close_position_ratio = (
                (latest[4] - latest[3]) / latest_range
                if latest_range > 0 else 0.5
            )

            result[code] = {
                "latest_price": latest[4],
                "average_volume": average_volume,
                "average_turnover": average_turnover,
                "latest_trading_date": latest[0].date(),
                "history_count": len(values),
                "atr_ratio": atr_ratio,
                "volume_ratio": volume_ratio,
                "return_5d": return_5d,
                "breakout_ratio": breakout_ratio,
                "range_expansion_ratio": range_expansion_ratio,
                "gap_ratio": gap_ratio,
                "close_position_ratio": close_position_ratio,
            }
        return result

    @staticmethod
    def _score(
        metric: dict[str, object],
        purchase_amount: float,
    ) -> tuple[float, float]:
        atr_ratio = float(metric["atr_ratio"])
        volume_ratio = float(metric["volume_ratio"])
        return_5d = float(metric["return_5d"])
        breakout_ratio = float(metric["breakout_ratio"])
        range_expansion_ratio = float(metric["range_expansion_ratio"])
        gap_ratio = float(metric["gap_ratio"])
        close_position_ratio = float(metric["close_position_ratio"])
        average_turnover = float(metric["average_turnover"])
        history_count = int(metric.get("history_count", 0))
        history_maturity = min(1.0, max(0.0, history_count / 20.0))

        # Liquidity is mainly an eligibility requirement.  Once tradeable,
        # extra mega-cap liquidity receives only a small ranking advantage.
        liquidity_score = min(
            10.0,
            max(
                0.0,
                (math.log10(max(average_turnover, 1.0)) - 6.5) / 3.0 * 10.0,
            ),
        )

        volatility_score = (
            min(22.0, max(0.0, atr_ratio / 0.04 * 22.0))
            * history_maturity
        )
        relative_volume_score = (
            min(22.0, max(0.0, (volume_ratio - 0.70) / 1.30 * 22.0))
            * history_maturity
        )
        range_score = (
            min(14.0, max(0.0, (range_expansion_ratio - 0.70) / 1.30 * 14.0))
            * history_maturity
        )

        momentum_score = (
            min(12.0, abs(return_5d) / 0.08 * 12.0)
            if history_count >= 5
            else 0.0
        )
        breakout_score = (
            min(8.0, max(0.0, breakout_ratio / 0.04 * 8.0))
            * history_maturity
        )
        gap_score = min(5.0, abs(gap_ratio) / 0.03 * 5.0)

        # Closes near an edge of the daily range are more informative than
        # dead-center closes for next-session continuation/reversal setups.
        edge_distance = abs(close_position_ratio - 0.5) * 2.0
        close_location_score = min(4.0, max(0.0, edge_distance * 4.0))

        affordability_score = max(
            0.0,
            3.0 * (1.0 - min(1.0, purchase_amount / 950_000.0)),
        )

        total = (
            volatility_score
            + relative_volume_score
            + range_score
            + momentum_score
            + breakout_score
            + gap_score
            + close_location_score
            + liquidity_score
            + affordability_score
        )
        return round(min(100.0, total), 4), round(liquidity_score, 4)

    @staticmethod
    def _mark_selected(
        item: UniverseScreeningCandidate,
    ) -> UniverseScreeningCandidate:
        payload = item.to_dict()
        payload["latest_trading_date"] = item.latest_trading_date
        payload["selected"] = True
        return UniverseScreeningCandidate(**payload)

    @staticmethod
    def _table_exists(
        connection: sqlite3.Connection,
        table_name: str,
    ) -> bool:
        row = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    def _current_time(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            raise ValueError("現在日時にはタイムゾーンが必要です。")
        return value.astimezone(timezone.utc)
