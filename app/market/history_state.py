"""履歴取込の途中再開状態をJSONで保存する。"""

import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

STATE_VERSION = 1


@dataclass(frozen=True, slots=True)
class HistoryTaskKey:
    """1銘柄・1チャンクを識別するキー。"""

    code: str
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        """キーの内容を検証する。"""

        normalized_code = self.code.strip()

        if not normalized_code:
            raise ValueError("銘柄コードを指定してください。")

        if self.start_date > self.end_date:
            raise ValueError("開始日は終了日以前にしてください。")

        object.__setattr__(
            self,
            "code",
            normalized_code,
        )

    @property
    def value(self) -> str:
        """JSON保存用の一意文字列を返す。"""

        return f"{self.code}:{self.start_date.isoformat()}:{self.end_date.isoformat()}"


@dataclass(frozen=True, slots=True)
class HistoryTaskFailureState:
    """失敗したチャンクの状態を表す。"""

    key: HistoryTaskKey
    message: str
    failed_at: datetime
    attempt_count: int


@dataclass(frozen=True, slots=True)
class HistoryImportState:
    """履歴取込全体の保存状態。"""

    state_version: int
    updated_at: datetime
    completed_task_keys: frozenset[str]
    failures: tuple[HistoryTaskFailureState, ...]

    @classmethod
    def empty(cls) -> HistoryImportState:
        """空の取込状態を返す。"""

        return cls(
            state_version=STATE_VERSION,
            updated_at=datetime.now(),
            completed_task_keys=frozenset(),
            failures=(),
        )

    def is_completed(
        self,
        key: HistoryTaskKey,
    ) -> bool:
        """指定チャンクが完了済みか返す。"""

        return key.value in self.completed_task_keys

    def mark_completed(
        self,
        key: HistoryTaskKey,
    ) -> HistoryImportState:
        """指定チャンクを完了済みにする。"""

        completed_keys = set(self.completed_task_keys)
        completed_keys.add(key.value)

        remaining_failures = tuple(
            failure for failure in self.failures if failure.key.value != key.value
        )

        return HistoryImportState(
            state_version=STATE_VERSION,
            updated_at=datetime.now(),
            completed_task_keys=frozenset(completed_keys),
            failures=remaining_failures,
        )

    def mark_failed(
        self,
        key: HistoryTaskKey,
        *,
        message: str,
        attempt_count: int,
    ) -> HistoryImportState:
        """指定チャンクの失敗状態を記録する。"""

        if attempt_count <= 0:
            raise ValueError("試行回数は0より大きい必要があります。")

        remaining_failures = [
            failure for failure in self.failures if failure.key.value != key.value
        ]

        remaining_failures.append(
            HistoryTaskFailureState(
                key=key,
                message=message,
                failed_at=datetime.now(),
                attempt_count=attempt_count,
            )
        )

        return HistoryImportState(
            state_version=STATE_VERSION,
            updated_at=datetime.now(),
            completed_task_keys=(self.completed_task_keys),
            failures=tuple(remaining_failures),
        )


class HistoryStateError(RuntimeError):
    """履歴取込状態ファイルの読込失敗を表す。"""


class HistoryStateRepository:
    """履歴取込状態をJSONファイルへ保存する。"""

    def __init__(
        self,
        file_path: Path,
    ) -> None:
        """状態ファイルのパスを設定する。"""

        self.file_path = file_path

    def load(self) -> HistoryImportState:
        """状態ファイルを読み込む。"""

        if not self.file_path.exists():
            return HistoryImportState.empty()

        if not self.file_path.is_file():
            raise HistoryStateError(
                f"履歴取込状態のパスがファイルではありません。 path={self.file_path}"
            )

        try:
            raw_text = self.file_path.read_text(encoding="utf-8")
            raw_state = json.loads(raw_text)

        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            raise HistoryStateError(
                f"履歴取込状態ファイルを読み込めませんでした。 path={self.file_path}"
            ) from error

        try:
            return self._deserialize(raw_state)

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise HistoryStateError(
                f"履歴取込状態ファイルの内容が不正です。 path={self.file_path}"
            ) from error

    def save(
        self,
        state: HistoryImportState,
    ) -> Path:
        """状態を安全にJSONへ保存する。"""

        self.file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.file_path.with_suffix(f"{self.file_path.suffix}.tmp")

        serialized = self._serialize(state)

        try:
            temporary_path.write_text(
                json.dumps(
                    serialized,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            os.replace(
                temporary_path,
                self.file_path,
            )

        except OSError as error:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

            raise HistoryStateError(
                f"履歴取込状態ファイルを保存できませんでした。 path={self.file_path}"
            ) from error

        return self.file_path

    def reset(self) -> None:
        """保存済みの状態ファイルを削除する。"""

        try:
            self.file_path.unlink(missing_ok=True)
        except OSError as error:
            raise HistoryStateError(
                f"履歴取込状態ファイルを削除できませんでした。 path={self.file_path}"
            ) from error

    @staticmethod
    def _serialize(
        state: HistoryImportState,
    ) -> dict[str, Any]:
        """状態をJSON互換形式へ変換する。"""

        return {
            "state_version": state.state_version,
            "updated_at": (state.updated_at.isoformat()),
            "completed_task_keys": sorted(state.completed_task_keys),
            "failures": [
                {
                    "key": {
                        "code": failure.key.code,
                        "start_date": (failure.key.start_date.isoformat()),
                        "end_date": (failure.key.end_date.isoformat()),
                    },
                    "message": failure.message,
                    "failed_at": (failure.failed_at.isoformat()),
                    "attempt_count": (failure.attempt_count),
                }
                for failure in state.failures
            ],
        }

    @staticmethod
    def _deserialize(
        raw_state: object,
    ) -> HistoryImportState:
        """JSON互換形式から状態を復元する。"""

        if not isinstance(raw_state, dict):
            raise TypeError("状態のルートは辞書形式である必要があります。")

        state_version = int(raw_state["state_version"])

        if state_version != STATE_VERSION:
            raise ValueError("未対応の状態ファイルバージョンです。")

        raw_completed_keys = raw_state["completed_task_keys"]

        if not isinstance(
            raw_completed_keys,
            list,
        ):
            raise TypeError("完了済みキーは一覧形式である必要があります。")

        raw_failures = raw_state["failures"]

        if not isinstance(raw_failures, list):
            raise TypeError("失敗情報は一覧形式である必要があります。")

        failures: list[HistoryTaskFailureState] = []

        for raw_failure in raw_failures:
            if not isinstance(
                raw_failure,
                dict,
            ):
                raise TypeError("失敗情報が辞書形式ではありません。")

            raw_key = raw_failure["key"]

            if not isinstance(raw_key, dict):
                raise TypeError("失敗キーが辞書形式ではありません。")

            failures.append(
                HistoryTaskFailureState(
                    key=HistoryTaskKey(
                        code=str(raw_key["code"]),
                        start_date=date.fromisoformat(str(raw_key["start_date"])),
                        end_date=date.fromisoformat(str(raw_key["end_date"])),
                    ),
                    message=str(raw_failure["message"]),
                    failed_at=(datetime.fromisoformat(str(raw_failure["failed_at"]))),
                    attempt_count=int(raw_failure["attempt_count"]),
                )
            )

        return HistoryImportState(
            state_version=state_version,
            updated_at=datetime.fromisoformat(str(raw_state["updated_at"])),
            completed_task_keys=frozenset(str(key) for key in raw_completed_keys),
            failures=tuple(failures),
        )
