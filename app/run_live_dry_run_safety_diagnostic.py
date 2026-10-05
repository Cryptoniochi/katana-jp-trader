"""Read-only operator CLI for Phase 6-D production safety diagnostics."""

from __future__ import annotations

import argparse
from app.live.live_dry_run_safety_diagnostic import ProductionSafetyDiagnostic


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="Inspect saved production safety inputs for the Live dry-run. Read-only; no recovery or order submission.")


def format_report(report) -> str:
    lines = ["production_live_dry_run_safety_diagnostic", f"generated_at={report.generated_at.isoformat()}", ""]
    for item in report.items:
        status = "READY" if item.passed else "BLOCKED"
        lines.append(f"{item.key:<32} {status:<7} {item.message}")
    lines += [
        "",
        f"activation_inputs_ready={str(report.activation_inputs_ready).lower()}",
        f"transport_ready={str(report.transport_ready).lower()}",
        f"live_order_ready={str(report.live_order_ready).lower()}",
        "broker_transmission_occurred=false",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    print(format_report(ProductionSafetyDiagnostic().check()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
