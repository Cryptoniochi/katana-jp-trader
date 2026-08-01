# Sprint99-3 Service Manager Unification

## 目的

常駐管理をService Managerへ一本化します。

### 旧構成

```text
Windows Task
  -> Dashboard Resident
      -> Dashboard
```

### 新構成

```text
Windows Task
  -> KATANA Service Manager
      -> Dashboard
      -> Paper Trading (disabled by default)
```

Dashboard Residentを子プロセスとして重ねず、Service Managerが
Dashboard本体を直接起動・監視します。

## 追加・置換ファイル

```text
app/runtime/katana_service_models.py
app/runtime/katana_service_manager.py
app/run_katana_service.py
app/katana_service_autostart.py

scripts/migrate_to_katana_service.cmd

tests/test_katana_service_unification.py
tests/test_katana_service_autostart.py
```

## 安全性

- 現行市場データはkabuステーションAPI
- J-Quantsは使用しない
- Paper Tradingは既定で無効
- Live Tradingは起動しない
- Dashboardだけ自動起動・自動再起動
- Tailscale接続を最大5分待機
- 旧Dashboardタスクを削除して新Serviceタスクへ移行

## テスト

```powershell
pytest tests/test_katana_service_unification.py tests/test_katana_service_autostart.py tests/test_katana_service_manager.py tests/test_run_katana_service.py -q
```

## Windowsタスク移行

管理者として起動したVS Codeのターミナルで、次を実行します。

```powershell
.\scripts\migrate_to_katana_service.cmd
```

成功後、タスクを起動します。

```powershell
schtasks /Run /TN "Project KATANA Service"
```

確認:

```powershell
netstat -ano | findstr :8000
```

ログ:

```powershell
Get-Content .\logs\service\katana_service.log -Tail 100
```

スマホDashboardでは、数秒後に次が表示されます。

```text
KATANA Service: HEALTHY
dashboard: running
paper_trading: disabled
kabu Station: NOT_CHECKED
```

`NOT_CHECKED`はPaper Tradingが無効であるため正常です。
