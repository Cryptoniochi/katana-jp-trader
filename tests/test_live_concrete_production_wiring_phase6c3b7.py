from pathlib import Path


def test_market_session_default_live_runner_is_concrete_and_not_paper():
    source = Path("app/run_market_session.py").read_text(encoding="utf-8")

    assert "from app.run_live_production import run_live_production" in source
    assert "live_trading_runner=run_live_production" in source
    assert "live_trading_runner=run_paper_trading" not in source


def test_concrete_live_composition_does_not_import_or_construct_paper_broker():
    source = Path(
        "app/live/live_production_composition.py"
    ).read_text(encoding="utf-8")

    assert "from app.paper" not in source
    assert "import PaperBroker" not in source
    assert "PaperBroker(" not in source

    assert "FinalLiveRuntimeFactory.create(" in source
    assert "LiveProductionApplicationFactory.create(" in source
    assert "LiveRealtimeSignalIntentProvider(" in source
