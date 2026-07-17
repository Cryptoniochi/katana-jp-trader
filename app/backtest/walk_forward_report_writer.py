"""Walk-Forward Optimization結果をCSV・JSONへ出力する。"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.backtest.walk_forward_result_models import (
    WalkForwardResult,
)
from app.backtest.walk_forward_summary_models import (
    WalkForwardSummary,
)


@dataclass(frozen=True, slots=True)
class WalkForwardReportPaths:
    """Walk-Forwardレポートの出力先。"""

    output_directory: Path
    summary_csv: Path
    windows_csv: Path
    summary_json: Path


class WalkForwardReportWriter:
    """Walk-Forward結果を分析用ファイルへ保存する。"""

    def write(
        self,
        *,
        output_directory: Path,
        result: WalkForwardResult,
        summary: WalkForwardSummary,
    ) -> WalkForwardReportPaths:
        """サマリーCSV・ウィンドウCSV・JSONを出力する。"""

        if summary.window_count != result.window_count:
            raise ValueError(
                "Walk-Forward結果とサマリーの"
                "ウィンドウ件数が一致しません。"
            )

        if (
            summary.completed_window_count
            != result.completed_count
        ):
            raise ValueError(
                "Walk-Forward結果とサマリーの"
                "完了件数が一致しません。"
            )

        if (
            summary.failed_window_count
            != result.failed_count
        ):
            raise ValueError(
                "Walk-Forward結果とサマリーの"
                "失敗件数が一致しません。"
            )

        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        paths = WalkForwardReportPaths(
            output_directory=output_directory,
            summary_csv=output_directory / "summary.csv",
            windows_csv=output_directory / "windows.csv",
            summary_json=output_directory / "summary.json",
        )

        self._write_summary_csv(
            paths.summary_csv,
            summary=summary,
        )
        self._write_windows_csv(
            paths.windows_csv,
            result=result,
        )
        self._write_summary_json(
            paths.summary_json,
            result=result,
            summary=summary,
        )

        return paths

    @staticmethod
    def _write_summary_csv(
        path: Path,
        *,
        summary: WalkForwardSummary,
    ) -> None:
        """全体集計を縦持ちCSVへ保存する。"""

        rows: list[tuple[str, object]] = [
            ("window_count", summary.window_count),
            (
                "completed_window_count",
                summary.completed_window_count,
            ),
            (
                "failed_window_count",
                summary.failed_window_count,
            ),
            (
                "profitable_validation_window_count",
                summary.profitable_validation_window_count,
            ),
            (
                "validation_profitable_window_rate",
                WalkForwardReportWriter._nullable(
                    summary.validation_profitable_window_rate
                ),
            ),
        ]

        for prefix, aggregate in (
            ("training", summary.training),
            ("validation", summary.validation),
        ):
            rows.extend(
                [
                    (
                        f"{prefix}_result_count",
                        aggregate.result_count,
                    ),
                    (
                        f"{prefix}_trade_count",
                        aggregate.trade_count,
                    ),
                    (
                        f"{prefix}_winning_trade_count",
                        aggregate.winning_trade_count,
                    ),
                    (
                        f"{prefix}_losing_trade_count",
                        aggregate.losing_trade_count,
                    ),
                    (
                        f"{prefix}_flat_trade_count",
                        aggregate.flat_trade_count,
                    ),
                    (
                        f"{prefix}_gross_profit",
                        aggregate.gross_profit,
                    ),
                    (
                        f"{prefix}_gross_loss",
                        aggregate.gross_loss,
                    ),
                    (
                        f"{prefix}_net_profit_loss",
                        aggregate.net_profit_loss,
                    ),
                    (
                        f"{prefix}_win_rate",
                        WalkForwardReportWriter._nullable(
                            aggregate.win_rate
                        ),
                    ),
                    (
                        f"{prefix}_profit_factor",
                        WalkForwardReportWriter._nullable(
                            aggregate.profit_factor
                        ),
                    ),
                    (
                        f"{prefix}_expectancy",
                        WalkForwardReportWriter._nullable(
                            aggregate.expectancy
                        ),
                    ),
                    (
                        f"{prefix}_average_net_profit_loss",
                        WalkForwardReportWriter._nullable(
                            aggregate.average_net_profit_loss
                        ),
                    ),
                    (
                        f"{prefix}_maximum_drawdown",
                        WalkForwardReportWriter._nullable(
                            aggregate.maximum_drawdown
                        ),
                    ),
                ]
            )

        with path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            writer = csv.writer(file)
            writer.writerow(("metric", "value"))
            writer.writerows(rows)

    @staticmethod
    def _write_windows_csv(
        path: Path,
        *,
        result: WalkForwardResult,
    ) -> None:
        """ウィンドウ別の学習・検証結果を保存する。"""

        fieldnames = [
            "window_number",
            "window_id",
            "status",
            "ranking_method",
            "training_start_date",
            "training_end_date",
            "validation_start_date",
            "validation_end_date",
            "training_trading_day_count",
            "validation_trading_day_count",
            "selected_parameter_id",
            "stop_loss_rate",
            "take_profit_rate",
            "opening_range_end",
            "best_training_score",
            "training_trade_count",
            "training_net_profit_loss",
            "training_profit_factor",
            "training_win_rate",
            "training_maximum_drawdown",
            "validation_trade_count",
            "validation_net_profit_loss",
            "validation_profit_factor",
            "validation_win_rate",
            "validation_expectancy",
            "validation_maximum_drawdown",
            "optimization_run_count",
            "optimization_completed_count",
            "optimization_failed_count",
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

            for item in result.window_results:
                selected = item.selected_parameter
                training = (
                    None
                    if item.best_training_run is None
                    else item.best_training_run.metrics
                )
                training_equity = (
                    None
                    if item.best_training_run is None
                    else item.best_training_run.equity_curve_report
                )
                validation = (
                    None
                    if item.validation_result is None
                    else item.validation_result.metrics
                )
                validation_equity = (
                    None
                    if item.validation_result is None
                    else item.validation_result.equity_curve_report
                )
                optimization = item.optimization_result

                writer.writerow(
                    {
                        "window_number": (
                            item.window.window_number
                        ),
                        "window_id": item.window_id,
                        "status": item.status.value,
                        "ranking_method": item.ranking_method,
                        "training_start_date": (
                            item.window.training_start_date
                            .isoformat()
                        ),
                        "training_end_date": (
                            item.window.training_end_date
                            .isoformat()
                        ),
                        "validation_start_date": (
                            item.window.validation_start_date
                            .isoformat()
                        ),
                        "validation_end_date": (
                            item.window.validation_end_date
                            .isoformat()
                        ),
                        "training_trading_day_count": (
                            item.window
                            .training_trading_day_count
                        ),
                        "validation_trading_day_count": (
                            item.window
                            .validation_trading_day_count
                        ),
                        "selected_parameter_id": (
                            ""
                            if selected is None
                            else selected.parameter_id
                        ),
                        "stop_loss_rate": (
                            ""
                            if selected is None
                            or selected.stop_loss_rate is None
                            else selected.stop_loss_rate
                        ),
                        "take_profit_rate": (
                            ""
                            if selected is None
                            or selected.take_profit_rate is None
                            else selected.take_profit_rate
                        ),
                        "opening_range_end": (
                            ""
                            if selected is None
                            else selected.opening_range_end
                            .isoformat(timespec="minutes")
                        ),
                        "best_training_score": (
                            WalkForwardReportWriter._nullable(
                                item.best_training_score
                            )
                        ),
                        "training_trade_count": (
                            ""
                            if training is None
                            else training.trade_count
                        ),
                        "training_net_profit_loss": (
                            ""
                            if training is None
                            else training.net_profit_loss
                        ),
                        "training_profit_factor": (
                            ""
                            if training is None
                            else WalkForwardReportWriter._nullable(
                                training.profit_factor
                            )
                        ),
                        "training_win_rate": (
                            ""
                            if training is None
                            else WalkForwardReportWriter._nullable(
                                training.win_rate
                            )
                        ),
                        "training_maximum_drawdown": (
                            ""
                            if training_equity is None
                            else training_equity.maximum_drawdown
                        ),
                        "validation_trade_count": (
                            ""
                            if validation is None
                            else validation.trade_count
                        ),
                        "validation_net_profit_loss": (
                            ""
                            if validation is None
                            else validation.net_profit_loss
                        ),
                        "validation_profit_factor": (
                            ""
                            if validation is None
                            else WalkForwardReportWriter._nullable(
                                validation.profit_factor
                            )
                        ),
                        "validation_win_rate": (
                            ""
                            if validation is None
                            else WalkForwardReportWriter._nullable(
                                validation.win_rate
                            )
                        ),
                        "validation_expectancy": (
                            ""
                            if validation is None
                            else WalkForwardReportWriter._nullable(
                                validation.expectancy
                            )
                        ),
                        "validation_maximum_drawdown": (
                            ""
                            if validation_equity is None
                            else validation_equity.maximum_drawdown
                        ),
                        "optimization_run_count": (
                            ""
                            if optimization is None
                            else optimization.run_count
                        ),
                        "optimization_completed_count": (
                            ""
                            if optimization is None
                            else optimization.completed_count
                        ),
                        "optimization_failed_count": (
                            ""
                            if optimization is None
                            else optimization.failed_count
                        ),
                        "error_message": (
                            item.error_message or ""
                        ),
                    }
                )

    @classmethod
    def _write_summary_json(
        cls,
        path: Path,
        *,
        result: WalkForwardResult,
        summary: WalkForwardSummary,
    ) -> None:
        """全体集計とウィンドウ詳細をJSONへ保存する。"""

        payload = {
            "plan": {
                "training_days": result.plan.training_days,
                "validation_days": result.plan.validation_days,
                "step_days": result.plan.step_days,
                "window_count": result.plan.window_count,
            },
            "summary": {
                "window_count": summary.window_count,
                "completed_window_count": (
                    summary.completed_window_count
                ),
                "failed_window_count": (
                    summary.failed_window_count
                ),
                "profitable_validation_window_count": (
                    summary.profitable_validation_window_count
                ),
                "validation_profitable_window_rate": (
                    summary.validation_profitable_window_rate
                ),
                "training": asdict(summary.training),
                "validation": asdict(summary.validation),
                "parameter_frequencies": [
                    asdict(item)
                    for item in summary.parameter_frequencies
                ],
            },
            "windows": [
                cls._serialize_window(item)
                for item in result.window_results
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

    @staticmethod
    def _serialize_window(
        item,
    ) -> dict[str, object]:
        """1ウィンドウの結果をJSON形式へ変換する。"""

        selected = item.selected_parameter
        training_run = item.best_training_run
        validation = item.validation_result
        optimization = item.optimization_result

        return {
            "window_number": item.window.window_number,
            "window_id": item.window_id,
            "status": item.status.value,
            "ranking_method": item.ranking_method,
            "period": {
                "training_start_date": (
                    item.window.training_start_date.isoformat()
                ),
                "training_end_date": (
                    item.window.training_end_date.isoformat()
                ),
                "validation_start_date": (
                    item.window.validation_start_date.isoformat()
                ),
                "validation_end_date": (
                    item.window.validation_end_date.isoformat()
                ),
                "training_trading_day_count": (
                    item.window.training_trading_day_count
                ),
                "validation_trading_day_count": (
                    item.window.validation_trading_day_count
                ),
            },
            "selected_parameter": (
                None
                if selected is None
                else {
                    "parameter_id": selected.parameter_id,
                    "stop_loss_rate": (
                        selected.stop_loss_rate
                    ),
                    "take_profit_rate": (
                        selected.take_profit_rate
                    ),
                    "opening_range_end": (
                        selected.opening_range_end
                        .isoformat(timespec="minutes")
                    ),
                }
            ),
            "best_training_score": item.best_training_score,
            "best_training_run": (
                None
                if training_run is None
                else {
                    "metrics": (
                        None
                        if training_run.metrics is None
                        else asdict(training_run.metrics)
                    ),
                    "maximum_drawdown": (
                        training_run.maximum_drawdown
                    ),
                }
            ),
            "validation": (
                None
                if validation is None
                else {
                    "metrics": asdict(validation.metrics),
                    "maximum_drawdown": (
                        None
                        if validation.equity_curve_report is None
                        else validation.equity_curve_report
                        .maximum_drawdown
                    ),
                }
            ),
            "optimization": (
                None
                if optimization is None
                else {
                    "run_count": optimization.run_count,
                    "completed_count": (
                        optimization.completed_count
                    ),
                    "failed_count": optimization.failed_count,
                }
            ),
            "error_message": item.error_message,
        }

    @staticmethod
    def _nullable(
        value: object | None,
    ) -> object:
        """CSVのNoneを空文字へ変換する。"""

        return "" if value is None else value
