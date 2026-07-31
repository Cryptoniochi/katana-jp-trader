# Sprint95-1 Existing Dashboard Strategy Extension

## 方針

新しいDashboardを作るのではなく、既存のFastAPI Dashboardへ
戦略パネルとRecent Tradesを追加します。

## 追加・置換ファイル

```text
app/dashboard/dashboard_strategy_service.py
app/dashboard/dashboard_web_app.py
app/dashboard/dashboard_launcher.py
app/dashboard/templates/dashboard.html
app/dashboard/static/dashboard.css

tests/test_dashboard_strategy_service.py
tests/test_dashboard_strategy_web_api.py
```

## 追加API

```text
GET /api/dashboard/strategies
```

表示内容:

- ORB
- Pullback
- High Breakout
- 当日シグナル数
- 当日約定数
- 完了取引数
- 勝率
- Profit Factor
- 実現損益
- High Breakout候補数
- 最近の約定

## 起動

```powershell
python -m app.dashboard `
  --database data\katana.db
```

## テスト

```powershell
pytest `
  tests/test_dashboard_strategy_service.py `
  tests/test_dashboard_strategy_web_api.py `
  tests/test_dashboard_web_app.py `
  tests/test_dashboard_web_service.py `
  tests/test_dashboard_launcher.py -q
```
