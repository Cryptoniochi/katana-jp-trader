"""DashboardSnapshotをCLI表示用テキストへ整形する。"""

from __future__ import annotations

from app.dashboard.dashboard_models import DashboardSnapshot


class DashboardFormatter:
    """Monitoring Dashboardを人が読みやすい文字列へ変換する。"""

    def format(
        self,
        snapshot: DashboardSnapshot,
    ) -> str:
        """Dashboard Snapshotを複数行テキストへ変換する。"""

        lines = [
            "=" * 40,
            "Project KATANA Dashboard",
            "=" * 40,
            "",
        ]

        self._append_health(lines, snapshot)
        self._append_broker(lines, snapshot)
        self._append_portfolio(lines, snapshot)
        self._append_orders(lines, snapshot)
        self._append_runtime(lines, snapshot)
        self._append_live_summary(lines, snapshot)
        self._append_errors(lines, snapshot)

        lines.extend(
            [
                "",
                (
                    "Updated: "
                    f"{snapshot.generated_at.isoformat()}"
                ),
            ]
        )

        return "\n".join(lines)

    @staticmethod
    def _append_health(
        lines: list[str],
        snapshot: DashboardSnapshot,
    ) -> None:
        lines.append("System Health")
        lines.append("-" * 40)

        if snapshot.system_health is None:
            lines.append("Status : UNAVAILABLE")
            lines.append("")
            return

        health = snapshot.system_health
        lines.append(
            f"Status : {health.status.value.upper()}"
        )

        if health.reasons:
            for reason in health.reasons:
                lines.append(f"Reason : {reason}")

        lines.append("")

    @staticmethod
    def _append_broker(
        lines: list[str],
        snapshot: DashboardSnapshot,
    ) -> None:
        lines.append("Broker")
        lines.append("-" * 40)

        if snapshot.broker is None:
            lines.append("Status : UNAVAILABLE")
            lines.append("")
            return

        broker = snapshot.broker
        lines.append(f"Name   : {broker.name}")
        lines.append(
            "Status : "
            + ("CONNECTED" if broker.connected else "DISCONNECTED")
        )

        if broker.message:
            lines.append(f"Message: {broker.message}")

        lines.append("")

    @staticmethod
    def _append_portfolio(
        lines: list[str],
        snapshot: DashboardSnapshot,
    ) -> None:
        lines.append("Portfolio")
        lines.append("-" * 40)

        if snapshot.portfolio is None:
            lines.append("Status       : UNAVAILABLE")
            lines.append("")
            return

        portfolio = snapshot.portfolio
        currency = portfolio.currency
        lines.append(
            "Cash         : "
            f"{portfolio.cash_balance:,.2f} {currency}"
        )
        lines.append(
            "Buying Power : "
            f"{portfolio.buying_power:,.2f} {currency}"
        )
        lines.append(
            "Market Value : "
            f"{portfolio.total_market_value:,.2f} {currency}"
        )
        lines.append(
            "Broker Equity: "
            f"{portfolio.broker_equity:,.2f} {currency}"
        )
        lines.append(
            "Unrealized PL: "
            f"{portfolio.total_unrealized_profit_loss:,.2f} "
            f"{currency}"
        )
        lines.append(
            f"Positions    : {portfolio.position_count}"
        )
        lines.append("")

    @staticmethod
    def _append_orders(
        lines: list[str],
        snapshot: DashboardSnapshot,
    ) -> None:
        lines.append("Orders")
        lines.append("-" * 40)

        if snapshot.orders is None:
            lines.append("Status   : UNAVAILABLE")
            lines.append("")
            return

        orders = snapshot.orders
        lines.append(f"Total    : {orders.total_count}")
        lines.append(f"Active   : {orders.active_count}")
        lines.append(f"Terminal : {orders.terminal_count}")
        lines.append("")

    @staticmethod
    def _append_runtime(
        lines: list[str],
        snapshot: DashboardSnapshot,
    ) -> None:
        lines.append("Runtime Metrics")
        lines.append("-" * 40)

        if snapshot.runtime_metrics is None:
            lines.append("Status               : UNAVAILABLE")
            lines.append("")
            return

        metrics = snapshot.runtime_metrics
        lines.append(
            f"Domain Events        : "
            f"{metrics.domain_event_count}"
        )
        lines.append(
            f"Errors               : {metrics.error_count}"
        )
        lines.append(
            "Error Rate           : "
            f"{metrics.error_rate:.2%}"
        )
        lines.append(
            "Notification Fail Rate: "
            f"{metrics.notification_failure_rate:.2%}"
        )
        lines.append("")

    @staticmethod
    def _append_live_summary(
        lines: list[str],
        snapshot: DashboardSnapshot,
    ) -> None:
        lines.append("Live Summary")
        lines.append("-" * 40)

        if snapshot.live_summary is None:
            lines.append("Status     : UNAVAILABLE")
            lines.append("")
            return

        summary = snapshot.live_summary
        lines.append(
            f"Trading Date: {summary.trading_date.isoformat()}"
        )
        lines.append(f"Signals     : {summary.signal_count}")
        lines.append(f"Orders      : {summary.order_count}")
        lines.append(
            f"Executions  : {summary.execution_count}"
        )
        lines.append(f"Errors      : {summary.error_count}")
        lines.append(
            f"Critical    : {summary.critical_count}"
        )
        lines.append("")

    @staticmethod
    def _append_errors(
        lines: list[str],
        snapshot: DashboardSnapshot,
    ) -> None:
        if not snapshot.errors:
            return

        lines.append("Unavailable Components")
        lines.append("-" * 40)

        for error in snapshot.errors:
            lines.append(
                f"{error.component}: {error.error_message}"
            )
