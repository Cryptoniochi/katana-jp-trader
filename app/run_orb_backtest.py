"""履歴CSVを使ってORBバックテストを実行する。"""

from datetime import datetime, time
from math import isinf

from app.backtest.engine import BacktestEngine
from app.backtest.historical_service import (
    HistoricalOrbBacktestService,
)
from app.backtest.report_writer import BacktestReportWriter
from app.logger import create_logger
from app.market.historical_csv_reader import HistoricalCsvReader
from app.settings import settings
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


def main() -> None:
    """ORBバックテストを実行して結果を出力する。"""

    print("=" * 50)
    print(f"{settings.app_name} - ORB Backtest")
    print(f"Version : {settings.version}")
    print("=" * 50)

    settings.create_directories()
    logger = create_logger(settings.logs_dir)

    strategy = OpeningRangeBreakoutStrategy(
        quantity=100,
        opening_range_end=time(9, 15),
        stop_loss_rate=0.01,
        take_profit_rate=0.02,
        force_exit_time=time(14, 50),
        commission=0.0,
        slippage_rate=0.0005,
    )

    service = HistoricalOrbBacktestService(
        historical_reader=HistoricalCsvReader(),
        strategy=strategy,
        engine=BacktestEngine(),
    )

    try:
        report = service.run_report(settings.historical_csv_dir)
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        logger.error(
            "ORBバックテストを実行できません: %s",
            error,
        )
        return

    result = report.result

    profit_factor_text = (
        "INF" if isinf(result.profit_factor) else f"{result.profit_factor:.2f}"
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = settings.reports_dir / f"orb_trades_{timestamp}.csv"

    BacktestReportWriter().write_trades(
        report.trades,
        report_path,
    )

    logger.info(
        "ORB条件: opening_range_end=%s stop_loss=%.2f%% "
        "take_profit=%.2f%% force_exit=%s",
        strategy.opening_range_end.strftime("%H:%M"),
        (strategy.stop_loss_rate or 0) * 100,
        (strategy.take_profit_rate or 0) * 100,
        strategy.force_exit_time.strftime("%H:%M"),
    )

    logger.info(
        "ORB結果: trades=%d wins=%d losses=%d breakeven=%d win_rate=%.2f%%",
        result.trade_count,
        result.win_count,
        result.loss_count,
        result.breakeven_count,
        result.win_rate,
    )

    logger.info(
        "ORB損益: total=%.2f gross_profit=%.2f gross_loss=%.2f average=%.2f",
        result.total_profit,
        result.gross_profit,
        result.gross_loss,
        result.average_profit,
    )

    logger.info(
        "ORB指標: PF=%s expectancy=%.2f max_drawdown=%.2f",
        profit_factor_text,
        result.expectancy,
        result.max_drawdown,
    )

    logger.info(
        "取引明細を出力しました。path=%s",
        report_path,
    )


if __name__ == "__main__":
    main()
