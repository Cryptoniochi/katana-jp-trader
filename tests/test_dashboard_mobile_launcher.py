"""Dashboard mobile launcher extensionsのテスト。"""

from app.dashboard.dashboard_launcher import (
    DEFAULT_HOST,
    mobile_dashboard_url,
)


def test_dashboard_is_local_only_by_default() -> None:
    assert DEFAULT_HOST == "127.0.0.1"


def test_mobile_dashboard_url_uses_mobile_path() -> None:
    assert mobile_dashboard_url(
        host="0.0.0.0",
        port=8000,
    ) == "http://127.0.0.1:8000/mobile"
