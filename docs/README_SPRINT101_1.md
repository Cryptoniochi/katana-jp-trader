# Sprint101-1 Operational Readiness

## 目的

Paper Tradingを有効化する前に、主要な運用依存関係を
スマホとCLIから一括確認できるようにします。

## チェック項目

```text
KATANA Service
SQLite Database
Watchlist
kabu Station
Tailscale
Storage
Operational Logs
```

## 総合状態

```text
READY      必須項目がすべて正常
ATTENTION  警告あり
BLOCKED    必須項目に失敗あり
```

`ready_for_paper_trading`は、次がすべてPASSの場合だけTrueです。

```text
KATANA Service
SQLite Database
Watchlist
kabu Station
```

## 追加・置換ファイル

```text
app/runtime/operational_readiness_models.py
app/runtime/operational_readiness_service.py
app/run_operational_readiness.py

app/dashboard/dashboard_launcher.py
app/dashboard/dashboard_web_app.py
app/dashboard/templates/dashboard.html
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css

tests/test_operational_readiness_service.py
tests/test_dashboard_operational_readiness_api.py
tests/test_operational_readiness_templates.py
```

## CLI

```powershell
python -m app.run_operational_readiness
```

出力:

```text
reports/service/operational_readiness.json
```

## API

```text
GET /api/dashboard/operational-readiness
```

## テスト

```powershell
pytest tests/test_operational_readiness_service.py tests/test_dashboard_operational_readiness_api.py tests/test_operational_readiness_templates.py tests/test_dashboard_launcher.py tests/test_dashboard_web_app.py -q
```

## Dashboardへ反映

```powershell
schtasks /End /TN "Project KATANA Service"
```

```powershell
schtasks /Run /TN "Project KATANA Service"
```

10～20秒後にスマホDashboardを更新してください。

## 重要

このSprintは状態確認だけです。

- Paper Tradingは自動で有効化しません。
- Live Tradingは起動しません。
- 注文は送信しません。
