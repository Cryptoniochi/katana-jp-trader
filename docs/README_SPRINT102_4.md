# Sprint102-4 Daily Report Dashboard UI

## 目的

Sprint102-3のDaily Report APIを、PC・スマホDashboardへ表示します。

このSprintではLINE・Discord通知はまだ追加しません。

## 追加・置換ファイル

```text
app/dashboard/templates/dashboard.html
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css

tests/test_daily_report_templates.py
tests/test_daily_report_ui_api_regression.py

docs/README_SPRINT102_4.md
```

## Desktop表示

```text
Report Date
Net P/L
Trades
Win Rate
Profit Factor
Maximum Drawdown
Strategy Ranking
Symbol Ranking
Errors
Recoveries
```

## Mobile表示

```text
Daily Report
Net P/L
Trades
Win Rate
Profit Factor
Max Drawdown
Strategy Ranking
Top Symbols
Errors
Recoveries
```

## レポート未生成時

APIの`available=false`を受け取り、次を表示します。

```text
Daily trading report has not been generated yet.
```

Dashboard全体をエラー状態にはしません。

## テスト

```powershell
pytest tests/test_daily_report_templates.py tests/test_daily_report_ui_api_regression.py tests/test_daily_report_reader.py tests/test_dashboard_daily_report_api.py tests/test_dashboard_launcher.py tests/test_dashboard_web_app.py -q
```

## 反映

```powershell
schtasks /End /TN "Project KATANA Service"
```

```powershell
schtasks /Run /TN "Project KATANA Service"
```

10～20秒後にスマホDashboardを更新してください。

## 表示確認用レポート生成

取引がない日でも空レポートを作成できます。

```powershell
python -m app.run_daily_report --report-date 2026-08-01
```

実際のDBスキーマが未対応の場合は、無理に生成せずエラー内容を確認してください。
