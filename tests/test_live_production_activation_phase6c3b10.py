from pathlib import Path

from app.live.live_production_activation_interlock import (
    LIVE_PRODUCTION_ENABLE_VARIABLE,
    LiveProductionActivationInterlock,
)


def test_production_activation_variable_name_is_stable():
    assert LIVE_PRODUCTION_ENABLE_VARIABLE == "KATANA_LIVE_PRODUCTION_ENABLED"


def test_lowercase_yes_is_normalized_but_other_truthy_values_are_not():
    assert LiveProductionActivationInterlock.state(
        {LIVE_PRODUCTION_ENABLE_VARIABLE: " yes "}
    ).released is True
    assert LiveProductionActivationInterlock.state(
        {LIVE_PRODUCTION_ENABLE_VARIABLE: "true"}
    ).released is False


def test_concrete_composition_does_not_hardcode_activated_transport_true():
    source = Path(
        "app/live/live_production_composition.py"
    ).read_text(encoding="utf-8")

    assert "activation_enabled=True" not in source
    assert "runtime_armed=True" not in source
    assert "activation_enabled=production_activation_enabled" in source
    assert "runtime_armed=runtime_armed" in source


def test_live_cli_passes_production_and_daily_arm_gates_separately():
    source = Path("app/run_live_production.py").read_text(encoding="utf-8")

    assert "production_activation_enabled=(" in source
    assert "activation_state.production_activation_enabled" in source
    assert "runtime_armed=bool(settings.live_armed)" in source
