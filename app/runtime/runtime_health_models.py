"""Trading Runtimeの自己診断結果モデル。"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class RuntimeHealthStatus(StrEnum):
    """Runtime全体または個別診断の状態。"""

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"

    @property
    def severity(
        self,
    ) -> int:
        """比較用の重大度を返す。"""

        return {
            RuntimeHealthStatus.OK: 0,
            RuntimeHealthStatus.WARNING: 1,
            RuntimeHealthStatus.ERROR: 2,
        }[self]

    @property
    def is_healthy(
        self,
    ) -> bool:
        """正常状態か返す。"""

        return self is RuntimeHealthStatus.OK

    @property
    def requires_attention(
        self,
    ) -> bool:
        """確認または対応が必要な状態か返す。"""

        return self in {
            RuntimeHealthStatus.WARNING,
            RuntimeHealthStatus.ERROR,
        }

    @classmethod
    def worst(
        cls,
        statuses: list[
            "RuntimeHealthStatus"
        ] | tuple[
            "RuntimeHealthStatus",
            ...,
        ],
    ) -> "RuntimeHealthStatus":
        """複数状態のうち最も重大なものを返す。"""

        if not statuses:
            return cls.OK

        return max(
            statuses,
            key=lambda status: status.severity,
        )


@dataclass(frozen=True, slots=True)
class RuntimeHealthCheck:
    """1項目分の自己診断結果。"""

    name: str
    status: RuntimeHealthStatus
    message: str
    checked_at: datetime
    details: dict[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        """文字列・日時・詳細情報を検証して正規化する。"""

        normalized_name = self.name.strip()
        normalized_message = self.message.strip()

        if not normalized_name:
            raise ValueError(
                "診断項目名を指定してください。"
            )

        if not normalized_message:
            raise ValueError(
                "診断結果メッセージを指定してください。"
            )

        if self.checked_at.tzinfo is None:
            raise ValueError(
                "診断日時にはタイムゾーンが必要です。"
            )

        object.__setattr__(
            self,
            "name",
            normalized_name,
        )
        object.__setattr__(
            self,
            "message",
            normalized_message,
        )
        object.__setattr__(
            self,
            "checked_at",
            self.checked_at.astimezone(
                timezone.utc,
            ),
        )
        object.__setattr__(
            self,
            "details",
            dict(self.details),
        )

    @property
    def is_healthy(
        self,
    ) -> bool:
        """診断結果が正常か返す。"""

        return self.status.is_healthy

    @property
    def requires_attention(
        self,
    ) -> bool:
        """確認または対応が必要か返す。"""

        return self.status.requires_attention


@dataclass(frozen=True, slots=True)
class RuntimeHealthReport:
    """Trading Runtime全体の自己診断レポート。"""

    status: RuntimeHealthStatus
    checks: tuple[
        RuntimeHealthCheck,
        ...,
    ]
    generated_at: datetime

    def __post_init__(self) -> None:
        """全体状態と個別診断結果の整合性を検証する。"""

        if self.generated_at.tzinfo is None:
            raise ValueError(
                "レポート生成日時にはタイムゾーンが必要です。"
            )

        normalized_checks = tuple(
            self.checks
        )
        expected_status = (
            RuntimeHealthStatus.worst(
                tuple(
                    check.status
                    for check in normalized_checks
                )
            )
        )

        if self.status is not expected_status:
            raise ValueError(
                "Runtime全体状態が個別診断結果と"
                "一致しません。 "
                f"expected={expected_status.value} "
                f"actual={self.status.value}"
            )

        check_names: set[str] = set()

        for check in normalized_checks:
            if check.name in check_names:
                raise ValueError(
                    "診断項目名が重複しています。 "
                    f"name={check.name}"
                )

            check_names.add(
                check.name
            )

        object.__setattr__(
            self,
            "checks",
            normalized_checks,
        )
        object.__setattr__(
            self,
            "generated_at",
            self.generated_at.astimezone(
                timezone.utc,
            ),
        )

    @classmethod
    def create(
        cls,
        *,
        checks: list[
            RuntimeHealthCheck
        ] | tuple[
            RuntimeHealthCheck,
            ...,
        ],
        generated_at: datetime,
    ) -> "RuntimeHealthReport":
        """個別診断結果から全体レポートを生成する。"""

        normalized_checks = tuple(
            checks
        )

        return cls(
            status=RuntimeHealthStatus.worst(
                tuple(
                    check.status
                    for check in normalized_checks
                )
            ),
            checks=normalized_checks,
            generated_at=generated_at,
        )

    @property
    def is_healthy(
        self,
    ) -> bool:
        """Runtime全体が正常か返す。"""

        return self.status.is_healthy

    @property
    def requires_attention(
        self,
    ) -> bool:
        """Runtime全体に確認または対応が必要か返す。"""

        return self.status.requires_attention

    @property
    def failed_checks(
        self,
    ) -> tuple[
        RuntimeHealthCheck,
        ...,
    ]:
        """ERROR状態の診断項目だけ返す。"""

        return tuple(
            check
            for check in self.checks
            if (
                check.status
                is RuntimeHealthStatus.ERROR
            )
        )

    @property
    def warning_checks(
        self,
    ) -> tuple[
        RuntimeHealthCheck,
        ...,
    ]:
        """WARNING状態の診断項目だけ返す。"""

        return tuple(
            check
            for check in self.checks
            if (
                check.status
                is RuntimeHealthStatus.WARNING
            )
        )

    def get_check(
        self,
        name: str,
    ) -> RuntimeHealthCheck | None:
        """指定名の診断結果を返す。"""

        normalized_name = name.strip()

        if not normalized_name:
            raise ValueError(
                "診断項目名を指定してください。"
            )

        for check in self.checks:
            if check.name == normalized_name:
                return check

        return None
