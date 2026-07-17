"""同期型の軽量Domain Event Bus。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.events.domain_events import (
    DomainEvent,
    DomainEventType,
)


DomainEventHandler = Callable[[DomainEvent], None]


class DomainEventDispatchDecision(StrEnum):
    """イベント配信結果。"""

    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DomainEventHandlerError:
    """1つのハンドラーで発生した例外。"""

    handler_name: str
    error_message: str

    def __post_init__(self) -> None:
        """エラー内容を検証する。"""

        handler_name = self.handler_name.strip()
        error_message = self.error_message.strip()

        if not handler_name:
            raise ValueError(
                "ハンドラー名を指定してください。"
            )

        if not error_message:
            raise ValueError(
                "エラーメッセージを指定してください。"
            )

        object.__setattr__(
            self,
            "handler_name",
            handler_name,
        )
        object.__setattr__(
            self,
            "error_message",
            error_message,
        )


@dataclass(frozen=True, slots=True)
class DomainEventDispatchResult:
    """1イベントの配信結果。"""

    event: DomainEvent
    decision: DomainEventDispatchDecision
    handler_count: int
    succeeded_count: int
    errors: tuple[DomainEventHandlerError, ...]

    def __post_init__(self) -> None:
        """件数と判定結果を検証する。"""

        if self.handler_count < 0:
            raise ValueError(
                "ハンドラー件数は0以上である必要があります。"
            )

        if not (
            0
            <= self.succeeded_count
            <= self.handler_count
        ):
            raise ValueError(
                "成功件数は0以上かつ"
                "ハンドラー件数以下である必要があります。"
            )

        if (
            self.succeeded_count
            + len(self.errors)
            != self.handler_count
        ):
            raise ValueError(
                "成功件数と失敗件数の合計が"
                "ハンドラー件数と一致しません。"
            )

        if (
            self.decision
            is DomainEventDispatchDecision.COMPLETED
            and self.errors
        ):
            raise ValueError(
                "正常完了結果にはエラーを設定できません。"
            )

        if (
            self.decision
            is not DomainEventDispatchDecision.COMPLETED
            and not self.errors
        ):
            raise ValueError(
                "異常結果にはエラーが必要です。"
            )

    @property
    def is_successful(self) -> bool:
        """全ハンドラーが成功したか返す。"""

        return (
            self.decision
            is DomainEventDispatchDecision.COMPLETED
        )


class DomainEventBus:
    """イベント種別ごとに同期ハンドラーを配信する。"""

    def __init__(
        self,
        *,
        history_limit: int = 1_000,
    ) -> None:
        """履歴上限と購読状態を初期化する。"""

        if history_limit < 0:
            raise ValueError(
                "履歴上限は0以上である必要があります。"
            )

        self.history_limit = history_limit
        self._handlers: dict[
            DomainEventType,
            list[DomainEventHandler],
        ] = {}
        self._history: list[DomainEvent] = []

    def subscribe(
        self,
        event_type: DomainEventType,
        handler: DomainEventHandler,
    ) -> bool:
        """ハンドラーを登録する。重複時はFalseを返す。"""

        if not callable(handler):
            raise TypeError(
                "ハンドラーは呼び出し可能である必要があります。"
            )

        handlers = self._handlers.setdefault(
            event_type,
            [],
        )

        if handler in handlers:
            return False

        handlers.append(handler)
        return True

    def unsubscribe(
        self,
        event_type: DomainEventType,
        handler: DomainEventHandler,
    ) -> bool:
        """登録済みハンドラーを解除する。"""

        handlers = self._handlers.get(event_type)

        if not handlers or handler not in handlers:
            return False

        handlers.remove(handler)

        if not handlers:
            self._handlers.pop(event_type, None)

        return True

    def publish(
        self,
        event: DomainEvent,
        *,
        continue_on_error: bool = True,
    ) -> DomainEventDispatchResult:
        """イベントを登録順に同期配信する。"""

        handlers = tuple(
            self._handlers.get(
                event.event_type,
                (),
            )
        )
        succeeded_count = 0
        errors: list[DomainEventHandlerError] = []

        self._record_history(event)

        for handler in handlers:
            try:
                handler(event)
                succeeded_count += 1
            except Exception as error:
                handler_error = DomainEventHandlerError(
                    handler_name=self._handler_name(handler),
                    error_message=(
                        str(error).strip()
                        or type(error).__name__
                    ),
                )
                errors.append(handler_error)

                if not continue_on_error:
                    raise

        if not errors:
            decision = (
                DomainEventDispatchDecision.COMPLETED
            )
        elif succeeded_count > 0:
            decision = (
                DomainEventDispatchDecision
                .COMPLETED_WITH_ERRORS
            )
        else:
            decision = DomainEventDispatchDecision.FAILED

        return DomainEventDispatchResult(
            event=event,
            decision=decision,
            handler_count=len(handlers),
            succeeded_count=succeeded_count,
            errors=tuple(errors),
        )

    def subscriber_count(
        self,
        event_type: DomainEventType,
    ) -> int:
        """指定イベント種別の購読数を返す。"""

        return len(
            self._handlers.get(
                event_type,
                (),
            )
        )

    def history(
        self,
        *,
        event_type: DomainEventType | None = None,
    ) -> tuple[DomainEvent, ...]:
        """配信済みイベント履歴を返す。"""

        if event_type is None:
            return tuple(self._history)

        return tuple(
            event
            for event in self._history
            if event.event_type is event_type
        )

    def clear_history(self) -> None:
        """イベント履歴を削除する。"""

        self._history.clear()

    def _record_history(
        self,
        event: DomainEvent,
    ) -> None:
        """履歴上限を維持してイベントを保存する。"""

        if self.history_limit == 0:
            return

        self._history.append(event)

        overflow = (
            len(self._history)
            - self.history_limit
        )

        if overflow > 0:
            del self._history[:overflow]

    @staticmethod
    def _handler_name(
        handler: DomainEventHandler,
    ) -> str:
        """ログ用のハンドラー名を返す。"""

        return getattr(
            handler,
            "__qualname__",
            getattr(
                handler,
                "__name__",
                type(handler).__name__,
            ),
        )
