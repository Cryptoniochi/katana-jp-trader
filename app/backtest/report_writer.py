"""バックテスト取引明細のCSV出力。"""

import csv
from pathlib import Path

from app.backtest.trade import Trade


class BacktestReportWriter:
    """取引明細をCSVファイルへ出力する。"""

    def write_trades(
        self,
        trades: list[Trade],
        file_path: Path,
    ) -> Path:
        """取引一覧をCSVへ保存し、保存先を返す。"""

        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with file_path.open(
            mode="w",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:
            writer = csv.writer(csv_file)

            writer.writerow(
                [
                    "code",
                    "entry_at",
                    "exit_at",
                    "exit_reason",
                    "buy_price",
                    "sell_price",
                    "quantity",
                    "gross_profit",
                    "commission",
                    "slippage_cost",
                    "total_cost",
                    "net_profit",
                    "return_rate",
                ]
            )

            for trade in trades:
                writer.writerow(
                    [
                        trade.code,
                        (
                            trade.entry_at.isoformat()
                            if trade.entry_at is not None
                            else ""
                        ),
                        (
                            trade.exit_at.isoformat()
                            if trade.exit_at is not None
                            else ""
                        ),
                        trade.exit_reason.value,
                        trade.buy_price,
                        trade.sell_price,
                        trade.quantity,
                        trade.gross_profit,
                        trade.commission,
                        trade.slippage_cost,
                        trade.total_cost,
                        trade.profit,
                        trade.return_rate,
                    ]
                )

        return file_path
