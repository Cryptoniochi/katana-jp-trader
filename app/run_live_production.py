"""Concrete CLI seam for the reviewed Live production composition."""
from __future__ import annotations

from app.live.execution_mode import LiveTradingUnavailableError
from app.live.live_production_activation_interlock import (
    LiveProductionActivationInterlock,
)
from app.live.live_production_composition import ConcreteLiveProductionFactory
from app.run_paper_trading import (
    build_argument_parser as build_trading_argument_parser,
    create_production_settings,
    load_runtime_environment,
)


def run_live_production(
    application_arguments,
    *,
    settings,
    trading_date,
    environ,
    output,
    error_output,
):
    """Run concrete Live only after explicit production activation."""
    environment = (
        load_runtime_environment()
        if environ is None
        else dict(environ)
    )

    try:
        activation_state = LiveProductionActivationInterlock.require_released(
            environment
        )
    except RuntimeError as error:
        raise LiveTradingUnavailableError(str(error)) from error

    parser = build_trading_argument_parser()
    arguments = parser.parse_args(application_arguments)
    production_settings = create_production_settings(
        arguments,
        environ=environment,
    )
    app = ConcreteLiveProductionFactory.create(
        production_settings=production_settings,
        execution_settings=settings,
        trading_date=trading_date,
        environment=environment,
        production_activation_enabled=(
            activation_state.production_activation_enabled
        ),
        runtime_armed=bool(settings.live_armed),
    )
    print("Concrete Live production runtime started.", file=output)
    return app.run()
