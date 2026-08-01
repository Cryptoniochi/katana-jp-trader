# Sprint96-2 Dashboard Performance Ranking

## 目的

Sprint96-1で追加したPerformance APIを、既存Dashboardの
Desktop画面とMobile画面へ表示します。

## 追加・置換ファイル

```text
app/dashboard/dashboard_launcher.py
app/dashboard/dashboard_web_app.py
app/dashboard/templates/dashboard.html
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css

tests/test_dashboard_performance_launcher.py
tests/test_dashboard_performance_templates.py
```

## Desktop表示

Strategy Performance Rankingには次を表示します。

- 順位
- Strategy Score
- 完了トレード数
- Net P/L
- Win Rate
- Profit Factor
- Expectancy
- 平均保有時間
- 最大ドローダウン

## Mobile表示

スマホ用画面にも同じランキングを縦型カードで表示します。

## 重要

Dashboard Launcherが`StrategyPerformanceAnalyzer`を生成し、
`create_dashboard_app()`へ渡すようになりました。
これにより通常のDashboard起動でもPerformance APIが実データを返します。

## 事前処理

約定後にTrade Journalを更新します。

```powershell
python -m app.run_trade_journal
```

Dashboard起動:

```powershell
python -m app.dashboard `
  --host 127.0.0.1 `
  --database data\katana.db
```

## テスト

```powershell
pytest `
  tests/test_dashboard_performance_launcher.py `
  tests/test_dashboard_performance_templates.py `
  tests/test_dashboard_performance_api.py `
  tests/test_strategy_performance_service.py `
  tests/test_dashboard_launcher.py `
  tests/test_dashboard_web_app.py -q
```
