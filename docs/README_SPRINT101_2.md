# Sprint101-2 Scheduled Paper Trading Controller

## 目的

既存の`run_market_session`と`TokyoMarketCalendar`を利用し、
営業日・時刻に応じてPaper Tradingを安全に起動・停止します。

## スケジュール

```text
08:45  Scheduler start / readiness period
09:00  Morning market open
11:30  Lunch break
12:30  Afternoon resume
15:30  Market close
15:35  Paper Trading process stop
```

昼休みの待機制御は既存`MarketSessionRunner`へ委譲します。

## 安全設計

- 既定では無効
- `--enable`指定時だけ起動可能
- 土日・JPX休場日は起動しない
- 15:35以降は子プロセスを停止
- Live Tradingは起動しない
- 注文はPaper Tradingのみ
- Service Managerへの統合も明示フラグ方式

## 追加・置換ファイル

```text
app/runtime/scheduled_paper_trading_models.py
app/runtime/scheduled_paper_trading.py
app/run_scheduled_paper_trading.py

app/runtime/katana_service_models.py
app/runtime/katana_service_manager.py
app/run_katana_service.py

app/dashboard/paper_trading_schedule_status_reader.py
app/dashboard/dashboard_launcher.py
app/dashboard/dashboard_web_app.py
app/dashboard/templates/dashboard.html
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css

tests/test_scheduled_paper_trading.py
tests/test_paper_trading_schedule_status_reader.py
tests/test_dashboard_paper_trading_schedule_api.py
tests/test_paper_trading_schedule_templates.py
```

## テスト

```powershell
pytest tests/test_scheduled_paper_trading.py tests/test_paper_trading_schedule_status_reader.py tests/test_dashboard_paper_trading_schedule_api.py tests/test_paper_trading_schedule_templates.py tests/test_dashboard_launcher.py tests/test_dashboard_web_app.py -q
```

## 無効状態の確認

```powershell
python -m app.run_scheduled_paper_trading --once
```

期待値:

```text
state=disabled
enabled=False
```

## 有効化前のドライ確認

営業日・時間帯の判定だけを確認する際は、テストを利用してください。
Service Managerの自動起動タスクは、現時点では既定の無効状態を維持します。

## 将来の有効化

十分なテストと運用確認後、Serviceタスクの起動コマンドへ次を追加します。

```text
--enable-paper-trading-schedule
```

このSprintでは自動有効化しません。
