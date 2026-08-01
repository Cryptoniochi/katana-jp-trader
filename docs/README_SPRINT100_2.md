# Sprint100-2 Self-Healing Runtime

## 目的

Service Managerの自己修復状況を記録・可視化し、
kabuステーション接続状態を定期確認します。

## 実装内容

### Service Uptime

Service Managerの起動時刻と連続稼働秒数を状態ファイルへ保存し、
Desktop/Mobile Dashboardに表示します。

### Recovery History

次のイベントを最大50件保持します。

```text
service_started
component_started
component_stopped
component_failed
restart_scheduled
restart_completed
readiness_changed
```

Dashboardには直近のイベントを表示します。

### kabuステーションReadiness Monitor

既存の次のProduction Readiness Checkを60秒ごとに実行します。

```text
python -m app.run_paper_trading --check
```

表示状態:

```text
CONNECTED
DISCONNECTED
TIMEOUT
ERROR
```

Paper Tradingが無効でも、接続状態だけを確認します。
Live Orderは起動しません。

### Dashboard Self-Healing

Dashboard異常終了時は従来どおり自動再起動し、
次を履歴へ記録します。

```text
restart_scheduled
restart_completed
```

## 追加・置換ファイル

```text
app/runtime/katana_service_models.py
app/runtime/katana_service_manager.py
app/runtime/kabu_station_readiness_probe.py
app/run_katana_service.py

app/dashboard/katana_service_status_reader.py
app/dashboard/templates/dashboard.html
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css

tests/test_katana_service_self_healing.py
tests/test_kabu_station_readiness_probe.py
tests/test_katana_service_runtime_status_reader.py
tests/test_self_healing_dashboard_templates.py
```

## テスト

```powershell
pytest tests/test_katana_service_self_healing.py tests/test_kabu_station_readiness_probe.py tests/test_katana_service_runtime_status_reader.py tests/test_self_healing_dashboard_templates.py tests/test_katana_service_manager.py tests/test_run_katana_service.py -q
```

## Serviceへ反映

```powershell
schtasks /End /TN "Project KATANA Service"
```

```powershell
schtasks /Run /TN "Project KATANA Service"
```

10～20秒後、スマホDashboardを更新してください。

## 期待表示

```text
KATANA Service  HEALTHY
kabu Station    CONNECTED または DISCONNECTED
Service Uptime  0m～
Recovery Events 2～
dashboard       running
paper_trading   disabled
```

kabuステーションアプリが未起動・未ログインの場合は
`DISCONNECTED`で正常です。
