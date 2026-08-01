# Sprint104-5 Morning Check Dashboard

## 目的

Morning Pre-Flightの自動実行状態と検証結果を、
PC・スマホDashboardから確認できるようにします。

## 追加・置換ファイル

```text
app/dashboard/morning_preflight_status_reader.py
app/dashboard/dashboard_launcher.py
app/dashboard/dashboard_web_app.py
app/dashboard/templates/dashboard.html
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css

tests/test_morning_preflight_status_reader.py
tests/test_morning_preflight_dashboard_templates.py

docs/README_SPRINT104_5.md
```

## API

```text
GET /api/dashboard/morning-preflight
```

## 表示内容

```text
Schedule State
Overall State
READY / NOT READY
Target Date
Last Attempt
Exit Code
Check Details
Message
```

## テスト

```powershell
pytest tests/test_morning_preflight_status_reader.py tests/test_morning_preflight_dashboard_templates.py tests/test_dashboard_launcher.py tests/test_dashboard_web_app.py -q
```

## Serviceへ反映

```powershell
schtasks /End /TN "Project KATANA Service"
schtasks /Run /TN "Project KATANA Service"
```

10～20秒後、スマホDashboardを更新してください。

## 期待される休場日表示

```text
Morning Check
CLOSED_DAY
```

Morning Pre-Flightの検証結果JSONが存在する場合は、
直近のREADY / BLOCKED結果も併記します。
