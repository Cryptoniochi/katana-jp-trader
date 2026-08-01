"""Daily Trading Reportの通知本文を生成する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DailyReportNotificationContent:
    """通知Gatewayへ渡す描画済み内容。"""

    title: str
    body: str
    metadata: dict[str, Any]


class DailyReportNotificationFormatter:
    """日次レポートPayloadをLINE・Discord向け本文へ変換する。"""

    def format(
        self,
        payload: dict[str, Any],
    ) -> DailyReportNotificationContent:
        """日次レポート通知を生成する。"""

        if not payload.get("available", False):
            report_date = (
                payload.get("report_date")
                or "latest"
            )
            return DailyReportNotificationContent(
                title="Project KATANA Daily Report",
                body=(
                    "Daily trading report is not available.\n\n"
                    f"Report Date\n{report_date}\n\n"
                    f"Status\n{payload.get('status', 'not_available')}\n\n"
                    f"Message\n{payload.get('message') or 'No report was generated.'}"
                ),
                metadata={
                    "event_type": "daily_report",
                    "report_date": report_date,
                    "report_status": payload.get(
                        "status",
                        "not_available",
                    ),
                    "available": False,
                },
            )

        summary = payload.get(
            "summary",
            {},
        )
        strategies = payload.get(
            "strategy_breakdown",
            [],
        )
        symbols = payload.get(
            "symbol_breakdown",
            [],
        )
        report_date = str(
            payload.get(
                "report_date",
                "unknown",
            )
        )
        status = str(
            payload.get(
                "status",
                "unknown",
            )
        )

        body_parts = [
            "━━━━━━━━━━━━━━━━━━",
            "Project KATANA",
            "Daily Trading Report",
            report_date,
            "━━━━━━━━━━━━━━━━━━",
            "",
            "Today's P/L",
            self._format_yen(
                summary.get(
                    "net_profit_loss",
                    0,
                )
            ),
            "",
            "Trades",
            str(
                summary.get(
                    "trade_count",
                    0,
                )
            ),
            "",
            "Win Rate",
            self._format_percent(
                summary.get("win_rate")
            ),
            "",
            "Profit Factor",
            self._format_number(
                summary.get("profit_factor")
            ),
            "",
            "Max Drawdown",
            self._format_optional_yen(
                summary.get(
                    "maximum_drawdown"
                )
            ),
        ]

        best_strategy = self._best_row(
            strategies
        )
        worst_strategy = self._worst_row(
            strategies
        )
        top_symbol = self._best_row(
            symbols
        )

        if best_strategy is not None:
            body_parts.extend(
                [
                    "",
                    "Best Strategy",
                    str(
                        best_strategy.get(
                            "label",
                            best_strategy.get(
                                "key",
                                "—",
                            ),
                        )
                    ),
                    self._format_yen(
                        best_strategy.get(
                            "net_profit_loss",
                            0,
                        )
                    ),
                ]
            )

        if worst_strategy is not None:
            body_parts.extend(
                [
                    "",
                    "Worst Strategy",
                    str(
                        worst_strategy.get(
                            "label",
                            worst_strategy.get(
                                "key",
                                "—",
                            ),
                        )
                    ),
                    self._format_yen(
                        worst_strategy.get(
                            "net_profit_loss",
                            0,
                        )
                    ),
                ]
            )

        if top_symbol is not None:
            body_parts.extend(
                [
                    "",
                    "Top Symbol",
                    str(
                        top_symbol.get(
                            "label",
                            top_symbol.get(
                                "key",
                                "—",
                            ),
                        )
                    ),
                    self._format_yen(
                        top_symbol.get(
                            "net_profit_loss",
                            0,
                        )
                    ),
                ]
            )

        body_parts.extend(
            [
                "",
                "Errors",
                str(
                    payload.get(
                        "error_count",
                        0,
                    )
                ),
                "",
                "Recoveries",
                str(
                    payload.get(
                        "recovery_count",
                        0,
                    )
                ),
            ]
        )

        notes = [
            str(note).strip()
            for note in payload.get(
                "notes",
                [],
            )
            if str(note).strip()
        ]

        if notes:
            body_parts.extend(
                [
                    "",
                    "Notes",
                    "\n".join(
                        f"- {note}"
                        for note in notes
                    ),
                ]
            )

        return DailyReportNotificationContent(
            title=(
                "Project KATANA Daily Report "
                f"{report_date}"
            ),
            body="\n".join(body_parts),
            metadata={
                "event_type": "daily_report",
                "report_date": report_date,
                "report_status": status,
                "available": True,
                "trade_count": int(
                    summary.get(
                        "trade_count",
                        0,
                    )
                ),
                "net_profit_loss": float(
                    summary.get(
                        "net_profit_loss",
                        0,
                    )
                ),
                "error_count": int(
                    payload.get(
                        "error_count",
                        0,
                    )
                ),
                "recovery_count": int(
                    payload.get(
                        "recovery_count",
                        0,
                    )
                ),
            },
        )

    @staticmethod
    def _format_yen(
        value: object,
    ) -> str:
        amount = float(
            value or 0
        )
        sign = "+" if amount > 0 else ""
        return (
            f"{sign}{amount:,.0f}円"
        )

    @classmethod
    def _format_optional_yen(
        cls,
        value: object,
    ) -> str:
        if value is None:
            return "—"

        return cls._format_yen(value)

    @staticmethod
    def _format_percent(
        value: object,
    ) -> str:
        if value is None:
            return "—"

        return (
            f"{float(value) * 100:.1f}%"
        )

    @staticmethod
    def _format_number(
        value: object,
    ) -> str:
        if value is None:
            return "—"

        return f"{float(value):.2f}"

    @staticmethod
    def _best_row(
        rows: object,
    ) -> dict[str, Any] | None:
        normalized = [
            row
            for row in rows
            if isinstance(row, dict)
        ]

        if not normalized:
            return None

        return max(
            normalized,
            key=lambda row: float(
                row.get(
                    "net_profit_loss",
                    0,
                )
            ),
        )

    @staticmethod
    def _worst_row(
        rows: object,
    ) -> dict[str, Any] | None:
        normalized = [
            row
            for row in rows
            if isinstance(row, dict)
        ]

        if not normalized:
            return None

        return min(
            normalized,
            key=lambda row: float(
                row.get(
                    "net_profit_loss",
                    0,
                )
            ),
        )
