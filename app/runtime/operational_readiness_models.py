"""Project KATANA運用準備チェックのモデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class ReadinessLevel(StrEnum):
    """運用準備チェックの重大度。"""

    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    """1件の運用準備チェック結果。"""

    key: str
    label: str
    level: ReadinessLevel
    message: str
    required: bool
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
class OperationalReadinessPayload:
    """Dashboardへ返す運用準備状態。"""

    generated_at: datetime
    overall_state: str
    ready_for_paper_trading: bool
    checks: tuple[ReadinessCheck, ...]

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError(
                "生成日時にはタイムゾーンが必要です。"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "overall_state": self.overall_state,
            "ready_for_paper_trading": (
                self.ready_for_paper_trading
            ),
            "checks": [
                check.to_dict()
                for check in self.checks
            ],
        }
