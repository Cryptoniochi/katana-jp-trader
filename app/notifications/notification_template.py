"""通知テンプレートの定義と描画。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from string import Formatter
from typing import Any

from app.notifications.notification_models import NotificationSeverity


class NotificationTemplateName(StrEnum):
    """Project KATANAの標準通知テンプレート。"""

    GENERIC = "generic"
    SYSTEM_HEALTH = "system_health"
    SUPERVISOR = "supervisor"
    RECOVERY = "recovery"
    FAULT_TOLERANCE = "fault_tolerance"
    ORDER = "order"
    EXECUTION = "execution"
    RISK = "risk"


@dataclass(frozen=True, slots=True)
class NotificationTemplate:
    """1つの通知テンプレート。"""

    name: NotificationTemplateName
    title_template: str
    body_template: str
    default_severity: NotificationSeverity

    def __post_init__(self) -> None:
        """テンプレート内容を検証する。"""

        title = self.title_template.strip()
        body = self.body_template.strip()

        if not title:
            raise ValueError(
                "通知タイトルテンプレートを指定してください。"
            )

        if not body:
            raise ValueError(
                "通知本文テンプレートを指定してください。"
            )

        object.__setattr__(self, "title_template", title)
        object.__setattr__(self, "body_template", body)

    @property
    def required_fields(self) -> frozenset[str]:
        """タイトル・本文で参照するフィールド名を返す。"""

        formatter = Formatter()
        fields: set[str] = set()

        for template in (
            self.title_template,
            self.body_template,
        ):
            for _literal, field_name, _format_spec, _conversion in (
                formatter.parse(template)
            ):
                if field_name:
                    fields.add(
                        field_name.split(".", 1)[0].split("[", 1)[0]
                    )

        return frozenset(fields)

    def render(
        self,
        context: dict[str, Any],
    ) -> tuple[str, str]:
        """Contextを使ってタイトル・本文を描画する。"""

        missing = sorted(
            self.required_fields - context.keys()
        )

        if missing:
            raise ValueError(
                "通知テンプレートに必要な値が不足しています。 "
                f"fields={','.join(missing)}"
            )

        try:
            title = self.title_template.format_map(context)
            body = self.body_template.format_map(context)
        except (KeyError, AttributeError, IndexError) as error:
            raise ValueError(
                "通知テンプレートの描画に失敗しました。"
            ) from error

        title = title.strip()
        body = body.strip()

        if not title or not body:
            raise ValueError(
                "通知テンプレートの描画結果が空です。"
            )

        return title, body


class NotificationTemplateRegistry:
    """標準・追加テンプレートを一元管理する。"""

    def __init__(
        self,
        templates: tuple[NotificationTemplate, ...] | None = None,
    ) -> None:
        """テンプレート一覧を登録する。"""

        source = templates or self.default_templates()
        mapping: dict[NotificationTemplateName, NotificationTemplate] = {}

        for template in source:
            if template.name in mapping:
                raise ValueError(
                    "通知テンプレート名が重複しています。 "
                    f"name={template.name.value}"
                )
            mapping[template.name] = template

        self._templates = mapping

    def get(
        self,
        name: NotificationTemplateName,
    ) -> NotificationTemplate:
        """指定テンプレートを返す。"""

        try:
            return self._templates[name]
        except KeyError as error:
            raise KeyError(
                f"通知テンプレートが見つかりません。 name={name.value}"
            ) from error

    @staticmethod
    def default_templates() -> tuple[NotificationTemplate, ...]:
        """Project KATANAの標準テンプレートを返す。"""

        return (
            NotificationTemplate(
                name=NotificationTemplateName.GENERIC,
                title_template="{title}",
                body_template="{message}",
                default_severity=NotificationSeverity.INFO,
            ),
            NotificationTemplate(
                name=NotificationTemplateName.SYSTEM_HEALTH,
                title_template="System Health: {status}",
                body_template="{message}",
                default_severity=NotificationSeverity.WARNING,
            ),
            NotificationTemplate(
                name=NotificationTemplateName.SUPERVISOR,
                title_template="Supervisor: {worker_name}",
                body_template="{message}",
                default_severity=NotificationSeverity.ERROR,
            ),
            NotificationTemplate(
                name=NotificationTemplateName.RECOVERY,
                title_template="Recovery: {status}",
                body_template="{message}",
                default_severity=NotificationSeverity.INFO,
            ),
            NotificationTemplate(
                name=NotificationTemplateName.FAULT_TOLERANCE,
                title_template="Fault Tolerance: {decision}",
                body_template="{message}",
                default_severity=NotificationSeverity.ERROR,
            ),
            NotificationTemplate(
                name=NotificationTemplateName.ORDER,
                title_template="Order: {code}",
                body_template="{message}",
                default_severity=NotificationSeverity.INFO,
            ),
            NotificationTemplate(
                name=NotificationTemplateName.EXECUTION,
                title_template="Execution: {code}",
                body_template="{message}",
                default_severity=NotificationSeverity.INFO,
            ),
            NotificationTemplate(
                name=NotificationTemplateName.RISK,
                title_template="Risk: {decision}",
                body_template="{message}",
                default_severity=NotificationSeverity.WARNING,
            ),
        )
