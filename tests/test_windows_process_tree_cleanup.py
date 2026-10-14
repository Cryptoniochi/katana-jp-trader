"""Regression tests for Windows descendant-process cleanup."""

from __future__ import annotations

import subprocess

import app.runtime.katana_service_manager as service_manager


class FakeProcess:
    def __init__(self, *, pid: int = 1234) -> None:
        self.pid = pid
        self.returncode = None
        self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("fake", timeout)
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9


class Completed:
    returncode = 0


def test_windows_tree_cleanup_uses_taskkill_tree_then_force(monkeypatch):
    process = FakeProcess(pid=4321)
    calls = []

    monkeypatch.setattr(service_manager.os, "name", "nt")
    monkeypatch.setattr(
        service_manager.subprocess,
        "run",
        lambda command, **kwargs: (
            calls.append((command, kwargs)) or Completed()
        ),
    )

    # Simulate graceful taskkill not updating the mocked Popen handle,
    # then forced taskkill completing it.
    original_wait = process.wait
    wait_count = {"value": 0}

    def wait(timeout=None):
        wait_count["value"] += 1
        if wait_count["value"] == 2:
            process.returncode = 1
        return original_wait(timeout=timeout)

    process.wait = wait

    service_manager._terminate_process_tree(
        process,
        timeout_seconds=1.0,
    )

    assert calls[0][0] == [
        "taskkill", "/PID", "4321", "/T"
    ]
    assert calls[1][0] == [
        "taskkill", "/PID", "4321", "/T", "/F"
    ]
    assert process.killed is False


def test_non_windows_cleanup_preserves_terminate_wait_behavior(monkeypatch):
    process = FakeProcess()

    monkeypatch.setattr(service_manager.os, "name", "posix")

    service_manager._terminate_process_tree(
        process,
        timeout_seconds=1.0,
    )

    assert process.returncode == 0
    assert process.killed is False


def test_windows_tree_cleanup_accepts_zero_timeout(monkeypatch):
    process = FakeProcess(pid=9876)
    calls = []

    monkeypatch.setattr(service_manager.os, "name", "nt")

    def run(command, **kwargs):
        calls.append((command, kwargs))
        process.returncode = 0
        return Completed()

    monkeypatch.setattr(
        service_manager.subprocess,
        "run",
        run,
    )

    service_manager._terminate_process_tree(
        process,
        timeout_seconds=0.0,
    )

    assert calls[0][0] == [
        "taskkill", "/PID", "9876", "/T"
    ]
    assert calls[0][1]["timeout"] > 0.0
    assert process.returncode == 0
