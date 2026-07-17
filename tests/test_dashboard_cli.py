"""Dashboard CLIのテスト。"""

from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from app.dashboard.dashboard_cli import (
    build_parser,
    run_dashboard_cli,
)
from app.dashboard.dashboard_models import (
    DashboardBrokerStatus,
    DashboardComponentError,
    DashboardSnapshot,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeProvider:
    def __init__(
        self,
        dashboard_snapshot: DashboardSnapshot,
    ) -> None:
        self.dashboard_snapshot = dashboard_snapshot
        self.call_count = 0

    def create_snapshot(self) -> DashboardSnapshot:
        self.call_count += 1
        return self.dashboard_snapshot


def snapshot(
    *,
    partial: bool = False,
) -> DashboardSnapshot:
    return DashboardSnapshot(
        generated_at=NOW,
        system_health=None,
        runtime_metrics=None,
        portfolio=None,
        orders=None,
        live_summary=None,
        broker=DashboardBrokerStatus(
            connected=True,
            name="paper",
        ),
        errors=(
            (
                DashboardComponentError(
                    component="portfolio",
                    error_message="portfolio failed",
                ),
            )
            if partial
            else ()
        ),
    )


def test_parser_accepts_dashboard_options() -> None:
    args = build_parser().parse_args(
        [
            "--json-output",
            "reports/dashboard",
            "--no-history",
            "--json-only",
            "--fail-on-partial",
        ]
    )

    assert args.json_output == Path(
        "reports/dashboard"
    )
    assert args.no_history
    assert args.json_only
    assert args.fail_on_partial


def test_cli_prints_dashboard_text() -> None:
    provider = FakeProvider(snapshot())
    output = StringIO()
    error_output = StringIO()

    result = run_dashboard_cli(
        provider=provider,
        argv=[],
        output=output,
        error_output=error_output,
    )

    assert result.exit_code == 0
    assert result.export_result is None
    assert provider.call_count == 1
    assert "Project KATANA Dashboard" in (
        output.getvalue()
    )
    assert error_output.getvalue() == ""


def test_cli_exports_json_without_text(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(snapshot())
    output = StringIO()
    error_output = StringIO()

    result = run_dashboard_cli(
        provider=provider,
        argv=[
            "--json-output",
            str(tmp_path),
            "--no-history",
            "--json-only",
        ],
        output=output,
        error_output=error_output,
    )

    assert result.exit_code == 0
    assert result.export_result is not None
    assert (
        result.export_result.latest_path
        == tmp_path / "dashboard.json"
    )
    assert result.export_result.history_path is None
    assert output.getvalue() == ""
    assert error_output.getvalue() == ""


def test_cli_can_fail_on_partial_snapshot() -> None:
    provider = FakeProvider(
        snapshot(partial=True)
    )
    output = StringIO()
    error_output = StringIO()

    result = run_dashboard_cli(
        provider=provider,
        argv=["--fail-on-partial"],
        output=output,
        error_output=error_output,
    )

    assert result.exit_code == 2
    assert "Unavailable Components" in (
        output.getvalue()
    )
