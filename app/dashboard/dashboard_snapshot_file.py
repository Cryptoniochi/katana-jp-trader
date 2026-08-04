"""Dashboard SnapshotをJSONとSQLiteからRead-onlyで構築する。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.trading.portfolio_repository import PortfolioRepository


class DashboardJsonSnapshotReader:
    """Dashboard JSONファイルをWeb表示用に提供する。"""

    def __init__(
        self,
        *,
        snapshot_path: Path,
        now_provider=None,
    ) -> None:
        self.snapshot_path = Path(snapshot_path)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def create_snapshot(self) -> dict[str, Any]:
        if not self.snapshot_path.exists():
            return self._unavailable_snapshot(
                "Dashboard JSONがまだ生成されていません。 "
                f"path={self.snapshot_path}"
            )

        try:
            raw = self.snapshot_path.read_text(
                encoding="utf-8"
            )
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError) as error:
            return self._unavailable_snapshot(
                "Dashboard JSONを読み込めませんでした。 "
                f"error={str(error).strip() or type(error).__name__}"
            )

        if not isinstance(payload, dict):
            return self._unavailable_snapshot(
                "Dashboard JSONのルートは辞書形式である必要があります。"
            )

        return self._normalize_snapshot(payload)

    def _normalize_snapshot(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(payload)
        normalized.setdefault(
            "generated_at",
            self._current_time().isoformat(),
        )
        normalized.setdefault("complete", False)
        normalized.setdefault("partial", True)
        normalized.setdefault("errors", [])
        normalized.setdefault("system_health", None)
        normalized.setdefault("runtime_metrics", None)
        normalized.setdefault("runtime_resource", None)
        normalized.setdefault("portfolio", None)
        normalized.setdefault("orders", None)
        normalized.setdefault("live_summary", None)
        normalized.setdefault("broker", None)
        return normalized

    def _unavailable_snapshot(
        self,
        message: str,
    ) -> dict[str, Any]:
        return {
            "generated_at": self._current_time().isoformat(),
            "complete": False,
            "partial": True,
            "errors": [
                {
                    "component": "dashboard_snapshot_file",
                    "error_message": message,
                }
            ],
            "system_health": None,
            "runtime_metrics": None,
            "runtime_resource": None,
            "portfolio": None,
            "orders": None,
            "live_summary": None,
            "broker": None,
        }

    def _current_time(self) -> datetime:
        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)


class DashboardSqliteSnapshotReader(DashboardJsonSnapshotReader):
    """JSONへSQLiteの最新Portfolioを上書きして返す。"""

    def __init__(
        self,
        *,
        database_path: Path,
        snapshot_path: Path,
        now_provider=None,
    ) -> None:
        super().__init__(
            snapshot_path=snapshot_path,
            now_provider=now_provider,
        )
        self.database_path = Path(database_path)
        self.portfolio_repository = PortfolioRepository(
            self.database_path,
            now_provider=self.now_provider,
        )

    def create_snapshot(self) -> dict[str, Any]:
        payload = super().create_snapshot()
        errors = list(payload.get("errors") or [])

        try:
            portfolio = self.portfolio_repository.latest()
        except Exception as error:
            errors.append(
                {
                    "component": "portfolio_database",
                    "error_message": (
                        str(error).strip()
                        or type(error).__name__
                    ),
                }
            )
            payload["errors"] = errors
            payload["partial"] = True
            return payload

        if portfolio is None:
            payload["portfolio"] = self._empty_portfolio()
        else:
            payload["portfolio"] = self._portfolio_to_dict(
                portfolio
            )

        payload["generated_at"] = self._current_time().isoformat()
        payload["errors"] = errors
        return payload

    @staticmethod
    def _empty_portfolio() -> dict[str, Any]:
        return {
            "currency": "JPY",
            "cash_balance": 0.0,
            "buying_power": 0.0,
            "broker_market_value": 0.0,
            "broker_equity": 0.0,
            "total_acquisition_value": 0.0,
            "total_market_value": 0.0,
            "total_unrealized_profit_loss": 0.0,
            "total_realized_profit_loss": 0.0,
            "calculated_equity": 0.0,
            "position_count": 0,
            "positions": [],
            "generated_at": None,
        }

    @staticmethod
    def _portfolio_to_dict(portfolio) -> dict[str, Any]:
        return {
            "currency": portfolio.currency,
            "cash_balance": portfolio.cash_balance,
            "buying_power": portfolio.buying_power,
            "broker_market_value": (
                portfolio.broker_market_value
            ),
            "broker_equity": portfolio.broker_equity,
            "total_acquisition_value": (
                portfolio.total_acquisition_value
            ),
            "total_market_value": (
                portfolio.total_market_value
            ),
            "total_unrealized_profit_loss": (
                portfolio.total_unrealized_profit_loss
            ),
            "total_realized_profit_loss": (
                portfolio.total_realized_profit_loss
            ),
            "calculated_equity": (
                portfolio.calculated_equity
            ),
            "position_count": portfolio.position_count,
            "positions": [
                {
                    "position_id": position.position_id,
                    "code": position.code,
                    "side": position.side.value,
                    "quantity": position.quantity,
                    "average_cost": position.average_cost,
                    "market_price": position.market_price,
                    "realized_profit_loss": (
                        position.realized_profit_loss
                    ),
                    "acquisition_value": (
                        position.acquisition_value
                    ),
                    "market_value": position.market_value,
                    "unrealized_profit_loss": (
                        position.unrealized_profit_loss
                    ),
                }
                for position in portfolio.positions
            ],
            "generated_at": (
                portfolio.generated_at.isoformat()
            ),
        }
