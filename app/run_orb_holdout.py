"""ORB戦略のホールドアウト検証を実行する。"""

from datetime import datetime, time
from math import isinf

from app.backtest.engine import BacktestEngine
from app.backtest.orb_holdout import OrbHoldoutValidator
from app.backtest.orb_optimizer import OrbOptimizer
from app.logger import create_logger
from app.market.historical_csv_reader import HistoricalCsvReader
from app.settings import settings


def format_profit_factor(value: float) -> str:
    """PFを画面表示用の文字列へ変換する。"""

    if isinf(value):
        return "INF"

    return f"{value:.2f}"


def main() -> None:
    """学習期間で最適化し、検証期間で評価する。"""

    print("=" * 50)
    print(f"{settings.app_name} - ORB Holdout Validation")
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

    reader = HistoricalCsvReader()
    engine = BacktestEngine()

    optimizer = OrbOptimizer(
        historical_reader=reader,
        engine=engine,
        quantity=100,
        opening_range_end=time(9, 15),
        force_exit_time=time(14, 50),
        commission=0.0,
        slippage_rate=0.0005,
    )

    validator = OrbHoldoutValidator(
        historical_reader=reader,
        optimizer=optimizer,
        engine=engine,
        training_ratio=0.7,
    )

    try:
        result = validator.run(
            directory=settings.historical_csv_dir,
            stop_loss_rates=stop_loss_rates,
            take_profit_rates=take_profit_rates,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        logger.error(
            "ORBホールドアウト検証を実行できません: %s",
            error,
        )
        return

    best = result.best_parameters
    validation = result.validation_result

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = settings.reports_dir / f"orb_holdout_{timestamp}.csv"

    validator.write_csv(
        result=result,
        file_path=report_path,
    )

    logger.info(
        "学習期間: %s ～ %s day_count=%d",
        result.training_start,
        result.training_end,
        result.training_day_count,
    )

    logger.info(
        "検証期間: %s ～ %s day_count=%d",
        result.validation_start,
        result.validation_end,
        result.validation_day_count,
    )

    logger.info(
        "学習期間の最良条件: 損切り=%.2f%% 利確=%.2f%% "
        "trades=%d total=%.2f PF=%s expectancy=%.2f DD=%.2f",
        best.stop_loss_rate * 100,
        best.take_profit_rate * 100,
        best.trade_count,
        best.total_profit,
        format_profit_factor(best.profit_factor),
        best.expectancy,
        best.max_drawdown,
    )

    logger.info(
        "検証期間の結果: trades=%d wins=%d losses=%d "
        "win_rate=%.2f%% total=%.2f PF=%s "
        "expectancy=%.2f DD=%.2f",
        validation.trade_count,
        validation.win_count,
        validation.loss_count,
        validation.win_rate,
        validation.total_profit,
        format_profit_factor(validation.profit_factor),
        validation.expectancy,
        validation.max_drawdown,
    )

    logger.info(
        "ホールドアウト結果を出力しました。path=%s",
        report_path,
    )

    if best.trade_count == 0:
        logger.warning(
            "学習期間の最良条件でも取引が0件です。履歴データを増やしてください。"
        )

    if validation.trade_count == 0:
        logger.warning("検証期間の取引が0件です。検証に十分な履歴データがありません。")


if __name__ == "__main__":
    main()
