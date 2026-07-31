"""古いProject KATANA Paper Trading検証を監査・停止・隔離する。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


OLD_MARKERS = (
    "previous-day-replay",
    "jquants-current-day",
    "run_katana_full_session",
    "run_kabu_station_30_symbols_full",
    "run_paper_trading",
    "paper_trading",
)

SAFE_CURRENT_MARKERS = (
    "kabu-station-realtime",
    "run_katana_risk_validation",
    "run_risk_gate_proof",
)

ARTIFACT_PATTERNS = (
    "data/*validation*.db",
    "data/*replay*.db",
    "logs/sprint91/*.log",
    "run_kabu_station_30_symbols.ps1",
    "run_kabu_station_30_symbols_short.cmd",
    "run_kabu_station_30_symbols_full.cmd",
    "run_katana_short_session.cmd",
    "run_katana_full_session.cmd",
)


@dataclass(frozen=True, slots=True)
class ScheduledTaskMatch:
    task_name: str
    task_path: str
    state: str
    actions: tuple[str, ...]
    old_markers: tuple[str, ...]
    safe_current_markers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProcessMatch:
    process_id: int
    name: str
    command_line: str
    old_markers: tuple[str, ...]
    safe_current_markers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArtifactMatch:
    path: str
    size_bytes: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(
            "reports/old_paper_validation_audit.json"
        ),
    )
    parser.add_argument("--disable-old-tasks", action="store_true")
    parser.add_argument("--stop-old-processes", action="store_true")
    parser.add_argument("--archive-old-artifacts", action="store_true")
    parser.add_argument(
        "--include-current-realtime",
        action="store_true",
    )
    return parser.parse_args()


def run_powershell(script: str) -> Any:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr.strip()
            or completed.stdout.strip()
            or "PowerShell command failed."
        )

    text = completed.stdout.strip()
    if not text:
        return []

    return json.loads(text)


def find_markers(
    text: str,
    markers: tuple[str, ...],
) -> tuple[str, ...]:
    lowered = text.lower()
    return tuple(
        marker
        for marker in markers
        if marker.lower() in lowered
    )


def load_tasks() -> list[ScheduledTaskMatch]:
    script = r"""
$items = Get-ScheduledTask | ForEach-Object {
    $actions = @(
        $_.Actions | ForEach-Object {
            ("{0} {1} {2}" -f $_.Execute, $_.Arguments, $_.WorkingDirectory).Trim()
        }
    )
    [PSCustomObject]@{
        TaskName = $_.TaskName
        TaskPath = $_.TaskPath
        State = [string]$_.State
        Actions = $actions
    }
}
$items | ConvertTo-Json -Depth 5 -Compress
"""
    raw = run_powershell(script)
    if isinstance(raw, dict):
        raw = [raw]

    matches: list[ScheduledTaskMatch] = []
    for item in raw:
        actions = tuple(item.get("Actions") or ())
        combined = " ".join(actions)
        old = find_markers(combined, OLD_MARKERS)
        current = find_markers(combined, SAFE_CURRENT_MARKERS)

        if old:
            matches.append(
                ScheduledTaskMatch(
                    task_name=item["TaskName"],
                    task_path=item["TaskPath"],
                    state=item["State"],
                    actions=actions,
                    old_markers=old,
                    safe_current_markers=current,
                )
            )

    return matches


def load_processes(root: Path) -> list[ProcessMatch]:
    escaped = str(root).replace("'", "''")
    script = rf"""
$items = Get-CimInstance Win32_Process |
    Where-Object {{
        $_.CommandLine -and
        $_.CommandLine -like '*{escaped}*'
    }} |
    Select-Object ProcessId, Name, CommandLine
