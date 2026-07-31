# Sprint93-3 Strategy Analytics

## 追加ファイル

```text
app/runtime/strategy_analytics_models.py
app/runtime/strategy_analytics_service.py
app/runtime/strategy_analytics_reporter.py
app/run_strategy_analytics.py
tests/test_strategy_analytics_service.py
tests/test_strategy_analytics_reporter.py
```

## 集計

`trade_signals.strategy_name` と `trade_executions.signal_id` を結合し、同一戦略・同一銘柄のBUYとEXIT/SELLをFIFOで対応付けます。未決済BUYはシグナル数・約定数には含めますが、損益指標には含めません。

## テスト

```powershell
pytest `
  tests/test_strategy_analytics_service.py `
  tests/test_strategy_analytics_reporter.py `
  tests/test_trade_execution_repository.py `
  tests/test_position_repository.py `
  tests/test_paper_trading_daily_repository.py -q
```

## 実行

```powershell
python -m app.run_strategy_analytics
```

生成物:

```text
reports/strategy/strategy_performance.json
reports/strategy/strategy_performance.csv
reports/strategy/strategy_performance.html
```
