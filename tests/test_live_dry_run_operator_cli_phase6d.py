from argparse import Namespace
from pathlib import Path

import pytest

from app.run_live_dry_run_operator import OPERATOR_CONFIRMATION, validate_operator_arguments


def _args(**overrides):
    values = dict(
        confirm=OPERATOR_CONFIRMATION,
        trading_date="2026-10-05",
        live_confirmation="KATANA-LIVE-2026-10-05",
        database_path="data/live_dry_run.db",
        report_path="reports/live/live_dry_run_audit.json",
    )
    values.update(overrides)
    return Namespace(**values)


def test_cli_requires_exact_operator_confirmation():
    with pytest.raises(SystemExit):
        validate_operator_arguments(_args(confirm="YES"))


def test_cli_requires_exact_daily_authorization():
    with pytest.raises(SystemExit):
        validate_operator_arguments(_args(live_confirmation="KATANA-LIVE-2026-10-04"))


def test_cli_rejects_production_database():
    with pytest.raises(SystemExit):
        validate_operator_arguments(_args(database_path="data/katana.db"))


def test_cli_accepts_isolated_arguments():
    assert validate_operator_arguments(_args()).isoformat() == "2026-10-05"


def test_cli_has_no_network_or_real_submit_primitives():
    source = Path("app/run_live_dry_run_operator.py").read_text(encoding="utf-8").lower()
    forbidden = (
        "requests.", "httpx.", "urllib.", "kabustationclient", "brokeradapter",
        "sendorder", "send_order", ".post(", ".put(", ".request(", "mark_submitted",
    )
    for token in forbidden:
        assert token not in source
