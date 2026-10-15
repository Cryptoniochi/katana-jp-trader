from pathlib import Path


def test_concrete_live_composition_uses_existing_high_breakout_modules():
    source=Path("app/live/live_production_composition.py").read_text(encoding="utf-8")
    assert "from app.market.high_breakout_candidate_provider import (" in source
    assert "from app.strategy.high_breakout_candidate_repository import (" in source
    assert "from app.backtest.high_breakout_candidate_provider import (" not in source
    assert "from app.backtest.high_breakout_candidate_repository import (" not in source


def test_concrete_live_composition_uses_dynamic_watchlist_routing_repository():
    source=Path("app/live/live_production_composition.py").read_text(encoding="utf-8")
    assert "from app.dynamic_watchlist.strategy_routing_repository import (" in source


def test_database_is_initialized_before_live_runtime_repositories_are_built():
    source=Path("app/live/live_production_composition.py").read_text(encoding="utf-8")
    assert source.index("initialize_database(db)") < source.index("FinalLiveRuntimeFactory.create(")


def test_market_service_start_is_owned_by_application_run_not_factory():
    source=Path("app/live/live_production_composition.py").read_text(encoding="utf-8")
    run_section=source[source.index("    def run(self)->int:"):source.index("class ConcreteLiveProductionFactory")]
    factory_section=source[source.index("class ConcreteLiveProductionFactory"):]
    assert "self.market_service.start(self.registration_codes)" in run_section
    assert "market_service.start(codes)" not in factory_section
