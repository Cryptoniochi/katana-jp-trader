"""Sprint91リスク・通知監査に必要な最新版ソースを収集する。"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


TARGETS = (
    "app/settings.py",
    "app/run_paper_trading.py",
    "app/runtime/paper_trading_composition.py",
    "app/runtime/paper_trading_runtime_factory.py",
    "app/runtime/paper_trading_runtime.py",
    "app/runtime/paper_trading_runtime_models.py",
    "app/runtime/paper_trading_day_service.py",
    "app/runtime/paper_trading_day_models.py",
    "app/market/realtime_paper_trading_service.py",
    "app/live/live_orchestrator.py",
    "app/application/trading_loop_service.py",
    "app/application/trading_loop_component.py",
    "app/risk/risk_engine.py",
    "app/risk/risk_models.py",
    "app/risk/risk_service.py",
    "app/risk/risk_aware_queue_execution_service.py",
    "app/risk/queue_execution_risk_service.py",
    "app/backtest/queue_execution_service.py",
    "app/backtest/order_queue_service.py",
    "app/backtest/orb_signal_strategy.py",
    "app/trading/paper_broker.py",
    "app/trading/portfolio_service.py",
    "app/trading/portfolio_repository.py",
    "app/trading/position_service.py",
    "app/trading/order_service.py",
    "app/trading/order_repository.py",
    "app/trading/trade_execution_repository.py",
    "app/notifications/notification_composition.py",
    "app/notifications/notification_gateway.py",
    "app/notifications/notification_rule_service.py",
    "app/notifications/notification_rule_engine.py",
    "app/notifications/notification_template.py",
    "app/notifications/execution_notification_service.py",
    "tests/test_paper_trading_composition.py",
    "tests/test_realtime_paper_trading_service.py",
    "tests/test_risk_engine.py",
    "tests/test_risk_aware_queue_execution_service.py",
    "tests/test_run_paper_trading.py",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("katana_sprint91_risk_audit.zip"),
    )
    args = parser.parse_args()

    root = args.root.resolve()
    output = (
        args.output.resolve()
        if args.output.is_absolute()
        else (root / args.output).resolve()
    )

    collected: list[str] = []
    missing: list[str] = []

    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for relative in TARGETS:
            path = root / relative

            if path.is_file():
                archive.write(path, arcname=relative)
                collected.append(relative)
            else:
                missing.append(relative)

        archive.writestr(
            "RISK_AUDIT_MANIFEST.txt",
            "\n".join(
                [
                    f"Collected: {len(collected)}",
                    f"Missing: {len(missing)}",
                    "",
                    "[Collected]",
                    *collected,
                    "",
                    "[Missing]",
                    *(missing or ["None"]),
                    "",
                ]
            ),
        )

    print(f"Output: {output}")
    print(f"Collected: {len(collected)}")
    print(f"Missing: {len(missing)}")

    if missing:
        print("Missing files:")
        for item in missing:
            print(f"  - {item}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
