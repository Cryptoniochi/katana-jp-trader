"""通知テンプレートのテスト。"""

import pytest

from app.notifications.notification_models import (
    NotificationSeverity,
)
from app.notifications.notification_template import (
    NotificationTemplate,
    NotificationTemplateName,
    NotificationTemplateRegistry,
)


def test_template_renders_title_and_body() -> None:
    template = NotificationTemplate(
        name=NotificationTemplateName.GENERIC,
        title_template="{title}",
        body_template="{message} ({code})",
        default_severity=NotificationSeverity.INFO,
    )

    title, body = template.render(
        {
            "title": "Order",
            "message": "Created",
            "code": "7203",
        }
    )

    assert title == "Order"
    assert body == "Created (7203)"
    assert template.required_fields == frozenset(
        {"title", "message", "code"}
    )


def test_template_rejects_missing_context() -> None:
    template = NotificationTemplate(
        name=NotificationTemplateName.ORDER,
        title_template="Order: {code}",
        body_template="{message}",
        default_severity=NotificationSeverity.INFO,
    )

    with pytest.raises(
        ValueError,
        match="不足",
    ):
        template.render(
            {"message": "created"}
        )


def test_registry_returns_default_template() -> None:
    registry = NotificationTemplateRegistry()

    template = registry.get(
        NotificationTemplateName.FAULT_TOLERANCE
    )

    assert template.default_severity is (
        NotificationSeverity.ERROR
    )


def test_registry_rejects_duplicate_names() -> None:
    template = NotificationTemplate(
        name=NotificationTemplateName.GENERIC,
        title_template="{title}",
        body_template="{message}",
        default_severity=NotificationSeverity.INFO,
    )

    with pytest.raises(
        ValueError,
        match="重複",
    ):
        NotificationTemplateRegistry(
            templates=(template, template)
        )
