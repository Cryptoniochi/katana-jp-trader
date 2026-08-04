# Sprint113-1 P/L Semantics and Restored Positions

## 問題

`Signals=0`、`Executions=0`なのに`Open Positions=23`となっていたのは、
本日作成したポジションではなく、起動時に復元された既存Portfolioを
Runtimeがそのまま表示していたためです。

また、`Today's P/L`は起動時純資産との差額であり、
実現損益・含み損益のどちらか一方ではありませんでした。

## 修正

Runtime状態へ次を追加します。

```text
portfolio_position_count
session_equity_change
realized_profit_loss
unrealized_profit_loss
total_portfolio_profit_loss
```

Dashboardでは次のように明確化します。

```text
Portfolio Positions
Session Equity Change
Realized P/L
Unrealized P/L
Total Portfolio P/L
```

本日の約定が0件なのにPortfolio Positionが存在する場合、
「本日の取引前から復元されていたポジション」である旨を表示します。

## 置換ファイル

```text
app/runtime/paper_trading_runtime.py
app/dashboard/paper_trading_runtime_status_reader.py
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css
tests/test_paper_trading_runtime.py
tests/test_dashboard_web_app.py
```

## テスト

```powershell
pytest `
  tests/test_paper_trading_runtime.py `
  tests/test_paper_trading_runtime_status_reader.py `
  tests/test_dashboard_web_app.py `
  -q `
  --basetemp=.pytest_tmp
```
