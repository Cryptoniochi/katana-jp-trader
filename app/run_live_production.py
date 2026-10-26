"""Concrete CLI seam for the reviewed Live production composition."""
from __future__ import annotations

from app.live.execution_mode import LiveTradingUnavailableError
from app.live.live_production_activation_interlock import (
    LiveProductionActivationInterlock,
)
from app.live.live_production_composition import ConcreteLiveProductionFactory
from app.notifications.notification_models import NotificationSeverity
from app.run_paper_trading import (
    _send_runtime_notification,
    build_argument_parser as build_trading_argument_parser,
    create_production_settings,
    create_runtime_notification_gateway,
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

    try:
        gateway = create_runtime_notification_gateway(environment)
    except Exception as error:
        print(
            "Live runtime notification initialization failed. "
            f"error={error}",
            file=error_output,
        )
        gateway = None

    print("Concrete Live production runtime started.", file=output)
    _send_runtime_notification(
        gateway,
        title="Live Trading Started",
        message=(
            "Project KATANA Live Trading has started.\n"
            f"Trading date: {trading_date.isoformat()}\n"
            "Execution mode: live"
        ),
        severity=NotificationSeverity.INFO,
        event_type="live_trading_started",
        error_output=error_output,
    )

    try:
        exit_code = int(app.run())
    except Exception as error:
        _send_runtime_notification(
            gateway,
            title="Live Trading Failed",
            message=(
                "Project KATANA Live Trading terminated with an exception.\n"
                f"Trading date: {trading_date.isoformat()}\n"
                f"Exception: {type(error).__name__}\n"
                f"Detail: {error}"
            ),
            severity=NotificationSeverity.CRITICAL,
            event_type="live_trading_failed",
            error_output=error_output,
        )
        raise

    _send_runtime_notification(
        gateway,
        title=(
            "Live Trading Finished"
            if exit_code == 0
            else "Live Trading Stopped"
        ),
        message=(
            "Project KATANA Live Trading has ended.\n"
            f"Trading date: {trading_date.isoformat()}\n"
            f"Exit code: {exit_code}"
        ),
        severity=(
            NotificationSeverity.INFO
            if exit_code == 0
            else NotificationSeverity.ERROR
        ),
        event_type=(
            "live_trading_finished"
            if exit_code == 0
            else "live_trading_stopped"
        ),
        error_output=error_output,
    )
    return exit_code
