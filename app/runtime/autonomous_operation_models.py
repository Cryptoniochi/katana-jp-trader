"""自律運転検証レポートのデータモデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class AutonomousCheckLevel(StrEnum):
    """自律運転チェック結果。"""

    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class AutonomousOperationCheck:
    """1件の自律運転チェック。"""

    key: str
    label: str
    level: AutonomousCheckLevel
    message: str
    details: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError(
                "チェックキーを指定してください。"
            )

        if not self.label.strip():
            raise ValueError(
                "チェック表示名を指定してください。"
            )

        if not self.message.strip():
            raise ValueError(
                "チェックメッセージを指定してください。"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["level"] = self.level.value
        return payload


@dataclass(frozen=True, slots=True)
class AutonomousOperationReport:
    """自律運転開始可否レポート。"""

    generated_at: datetime
    overall_state: str
    ready_for_next_business_day: bool
    checks: tuple[AutonomousOperationCheck, ...]

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError(
                "生成日時にはタイムゾーンが必要です。"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "overall_state": self.overall_state,
            "ready_for_next_business_day": (
                self.ready_for_next_business_day
            ),
            "checks": [
                check.to_dict()
                for check in self.checks
            ],
        }
