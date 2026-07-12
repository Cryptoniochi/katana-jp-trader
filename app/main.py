"""Project KATANAの起動処理。"""

from app.database import initialize_database
from app.logger import create_logger
from app.settings import settings


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
    logger.info("Startup completed.")


if __name__ == "__main__":
    main()