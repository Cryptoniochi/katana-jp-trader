"""ポートフォリオ履歴をSQLiteへ追加専用で保存する。"""

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.trading.broker_adapter import BrokerPositionSide
from app.trading.portfolio_models import (
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
)


class PortfolioRepositoryError(RuntimeError):
    """ポートフォリオRepositoryの基底例外。"""


class PortfolioSnapshotNotFoundError(PortfolioRepositoryError):
    """指定されたポートフォリオ履歴が存在しない。"""


class DuplicatePortfolioSnapshotError(PortfolioRepositoryError):
    """同じ集計日時の履歴が既に存在する。"""


class PortfolioRepository:
    """ポートフォリオ履歴を追加専用で管理する。"""

    def __init__(
        self,
        database_path: Path,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = database_path
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def save(
        self,
        snapshot: PortfolioSnapshot,
    ) -> PortfolioSnapshot:
        """ポートフォリオSnapshotを保存する。"""

        generated_at = snapshot.generated_at.astimezone(
            timezone.utc
        )
        created_at = self._current_time()

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO portfolio_snapshots (
                        generated_at,
                        currency,
                        cash_balance,
                        buying_power,
                        broker_market_value,
                        broker_equity,
                        total_acquisition_value,
                        total_market_value,
                        total_unrealized_profit_loss,
                        total_realized_profit_loss,
                        calculated_equity,
                        position_count,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        generated_at.isoformat(),
                        snapshot.currency,
                        snapshot.cash_balance,
                        snapshot.buying_power,
                        snapshot.broker_market_value,
                        snapshot.broker_equity,
                        snapshot.total_acquisition_value,
                        snapshot.total_market_value,
                        snapshot.total_unrealized_profit_loss,
                        snapshot.total_realized_profit_loss,
                        snapshot.calculated_equity,
                        snapshot.position_count,
                        created_at.isoformat(),
                    ),
                )
                snapshot_id = int(cursor.lastrowid)

                for position in snapshot.positions:
                    connection.execute(
                        """
                        INSERT INTO portfolio_snapshot_positions (
                            snapshot_id,
                            position_id,
                            code,
                            side,
                            quantity,
                            average_cost,
                            market_price,
                            realized_profit_loss,
                            acquisition_value,
                            market_value,
                            unrealized_profit_loss
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            snapshot_id,
                            position.position_id,
                            position.code,
                            position.side.value,
                            position.quantity,
                            position.average_cost,
                            position.market_price,
                            position.realized_profit_loss,
                            position.acquisition_value,
                            position.market_value,
                            position.unrealized_profit_loss,
                        ),
                    )

                connection.commit()

        except sqlite3.IntegrityError as error:
            raise DuplicatePortfolioSnapshotError(
                "同じ集計日時のポートフォリオ履歴が"
                "既に存在します。 "
                f"generated_at={generated_at.isoformat()}"
            ) from error
        except sqlite3.Error as error:
            raise PortfolioRepositoryError(
                "ポートフォリオ履歴を保存できませんでした。 "
                f"generated_at={generated_at.isoformat()}"
            ) from error

        return self.get(generated_at)

    def get(
        self,
        generated_at: datetime,
    ) -> PortfolioSnapshot:
        """集計日時に一致するSnapshotを返す。"""

        normalized = self._normalize_datetime(
            generated_at,
            "集計日時",
        )

        try:
            with self._connect() as connection:
                header = connection.execute(
                    self._select_header_sql()
                    + """
                    WHERE generated_at = ?
                    """,
                    (normalized.isoformat(),),
                ).fetchone()

                if header is None:
                    raise PortfolioSnapshotNotFoundError(
                        "指定されたポートフォリオ履歴が"
                        "存在しません。 "
                        f"generated_at={normalized.isoformat()}"
                    )

                positions = connection.execute(
                    self._select_positions_sql()
                    + """
                    WHERE snapshot_id = ?
                    ORDER BY code, side, position_id
                    """,
                    (int(header[0]),),
                ).fetchall()

        except PortfolioSnapshotNotFoundError:
            raise
        except sqlite3.Error as error:
            raise PortfolioRepositoryError(
                "ポートフォリオ履歴を読み込めませんでした。 "
                f"generated_at={normalized.isoformat()}"
            ) from error

        return self._rows_to_snapshot(
            header=header,
            position_rows=positions,
        )

    def latest(self) -> PortfolioSnapshot | None:
        """最新のポートフォリオ履歴を返す。"""

        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT generated_at
                    FROM portfolio_snapshots
                    ORDER BY generated_at DESC, id DESC
                    LIMIT 1
                    """
                ).fetchone()
        except sqlite3.Error as error:
            raise PortfolioRepositoryError(
                "最新ポートフォリオ履歴を取得できませんでした。"
            ) from error

        if row is None:
            return None

        return self.get(self._parse_datetime(str(row[0])))

    def list_recent(
        self,
        *,
        limit: int = 100,
    ) -> list[PortfolioSnapshot]:
        """ポートフォリオ履歴を新しい順に返す。"""

        if limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT generated_at
                    FROM portfolio_snapshots
                    ORDER BY generated_at DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        except sqlite3.Error as error:
            raise PortfolioRepositoryError(
                "ポートフォリオ履歴一覧を取得できませんでした。"
            ) from error

        return [
            self.get(self._parse_datetime(str(row[0])))
            for row in rows
        ]

    def count(self) -> int:
        """保存済みポートフォリオ履歴件数を返す。"""

        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT COUNT(*) FROM portfolio_snapshots"
                ).fetchone()
        except sqlite3.Error as error:
            raise PortfolioRepositoryError(
                "ポートフォリオ履歴件数を取得できませんでした。"
            ) from error

        return int(row[0]) if row is not None else 0

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _current_time(self) -> datetime:
        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)

    @staticmethod
    def _normalize_datetime(
        value: datetime,
        name: str,
    ) -> datetime:
        if value.tzinfo is None:
            raise ValueError(
                f"{name}にはタイムゾーンが必要です。"
            )

        return value.astimezone(timezone.utc)

    @staticmethod
    def _select_header_sql() -> str:
        return """
            SELECT
                id,
                generated_at,
                currency,
                cash_balance,
                buying_power,
                broker_market_value,
                broker_equity
            FROM portfolio_snapshots
        """

    @staticmethod
    def _select_positions_sql() -> str:
        return """
            SELECT
                position_id,
                code,
                side,
                quantity,
                average_cost,
                market_price,
                realized_profit_loss
            FROM portfolio_snapshot_positions
        """

    @classmethod
    def _rows_to_snapshot(
        cls,
        *,
        header: tuple[object, ...],
        position_rows: list[tuple[object, ...]],
    ) -> PortfolioSnapshot:
        positions = tuple(
            PortfolioPositionSnapshot(
                position_id=str(row[0]),
                code=str(row[1]),
                side=BrokerPositionSide(str(row[2])),
                quantity=int(row[3]),
                average_cost=float(row[4]),
                market_price=float(row[5]),
                realized_profit_loss=float(row[6]),
            )
            for row in position_rows
        )

        return PortfolioSnapshot(
            currency=str(header[2]),
            cash_balance=float(header[3]),
            buying_power=float(header[4]),
            broker_market_value=float(header[5]),
            broker_equity=float(header[6]),
            positions=positions,
            generated_at=cls._parse_datetime(str(header[1])),
        )

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)
