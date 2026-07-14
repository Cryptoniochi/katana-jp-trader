"""ORB戦略のパラメータ最適化を実行する。"""

from datetime import datetime, time
from math import isinf

from app.backtest.engine import BacktestEngine
from app.backtest.orb_optimizer import OrbOptimizer
from app.logger import create_logger
from app.market.historical_csv_reader import HistoricalCsvReader
from app.settings import settings


def main() -> None:
    """複数の損切り率と利確率を総当たりする。"""

    print("=" * 50)
    print(f"{settings.app_name} - ORB Optimization")
    print(f"Version : {settings.version}")
    print("=" * 50)

    settings.create_directories()
    logger = create_logger(settings.logs_dir)

    stop_loss_rates = [
        0.005,
        0.008,
        0.010,
        0.012,
        0.015,
    ]

    take_profit_rates = [
        0.010,
        0.015,
        0.020,
        0.030,
        0.040,
    ]

    optimizer = OrbOptimizer(
        historical_reader=HistoricalCsvReader(),
        engine=BacktestEngine(),
        quantity=100,
        opening_range_end=time(9, 15),
        force_exit_time=time(14, 50),
        commission=0.0,
        slippage_rate=0.0005,
    )

    try:
        results = optimizer.run(
            directory=settings.historical_csv_dir,
            stop_loss_rates=stop_loss_rates,
            take_profit_rates=take_profit_rates,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        logger.error(
            "ORB最適化を実行できません: %s",
            error,
        )
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = settings.reports_dir / f"orb_optimization_{timestamp}.csv"

    optimizer.write_csv(
        results=results,
        file_path=report_path,
    )

    logger.info(
        "ORB最適化を完了しました。combinations=%d",
        len(results),
    )

    for rank, result in enumerate(results[:5], start=1):
        profit_factor_text = (
            "INF" if isinf(result.profit_factor) else f"{result.profit_factor:.2f}"
        )

        logger.info(
            "順位=%d 損切り=%.2f%% 利確=%.2f%% "
            "trades=%d win_rate=%.2f%% total=%.2f "
            "PF=%s expectancy=%.2f DD=%.2f",
            rank,
            result.stop_loss_rate * 100,
            result.take_profit_rate * 100,
            result.trade_count,
            result.win_rate,
            result.total_profit,
            profit_factor_text,
            result.expectancy,
            result.max_drawdown,
        )

    logger.info(
        "最適化結果を出力しました。path=%s",
        report_path,
    )

    if results and all(result.trade_count == 0 for result in results):
        logger.warning(
            "全パラメータで取引が0件です。"
            "履歴CSVにORB条件を満たす5分足があるか確認してください。"
        )


if __name__ == "__main__":
    main()
