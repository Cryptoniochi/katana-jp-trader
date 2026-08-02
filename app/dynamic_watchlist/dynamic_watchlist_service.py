"""SQLite市場データからDynamic Watchlistを生成する。"""

from __future__ import annotations

import csv
import json
import math
import shutil
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Iterable

from app.dynamic_watchlist.dynamic_watchlist_feature_engine import (
    DynamicWatchlistFeatureEngine,
    DynamicWatchlistFeatureInput,
)
from app.learning.strategy_learning_feedback import (
    StrategyLearningFeedbackProvider,
    SymbolLearningFeedback,
)
from app.dynamic_watchlist.dynamic_watchlist_models import (
    DynamicWatchlistCandidate,
    DynamicWatchlistResult,
    DynamicWatchlistSettings,
)


@dataclass(frozen=True, slots=True)
class _DailyBar:
    trading_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class DynamicWatchlistService:
    """保存済み市場データを採点し、上位銘柄を選定する。"""

    def __init__(
        self,
        *,
        database_path: Path,
        watchlist_path: Path,
        report_directory: Path,
        settings: DynamicWatchlistSettings | None = None,
        candidate_universe_path: Path | None = None,
        require_candidate_universe: bool = False,
        now_provider=None,
    ) -> None:
        self.database_path = Path(database_path)
        self.watchlist_path = Path(watchlist_path)
        self.report_directory = Path(report_directory)
        self.candidate_universe_path = (
            Path(candidate_universe_path)
            if candidate_universe_path is not None
            else None
        )
        self.require_candidate_universe = (
            require_candidate_universe
        )
        self.settings = (
            settings
            if settings is not None
            else DynamicWatchlistSettings()
        )
        self.feature_engine = (
            DynamicWatchlistFeatureEngine()
        )
        self.learning_feedback_provider = (
            StrategyLearningFeedbackProvider(
                self.database_path
            )
        )
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def generate(
        self,
        *,
        apply: bool = False,
    ) -> DynamicWatchlistResult:
        now = self._current_time()
        allowed_codes = self._load_candidate_universe()
        series_by_code = self._load_daily_series(
            allowed_codes=allowed_codes
        )
        learning_feedback = (
            self.learning_feedback_provider.load_all()
            if self.settings.learning_feedback_enabled
            else {}
        )
        candidates = tuple(
            self._evaluate_code(
                code=code,
                bars=bars,
                today=now.date(),
                learning_feedback=learning_feedback.get(code),
            )
            for code, bars in sorted(series_by_code.items())
        )
        strict = sorted(
            (
                candidate
                for candidate in candidates
                if candidate.selection_tier == "strict"
                and not candidate.exclusion_reasons
            ),
            key=self._ranking_key,
        )
        fallback = sorted(
            (
                candidate
                for candidate in candidates
                if candidate.selection_tier == "fallback"
                and not candidate.exclusion_reasons
            ),
            key=self._ranking_key,
        )
        eligible = strict + [
            candidate
            for candidate in fallback
            if candidate.code not in {
                item.code for item in strict
            }
        ]
        selected = tuple(
            self._mark_selected(candidate)
            for candidate in eligible[
                : self.settings.maximum_symbols
            ]
        )

        applied = False
        backup_path: Path | None = None
        message = (
            f"Selected {len(selected)} symbols "
            f"from {len(candidates)} evaluated symbols."
        )

        if apply:
            if len(selected) < self.settings.minimum_symbols:
                message = (
                    "Dynamic Watchlist was not applied because "
                    f"only {len(selected)} eligible symbols were found; "
                    f"minimum={self.settings.minimum_symbols}."
                )
            else:
                backup_path = self._apply_watchlist(
                    selected=selected,
                    target_date=now.date(),
                )
                applied = True
                message += " watchlist.txt was updated safely."

        result = DynamicWatchlistResult(
            generated_at=now,
            target_date=now.date(),
            settings=self.settings,
            selected=selected,
            evaluated_count=len(candidates),
            eligible_count=len(eligible),
            applied=applied,
            watchlist_path=(
                str(self.watchlist_path)
                if applied
                else None
            ),
            backup_path=(
                str(backup_path)
                if backup_path is not None
                else None
            ),
            message=message,
        )
        self._write_reports(
            result=result,
            all_candidates=candidates,
        )
        return result

    def _load_candidate_universe(
        self,
    ) -> set[str] | None:
        if self.candidate_universe_path is None:
            return None

        if not self.candidate_universe_path.exists():
            if self.require_candidate_universe:
                raise FileNotFoundError(
                    "Universe candidate file was not found: "
                    f"{self.candidate_universe_path}"
                )
            return None

        codes = {
            line.strip()
            for line in self.candidate_universe_path.read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        }

        if not codes and self.require_candidate_universe:
            raise RuntimeError(
                "Universe candidate file contains no symbols."
            )

        return codes or None

    def _load_daily_series(
        self,
        *,
        allowed_codes: set[str] | None = None,
    ) -> dict[str, list[_DailyBar]]:
        if not self.database_path.exists():
            raise FileNotFoundError(
                f"Database not found: {self.database_path}"
            )

        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            table = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'market_bars'
                """
            ).fetchone()

            if table is None:
                raise RuntimeError(
                    "market_bars table does not exist."
                )

            rows = connection.execute(
                """
                SELECT
                    code,
                    traded_at,
                    interval_minutes,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM market_bars
                WHERE close > 0
                  AND volume >= 0
                ORDER BY code, traded_at
                """
            ).fetchall()

        daily_rows: dict[str, list[_DailyBar]] = defaultdict(list)
        intraday: dict[tuple[str, date], list[sqlite3.Row]] = (
            defaultdict(list)
        )

        for row in rows:
            traded_at = datetime.fromisoformat(
                str(row["traded_at"])
            )
            code = str(row["code"]).strip()

            if (
                allowed_codes is not None
                and code not in allowed_codes
            ):
                continue

            interval = int(row["interval_minutes"])

            if interval >= 1_000:
                daily_rows[code].append(
                    _DailyBar(
                        trading_date=traded_at.date(),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["volume"]),
                    )
                )
            else:
                intraday[(code, traded_at.date())].append(row)

        for (code, trading_date), day_rows in intraday.items():
            if daily_rows.get(code):
                continue

            daily_rows[code].append(
                _DailyBar(
                    trading_date=trading_date,
                    open=float(day_rows[0]["open"]),
                    high=max(
                        float(row["high"])
                        for row in day_rows
                    ),
                    low=min(
                        float(row["low"])
                        for row in day_rows
                    ),
                    close=float(day_rows[-1]["close"]),
                    volume=sum(
                        int(row["volume"])
                        for row in day_rows
                    ),
                )
            )

        return {
            code: sorted(
                bars,
                key=lambda bar: bar.trading_date,
            )
            for code, bars in daily_rows.items()
        }

    def _evaluate_code(
        self,
        *,
        code: str,
        bars: list[_DailyBar],
        today: date,
        learning_feedback: SymbolLearningFeedback | None,
    ) -> DynamicWatchlistCandidate:
        settings = self.settings
        latest = bars[-1]
        recent = bars[-20:]
        previous = bars[-21:-1]
        purchase_amount = (
            latest.close * settings.trading_unit
        )
        exclusion_reasons: list[str] = []
        selection_tier = "strict"

        age_days = (today - latest.trading_date).days

        strict_history = (
            len(bars) >= settings.minimum_history_days
        )
        strict_freshness = (
            age_days <= settings.maximum_data_age_days
        )

        if not strict_history or not strict_freshness:
            selection_tier = "fallback"

        if len(bars) < settings.fallback_minimum_history_days:
            exclusion_reasons.append("insufficient_history")

        if age_days > settings.fallback_maximum_data_age_days:
            exclusion_reasons.append("stale_data")

        if purchase_amount > settings.purchase_budget:
            exclusion_reasons.append("over_purchase_budget")

        average_volume = (
            fmean(bar.volume for bar in recent)
            if recent
            else 0.0
        )
        average_turnover = (
            fmean(bar.close * bar.volume for bar in recent)
            if recent
            else 0.0
        )

        if selection_tier == "strict":
            minimum_volume = settings.minimum_average_volume
            minimum_turnover = settings.minimum_average_turnover
        else:
            minimum_volume = (
                settings.fallback_minimum_average_volume
            )
            minimum_turnover = (
                settings.fallback_minimum_average_turnover
            )

        if average_volume < minimum_volume:
            exclusion_reasons.append("insufficient_volume")

        if average_turnover < minimum_turnover:
            exclusion_reasons.append("insufficient_turnover")

        prior_high = (
            max(bar.high for bar in previous)
            if previous
            else latest.high
        )
        breakout_ratio = (
            latest.close / prior_high - 1.0
            if prior_high > 0
            else 0.0
        )
        return_20d = (
            latest.close / recent[0].close - 1.0
            if len(recent) >= 2 and recent[0].close > 0
            else 0.0
        )
        previous_volume = (
            fmean(bar.volume for bar in previous)
            if previous
            else average_volume
        )
        volume_ratio = (
            latest.volume / previous_volume
            if previous_volume > 0
            else 0.0
        )
        true_ranges = []
        for index, bar in enumerate(recent):
            previous_close = (
                recent[index - 1].close
                if index > 0
                else bar.close
            )
            true_ranges.append(
                max(
                    bar.high - bar.low,
                    abs(bar.high - previous_close),
                    abs(bar.low - previous_close),
                )
            )
        atr = fmean(true_ranges) if true_ranges else 0.0
        atr_ratio = (
            atr / latest.close
            if latest.close > 0
            else 0.0
        )

        gap_ratio = (
            latest.open / recent[-2].close - 1.0
            if len(recent) >= 2
            and recent[-2].close > 0
            else 0.0
        )
        typical_values = [
            (
                (bar.high + bar.low + bar.close) / 3.0,
                max(bar.volume, 0),
            )
            for bar in recent
        ]
        total_volume = sum(
            volume
            for _, volume in typical_values
        )
        vwap = (
            sum(
                price * volume
                for price, volume in typical_values
            ) / total_volume
            if total_volume > 0
            else latest.close
        )
        vwap_distance_ratio = (
            latest.close / vwap - 1.0
            if vwap > 0
            else 0.0
        )
        day_range = latest.high - latest.low
        close_position_ratio = (
            (latest.close - latest.low) / day_range
            if day_range > 0
            else 0.5
        )
        recent_high = max(
            bar.high
            for bar in recent
        )
        pullback_depth_ratio = (
            recent_high / latest.close - 1.0
            if latest.close > 0
            else 0.0
        )
        feature_scores = self.feature_engine.evaluate(
            DynamicWatchlistFeatureInput(
                average_turnover_20d=average_turnover,
                volume_ratio=volume_ratio,
                atr_ratio=atr_ratio,
                gap_ratio=gap_ratio,
                vwap_distance_ratio=vwap_distance_ratio,
                return_20d=return_20d,
                breakout_ratio=breakout_ratio,
                close_position_ratio=close_position_ratio,
                pullback_depth_ratio=pullback_depth_ratio,
            )
        )

        breakout_score = self._scale(
            breakout_ratio,
            lower=-0.05,
            upper=0.05,
            maximum=30.0,
        )
        momentum_score = self._scale(
            return_20d,
            lower=-0.10,
            upper=0.20,
            maximum=20.0,
        )
        liquidity_score = self._log_scale(
            average_turnover,
            lower=settings.minimum_average_turnover,
            upper=5_000_000_000.0,
            maximum=20.0,
        )
        volume_score = self._scale(
            volume_ratio,
            lower=0.5,
            upper=3.0,
            maximum=15.0,
        )
        volatility_score = self._bell_score(
            atr_ratio,
            ideal=0.035,
            tolerance=0.03,
            maximum=15.0,
        )
        technical_score = feature_scores.total_score
        (
            historical_score,
            historical_trade_count,
            learned_preferred_strategy,
            preferred_strategy,
        ) = self._apply_learning_feedback(
            feature_scores=feature_scores,
            feedback=learning_feedback,
        )
        total_score = round(
            min(
                100.0,
                technical_score
                + historical_score
                * settings.learning_total_score_weight,
            ),
            4,
        )
        rating_tier = self._resolve_rating_tier(
            total_score
        )

        return DynamicWatchlistCandidate(
            code=code,
            latest_date=latest.trading_date,
            latest_price=round(latest.close, 4),
            trading_unit=settings.trading_unit,
            purchase_amount=round(purchase_amount, 2),
            history_days=len(bars),
            average_volume_20d=round(average_volume, 2),
            average_turnover_20d=round(average_turnover, 2),
            volume_ratio=round(volume_ratio, 6),
            return_20d=round(return_20d, 6),
            breakout_ratio=round(breakout_ratio, 6),
            atr_ratio=round(atr_ratio, 6),
            gap_ratio=round(gap_ratio, 6),
            vwap_distance_ratio=round(
                vwap_distance_ratio,
                6,
            ),
            close_position_ratio=round(
                close_position_ratio,
                6,
            ),
            pullback_depth_ratio=round(
                pullback_depth_ratio,
                6,
            ),
            breakout_score=round(breakout_score, 4),
            momentum_score=round(momentum_score, 4),
            liquidity_score=round(liquidity_score, 4),
            volume_score=round(volume_score, 4),
            volatility_score=round(volatility_score, 4),
            gap_score=feature_scores.gap_score,
            vwap_score=feature_scores.vwap_score,
            orb_score=feature_scores.orb_score,
            pullback_score=feature_scores.pullback_score,
            high_breakout_score=(
                feature_scores.high_breakout_score
            ),
            technical_score=technical_score,
            historical_score=historical_score,
            historical_trade_count=(
                historical_trade_count
            ),
            learning_applied=(
                learning_feedback is not None
                and historical_trade_count > 0
            ),
            learned_preferred_strategy=(
                learned_preferred_strategy
            ),
            total_score=total_score,
            rating_tier=rating_tier,
            preferred_strategy=preferred_strategy,
            selection_tier=selection_tier,
            selected=False,
            exclusion_reasons=tuple(exclusion_reasons),
        )


    def _apply_learning_feedback(
        self,
        *,
        feature_scores,
        feedback: SymbolLearningFeedback | None,
    ) -> tuple[
        float,
        int,
        str | None,
        str,
    ]:
        """技術スコアへ十分なサンプルの学習結果を加える。"""

        if feedback is None or not feedback.strategies:
            return (
                0.0,
                0,
                None,
                feature_scores.preferred_strategy,
            )

        technical_by_strategy = {
            "orb": feature_scores.orb_score,
            "pullback": feature_scores.pullback_score,
            "high-breakout": (
                feature_scores.high_breakout_score
            ),
        }
        adjusted = {}

        for strategy_name, technical_score in (
            technical_by_strategy.items()
        ):
            learned = feedback.for_strategy(
                strategy_name
            )
            learned_bonus = (
                learned.historical_score
                * self.settings
                .learning_strategy_score_weight
                if learned is not None
                else 0.0
            )
            adjusted[strategy_name] = (
                technical_score + learned_bonus
            )

        preferred_strategy = max(
            adjusted,
            key=lambda name: (
                adjusted[name],
                technical_by_strategy[name],
                name,
            ),
        )
        best = feedback.best

        return (
            round(
                best.historical_score
                if best is not None
                else 0.0,
                4,
            ),
            (
                best.trade_count
                if best is not None
                else 0
            ),
            (
                best.strategy_name
                if best is not None
                else None
            ),
            preferred_strategy,
        )

    @staticmethod
    def _resolve_rating_tier(
        total_score: float,
    ) -> str:
        if total_score >= 80:
            return "A+"
        if total_score >= 65:
            return "A"
        if total_score >= 50:
            return "B"
        return "C"

    @staticmethod
    def _ranking_key(
        candidate: DynamicWatchlistCandidate,
    ) -> tuple[float, float, str]:
        return (
            -candidate.total_score,
            -candidate.average_turnover_20d,
            candidate.code,
        )

    @staticmethod
    def _mark_selected(
        candidate: DynamicWatchlistCandidate,
    ) -> DynamicWatchlistCandidate:
        payload = candidate.to_dict()
        payload["latest_date"] = candidate.latest_date
        payload["exclusion_reasons"] = tuple()
        payload["selected"] = True
        return DynamicWatchlistCandidate(**payload)

    def _apply_watchlist(
        self,
        *,
        selected: tuple[DynamicWatchlistCandidate, ...],
        target_date: date,
    ) -> Path | None:
        self.watchlist_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        backup_path: Path | None = None

        if self.watchlist_path.exists():
            backup_directory = (
                self.report_directory / "backups"
            )
            backup_directory.mkdir(
                parents=True,
                exist_ok=True,
            )
            backup_path = (
                backup_directory
                / f"watchlist_{target_date.isoformat()}.txt"
            )
            shutil.copy2(
                self.watchlist_path,
                backup_path,
            )

        temporary = self.watchlist_path.with_suffix(
            self.watchlist_path.suffix + ".tmp"
        )
        temporary.write_text(
            "\n".join(
                candidate.code
                for candidate in selected
            )
            + "\n",
            encoding="utf-8",
        )

        codes = [
            line.strip()
            for line in temporary.read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        ]

        if (
            len(codes) < self.settings.minimum_symbols
            or len(codes) > self.settings.maximum_symbols
            or len(codes) != len(set(codes))
            or any(
                not code.isdigit()
                or len(code) not in {4, 5}
                for code in codes
            )
        ):
            temporary.unlink(missing_ok=True)
            raise RuntimeError(
                "Generated watchlist validation failed."
            )

        temporary.replace(self.watchlist_path)
        return backup_path

    def _write_reports(
        self,
        *,
        result: DynamicWatchlistResult,
        all_candidates: Iterable[DynamicWatchlistCandidate],
    ) -> None:
        self.report_directory.mkdir(
            parents=True,
            exist_ok=True,
        )
        stem = (
            "dynamic_watchlist_"
            f"{result.target_date.isoformat()}"
        )
        json_path = self.report_directory / f"{stem}.json"
        csv_path = self.report_directory / f"{stem}.csv"
        latest_path = self.report_directory / "latest.json"

        payload = result.to_dict()
        payload["evaluated"] = [
            candidate.to_dict()
            for candidate in all_candidates
        ]
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        json_path.write_text(
            serialized,
            encoding="utf-8",
        )
        latest_path.write_text(
            serialized,
            encoding="utf-8",
        )

        fieldnames = [
            "selected",
            "code",
            "total_score",
            "selection_tier",
            "latest_date",
            "latest_price",
            "trading_unit",
            "purchase_amount",
            "history_days",
            "average_volume_20d",
            "average_turnover_20d",
            "volume_ratio",
            "return_20d",
            "breakout_ratio",
            "atr_ratio",
            "gap_ratio",
            "vwap_distance_ratio",
            "close_position_ratio",
            "pullback_depth_ratio",
            "breakout_score",
            "momentum_score",
            "liquidity_score",
            "volume_score",
            "volatility_score",
            "gap_score",
            "vwap_score",
            "orb_score",
            "pullback_score",
            "high_breakout_score",
            "technical_score",
            "historical_score",
            "historical_trade_count",
            "learning_applied",
            "learned_preferred_strategy",
            "rating_tier",
            "preferred_strategy",
            "exclusion_reasons",
        ]
        with csv_path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames,
            )
            writer.writeheader()

            for candidate in all_candidates:
                row = candidate.to_dict()
                row["exclusion_reasons"] = ",".join(
                    row["exclusion_reasons"]
                )
                writer.writerow(
                    {
                        key: row.get(key)
                        for key in fieldnames
                    }
                )

    @staticmethod
    def _scale(
        value: float,
        *,
        lower: float,
        upper: float,
        maximum: float,
    ) -> float:
        if upper <= lower:
            return 0.0
        ratio = (value - lower) / (upper - lower)
        return max(
            0.0,
            min(maximum, ratio * maximum),
        )

    @staticmethod
    def _log_scale(
        value: float,
        *,
        lower: float,
        upper: float,
        maximum: float,
    ) -> float:
        if value <= 0 or upper <= lower:
            return 0.0
        return DynamicWatchlistService._scale(
            math.log10(value),
            lower=math.log10(lower),
            upper=math.log10(upper),
            maximum=maximum,
        )

    @staticmethod
    def _bell_score(
        value: float,
        *,
        ideal: float,
        tolerance: float,
        maximum: float,
    ) -> float:
        if tolerance <= 0:
            return 0.0
        distance = abs(value - ideal)
        return max(
            0.0,
            maximum * (1.0 - distance / tolerance),
        )

    def _current_time(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )
        return value.astimezone(timezone.utc)
