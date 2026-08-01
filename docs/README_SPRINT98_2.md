# Sprint98-2 Dashboard Startup Reliability

## 修正した問題

Windowsログオン直後はTailscaleがまだ接続されておらず、
Dashboard自動起動が一度だけ失敗して終了していました。

## 改善内容

- タスク実行をログオン30秒後に遅延
- Tailscale IPv4を最大5分待機
- 5秒間隔で最大60回再試行
- Dashboard異常終了時に10秒後再起動
- 最大100回の再起動
- ログを従来どおり保存

## 追加・置換ファイル

```text
app/run_dashboard_resident.py
app/dashboard_autostart.py

scripts/run_dashboard_resident.cmd
scripts/reinstall_dashboard_autostart.cmd

tests/test_dashboard_resident_recovery.py
tests/test_dashboard_autostart_retry.py
```

## テスト

1行で実行してください。

```powershell
pytest tests/test_dashboard_resident_recovery.py tests/test_dashboard_autostart_retry.py tests/test_run_dashboard_resident.py tests/test_dashboard_autostart.py -q
```

## 既存タスクの更新

既存タスクは古い起動コマンドを保持しているため、再登録が必要です。

管理者として起動したVS Codeのターミナルで、次の1行を実行します。

```powershell
.\scripts\reinstall_dashboard_autostart.cmd
```

または次の2行を個別に実行します。

```powershell
python -m app.dashboard_autostart remove
python -m app.dashboard_autostart install --project-directory C:\projects\katana --database-path data\katana.db --host-mode tailscale --port 8000
```

## 確認

```powershell
schtasks /Run /TN "Project KATANA Dashboard"
```

```powershell
netstat -ano | findstr :8000
```

ログ:

```powershell
Get-Content .\logs\dashboard\dashboard_resident.log -Tail 100
```

## 再起動テスト

Windowsを再起動してログオン後、30秒から1分ほど待ちます。
その後、スマホで従来のTailscale URLを開きます。
