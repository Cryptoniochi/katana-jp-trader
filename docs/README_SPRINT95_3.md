# Sprint95-3 Trade Journal

## 追加・置換ファイル

```text
app/database.py
app/trading/trade_journal_models.py
app/trading/trade_journal_repository.py
app/trading/trade_journal_service.py
app/run_trade_journal.py
app/dashboard/dashboard_strategy_service.py
app/dashboard/dashboard_web_app.py

tests/test_trade_journal_repository.py
tests/test_trade_journal_service.py
tests/test_run_trade_journal.py
tests/test_dashboard_strategy_service.py
tests/test_dashboard_strategy_web_api.py
```

## データベース

```text
SCHEMA_VERSION = 14
```

新規テーブル:

```text
trade_journal
```

## 生成内容

- 戦略名・銘柄
- Entry/Exit Signal ID
- Entry/Exit Execution ID
- Entry/Exit時刻
- Entry/Exit価格
- 数量
- 手数料・スリッページ
- 実現損益
- リターン率
- 保有時間
- Exit Reason
- MFE / MAE（金額・率）

約定は同一戦略・同一銘柄ごとにFIFOで対応付けます。
未決済BUYはJournalへ保存しません。

## MFE / MAE

`market_bars`の5分足を、EntryからExitまで参照します。

- MFE: 保有中最高値とEntry価格との差
- MAE: 保有中最安値とEntry価格との差

対象期間の分足がない場合、MFE/MAEは`None`です。

## 実行

```powershell
python -m app.run_trade_journal
```

## Dashboard API

既存APIへ次を追加します。

```text
recent_completed_trades
```

```text
GET /api/dashboard/strategies
```

## テスト

```powershell
pytest `
  tests/test_trade_journal_repository.py `
  tests/test_trade_journal_service.py `
  tests/test_run_trade_journal.py `
  tests/test_dashboard_strategy_service.py `
  tests/test_dashboard_strategy_web_api.py `
  tests/test_trade_execution_repository.py -q
```

## Git

```powershell
git add .
git diff --cached --name-only
git commit -m "Sprint95-3: add trade journal and completed trade analytics"
git push origin main
```
