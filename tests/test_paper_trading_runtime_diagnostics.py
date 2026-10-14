"""Runtime status diagnostics persistence tests."""

import json
from datetime import datetime, timezone

from app.application.trading_loop_models import TradingLoopCycleStatus
from app.runtime.paper_trading_runtime import PaperTradingRuntime
from app.trading.portfolio_models import PortfolioSnapshot


NOW = datetime(2026, 10, 14, 0, 15, tzinfo=timezone.utc)


class FakeCycle:
    status = TradingLoopCycleStatus.COMPLETED
    error_message = None
    signal_count = 0
    execution_count = 0

    @property
    def is_successful(self) -> bool:
        return True


class FakeCycleRunner:
    def run_cycle(self):
        return FakeCycle()


class FakePortfolioReader:
    def create_snapshot(self, *, generated_at=None) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            currency="JPY",
            cash_balance=1_000_000.0,
            buying_power=1_000_000.0,
            broker_market_value=0.0,
            broker_equity=1_000_000.0,
            positions=(),
            generated_at=generated_at,
        )


def make_runtime(tmp_path, provider=None):
    return PaperTradingRuntime(
        cycle_runner=FakeCycleRunner(),
        portfolio_reader=FakePortfolioReader(),
        status_path=tmp_path / "runtime.json",
        process_id_provider=lambda: 4321,
        now_provider=lambda: NOW,
        runtime_diagnostics_provider=provider,
    )


def read_payload(tmp_path):
    return json.loads((tmp_path / "runtime.json").read_text(encoding="utf-8"))


def test_runtime_status_persists_market_data_and_diagnostics(tmp_path) -> None:
    last_message_at = datetime(
        2026, 10, 14, 0, 14, 58, tzinfo=timezone.utc
    )

    def provider():
        return {
            "market_data": {
                "is_connected": True,
                "registered_code_count": 50,
                "registered_codes": ["7203", "6758"],
                "last_message_at": last_message_at.isoformat(),
                "last_error": None,
            },
            "diagnostics": {
                "cycle_count": 1,
                "market_decision_counts": {
                    "no_new_bar": 1,
                    "new_bars_saved": 0,
                },
                "no_new_bar_cycle_count": 1,
                "new_bars_saved_cycle_count": 0,
                "fetched_bar_count": 0,
                "new_bar_count": 0,
                "saved_bar_count": 0,
                "paper_trading_call_count": 0,
                "paper_trading_input_bar_count": 0,
            },
        }

    runtime = make_runtime(tmp_path, provider)
    runtime.start()
    runtime.run_cycle()

    payload = read_payload(tmp_path)

    assert payload["state"] == "running"
    assert payload["market_data"]["is_connected"] is True
    assert payload["market_data"]["registered_code_count"] == 50
    assert payload["market_data"]["last_message_at"] == last_message_at.isoformat()
    assert payload["market_data"]["last_error"] is None
    assert payload["diagnostics"]["cycle_count"] == 1
    assert payload["diagnostics"]["no_new_bar_cycle_count"] == 1
    assert payload["diagnostics"]["new_bars_saved_cycle_count"] == 0
    assert payload["diagnostics"]["saved_bar_count"] == 0
    assert payload["diagnostics"]["paper_trading_call_count"] == 0


def test_runtime_status_diagnostics_provider_failure_is_nonfatal(tmp_path) -> None:
    def provider():
        raise RuntimeError("diagnostics unavailable")

    runtime = make_runtime(tmp_path, provider)

    runtime.start()
    runtime.run_cycle()

    payload = read_payload(tmp_path)

    assert payload["state"] == "running"
    assert payload["cycle_count"] == 1
    assert payload["runtime_diagnostics_error"] == (
        "RuntimeError: diagnostics unavailable"
    )


def test_runtime_status_without_diagnostics_provider_is_backward_compatible(
    tmp_path,
) -> None:
    runtime = make_runtime(tmp_path)

    runtime.start()
    runtime.run_cycle()

    payload = read_payload(tmp_path)

    assert payload["state"] == "running"
    assert payload["cycle_count"] == 1
    assert "market_data" not in payload
    assert "diagnostics" not in payload
    assert "runtime_diagnostics_error" not in payload
