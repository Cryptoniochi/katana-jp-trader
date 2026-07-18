"""Paper Trading日次結果からJSON・HTMLレポートを生成する。"""

from __future__ import annotations

import html
import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runtime.daily_operation_report_models import (
    DailyOperationReportPaths,
    DailyOperationReportResult,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDayResult,
)
from app.runtime.paper_trading_day_report import (
    paper_trading_day_result_to_dict,
)


class DailyOperationReportService:
    """1営業日分のRead-only運用レポートを生成する。"""

    def __init__(
        self,
        *,
        report_root: Path = Path("reports/daily"),
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """出力Rootと時計を設定する。"""

        self.report_root = Path(report_root)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def generate(
        self,
        result: PaperTradingDayResult,
    ) -> DailyOperationReportResult:
        """JSON・HTMLレポートをAtomic Writeで生成する。"""

        generated_at = self._current_time()
        paths = self._paths(result)
        payload = paper_trading_day_result_to_dict(result)
        payload["report_generated_at"] = (
            generated_at.isoformat()
        )

        paths.directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        json_text = (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        html_text = self._render_html(payload)

        self._atomic_write(
            paths.json_path,
            json_text,
        )
        self._atomic_write(
            paths.html_path,
            html_text,
        )

        return DailyOperationReportResult(
            trading_date=result.trading_date,
            generated_at=generated_at,
            paths=paths,
            json_size_bytes=paths.json_path.stat().st_size,
            html_size_bytes=paths.html_path.stat().st_size,
        )

    def _paths(
        self,
        result: PaperTradingDayResult,
    ) -> DailyOperationReportPaths:
        """営業日単位の出力Pathを作成する。"""

        directory = (
            self.report_root
            / result.trading_date.isoformat()
        )

        return DailyOperationReportPaths(
            trading_date=result.trading_date,
            directory=directory,
            json_path=directory / "summary.json",
            html_path=directory / "summary.html",
        )

    @staticmethod
    def _atomic_write(
        path: Path,
        content: str,
    ) -> None:
        """一時ファイル経由で安全に保存する。"""

        temporary_path = path.with_suffix(
            path.suffix + ".tmp"
        )

        try:
            temporary_path.write_text(
                content,
                encoding="utf-8",
                newline="\n",
            )
            os.replace(
                temporary_path,
                path,
            )
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def _render_html(
        self,
        payload: dict[str, Any],
    ) -> str:
        """依存ライブラリ不要の単一HTMLを生成する。"""

        summary = payload.get("summary", {})

        dashboard = payload.get(
            "dashboard",
            {
                "published": False,
                "error_message": None,
            },
        )

        persistence = payload.get(
            "persistence",
            {
                "status": None,
            },
        )

        def text(value: Any) -> str:
            return html.escape(
                "—" if value is None else str(value)
            )

        def money(value: Any) -> str:
            if value is None:
                return "—"

            return f"¥{float(value):,.0f}"

        def percent(value: Any) -> str:
            if value is None:
                return "—"

            return f"{float(value) * 100:.2f}%"

        rows = "".join(
            f"""
            <tr>
              <td>{text(record.get("cycle_number"))}</td>
              <td>{text(record.get("status"))}</td>
              <td>{text(record.get("signal_count"))}</td>
              <td>{text(record.get("execution_count"))}</td>
              <td>{money(record.get("portfolio_equity"))}</td>
              <td>{text(record.get("error_message"))}</td>
            </tr>
            """
            for record in summary.get("records", ())
        )

        if not rows:
            rows = """
            <tr>
              <td colspan="6" class="empty">No cycle records.</td>
            </tr>
            """

        dashboard_published = bool(
            dashboard.get("published", False)
        )
        dashboard_status_class = (
            "ok"
            if dashboard_published
            else "error"
        )

        return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KATANA Daily Report {text(payload.get("trading_date"))}</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: Inter, system-ui, sans-serif;
      background: #071018;
      color: #edf4f7;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #071018; }}
    main {{
      width: min(1100px, calc(100% - 32px));
      margin: 0 auto;
      padding: 40px 0 64px;
    }}
    .eyebrow {{
      color: #78d5c7;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: .18em;
    }}
    h1 {{ margin: 8px 0 8px; font-size: 42px; }}
    .muted {{ color: #8da2ad; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-top: 28px;
    }}
    .metric, .panel {{
      border: 1px solid #1d3743;
      border-radius: 16px;
      background: #0a1a23;
    }}
    .metric {{ padding: 20px; }}
    .metric span {{
      display: block;
      color: #8da2ad;
      font-size: 12px;
      margin-bottom: 8px;
    }}
    .metric strong {{ font-size: 24px; }}
    .panel {{ margin-top: 20px; padding: 22px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{
      padding: 12px;
      border-bottom: 1px solid #19323e;
      text-align: right;
    }}
    th:first-child, td:first-child,
    th:nth-child(2), td:nth-child(2) {{
      text-align: left;
    }}
    th {{ color: #8da2ad; font-size: 12px; }}
    .empty {{ text-align: center !important; color: #8da2ad; }}
    .ok {{ color: #78d5c7; }}
    .error {{ color: #ff8f8f; }}
    pre {{
      overflow: auto;
      padding: 16px;
      background: #071018;
      border-radius: 12px;
      color: #b9cad2;
    }}
    @media (max-width: 760px) {{
      .metrics {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
  </style>
</head>
<body>
<main>
  <p class="eyebrow">PROJECT KATANA</p>
  <h1>Daily Operations Report</h1>
  <p class="muted">
    Trading date: {text(payload.get("trading_date"))}
    · Generated: {text(payload.get("report_generated_at"))}
  </p>

  <section class="metrics">
    <article class="metric">
      <span>Stop Reason</span>
      <strong>{text(payload.get("stop_reason"))}</strong>
    </article>
    <article class="metric">
      <span>Net P/L</span>
      <strong>{money(payload.get("net_profit_loss"))}</strong>
    </article>
    <article class="metric">
      <span>Return</span>
      <strong>{percent(payload.get("return_rate"))}</strong>
    </article>
    <article class="metric">
      <span>Cycles</span>
      <strong>{text(payload.get("cycle_count"))}</strong>
    </article>
    <article class="metric">
      <span>Signals</span>
      <strong>{text(summary.get("signal_count"))}</strong>
    </article>
    <article class="metric">
      <span>Executions</span>
      <strong>{text(summary.get("execution_count"))}</strong>
    </article>
    <article class="metric">
      <span>Initial Equity</span>
      <strong>{money(summary.get("initial_equity"))}</strong>
    </article>
    <article class="metric">
      <span>Final Equity</span>
      <strong>{money(summary.get("final_equity"))}</strong>
    </article>
  </section>

  <section class="panel">
    <h2>Cycle Records</h2>
    <table>
      <thead>
        <tr>
          <th>Cycle</th>
          <th>Status</th>
          <th>Signals</th>
          <th>Executions</th>
          <th>Portfolio Equity</th>
          <th>Error</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </section>

  <section class="panel">
    <h2>Operation Details</h2>
    <p>
      Dashboard publish:
      <strong class="{dashboard_status_class}">
        {text(dashboard_published)}
      </strong>
    </p>
    <p>
      Dashboard error:
      {text(dashboard.get("error_message"))}
    </p>
    <p>
      Persistence status:
      {text(persistence.get("status"))}
    </p>
    <p>
      Runtime error:
      {text(payload.get("error_message"))}
    </p>
  </section>
</main>
</body>
</html>
"""

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
