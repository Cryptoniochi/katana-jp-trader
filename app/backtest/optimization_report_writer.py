"""ORB最適化結果をCSV・JSONへ出力する。"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.backtest.optimization_ranking import (
    RankedOptimizationResult,
)
from app.backtest.optimization_result_models import (
    OrbOptimizationResult,
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
        ranking: tuple[RankedOptimizationResult, ...],
    ) -> OptimizationReportPaths:
        """CSVとJSONを出力する。"""

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

        rank_by_parameter_id = {
            item.run.parameter_id: item.rank
            for item in ranking
        }

        self._write_csv(
            paths.optimization_csv,
            result=result,
            rank_by_parameter_id=rank_by_parameter_id,
        )
        self._write_json(
            paths.optimization_json,
            result=result,
            ranking=ranking,
        )

        return paths

    @staticmethod
    def _write_csv(
        path: Path,
        *,
        result: OrbOptimizationResult,
        rank_by_parameter_id: dict[str, int],
    ) -> None:
        """全試行結果をCSVへ保存する。"""

        fieldnames = [
            "rank",
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

                writer.writerow(
                    {
                        "rank": rank_by_parameter_id.get(
                            run.parameter_id,
                            "",
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

    @staticmethod
    def _write_json(
        path: Path,
        *,
        result: OrbOptimizationResult,
        ranking: tuple[RankedOptimizationResult, ...],
    ) -> None:
        """全試行結果とランキングをJSONへ保存する。"""

        payload = {
            "run_count": result.run_count,
            "completed_count": result.completed_count,
            "failed_count": result.failed_count,
            "ranking": [
                {
                    "rank": item.rank,
                    "parameter_id": item.run.parameter_id,
                }
                for item in ranking
            ],
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
