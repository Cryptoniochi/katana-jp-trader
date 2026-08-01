# Sprint104-1 Autonomous Operation Validator

## 目的

実際の営業日運用を開始する前に、Project KATANAの自律運転構成を
1コマンドで確認します。

このSprintは読み取り専用です。

- 売買注文を送りません。
- Paper Tradingを開始しません。
- Serviceを再起動しません。
- 通知を送りません。

## 追加ファイル

```text
app/runtime/autonomous_operation_models.py
app/runtime/autonomous_operation_validator.py
app/run_autonomous_operation_validation.py

tests/test_autonomous_operation_validator.py
docs/README_SPRINT104_1.md
```

## チェック項目

```text
KATANA Service
Service component topology
Paper Trading Scheduler
Daily Report Scheduler
Watchlist 1～50銘柄
Database
Production Readiness
```

## テスト

```powershell
pytest tests/test_autonomous_operation_validator.py -q
```

## 実行

```powershell
python -m app.run_autonomous_operation_validation
```

期待値:

```text
Overall: READY
Ready for next business day: True
```

結果JSON:

```text
reports/service/autonomous_operation_report.json
```

## ATTENTION

`failed`または`retry_wait`のScheduler状態は警告として扱います。
ただしProduction Readiness、Watchlist、Database、Service構成の失敗は
次営業日の自律運転をBLOCKEDにします。

## 次の段階

この検証がREADYになったら、次の営業日に以下を確認します。

```text
08:45 Paper Trading Scheduler待機解除
09:00 前場開始
11:30 昼休み
12:30 後場再開
15:35 Paper Trading終了
15:40 Daily Report生成・通知
```
