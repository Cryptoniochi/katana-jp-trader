# Sprint96-1 Strategy Performance Analyzer

## 追加・置換ファイル

```text
app/analytics/strategy_performance_models.py
app/analytics/strategy_performance_service.py
app/run_strategy_performance.py
app/dashboard/dashboard_web_app.py

tests/test_strategy_performance_service.py
tests/test_dashboard_performance_api.py
tests/test_run_strategy_performance.py
```

## 集計内容

Trade Journalを戦略単位で集計します。

- 取引数
- 勝数・敗数・引分数
- 勝率
- Gross Profit / Gross Loss
- Net P/L
- Profit Factor
- 平均損益
- 平均利益・平均損失
- 平均リターン
- 平均勝率・平均負率
- Expectancy
- 平均保有時間
- 最大ドローダウン
- 平均MFE率・平均MAE率
- Strategy Score
- Strategy Ranking

## CLI

```powershell
python -m app.run_strategy_performance
```

出力:

```text
reports/strategy_performance.json
```

## Dashboard API

```text
GET /api/dashboard/performance
```

## テスト

```powershell
pytest `
  tests/test_strategy_performance_service.py `
  tests/test_dashboard_performance_api.py `
  tests/test_run_strategy_performance.py `
  tests/test_trade_journal_service.py `
  tests/test_dashboard_strategy_web_api.py -q
```
