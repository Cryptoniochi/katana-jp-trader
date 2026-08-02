# Sprint107-2 Dynamic Watchlist Dashboard

## 目的

Dynamic Watchlistのランキング、Tier、推奨戦略、100株購入額、
戦略適性スコアをDesktop・Mobile Dashboardへ表示します。

## 追加・置換ファイル

```text
app/dashboard/dynamic_watchlist_status_reader.py
app/dashboard/dashboard_launcher.py
app/dashboard/dashboard_web_app.py
app/dashboard/templates/dashboard.html
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css

tests/test_dynamic_watchlist_status_reader.py
tests/test_dynamic_watchlist_dashboard_templates.py
```

## API

```text
GET /api/dashboard/dynamic-watchlist
```

## 表示内容

```text
Schedule State
Applied
Evaluated Count
Eligible Count
Selected Count
Capital Limit
Purchase Budget

Rank
Code
Rating Tier
Data Tier
Preferred Strategy
Total Score
Latest Price
100-share Amount
ORB Score
Pullback Score
High Breakout Score
```

## テスト

```powershell
pytest tests/test_dynamic_watchlist_status_reader.py tests/test_dynamic_watchlist_dashboard_templates.py tests/test_dashboard_launcher.py tests/test_dashboard_web_app.py -q
```

## Service反映

```powershell
schtasks /End /TN "Project KATANA Service"
schtasks /Run /TN "Project KATANA Service"
```

起動後、API確認:

```powershell
Invoke-RestMethod http://100.64.14.23:8000/api/dashboard/dynamic-watchlist
```

スマホ:

```text
http://100.64.14.23:8000/mobile
```

## 補足

このSprintは表示機能のみです。

`preferred_strategy`はまだPaper Tradingの戦略実行を制限しません。
銘柄別戦略ルーティングは次のSprintで実装します。
