"""Application Componentモデルのテスト。"""

import pytest

from app.application.application_component import (
    ApplicationComponentRegistration,
    ApplicationComponentSnapshot,
    ApplicationComponentState,
)


class FakeComponent:
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def component_name(self) -> str:
        return self._name

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def test_registration_uses_start_order_as_default_stop_order() -> None:
    registration = ApplicationComponentRegistration(
        component=FakeComponent("runtime-session"),
        start_order=10,
    )

    assert registration.component_name == "runtime-session"
    assert registration.stop_order == 10


def test_registration_rejects_invalid_order() -> None:
    with pytest.raises(ValueError, match="開始順序"):
        ApplicationComponentRegistration(
            component=FakeComponent("component"),
            start_order=-1,
        )


def test_failed_snapshot_requires_error_message() -> None:
    with pytest.raises(ValueError, match="エラー"):
        ApplicationComponentSnapshot(
            component_name="component",
            state=ApplicationComponentState.FAILED,
            start_order=1,
            stop_order=1,
        )


def test_non_failed_snapshot_rejects_error_message() -> None:
    with pytest.raises(ValueError, match="FAILED以外"):
        ApplicationComponentSnapshot(
            component_name="component",
            state=ApplicationComponentState.RUNNING,
            start_order=1,
            stop_order=1,
            error_message="unexpected",
        )
