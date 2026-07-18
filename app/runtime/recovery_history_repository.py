"""Recovery履歴を保持するRepository。"""

from threading import RLock

from app.runtime.recovery_history_models import (
    RecoveryComponent,
    RecoveryHistoryEntry,
)


class RecoveryHistoryRepository:
    """Recovery履歴をメモリ上へ保存するRepository。

    現段階ではRuntime内で共有するインメモリ実装とする。
    永続化が必要になった場合は、同じ公開インターフェースを保ったまま
    SQLite実装へ差し替えられる。
    """

    def __init__(self) -> None:
        self._entries: list[RecoveryHistoryEntry] = []
        self._lock = RLock()

    def add(self, entry: RecoveryHistoryEntry) -> None:
        """Recovery履歴を追加する。"""

        if not isinstance(entry, RecoveryHistoryEntry):
            raise TypeError(
                "entry must be a RecoveryHistoryEntry"
            )

        with self._lock:
            self._entries.append(entry)
            self._entries.sort(
                key=lambda item: item.completed_at
            )

    def list_all(self) -> tuple[RecoveryHistoryEntry, ...]:
        """保存されている全履歴を完了日時順で返す。"""

        with self._lock:
            return tuple(self._entries)

    def list_by_component(
        self,
        component: RecoveryComponent,
    ) -> tuple[RecoveryHistoryEntry, ...]:
        """指定コンポーネントの履歴を返す。"""

        if not isinstance(component, RecoveryComponent):
            raise TypeError(
                "component must be a RecoveryComponent"
            )

        with self._lock:
            return tuple(
                entry
                for entry in self._entries
                if entry.component is component
            )

    def latest(
        self,
        component: RecoveryComponent | None = None,
    ) -> RecoveryHistoryEntry | None:
        """最新のRecovery履歴を返す。"""

        if component is not None and not isinstance(
            component,
            RecoveryComponent,
        ):
            raise TypeError(
                "component must be a RecoveryComponent or None"
            )

        entries = (
            self.list_all()
            if component is None
            else self.list_by_component(component)
        )

        if not entries:
            return None

        return entries[-1]

    def count(
        self,
        component: RecoveryComponent | None = None,
    ) -> int:
        """保存済み履歴件数を返す。"""

        if component is None:
            return len(self.list_all())

        return len(self.list_by_component(component))

    def clear(self) -> None:
        """保存済み履歴をすべて削除する。"""

        with self._lock:
            self._entries.clear()