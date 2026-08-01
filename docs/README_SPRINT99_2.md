# Sprint99-2 Service Status Dashboard

## 目的

Sprint99-1のService Manager状態を、既存のDesktop/Mobile
Dashboardへ表示します。

## 追加・置換ファイル

```text
app/dashboard/katana_service_status_reader.py
app/dashboard/dashboard_launcher.py
app/dashboard/dashboard_web_app.py
app/dashboard/templates/dashboard.html
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css

tests/test_katana_service_status_reader.py
tests/test_dashboard_service_status_api.py
tests/test_dashboard_service_status_templates.py
```

## 追加API

```text
GET /api/dashboard/service-status
```

## 表示項目

- Service全体状態
- kabuステーションReadiness
- Dashboard状態
- Paper Trading状態
- 有効/無効
- PID
- 再起動回数
- 最終終了コード
- エラーメッセージ

## 状態ファイル

```text
reports/service/katana_service_status.json
```

Service Managerをまだ起動していない場合、Dashboardには
`Service Manager status file has not been created.` と表示されます。

## テスト

```powershell
pytest tests/test_katana_service_status_reader.py tests/test_dashboard_service_status_api.py tests/test_dashboard_service_status_templates.py tests/test_dashboard_launcher.py tests/test_dashboard_web_app.py -q
```

## 確認

既存のDashboard自動起動タスクはそのまま利用できます。
ファイル差し替え後にタスクを一度再実行します。

```powershell
schtasks /End /TN "Project KATANA Dashboard"
schtasks /Run /TN "Project KATANA Dashboard"
```

ブラウザを更新するとService Statusパネルが表示されます。

現時点ではWindows自動起動タスクはDashboard Residentを起動しており、
Service Manager本体はまだ自動起動へ移行していません。
そのためService Managerを実行するまでは、状態ファイル未生成の案内が
正常表示です。
