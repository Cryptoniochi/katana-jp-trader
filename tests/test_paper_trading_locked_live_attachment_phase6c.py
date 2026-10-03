"""Phase 6-C locked-live Paper runtime attachment regression tests.

Step 4C-3 supersedes the Step 4C-2 ``None`` attachment with a deliberately
disabled integration instance.  The Paper runtime must still never start,
process, or otherwise activate live execution.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import fields
from pathlib import Path

import app.runtime.paper_trading_composition as composition_module
from app.live.locked_live_runtime_integration import LockedLiveRuntimeIntegration
from app.runtime.paper_trading_composition import (
    PaperTradingComposition,
    PaperTradingProductionBundle,
)


def _source() -> str:
    return inspect.getsource(composition_module)


def test_production_bundle_exposes_optional_locked_live_integration_slot():
    bundle_fields = {field.name: field for field in fields(PaperTradingProductionBundle)}

    assert "locked_live_runtime_integration" in bundle_fields
    assert bundle_fields["locked_live_runtime_integration"].default is None


def test_paper_composition_does_not_directly_construct_locked_live_integration():
    tree = ast.parse(_source())

    constructor_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "LockedLiveRuntimeIntegration"
    ]

    assert constructor_calls == []


def test_paper_composition_does_not_call_locked_live_process():
    tree = ast.parse(_source())

    process_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "process"
    ]

    assert process_calls == []


def test_paper_bundle_run_does_not_reference_locked_live_integration():
    source = inspect.getsource(PaperTradingProductionBundle.run)

    assert "locked_live_runtime_integration" not in source
    assert ".process(" not in source


def test_paper_composition_create_attaches_disabled_integration_in_source():
    source = inspect.getsource(PaperTradingComposition.create)

    assert "disabled_state_connected_attachment(" in source
    assert "LockedLiveRuntimeIntegration.disabled_attachment(" not in source
    assert "locked_live_runtime_integration=None" not in source
    assert "locked_live_runtime_integration=(" in source
    assert ".process(" not in source


def test_paper_composition_has_no_live_runtime_enable_setting():
    source = inspect.getsource(composition_module.PaperTradingProductionSettings)

    assert "locked_live_runtime_enabled" not in source
    assert "live_runtime_enabled" not in source
    assert "live_order_enabled" not in source


def test_attachment_does_not_add_live_database_or_journal_construction():
    source = _source()

    forbidden = (
        "SQLiteLiveExecutionJournal(",
        "SQLiteLiveOrderIdempotencyStore(",
        "FreshLockedLiveRuntimeFactory.create(",
    )

    for expression in forbidden:
        assert expression not in source


def test_attachment_does_not_add_live_transport_or_submission_construction():
    source = _source()

    forbidden = (
        "LockedLiveBrokerTransport(",
        "LockedLiveSubmissionCoordinator(",
        "LockedLiveSubmissionBoundary(",
        "LiveExecutionClaimGate(",
    )

    for expression in forbidden:
        assert expression not in source


def test_bundle_annotation_resolves_to_locked_live_integration():
    annotations = inspect.get_annotations(
        PaperTradingProductionBundle,
        eval_str=True,
    )

    annotation = annotations["locked_live_runtime_integration"]
    assert LockedLiveRuntimeIntegration in getattr(annotation, "__args__", ())
