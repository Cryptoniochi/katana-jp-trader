"""長時間運転中のプロセスリソース監視モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RuntimeResourceStatus(StrEnum):
    """リソース監視の総合状態。"""

    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class RuntimeResourceThresholds:
    """CPU・メモリ・スレッド数の判定閾値。"""

    cpu_warning_percent: float = 70.0
    cpu_critical_percent: float = 90.0
    rss_warning_bytes: int = 1_500_000_000
    rss_critical_bytes: int = 2_500_000_000
    thread_warning_count: int = 100
    thread_critical_count: int = 200

    def __post_init__(self) -> None:
        """閾値の範囲と大小関係を検証する。"""

        for name, value in {
            "CPU警告率": self.cpu_warning_percent,
            "CPU重大率": self.cpu_critical_percent,
        }.items():
            if not 0.0 <= value <= 100.0:
                raise ValueError(
                    f"{name}は0以上100以下である必要があります。"
                )

        if self.cpu_critical_percent < self.cpu_warning_percent:
            raise ValueError(
                "CPU重大率はCPU警告率以上である必要があります。"
            )

        for name, value in {
            "RSS警告値": self.rss_warning_bytes,
            "RSS重大値": self.rss_critical_bytes,
            "スレッド警告数": self.thread_warning_count,
            "スレッド重大数": self.thread_critical_count,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        if self.rss_critical_bytes < self.rss_warning_bytes:
            raise ValueError(
                "RSS重大値はRSS警告値以上である必要があります。"
            )

        if self.thread_critical_count < self.thread_warning_count:
            raise ValueError(
                "スレッド重大数は警告数以上である必要があります。"
            )


@dataclass(frozen=True, slots=True)
class RuntimeResourceSnapshot:
    """1回分のプロセスリソース計測値。"""

    sampled_at: datetime
    cpu_percent: float
    rss_bytes: int
    vms_bytes: int
    thread_count: int
    process_uptime_seconds: float

    def __post_init__(self) -> None:
        """リソース計測値を検証する。"""

        if self.sampled_at.tzinfo is None:
            raise ValueError(
                "サンプリング日時にはタイムゾーンが必要です。"
            )

        if not 0.0 <= self.cpu_percent <= 100.0:
            raise ValueError(
                "CPU使用率は0以上100以下である必要があります。"
            )

        for name, value in {
            "RSS使用量": self.rss_bytes,
            "VMS使用量": self.vms_bytes,
            "スレッド数": self.thread_count,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        if self.process_uptime_seconds < 0:
            raise ValueError(
                "プロセス稼働時間は0以上である必要があります。"
            )

    @property
    def rss_megabytes(self) -> float:
        """RSSをMiB単位で返す。"""

        return self.rss_bytes / (1024 ** 2)

    @property
    def vms_megabytes(self) -> float:
        """VMSをMiB単位で返す。"""

        return self.vms_bytes / (1024 ** 2)

    def evaluate(
        self,
        thresholds: RuntimeResourceThresholds,
    ) -> "RuntimeResourceEvaluation":
        """閾値に基づく状態判定を返す。"""

        reasons: list[str] = []
        severity = 0

        if self.cpu_percent >= thresholds.cpu_critical_percent:
            severity = max(severity, 2)
            reasons.append(
                "CPU使用率が重大閾値以上です。 "
                f"cpu_percent={self.cpu_percent:.2f}"
            )
        elif self.cpu_percent >= thresholds.cpu_warning_percent:
            severity = max(severity, 1)
            reasons.append(
                "CPU使用率が警告閾値以上です。 "
                f"cpu_percent={self.cpu_percent:.2f}"
            )

        if self.rss_bytes >= thresholds.rss_critical_bytes:
            severity = max(severity, 2)
            reasons.append(
                "RSS使用量が重大閾値以上です。 "
                f"rss_bytes={self.rss_bytes}"
            )
        elif self.rss_bytes >= thresholds.rss_warning_bytes:
            severity = max(severity, 1)
            reasons.append(
                "RSS使用量が警告閾値以上です。 "
                f"rss_bytes={self.rss_bytes}"
            )

        if self.thread_count >= thresholds.thread_critical_count:
            severity = max(severity, 2)
            reasons.append(
                "スレッド数が重大閾値以上です。 "
                f"thread_count={self.thread_count}"
            )
        elif self.thread_count >= thresholds.thread_warning_count:
            severity = max(severity, 1)
            reasons.append(
                "スレッド数が警告閾値以上です。 "
                f"thread_count={self.thread_count}"
            )

        status = {
            0: RuntimeResourceStatus.NORMAL,
            1: RuntimeResourceStatus.WARNING,
            2: RuntimeResourceStatus.CRITICAL,
        }[severity]

        return RuntimeResourceEvaluation(
            snapshot=self,
            status=status,
            reasons=tuple(reasons),
        )


@dataclass(frozen=True, slots=True)
class RuntimeResourceEvaluation:
    """リソース計測値と閾値判定結果。"""

    snapshot: RuntimeResourceSnapshot
    status: RuntimeResourceStatus
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        """状態と理由の整合性を検証する。"""

        normalized_reasons = tuple(
            reason.strip()
            for reason in self.reasons
            if reason.strip()
        )

        if (
            self.status is RuntimeResourceStatus.NORMAL
            and normalized_reasons
        ):
            raise ValueError(
                "正常状態には異常理由を設定できません。"
            )

        if (
            self.status is not RuntimeResourceStatus.NORMAL
            and not normalized_reasons
        ):
            raise ValueError(
                "警告・重大状態には理由が必要です。"
            )

        object.__setattr__(
            self,
            "reasons",
            normalized_reasons,
        )

    @property
    def requires_attention(self) -> bool:
        """運用者の確認が必要か返す。"""

        return self.status is not RuntimeResourceStatus.NORMAL
