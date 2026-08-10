"""Dynamic Watchlistの選定理由を可視化する診断CLI。"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Sequence

DEFAULT_REPORT_PATH = Path("reports/watchlist/latest.json")
DEFAULT_OUTPUT_PATH = Path("reports/watchlist/diagnostics_latest.csv")

DIAGNOSTIC_FIELDS = (
    "rank", "selected", "code", "total_score", "rating_tier",
    "selection_tier", "preferred_strategy", "latest_price",
    "purchase_amount", "history_days", "average_volume_20d",
    "average_turnover_20d", "volume_ratio", "return_20d",
    "breakout_ratio", "atr_ratio", "gap_ratio", "vwap_distance_ratio",
    "close_position_ratio", "pullback_depth_ratio", "breakout_score",
    "momentum_score", "liquidity_score", "volume_score",
    "volatility_score", "gap_score", "vwap_score", "orb_score",
    "pullback_score", "high_breakout_score", "technical_score",
    "historical_score", "historical_trade_count", "learning_applied",
    "learned_preferred_strategy", "exclusion_reasons",
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dynamic Watchlist latest.jsonから、各銘柄がなぜ上位に来たのかを"
            "スコア要素別に表示します。"
        )
    )
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--code", action="append", default=[])
    return parser


def load_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Dynamic Watchlist report not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Dynamic Watchlist report must be a JSON object.")
    return payload


def build_diagnostics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    evaluated = payload.get("evaluated", [])
    selected = payload.get("selected", [])
    if not isinstance(evaluated, list):
        raise RuntimeError("Report field 'evaluated' must be a list.")

    selected_codes = {
        str(item.get("code") or "").strip()
        for item in selected
        if isinstance(item, dict)
    }
    candidates = [item for item in evaluated if isinstance(item, dict)]
    ranked = sorted(
        candidates,
        key=lambda item: (
            -_as_float(item.get("total_score")),
            -_as_float(item.get("average_turnover_20d")),
            str(item.get("code") or ""),
        ),
    )

    rows: list[dict[str, Any]] = []
    for rank, item in enumerate(ranked, start=1):
        row = {field: item.get(field) for field in DIAGNOSTIC_FIELDS}
        row["rank"] = rank
        row["selected"] = str(item.get("code") or "").strip() in selected_codes
        reasons = item.get("exclusion_reasons", [])
        if isinstance(reasons, list):
            row["exclusion_reasons"] = ",".join(str(value) for value in reasons)
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DIAGNOSTIC_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _format_percent(value: object) -> str:
    return f"{_as_float(value) * 100:.2f}%"


def _format_number(value: object) -> str:
    return f"{_as_float(value):,.2f}"


def print_candidate(row: dict[str, Any]) -> None:
    print(
        f"#{row['rank']:>3} {row.get('code', ''):<5} "
        f"selected={str(row.get('selected')):<5} "
        f"score={_format_number(row.get('total_score'))} "
        f"strategy={row.get('preferred_strategy')}"
    )
    print(
        "      "
        f"ATR%={_format_percent(row.get('atr_ratio'))}  "
        f"20dReturn={_format_percent(row.get('return_20d'))}  "
        f"Breakout={_format_percent(row.get('breakout_ratio'))}  "
        f"VolumeRatio={_format_number(row.get('volume_ratio'))}"
    )
    print(
        "      "
        f"Turnover={_format_number(row.get('average_turnover_20d'))}  "
        f"LiquidityScore={_format_number(row.get('liquidity_score'))}  "
        f"VolatilityScore={_format_number(row.get('volatility_score'))}  "
        f"VolumeScore={_format_number(row.get('volume_score'))}"
    )
    print(
        "      "
        f"ORB={_format_number(row.get('orb_score'))}  "
        f"Pullback={_format_number(row.get('pullback_score'))}  "
        f"HighBreakout={_format_number(row.get('high_breakout_score'))}  "
        f"Technical={_format_number(row.get('technical_score'))}  "
        f"Historical={_format_number(row.get('historical_score'))}"
    )
    reasons = str(row.get("exclusion_reasons") or "")
    if reasons:
        print(f"      Excluded: {reasons}")


def run(arguments: Sequence[str] | None = None) -> int:
    parsed = build_argument_parser().parse_args(arguments)
    if parsed.top <= 0:
        raise ValueError("--topは1以上で指定してください。")

    payload = load_report(parsed.report_path)
    rows = build_diagnostics(payload)
    write_csv(parsed.output_path, rows)

    print("Project KATANA Dynamic Watchlist Diagnostics")
    print("=" * 56)
    print(f"target_date={payload.get('target_date')}")
    print(f"market_data_date={payload.get('market_data_date')}")
    print(f"evaluated={len(rows)} selected={sum(bool(row['selected']) for row in rows)}")
    print()

    print(f"Top {min(parsed.top, len(rows))}")
    for row in rows[: parsed.top]:
        print_candidate(row)

    requested_codes = tuple(
        dict.fromkeys(
            str(code).strip().upper()
            for code in parsed.code
            if str(code).strip()
        )
    )
    if requested_codes:
        by_code = {str(row.get("code") or "").upper(): row for row in rows}
        print()
        print("Requested symbols")
        for code in requested_codes:
            row = by_code.get(code)
            if row is None:
                print(f"{code}: not found in evaluated candidates.")
                continue
            print_candidate(row)

    print()
    print(f"CSV: {parsed.output_path}")
    return 0


def _as_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(run())
