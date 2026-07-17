"""バックテスト結果をCSV・JSONへ出力する。"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)
from app.backtest.trade_report_models import (
    BacktestTradeReport,
)
from app.trading.equity_curve_models import (
    EquityCurveReport,
)


@dataclass(frozen=True, slots=True)
class BacktestReportPaths:
    """出力したバックテストレポートのパス。"""

    output_directory: Path
    trades_csv: Path
    equity_curve_csv: Path
    metrics_csv: Path
    summary_json: Path


class BacktestReportWriter:
    """バックテスト結果を分析用ファイルへ保存する。"""

    def write(
        self,
        *,
        output_directory: Path,
        trade_report: BacktestTradeReport,
        metrics: BacktestPerformanceMetrics,
        equity_curve_report: EquityCurveReport | None,
    ) -> BacktestReportPaths:
        """4種類のレポートファイルを出力する。"""

        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        paths = BacktestReportPaths(
            output_directory=output_directory,
            trades_csv=output_directory / "trades.csv",
            equity_curve_csv=(
                output_directory / "equity_curve.csv"
            ),
            metrics_csv=output_directory / "metrics.csv",
            summary_json=output_directory / "summary.json",
        )

        self._write_trades(
            paths.trades_csv,
            trade_report,
        )
        self._write_equity_curve(
            paths.equity_curve_csv,
            equity_curve_report,
        )
        self._write_metrics(
            paths.metrics_csv,
            metrics,
            equity_curve_report,
        )
        self._write_summary(
            paths.summary_json,
            trade_report,
            metrics,
            equity_curve_report,
        )

        return paths

    @staticmethod
    def _write_trades(
        path: Path,
        report: BacktestTradeReport,
    ) -> None:
        """完結トレード一覧をCSVへ保存する。"""

        fieldnames = [
            "trade_id",
            "code",
            "quantity",
            "entered_at",
            "exited_at",
            "holding_seconds",
            "entry_price",
            "exit_price",
            "gross_profit_loss",
            "total_cost",
            "net_profit_loss",
            "return_rate",
            "exit_reason",
            "entry_execution_id",
            "exit_execution_id",
            "entry_signal_id",
            "exit_signal_id",
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

            for trade in report.trades:
                writer.writerow(
                    {
                        "trade_id": trade.trade_id,
                        "code": trade.code,
                        "quantity": trade.quantity,
                        "entered_at": (
                            trade.entered_at.isoformat()
                        ),
                        "exited_at": (
                            trade.exited_at.isoformat()
                        ),
                        "holding_seconds": (
                            trade.holding_seconds
                        ),
                        "entry_price": trade.entry_price,
                        "exit_price": trade.exit_price,
                        "gross_profit_loss": (
                            trade.gross_profit_loss
                        ),
                        "total_cost": trade.total_cost,
                        "net_profit_loss": (
                            trade.net_profit_loss
                        ),
                        "return_rate": trade.return_rate,
                        "exit_reason": (
                            trade.exit_reason or ""
                        ),
                        "entry_execution_id": (
                            trade.entry_execution_id
                        ),
                        "exit_execution_id": (
                            trade.exit_execution_id
                        ),
                        "entry_signal_id": (
                            trade.entry_signal_id
                        ),
                        "exit_signal_id": (
                            trade.exit_signal_id
                        ),
                    }
                )

    @staticmethod
    def _write_equity_curve(
        path: Path,
        report: EquityCurveReport | None,
    ) -> None:
        """資産曲線をCSVへ保存する。"""

        fieldnames = [
            "generated_at",
            "equity",
            "cash_balance",
            "market_value",
            "realized_profit_loss",
            "unrealized_profit_loss",
            "period_return",
            "cumulative_return",
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

            if report is None:
                return

            for point in report.points:
                writer.writerow(
                    {
                        "generated_at": (
                            point.generated_at.isoformat()
                        ),
                        "equity": point.equity,
                        "cash_balance": (
                            point.cash_balance
                        ),
                        "market_value": (
                            point.market_value
                        ),
                        "realized_profit_loss": (
                            point.realized_profit_loss
                        ),
                        "unrealized_profit_loss": (
                            point.unrealized_profit_loss
                        ),
                        "period_return": (
                            ""
                            if point.period_return is None
                            else point.period_return
                        ),
                        "cumulative_return": (
                            point.cumulative_return
                        ),
                    }
                )

    @staticmethod
    def _write_metrics(
        path: Path,
        metrics: BacktestPerformanceMetrics,
        equity_report: EquityCurveReport | None,
    ) -> None:
        """主要指標を縦型CSVへ保存する。"""

        rows = [
            ("trade_count", metrics.trade_count),
            (
                "winning_trade_count",
                metrics.winning_trade_count,
            ),
            (
                "losing_trade_count",
                metrics.losing_trade_count,
            ),
            (
                "flat_trade_count",
                metrics.flat_trade_count,
            ),
            ("gross_profit", metrics.gross_profit),
            ("gross_loss", metrics.gross_loss),
            (
                "net_profit_loss",
                metrics.net_profit_loss,
            ),
            ("win_rate", metrics.win_rate),
            (
                "profit_factor",
                metrics.profit_factor,
            ),
            (
                "average_profit",
                metrics.average_profit,
            ),
            (
                "average_loss",
                metrics.average_loss,
            ),
            ("expectancy", metrics.expectancy),
            (
                "maximum_consecutive_wins",
                metrics.maximum_consecutive_wins,
            ),
            (
                "maximum_consecutive_losses",
                metrics.maximum_consecutive_losses,
            ),
            (
                "unmatched_buy_quantity",
                metrics.unmatched_buy_quantity,
            ),
            (
                "unmatched_sell_quantity",
                metrics.unmatched_sell_quantity,
            ),
            (
                "initial_equity",
                None
                if equity_report is None
                else equity_report.initial_equity,
            ),
            (
                "final_equity",
                None
                if equity_report is None
                else equity_report.final_equity,
            ),
            (
                "absolute_profit_loss",
                None
                if equity_report is None
                else equity_report.absolute_profit_loss,
            ),
            (
                "total_return",
                None
                if equity_report is None
                else equity_report.total_return,
            ),
            (
                "maximum_drawdown",
                None
                if equity_report is None
                else equity_report.maximum_drawdown,
            ),
            (
                "maximum_drawdown_amount",
                None
                if equity_report is None
                else equity_report.maximum_drawdown_amount,
            ),
        ]

        with path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            writer = csv.writer(file)
            writer.writerow(["metric", "value"])

            for name, value in rows:
                writer.writerow(
                    [
                        name,
                        "" if value is None else value,
                    ]
                )

    @staticmethod
    def _write_summary(
        path: Path,
        trade_report: BacktestTradeReport,
        metrics: BacktestPerformanceMetrics,
        equity_report: EquityCurveReport | None,
    ) -> None:
        """主要結果をJSONへ保存する。"""

        equity_summary = None

        if equity_report is not None:
            equity_summary = {
                "point_count": equity_report.point_count,
                "initial_equity": (
                    equity_report.initial_equity
                ),
                "final_equity": (
                    equity_report.final_equity
                ),
                "absolute_profit_loss": (
                    equity_report.absolute_profit_loss
                ),
                "total_return": (
                    equity_report.total_return
                ),
                "maximum_drawdown": (
                    equity_report.maximum_drawdown
                ),
                "maximum_drawdown_amount": (
                    equity_report.maximum_drawdown_amount
                ),
            }

        payload = {
            "metrics": asdict(metrics),
            "trade_report": {
                "trade_count": (
                    trade_report.trade_count
                ),
                "total_net_profit_loss": (
                    trade_report.total_net_profit_loss
                ),
                "unmatched_buy_quantity": (
                    trade_report.unmatched_buy_quantity
                ),
                "unmatched_sell_quantity": (
                    trade_report.unmatched_sell_quantity
                ),
            },
            "equity_curve": equity_summary,
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
