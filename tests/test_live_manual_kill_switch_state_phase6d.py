"""Phase 6-D Step 4A durable manual Kill Switch tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.live.live_manual_kill_switch_state import (
    MANUAL_KILL_SWITCH_SCHEMA_VERSION,
)
from app.live.live_manual_kill_switch_state_reader import (
    ManualKillSwitchStateReader,
)
from app.live.live_manual_kill_switch_state_writer import (
    ManualKillSwitchStateWriter,
)


NOW = datetime(2026, 10, 5, 5, 0, tzinfo=timezone.utc)


def test_missing_state_fails_closed(tmp_path):
    reader = ManualKillSwitchStateReader(tmp_path / "missing.json")

    state = reader.read_state()

    assert state.manual_blocked is True
    assert state.reason == "manual_kill_switch_state_unavailable"
    assert reader.manual_blocked() is True


@pytest.mark.parametrize(
    "raw",
    (
        "{",
        "[]",
        '{"schema_version":1}',
        '{"schema_version":999,"manual_blocked":false,'
        '"updated_at":"2026-10-05T05:00:00+00:00","reason":"release"}',
        '{"schema_version":1,"manual_blocked":"false",'
        '"updated_at":"2026-10-05T05:00:00+00:00","reason":"release"}',
    ),
)
def test_invalid_state_fails_closed(tmp_path, raw):
    path = tmp_path / "manual-kill-switch.json"
    path.write_text(raw, encoding="utf-8")

    assert ManualKillSwitchStateReader(path).manual_blocked() is True


def test_engage_persists_blocked_state(tmp_path):
    path = tmp_path / "manual-kill-switch.json"
    writer = ManualKillSwitchStateWriter(
        path,
        now_provider=lambda: NOW,
    )

    state = writer.engage(reason="operator emergency stop")
    loaded = ManualKillSwitchStateReader(path).read_state()

    assert state.manual_blocked is True
    assert loaded == state

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == MANUAL_KILL_SWITCH_SCHEMA_VERSION
    assert payload["manual_blocked"] is True


def test_release_requires_explicit_write_and_persists_unblocked_state(tmp_path):
    path = tmp_path / "manual-kill-switch.json"
    writer = ManualKillSwitchStateWriter(
        path,
        now_provider=lambda: NOW,
    )

    writer.engage()
    released = writer.release(reason="operator verified safe")
    loaded = ManualKillSwitchStateReader(path).read_state()

    assert released.manual_blocked is False
    assert loaded.manual_blocked is False
    assert loaded.reason == "operator verified safe"


def test_reader_is_read_only(tmp_path):
    path = tmp_path / "manual-kill-switch.json"
    reader = ManualKillSwitchStateReader(path)

    assert reader.manual_blocked() is True
    assert not path.exists()


def test_writer_rejects_naive_time(tmp_path):
    writer = ManualKillSwitchStateWriter(
        tmp_path / "manual-kill-switch.json",
        now_provider=lambda: datetime(2026, 10, 5, 5, 0),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        writer.engage()


def test_writer_rejects_blank_reason(tmp_path):
    writer = ManualKillSwitchStateWriter(
        tmp_path / "manual-kill-switch.json",
        now_provider=lambda: NOW,
    )

    with pytest.raises(ValueError, match="reason must not be empty"):
        writer.engage(reason="   ")
