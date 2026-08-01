# Sprint103-1 Paper Trading Service Integration

## 目的

Paper Trading SchedulerをKATANA Serviceの通常運用経路として有効化し、
営業日の自律運転を開始できる構成にします。

## 自律運転フロー

```text
Windowsログオン
  ↓
Project KATANA Service
  ├ Dashboard
  ├ Paper Trading Scheduler
  └ Daily Report Scheduler
```

Paper Trading Scheduler:

```text
営業日判定
  ↓
8:45まで待機
  ↓
Production Readiness Check
  ↓
run_market_session
  ↓
前場・昼休み・後場を既存MarketSessionRunnerで制御
  ↓
15:35停止
```

Daily Report Scheduler:

```text
15:40
  ↓
Daily Report生成
  ↓
LINE・Discord通知
```

## 重要な安全設計

- 自動運用は`paper_trading_scheduler`だけが起動します。
- 直接の`paper_trading`コンポーネントは引き続き無効です。
- 二重起動を防ぎます。
- 起動前に`python -m app.run_paper_trading --check`を実行します。
- Readiness Check失敗時は市場セッションを起動しません。
- Live Tradingや実注文には切り替えません。
- 市場データは`kabu-station-realtime`です。

## 追加・置換ファイル

```text
app/runtime/scheduled_paper_trading.py
app/run_scheduled_paper_trading.py

app/runtime/katana_service_manager.py
app/run_katana_service.py

scripts/run_katana_service_task.cmd

tests/test_paper_trading_scheduler_service_integration.py
tests/test_scheduled_paper_trading_preflight.py
tests/test_service_task_autonomous_operation.py
```

## テスト

```powershell
pytest tests/test_paper_trading_scheduler_service_integration.py tests/test_scheduled_paper_trading_preflight.py tests/test_service_task_autonomous_operation.py tests/test_scheduled_paper_trading.py tests/test_run_katana_service.py -q
```

## Dry Run確認

```powershell
python -m app.run_katana_service --dry-run
```

期待される構成:

```text
dashboard: enabled=True
daily_report_scheduler: enabled=True
paper_trading_scheduler: enabled=True
paper_trading: enabled=False
```

Paper Trading Schedulerのコマンドには次が含まれます。

```text
--enable
--database-path data\katana.db
--watchlist watchlist.txt
--market-data-mode kabu-station-realtime
--strategy orb
--strategy pullback
--strategy high-breakout
```

## Serviceへ反映

テスト成功後:

```powershell
schtasks /End /TN "Project KATANA Service"
```

```powershell
schtasks /Run /TN "Project KATANA Service"
```

状態確認:

```powershell
Get-Content reports\service\katana_service_status.json
```

```powershell
Get-Content reports\service\paper_trading_schedule.json
```

kabuステーションが未起動・未ログインの場合、事前確認が失敗し、
Paper Tradingは起動しません。これは安全側の正常動作です。
