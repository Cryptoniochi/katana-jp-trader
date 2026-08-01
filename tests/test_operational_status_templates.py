"""Operational status表示のテスト。"""

from pathlib import Path

from app.dashboard.dashboard_web_app import (
    TEMPLATE_DIRECTORY,
)


def test_mobile_labels_data_status_separately() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "mobile_dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert 'class="mobile-data-status"' in content
    assert "Data completeness and service health" in content
    assert '"stale"' in content


def test_desktop_supports_stale_service_state() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert '"stale"' in content
    assert "status_age_seconds" in content
