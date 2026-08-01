# Sprint100-1 Operational Stability Baseline

## 目的

Service Manager統合後の運用状態を明確化し、長期運転へ向けた
ログ肥大化と状態ファイル陳腐化を防ぎます。

## 実装内容

### 1. DATA状態とSERVICE状態を分離

スマホ画面上部の`PARTIAL`は、Service障害ではなく
Trading Snapshotの一部不足を表します。

画面では次の2つを明確に分けます。

```text
DATA            PARTIAL / AVAILABLE
KATANA Service  HEALTHY / STALE / DEGRADED
```

`DATA PARTIAL`でも`KATANA Service HEALTHY`なら、
サービス自体は正常に稼働しています。

### 2. Service状態の鮮度監視

Service Managerは通常5秒ごとに状態ファイルを更新します。
30秒以上更新されない場合、過去に`healthy`と書かれていても
Dashboardでは`STALE`と表示します。

### 3. 運用ログローテーション

既定設定:

```text
最大サイズ: 5 MB
保存世代数: 5
```

対象:

```text
logs/service/katana_service.log
logs/dashboard/dashboard_resident.log
katana.log
```

Serviceタスク起動前に自動実行します。

## 追加・置換ファイル

```text
app/runtime/operational_log_rotation.py
app/run_operational_maintenance.py

app/dashboard/katana_service_status_reader.py
app/dashboard/templates/dashboard.html
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css

scripts/run_katana_service_task.cmd

tests/test_operational_log_rotation.py
tests/test_katana_service_status_staleness.py
tests/test_operational_status_templates.py
```

## テスト

```powershell
pytest tests/test_operational_log_rotation.py tests/test_katana_service_status_staleness.py tests/test_operational_status_templates.py tests/test_katana_service_status_reader.py tests/test_dashboard_service_status_api.py tests/test_dashboard_service_status_templates.py -q
```

## 手動メンテナンス

```powershell
python -m app.run_operational_maintenance
```

## 反映

Serviceタスクを再起動します。

```powershell
schtasks /End /TN "Project KATANA Service"
schtasks /Run /TN "Project KATANA Service"
```

その後、スマホ画面を更新してください。
