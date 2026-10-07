"""Phase 6-E Step 6: final Live activation safety audit.

This audit closes Phase 6-E without enabling Live trading. It verifies the
authorization/review/E2E boundaries remain review-only and that every hard
Live execution lock is still closed.
"""

from __future__ import annotations

import inspect

import app.live.live_activation_authorization as authorization_module
import app.live.live_activation_authorization_composition as composition_module
import app.live.live_activation_e2e_composition as e2e_module
import app.live.live_activation_operator_review as review_module
import app.run_live_activation_review as cli_module
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)


def _source(obj) -> str:
    return inspect.getsource(obj).lower()


def test_phase6e_final_audit_all_hard_live_locks_are_closed():
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_authorization_gate_explicitly_requires_closed_hard_locks():
    source = _source(authorization_module.LiveActivationAuthorizationGate)
    assert "live_order_transmission_enabled is false" in source
    assert "live_broker_transport_enabled is false" in source
    assert "locked_live_runtime_integration_enabled is false" in source


def test_authorization_composition_is_provider_only():
    source = _source(
        composition_module.ProductionLiveActivationAuthorizationFactory
    )
    forbidden = (
        ".start(",
        ".run(",
        ".recover(",
        ".release(",
        "sendorder",
        "submit_order(",
        "runtime_armed",
    )
    assert all(token not in source for token in forbidden)


def test_operator_review_is_render_and_evaluate_only():
    source = _source(review_module.LiveActivationOperatorReview)
    assert "gate.check()" in source
    forbidden = (
        ".start(",
        ".recover(",
        ".release(",
        "sendorder",
        "submit_order(",
        "runtime_armed",
    )
    assert all(token not in source for token in forbidden)


def test_operator_notice_says_ready_does_not_enable_live_execution():
    source = inspect.getsource(
        review_module.LiveActivationOperatorReview.to_dict
    )
    assert "AUTHORIZATION_READY does not enable" in source
    assert "Live runtime integration" in source
    assert "broker transport" in source
    assert "order transmission" in source


def test_operator_cli_has_no_production_activation_composition_root():
    source = _source(cli_module)
    assert "production composition is intentionally not attached yet" in source
    forbidden = (
        "papertradingcomposition.create",
        ".recover(",
        ".release(",
        "sendorder",
        "submit_order(",
        "runtime_armed = true",
    )
    assert all(token not in source for token in forbidden)


def test_e2e_factory_stops_at_operator_review_boundary():
    source = _source(e2e_module.ProductionLiveActivationE2EFactory)
    assert "liveactivationoperatorreview" in source
    forbidden = (
        ".start(",
        ".run(",
        ".recover(",
        ".release(",
        "sendorder",
        "submit_order(",
        "runtime_armed",
    )
    assert all(token not in source for token in forbidden)


def test_phase6e_modules_do_not_import_live_execution_transport_objects():
    modules = (
        authorization_module,
        composition_module,
        review_module,
        cli_module,
        e2e_module,
    )
    forbidden = (
        "LockedLiveRuntimeFactory",
        "FreshLockedLiveRuntimeFactory",
        "LockedLiveBrokerTransport",
        "LockedLiveSubmissionCoordinator",
        "LockedLiveSubmissionBoundary",
        "LiveExecutionClaimGate",
        "SQLiteLiveExecutionJournal",
        "SQLiteLiveOrderIdempotencyStore",
        "KabuStationClient",
        "KabuStationReadOnlyService",
    )
    for module in modules:
        source = inspect.getsource(module)
        for token in forbidden:
            assert token not in source


def test_phase6e_modules_expose_no_unlock_or_order_submission_api():
    classes = (
        authorization_module.LiveActivationAuthorizationGate,
        composition_module.ProductionLiveActivationAuthorizationFactory,
        review_module.LiveActivationOperatorReview,
        e2e_module.ProductionLiveActivationE2EFactory,
        e2e_module.ProductionLiveActivationE2EReview,
    )
    forbidden = {
        "unlock",
        "arm",
        "release",
        "recover",
        "start",
        "run",
        "execute",
        "send",
        "send_order",
        "sendorder",
        "submit",
        "submit_order",
        "transmit",
    }
    for cls in classes:
        assert forbidden.isdisjoint(dir(cls))


def test_phase6e_final_audit_targets_production_modules_only():
    audited_modules = (
        authorization_module,
        composition_module,
        review_module,
        cli_module,
        e2e_module,
    )
    for module in audited_modules:
        assert module.__name__.startswith("app.")
        assert not module.__name__.startswith("tests.")
