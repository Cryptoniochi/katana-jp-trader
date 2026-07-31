"""新高値ブレイク候補をCSV・JSON・HTMLへ出力する。"""

from __future__ import annotations

import csv
import json
from html import escape
from pathlib import Path

from app.strategy.high_breakout_models import (
    HighBreakoutCandidate,
)


class HighBreakoutReporter:
    """新高値候補レポートを生成する。"""

    def __init__(
        self,
        output_directory: Path,
    ) -> None:
        self.output_directory = Path(
            output_directory
        )

    def write(
        self,
        candidates: tuple[
            HighBreakoutCandidate,
            ...
        ],
    ) -> tuple[Path, Path, Path, Path]:
        self.output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        json_path = (
            self.output_directory
            / "candidates.json"
        )
        csv_path = (
            self.output_directory
            / "candidates.csv"
        )
        html_path = (
            self.output_directory
            / "candidates.html"
        )
        summary_path = (
            self.output_directory
            / "summary.txt"
        )

        self._write_json(
            json_path,
            candidates,
        )
        self._write_csv(
            csv_path,
            candidates,
        )
        self._write_html(
            html_path,
            candidates,
        )
        self._write_summary(
            summary_path,
            candidates,
        )

        return (
            json_path,
            csv_path,
            html_path,
            summary_path,
        )

    @staticmethod
    def _to_dict(
        candidate: HighBreakoutCandidate,
    ) -> dict[str, object]:
        return {
            "code": candidate.code,
            "trading_date": (
                candidate.trading_date.isoformat()
            ),
            "breakout_types": [
                item.value
                for item in candidate.breakout_types
            ],
            "close_price": candidate.close_price,
            "previous_20_day_high": (
                candidate.previous_20_day_high
            ),
            "previous_60_day_high": (
                candidate.previous_60_day_high
            ),
            "previous_year_high": (
                candidate.previous_year_high
            ),
            "volume_ratio": candidate.volume_ratio,
            "turnover": candidate.turnover,
            "atr": candidate.atr,
            "atr_rate": candidate.atr_rate,
            "score": candidate.score,
        }

    @classmethod
    def _write_json(
        cls,
        path: Path,
        candidates: tuple[
            HighBreakoutCandidate,
            ...
        ],
    ) -> None:
        path.write_text(
            json.dumps(
                [
                    cls._to_dict(candidate)
                    for candidate in candidates
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def _write_csv(
        cls,
        path: Path,
        candidates: tuple[
            HighBreakoutCandidate,
            ...
        ],
    ) -> None:
        fieldnames = [
            "code",
            "trading_date",
            "breakout_types",
            "close_price",
            "previous_20_day_high",
            "previous_60_day_high",
            "previous_year_high",
            "volume_ratio",
            "turnover",
            "atr",
            "atr_rate",
            "score",
        ]

        with path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=fieldnames,
            )
            writer.writeheader()

            for candidate in candidates:
                row = cls._to_dict(candidate)
                row["breakout_types"] = ",".join(
                    row["breakout_types"]
                )
                writer.writerow(row)

    @classmethod
    def _write_html(
        cls,
        path: Path,
        candidates: tuple[
            HighBreakoutCandidate,
            ...
        ],
    ) -> None:
        rows = []

        for candidate in candidates:
            breakout_types = ", ".join(
                item.value
                for item in candidate.breakout_types
            )
            rows.append(
                "<tr>"
                f"<td>{escape(candidate.code)}</td>"
                f"<td>{candidate.trading_date}</td>"
                f"<td>{escape(breakout_types)}</td>"
                f"<td>{candidate.score:.2f}</td>"
                f"<td>{candidate.close_price:,.2f}</td>"
                f"<td>{candidate.volume_ratio:.2f}</td>"
                f"<td>{candidate.atr_rate:.2%}</td>"
                f"<td>{candidate.turnover:,.0f}</td>"
                "</tr>"
            )

        html = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>Project KATANA High Breakout Candidates</title>
<style>
body {{
  font-family: system-ui, sans-serif;
  margin: 32px;
  color: #1f2937;
}}
h1 {{ margin-bottom: 4px; }}
.meta {{ color: #6b7280; margin-bottom: 24px; }}
table {{
  border-collapse: collapse;
  width: 100%;
}}
th, td {{
  border: 1px solid #d1d5db;
  padding: 10px;
  text-align: right;
}}
th:first-child, td:first-child,
th:nth-child(3), td:nth-child(3) {{
  text-align: left;
}}
th {{
  background: #f3f4f6;
}}
</style>
</head>
<body>
<h1>Project KATANA High Breakout Candidates</h1>
<div class="meta">
候補数: {len(candidates)}
</div>
<table>
<thead>
<tr>
<th>Code</th>
<th>Date</th>
<th>Breakout</th>
<th>Score</th>
<th>Close</th>
<th>Volume Ratio</th>
<th>ATR Rate</th>
<th>Turnover</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>
"""
        path.write_text(
            html,
            encoding="utf-8",
        )

    @staticmethod
    def _write_summary(
        path: Path,
        candidates: tuple[
            HighBreakoutCandidate,
            ...
        ],
    ) -> None:
        lines = [
            "Project KATANA High Breakout Screening",
            f"candidate_count={len(candidates)}",
        ]

        for candidate in candidates:
            lines.append(
                f"{candidate.code} "
                f"date={candidate.trading_date} "
                f"score={candidate.score:.2f} "
                f"breakout="
                + ",".join(
                    item.value
                    for item in candidate.breakout_types
                )
            )

        path.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
