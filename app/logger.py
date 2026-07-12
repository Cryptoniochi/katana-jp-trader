"""ログ出力機能。"""

import logging
from pathlib import Path


def create_logger(logs_dir: Path) -> logging.Logger:
    """画面とファイルへログを出力するロガーを作成する。"""

    logs_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("katana")
    logger.setLevel(logging.INFO)

    # 二重にログが表示されるのを防ぐ
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(
        logs_dir / "katana.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger