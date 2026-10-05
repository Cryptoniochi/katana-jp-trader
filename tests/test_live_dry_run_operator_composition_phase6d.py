from pathlib import Path

import pytest

from app.live.live_dry_run_operator_composition import LiveDryRunOperatorPaths
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.locked_live_runtime_integration import LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED


def test_operator_paths_are_isolated():
    paths = LiveDryRunOperatorPaths()
    assert paths.database_path == Path("data/live_dry_run.db")
    assert paths.database_path != Path("data/katana.db")
    assert paths.report_path == Path("reports/live/live_dry_run_audit.json")


def test_operator_paths_reject_production_database():
    with pytest.raises(ValueError):
        LiveDryRunOperatorPaths(database_path=Path("data/katana.db"))


def test_existing_hard_live_locks_remain_false():
    assert LIVE_BROKER_TRANSPORT_ENABLED is False
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_operator_composition_has_no_network_or_real_submit_primitives():
    source = Path("app/live/live_dry_run_operator_composition.py").read_text(encoding="utf-8").lower()
    forbidden = (
        "requests.", "httpx.", "urllib.", "kabustationclient", "brokeradapter",
        "sendorder", "send_order", ".post(", ".put(", ".request(", "mark_submitted",
    )
    for token in forbidden:
        assert token not in source
