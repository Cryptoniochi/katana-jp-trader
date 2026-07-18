"""日次運用レポートの共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DailyOperationReportPaths:
    """1営業日分のレポート出力先。"""

    trading_date: date
    directory: Path
    json_path: Path
    html_path: Path

    def __post_init__(self) -> None:
        """出力先の整合性を検証する。"""

        if self.json_path.parent != self.directory:
            raise ValueError(
                "JSON出力先はレポートDirectory配下である必要があります。"
            )

        if self.html_path.parent != self.directory:
            raise ValueError(
                "HTML出力先はレポートDirectory配下である必要があります。"
            )


@dataclass(frozen=True, slots=True)
class DailyOperationReportResult:
    """日次運用レポート生成結果。"""

    trading_date: date
    generated_at: datetime
    paths: DailyOperationReportPaths
    json_size_bytes: int
    html_size_bytes: int

    def __post_init__(self) -> None:
        """生成結果を検証する。"""

        if self.generated_at.tzinfo is None:
            raise ValueError(
                "レポート生成日時にはタイムゾーンが必要です。"
            )

        if self.paths.trading_date != self.trading_date:
            raise ValueError(
                "レポートPathの営業日が生成結果と一致しません。"
            )

        if self.json_size_bytes < 0:
            raise ValueError(
                "JSONサイズは0以上である必要があります。"
            )

        if self.html_size_bytes < 0:
            raise ValueError(
                "HTMLサイズは0以上である必要があります。"
            )
