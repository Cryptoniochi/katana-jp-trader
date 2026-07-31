"""実行中のProject KATANAが読み込むソース経路を監査する。"""

from __future__ import annotations

import inspect
from pathlib import Path

import app.run_paper_trading as run_module
import app.runtime.paper_trading_composition as composition_module
import app.risk.paper_trading_trace as trace_module
from app.runtime.paper_trading_composition import (
    PaperTradingProductionSettings,
)


def yes_no(value: bool) -> str:
    return "YES" if value else "NO"


def main() -> int:
    root = Path.cwd().resolve()
    composition_source = inspect.getsource(
        composition_module.PaperTradingComposition
    )
    settings_source = inspect.getsource(
        composition_module.PaperTradingProductionSettings
    )

    settings = PaperTradingProductionSettings(
        database_path=root / "data" / "execution_audit.db",
        codes=("7203",),
        market_data_mode="kabu-station-realtime",
        kabu_station_api_password="audit-only",
    )

    print("Project KATANA execution-path audit")
    print(f"cwd={root}")
    print(f"run_paper_trading={Path(run_module.__file__).resolve()}")
    print(
        "paper_trading_composition="
        f"{Path(composition_module.__file__).resolve()}"
    )
    print(
        "paper_trading_trace="
        f"{Path(trace_module.__file__).resolve()}"
    )
    print(
        "run_module_composition_identity="
        f"{yes_no(run_module.PaperTradingComposition is composition_module.PaperTradingComposition)}"
    )
    print(
        "composition_has_runtime_started="
        f"{yes_no('trace_recorder.runtime_started(' in composition_source)}"
    )
    print(
        "settings_normalizes_trace_path="
        f"{yes_no('normalized_risk_trace_path' in settings_source)}"
    )
    print(f"resolved_trace_path={settings.risk_trace_path}")
    print(
        "trace_path_under_project_root="
        f"{yes_no(root in settings.risk_trace_path.parents)}"
    )

    failures = []

    if run_module.PaperTradingComposition is not composition_module.PaperTradingComposition:
        failures.append(
            "run_paper_tradingが別のCompositionを参照しています。"
        )
    if "trace_recorder.runtime_started(" not in composition_source:
        failures.append(
            "Compositionにruntime_started呼出がありません。"
        )
    if not settings.risk_trace_path.is_absolute():
        failures.append(
            "risk_trace_pathが絶対パスへ正規化されていません。"
        )
    if root not in settings.risk_trace_path.parents:
        failures.append(
            "risk_trace_pathがProject KATANA配下ではありません。"
        )

    if failures:
        print()
        print("AUDIT FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print()
    print("AUDIT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
