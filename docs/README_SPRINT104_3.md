# Sprint104-3 Scheduler Guard

## 目的

Paper Trading Schedulerが市場セッションを起動する直前に、
Autonomous Operation Validatorを実行します。

検証がBLOCKEDなら、Paper Tradingを開始しません。

## 起動フロー

```text
営業日・開始時刻到達
        ↓
Autonomous Operation Validator
        ↓
READY?
   ┌────┴────┐
   │         │
  YES       NO
   │         │
Production  起動禁止
Readiness   FAILED状態を保存
   ↓
Paper Trading開始
```

## 追加・置換ファイル

```text
app/runtime/scheduled_paper_trading.py
app/run_scheduled_paper_trading.py

tests/test_scheduled_paper_trading_guard.py
tests/test_scheduled_paper_trading_guard_cli.py

docs/README_SPRINT104_3.md
```

## Guardが確認する内容

```text
KATANA Service
Service component topology
Paper Trading Scheduler
Daily Report Scheduler
Watchlist 1～50銘柄
Database
Production Readiness
```

## Guardレポート

```text
reports/service/autonomous_operation_report.json
```

## 安全性

- Guard失敗時は子Paper Tradingプロセスを起動しません。
- 実注文には切り替えません。
- 既存Production Readiness Checkも継続します。
- テストや診断では明示的にGuardを無効化できます。

## テスト

```powershell
pytest tests/test_scheduled_paper_trading_guard.py tests/test_scheduled_paper_trading_guard_cli.py tests/test_scheduled_paper_trading_preflight.py tests/test_scheduled_paper_trading.py -q
```

## 手動確認

休場日はGuardを実行せず`closed_day`になります。

営業日・対象時間外でCLI構成だけ確認する場合:

```powershell
python -m app.run_scheduled_paper_trading --once
```

Guardを明示的に無効化する診断用オプション:

```powershell
python -m app.run_scheduled_paper_trading --once --skip-autonomous-guard
```

通常運用では`--skip-autonomous-guard`を使用しないでください。

## 次のSprint

Sprint104-4で、Morning Pre-Flightを営業日8:40に自動実行し、
送信済みマーカーで重複通知を防止します。
