# Sprint99-3B Fixed CMD Scheduled Task

## 修正理由

Sprint99-3のWindowsタスク登録がアクセス拒否または`/TR`の引用符解釈で
失敗する環境がありました。

Sprint99-3Bでは、Task Schedulerに長いPythonコマンドを渡しません。

```text
Task Scheduler
  -> cmd.exe
      -> scripts\run_katana_service_task.cmd
          -> python -m app.run_katana_service
```

固定CMDファイルだけを登録する、既存Dashboardタスクで実績のある方式です。

## 追加・置換ファイル

```text
app/katana_service_autostart.py
scripts/run_katana_service_task.cmd
scripts/migrate_to_katana_service.cmd
tests/test_katana_service_autostart_fixed_cmd.py
```

## テスト

```powershell
pytest tests/test_katana_service_autostart_fixed_cmd.py tests/test_katana_service_autostart.py tests/test_katana_service_unification.py tests/test_katana_service_manager.py tests/test_run_katana_service.py -q
```

## 移行

管理者として起動したVS Codeのターミナルで実行します。

```powershell
.\scripts\migrate_to_katana_service.cmd
```

成功後:

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

スマホDashboardの期待表示:

```text
KATANA Service  HEALTHY
dashboard       running
paper_trading   disabled
kabu Station    NOT_CHECKED
```

`NOT_CHECKED`はPaper Tradingが無効であるため正常です。
