"""履歴CSVを使ってORBバックテストを実行する。"""

from math import isinf

from app.backtest.engine import BacktestEngine
from app.backtest.historical_service import (
    HistoricalOrbBacktestService,
)
from app.logger import create_logger
from app.market.historical_csv_reader import HistoricalCsvReader
from app.settings import settings
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


def main() -> None:
    """ORBバックテストを実行し、結果をログへ出力する。"""

    print("=" * 50)
    print(f"{settings.app_name} - ORB Backtest")
    print(f"Version : {settings.version}")
    print("=" * 50)

    settings.create_directories()
    logger = create_logger(settings.logs_dir)

    service = HistoricalOrbBacktestService(
        historical_reader=HistoricalCsvReader(),
        strategy=OpeningRangeBreakoutStrategy(
            quantity=100,
            commission=0.0,
            slippage_rate=0.0005,
        ),
        engine=BacktestEngine(),
    )

    try:
        result = service.run(settings.historical_csv_dir)
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        logger.error("ORBバックテストを実行できません: %s", error)
        return

    profit_factor_text = (
        "INF" if isinf(result.profit_factor) else f"{result.profit_factor:.2f}"
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


if __name__ == "__main__":
    main()
