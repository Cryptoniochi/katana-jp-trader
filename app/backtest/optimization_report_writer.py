"""ORB最適化結果をCSV・JSONへ出力する。"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TypeAlias

from app.backtest.composite_ranking import (
    CompositeOptimizationRanking,
)
from app.backtest.composite_score_models import (
    CompositeOptimizationScore,
    CompositeOptimizationScoreReport,
    CompositeScoreWeights,
)
from app.backtest.optimization_ranking import (
    RankedOptimizationResult,
    RankingMetric,
)
from app.backtest.optimization_result_models import (
    OrbOptimizationResult,
    OrbOptimizationRunResult,
)


OptimizationRanking: TypeAlias = (
    tuple[RankedOptimizationResult, ...]
    | CompositeOptimizationRanking
)


@dataclass(frozen=True, slots=True)
class OptimizationReportPaths:
    """最適化レポートの出力先。"""

    output_directory: Path
    optimization_csv: Path
    optimization_json: Path


class OptimizationReportWriter:
    """最適化結果とランキングを分析用ファイルへ保存する。"""

    def write(
        self,
        *,
        output_directory: Path,
        result: OrbOptimizationResult,
        ranking: OptimizationRanking,
        ranking_method: str = RankingMetric.NET_PROFIT.value,
        composite_score_report: (
            CompositeOptimizationScoreReport | None
        ) = None,
        weights: CompositeScoreWeights | None = None,
    ) -> OptimizationReportPaths:
        """CSVとJSONを出力する。"""

        normalized_method = ranking_method.strip().lower()

        if not normalized_method:
            raise ValueError(
                "ranking_methodを指定してください。"
            )

        is_composite = normalized_method == "composite"

        if is_composite:
            if not isinstance(
                ranking,
                CompositeOptimizationRanking,
            ):
                raise TypeError(
                    "compositeランキングには"
                    "CompositeOptimizationRankingが必要です。"
                )

            if composite_score_report is None:
                raise ValueError(
                    "compositeランキングには"
                    "composite_score_reportが必要です。"
                )
        elif isinstance(
            ranking,
            CompositeOptimizationRanking,
        ):
            raise TypeError(
                "単一指標ランキングには"
                "RankedOptimizationResultのタプルが必要です。"
            )

        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        paths = OptimizationReportPaths(
            output_directory=output_directory,
            optimization_csv=(
                output_directory / "optimization.csv"
            ),
            optimization_json=(
                output_directory / "optimization.json"
            ),
        )

        rank_by_parameter_id = (
            self._create_rank_map(ranking)
        )
        score_by_parameter_id = (
            self._create_composite_score_map(
                composite_score_report
            )
        )

        self._write_csv(
            paths.optimization_csv,
            result=result,
            rank_by_parameter_id=rank_by_parameter_id,
            score_by_parameter_id=score_by_parameter_id,
        )
        self._write_json(
            paths.optimization_json,
            result=result,
            ranking=ranking,
            ranking_method=normalized_method,
            composite_score_report=(
                composite_score_report
            ),
            weights=weights,
        )

        return paths

    @staticmethod
    def _create_rank_map(
        ranking: OptimizationRanking,
    ) -> dict[str, int]:
        """ランキングからパラメータID別順位を作成する。"""

        if isinstance(
            ranking,
            CompositeOptimizationRanking,
        ):
            return {
                item.parameter_id: item.rank
                for item in ranking.items
            }

        return {
            item.run.parameter_id: item.rank
            for item in ranking
        }

    @staticmethod
    def _create_composite_score_map(
        report: CompositeOptimizationScoreReport | None,
    ) -> dict[str, CompositeOptimizationScore]:
        """パラメータID別複合スコアを作成する。"""

        if report is None:
            return {}

        return {
            item.parameter_id: item
            for item in report.scores
        }

    @staticmethod
    def _write_csv(
        path: Path,
        *,
        result: OrbOptimizationResult,
        rank_by_parameter_id: dict[str, int],
        score_by_parameter_id: dict[
            str,
            CompositeOptimizationScore,
        ],
    ) -> None:
        """全試行結果をCSVへ保存する。"""

        fieldnames = [
            "rank",
            "composite_score",
            "net_profit_score",
            "profit_factor_score",
            "win_rate_score",
            "drawdown_score",
            "parameter_id",
            "status",
            "stop_loss_rate",
            "take_profit_rate",
            "opening_range_end",
            "trade_count",
            "net_profit_loss",
            "profit_factor",
            "win_rate",
            "expectancy",
            "maximum_drawdown",
            "error_message",
        ]

        with path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames,
            )
            writer.writeheader()

            for run in result.runs:
                metrics = run.metrics
                composite = score_by_parameter_id.get(
                    run.parameter_id
                )

                writer.writerow(
                    {
                        "rank": rank_by_parameter_id.get(
                            run.parameter_id,
                            "",
                        ),
                        "composite_score": (
                            ""
                            if composite is None
                            else composite.score
                        ),
                        "net_profit_score": (
                            ""
                            if composite is None
                            else composite.components.net_profit
                        ),
                        "profit_factor_score": (
                            ""
                            if composite is None
                            else composite.components.profit_factor
                        ),
                        "win_rate_score": (
                            ""
                            if composite is None
                            else composite.components.win_rate
                        ),
                        "drawdown_score": (
                            ""
                            if composite is None
                            else composite.components.maximum_drawdown
                        ),
                        "parameter_id": run.parameter_id,
                        "status": run.status.value,
                        "stop_loss_rate": (
                            ""
                            if run.parameter.stop_loss_rate is None
                            else run.parameter.stop_loss_rate
                        ),
                        "take_profit_rate": (
                            ""
                            if run.parameter.take_profit_rate is None
                            else run.parameter.take_profit_rate
                        ),
                        "opening_range_end": (
                            run.parameter.opening_range_end.strftime(
                                "%H:%M"
                            )
                        ),
                        "trade_count": (
                            ""
                            if metrics is None
                            else metrics.trade_count
                        ),
                        "net_profit_loss": (
                            ""
                            if metrics is None
                            else metrics.net_profit_loss
                        ),
                        "profit_factor": (
                            ""
                            if run.profit_factor is None
                            else run.profit_factor
                        ),
                        "win_rate": (
                            ""
                            if run.win_rate is None
                            else run.win_rate
                        ),
                        "expectancy": (
                            ""
                            if metrics is None
                            or metrics.expectancy is None
                            else metrics.expectancy
                        ),
                        "maximum_drawdown": (
                            ""
                            if run.maximum_drawdown is None
                            else run.maximum_drawdown
                        ),
                        "error_message": (
                            run.error_message or ""
                        ),
                    }
                )

    @classmethod
    def _write_json(
        cls,
        path: Path,
        *,
        result: OrbOptimizationResult,
        ranking: OptimizationRanking,
        ranking_method: str,
        composite_score_report: (
            CompositeOptimizationScoreReport | None
        ),
        weights: CompositeScoreWeights | None,
    ) -> None:
        """全試行結果とランキングをJSONへ保存する。"""

        score_by_parameter_id = (
            cls._create_composite_score_map(
                composite_score_report
            )
        )
        ranking_items = cls._serialize_ranking(
            ranking,
            ranking_method=ranking_method,
        )
        best_parameter = (
            None
            if not ranking_items
            else ranking_items[0]["parameter_id"]
        )
        best_score = (
            None
            if not ranking_items
            else ranking_items[0]["score"]
        )

        payload = {
            "run_count": result.run_count,
            "completed_count": result.completed_count,
            "failed_count": result.failed_count,
            "ranking_method": ranking_method,
            "weights": (
                None
                if weights is None
                else asdict(weights.normalized)
            ),
            "best_parameter": best_parameter,
            "best_score": best_score,
            "ranking": ranking_items,
            "runs": [
                {
                    "parameter_id": run.parameter_id,
                    "status": run.status.value,
                    "parameter": {
                        "stop_loss_rate": (
                            run.parameter.stop_loss_rate
                        ),
                        "take_profit_rate": (
                            run.parameter.take_profit_rate
                        ),
                        "opening_range_end": (
                            run.parameter.opening_range_end
                            .isoformat(timespec="minutes")
                        ),
                    },
                    "metrics": (
                        None
                        if run.metrics is None
                        else asdict(run.metrics)
                    ),
                    "maximum_drawdown": (
                        run.maximum_drawdown
                    ),
                    "composite_score": (
                        cls._serialize_composite_score(
                            score_by_parameter_id.get(
                                run.parameter_id
                            )
                        )
                    ),
                    "error_message": run.error_message,
                }
                for run in result.runs
            ],
        }

        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )

    @classmethod
    def _serialize_ranking(
        cls,
        ranking: OptimizationRanking,
        *,
        ranking_method: str,
    ) -> list[dict[str, object]]:
        """ランキングをJSON形式へ変換する。"""

        if isinstance(
            ranking,
            CompositeOptimizationRanking,
        ):
            return [
                {
                    "rank": item.rank,
                    "parameter_id": item.parameter_id,
                    "score": item.score,
                }
                for item in ranking.items
            ]

        return [
            {
                "rank": item.rank,
                "parameter_id": item.run.parameter_id,
                "score": cls._metric_value(
                    item.run,
                    ranking_method,
                ),
            }
            for item in ranking
        ]

    @staticmethod
    def _metric_value(
        run: OrbOptimizationRunResult,
        ranking_method: str,
    ) -> float | None:
        """ランキング方式に対応する実測値を返す。"""

        if ranking_method == RankingMetric.NET_PROFIT.value:
            return run.net_profit_loss

        if ranking_method == RankingMetric.PROFIT_FACTOR.value:
            return run.profit_factor

        if ranking_method == RankingMetric.WIN_RATE.value:
            return run.win_rate

        if ranking_method == RankingMetric.MAX_DRAWDOWN.value:
            return run.maximum_drawdown

        return None

    @staticmethod
    def _serialize_composite_score(
        score: CompositeOptimizationScore | None,
    ) -> dict[str, object] | None:
        """複合スコアをJSON形式へ変換する。"""

        if score is None:
            return None

        return {
            "score": score.score,
            "components": asdict(score.components),
            "weights": asdict(score.weights),
        }
