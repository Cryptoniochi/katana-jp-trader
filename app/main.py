"""Project KATANAの起動処理。"""

from math import isinf

from app.backtest.engine import BacktestEngine
from app.backtest.service import CsvBacktestService
from app.database import initialize_database
from app.logger import create_logger
from app.market.csv_reader import CsvStockReader
from app.market.csv_repository import CsvStockRepository
from app.market.downloader import DummyDownloader
from app.market.repository import StockRepository
from app.market.service import MarketDataService
from app.market.summary import summarize_prices
from app.settings import settings
from app.strategy.buy_open_sell_close import BuyOpenSellCloseStrategy


def main() -> None:
    """アプリケーションを起動する。"""

    print("=" * 50)
    print(settings.app_name)
    print(f"Version : {settings.version}")
    print("=" * 50)

    settings.create_directories()
    logger = create_logger(settings.logs_dir)

    logger.info("Project KATANAを起動します。")
    logger.info("設定を読み込みました。")

    initialize_database(settings.database_path)
    logger.info("データベースを初期化しました。")

    market_service = MarketDataService(
        downloader=DummyDownloader(),
        sqlite_repository=StockRepository(settings.database_path),
        csv_repository=CsvStockRepository(settings.csv_dir),
    )

    import_result = market_service.import_prices()

    logger.info(
        "市場データを取り込みました。downloaded=%d database_count=%d",
        import_result.downloaded_count,
        import_result.database_count,
    )

    if import_result.latest_csv_path is not None:
        csv_path = import_result.latest_csv_path

        logger.info("CSVへ保存しました。path=%s", csv_path)

        csv_reader = CsvStockReader()
        saved_prices = csv_reader.read(csv_path)
        summary = summarize_prices(saved_prices)

        logger.info(
            "CSV集計: records=%d latest_close=%.2f "
            "total_volume=%d highest=%.2f lowest=%.2f",
            summary.record_count,
            summary.latest_close,
            summary.total_volume,
            summary.highest_price,
            summary.lowest_price,
        )

        backtest_service = CsvBacktestService(
            csv_reader=csv_reader,
            strategy=BuyOpenSellCloseStrategy(quantity=100),
            engine=BacktestEngine(),
        )

        result = backtest_service.run(csv_path)

        profit_factor_text = (
            "INF" if isinf(result.profit_factor) else f"{result.profit_factor:.2f}"
        )

        logger.info(
            "バックテスト結果: trades=%d wins=%d losses=%d "
            "breakeven=%d win_rate=%.2f%%",
            result.trade_count,
            result.win_count,
            result.loss_count,
            result.breakeven_count,
            result.win_rate,
        )

        logger.info(
            "バックテスト損益: total=%.2f gross_profit=%.2f "
            "gross_loss=%.2f average=%.2f",
            result.total_profit,
            result.gross_profit,
            result.gross_loss,
            result.average_profit,
        )

        logger.info(
            "バックテスト指標: PF=%s expectancy=%.2f max_drawdown=%.2f",
            profit_factor_text,
            result.expectancy,
            result.max_drawdown,
        )

    logger.info("Startup completed.")


if __name__ == "__main__":
    main()