$items | ConvertTo-Json -Depth 4 -Compress
"""
    raw = run_powershell(script)
    if isinstance(raw, dict):
        raw = [raw]

    matches: list[ProcessMatch] = []
    for item in raw:
        command_line = item.get("CommandLine") or ""
        old = find_markers(command_line, OLD_MARKERS)
        current = find_markers(
            command_line,
            SAFE_CURRENT_MARKERS,
        )

        if old:
            matches.append(
                ProcessMatch(
                    process_id=int(item["ProcessId"]),
                    name=item.get("Name") or "",
                    command_line=command_line,
                    old_markers=old,
                    safe_current_markers=current,
                )
            )

    return matches


def load_artifacts(root: Path) -> list[ArtifactMatch]:
    paths: set[Path] = set()

    for pattern in ARTIFACT_PATTERNS:
        for path in root.glob(pattern):
            if path.is_file():
                paths.add(path.resolve())

    return [
        ArtifactMatch(
            path=str(path.relative_to(root)),
            size_bytes=path.stat().st_size,
        )
        for path in sorted(paths)
    ]


def is_old_only(
    old_markers: tuple[str, ...],
    safe_current_markers: tuple[str, ...],
    include_current_realtime: bool,
) -> bool:
    if include_current_realtime:
        return bool(old_markers)

    return bool(old_markers) and not safe_current_markers


def disable_tasks(
    tasks: list[ScheduledTaskMatch],
    include_current_realtime: bool,
) -> list[str]:
    disabled: list[str] = []

    for task in tasks:
        if not is_old_only(
            task.old_markers,
            task.safe_current_markers,
            include_current_realtime,
        ):
            continue

        task_name = task.task_name.replace("'", "''")
        task_path = task.task_path.replace("'", "''")
        script = (
            "Disable-ScheduledTask "
            f"-TaskName '{task_name}' "
            f"-TaskPath '{task_path}' | Out-Null"
        )
        run_powershell(script)
        disabled.append(
            f"{task.task_path}{task.task_name}"
        )

    return disabled


def stop_processes(
    processes: list[ProcessMatch],
    include_current_realtime: bool,
) -> list[int]:
    stopped: list[int] = []
    current_pid = os.getpid()

    for process in processes:
        if process.process_id == current_pid:
            continue

        if not is_old_only(
            process.old_markers,
            process.safe_current_markers,
            include_current_realtime,
        ):
            continue

        completed = subprocess.run(
            [
                "taskkill",
                "/PID",
                str(process.process_id),
                "/T",
                "/F",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            stopped.append(process.process_id)

    return stopped


def archive_artifacts(
    root: Path,
    artifacts: list[ArtifactMatch],
) -> list[str]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_root = (
        root
        / "archive"
        / f"old_paper_validation_{stamp}"
    )
    moved: list[str] = []

    for artifact in artifacts:
        source = root / artifact.path

        if not source.exists():
            continue

        destination = archive_root / artifact.path
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        shutil.move(str(source), str(destination))
        moved.append(artifact.path)

    return moved


def main() -> int:
    args = parse_args()
    root = args.root.resolve()

    tasks = load_tasks()
    processes = load_processes(root)
    artifacts = load_artifacts(root)

    disabled_tasks: list[str] = []
    stopped_processes: list[int] = []
    archived_artifacts: list[str] = []

    if args.disable_old_tasks:
        disabled_tasks = disable_tasks(
            tasks,
            args.include_current_realtime,
        )

    if args.stop_old_processes:
        stopped_processes = stop_processes(
            processes,
            args.include_current_realtime,
        )

    if args.archive_old_artifacts:
        archived_artifacts = archive_artifacts(
            root,
            artifacts,
        )

    report = {
        "project_root": str(root),
        "generated_at": datetime.now().isoformat(),
        "scheduled_tasks": [asdict(item) for item in tasks],
        "processes": [asdict(item) for item in processes],
        "artifacts": [asdict(item) for item in artifacts],
        "actions": {
            "disabled_tasks": disabled_tasks,
            "stopped_processes": stopped_processes,
            "archived_artifacts": archived_artifacts,
        },
    }

    report_path = (
        args.report
        if args.report.is_absolute()
        else root / args.report
    )
    report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    report_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Old Paper Trading validation audit completed.")
    print(f"Scheduled task matches: {len(tasks)}")
    for task in tasks:
        print(
            f"  TASK {task.task_path}{task.task_name} "
            f"state={task.state} "
            f"old={','.join(task.old_markers)} "
            f"current={','.join(task.safe_current_markers) or '-'}"
        )

    print(f"Running process matches: {len(processes)}")
    for process in processes:
        print(
            f"  PID {process.process_id} "
            f"{process.name} "
            f"old={','.join(process.old_markers)} "
            f"current={','.join(process.safe_current_markers) or '-'}"
        )

    print(f"Old artifact matches: {len(artifacts)}")
    for artifact in artifacts:
        print(
            f"  FILE {artifact.path} "
            f"size={artifact.size_bytes}"
        )

    print(f"Disabled tasks: {len(disabled_tasks)}")
    print(f"Stopped processes: {len(stopped_processes)}")
    print(f"Archived artifacts: {len(archived_artifacts)}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
