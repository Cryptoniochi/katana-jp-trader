"""複数銘柄のORBバックテストを実行する。"""

from datetime import datetime, time
from math import isinf

from app.backtest.engine import BacktestEngine
from app.backtest.multi_symbol import (
    MultiSymbolBacktestReportWriter,
    MultiSymbolOrbBacktestService,
)
from app.backtest.report_writer import BacktestReportWriter
from app.logger import create_logger
from app.market.historical_csv_reader import HistoricalCsvReader
from app.settings import settings
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


def format_profit_factor(value: float) -> str:
    """PFを表示用文字列へ変換する。"""

    if isinf(value):
        return "INF"

    return f"{value:.2f}"


def main() -> None:
    """複数銘柄ORBバックテストを実行する。"""

    print("=" * 50)
    print(f"{settings.app_name} - Multi-Symbol ORB Backtest")
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

    service = MultiSymbolOrbBacktestService(
        historical_reader=HistoricalCsvReader(),
        strategy=strategy,
        engine=BacktestEngine(),
    )

    try:
        report = service.run(settings.historical_csv_dir)
    except (
        FileNotFoundError,
        NotADirectoryError,
        ValueError,
    ) as error:
        logger.error(
            "複数銘柄ORBバックテストを実行できません: %s",
            error,
        )
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    symbol_report_path = settings.reports_dir / f"orb_symbols_{timestamp}.csv"
    trade_report_path = settings.reports_dir / f"orb_all_trades_{timestamp}.csv"

    MultiSymbolBacktestReportWriter().write_symbol_results(
        report=report,
        file_path=symbol_report_path,
    )

    BacktestReportWriter().write_trades(
        trades=report.all_trades,
        file_path=trade_report_path,
    )

    total = report.total_result

    logger.info(
        "検証銘柄数: total=%d traded=%d",
        report.symbol_count,
        report.traded_symbol_count,
    )

    logger.info(
        "全銘柄結果: trades=%d wins=%d losses=%d breakeven=%d win_rate=%.2f%%",
        total.trade_count,
        total.win_count,
        total.loss_count,
        total.breakeven_count,
        total.win_rate,
    )

    logger.info(
        "全銘柄損益: total=%.2f gross_profit=%.2f gross_loss=%.2f average=%.2f",
        total.total_profit,
        total.gross_profit,
        total.gross_loss,
        total.average_profit,
    )

    logger.info(
        "全銘柄指標: PF=%s expectancy=%.2f max_drawdown=%.2f",
        format_profit_factor(total.profit_factor),
        total.expectancy,
        total.max_drawdown,
    )

    for rank, symbol_result in enumerate(
        report.symbol_results[:5],
        start=1,
    ):
        result = symbol_result.result

        logger.info(
            "銘柄順位=%d code=%s trades=%d win_rate=%.2f%% total=%.2f PF=%s DD=%.2f",
            rank,
            symbol_result.code,
            result.trade_count,
            result.win_rate,
            result.total_profit,
            format_profit_factor(result.profit_factor),
            result.max_drawdown,
        )

    logger.info(
        "銘柄別結果を出力しました。path=%s",
        symbol_report_path,
    )
    logger.info(
        "全取引明細を出力しました。path=%s",
        trade_report_path,
    )

    if report.total_result.trade_count == 0:
        logger.warning(
            "全銘柄で取引が0件です。"
            "ORB条件を満たす5分足データがあるか確認してください。"
        )


if __name__ == "__main__":
    main()
