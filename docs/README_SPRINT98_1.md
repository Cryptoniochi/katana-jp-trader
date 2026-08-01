# Sprint98-1 Dashboard Resident and Auto-start

## 目的

Dashboardを毎回PowerShellから手動起動しなくても済むようにします。

今回のSprintではPaper TradingとDashboardを同一プロセスへ統合しません。
Dashboardだけを独立した読み取り専用プロセスとしてWindowsログオン時に
自動起動します。

この分離により、Dashboard障害がPaper Tradingへ影響することを防ぎます。

## 追加ファイル

```text
app/run_dashboard_resident.py
app/dashboard_autostart.py

scripts/run_dashboard_resident.cmd

tests/test_run_dashboard_resident.py
tests/test_dashboard_autostart.py
```

## 仕組み

```text
Windowsログオン
        |
        v
Task Scheduler
        |
        v
run_dashboard_resident_task.cmd
        |
        v
Tailscale IPv4を取得
        |
        v
DashboardをTailscale IP:8000で起動
```

`0.0.0.0`では待ち受けません。

## テスト

```powershell
pytest `
  tests/test_run_dashboard_resident.py `
  tests/test_dashboard_autostart.py `
  tests/test_dashboard_launcher.py `
  tests/test_dashboard_web_app.py -q
```

## 自動起動タスクの登録

通常のPowerShellで実行します。

```powershell
python -m app.dashboard_autostart install `
  --project-directory C:\projects\katana `
  --database-path data\katana.db `
  --host-mode tailscale `
  --port 8000
```

登録後の状態確認:

```powershell
python -m app.dashboard_autostart status
```

すぐに試す場合は、一度サインアウトして再ログオンするか、
生成されたタスクをWindows Task Schedulerから手動実行します。

## ログ

```text
logs\dashboard\dashboard_resident.log
```

## 自動起動タスクの削除

```powershell
python -m app.dashboard_autostart remove
```

## 注意

- PCが起動している必要があります。
- Windowsへログオンしている必要があります。
- PC側Tailscaleが接続済みである必要があります。
- スマホ側Tailscaleも接続する必要があります。
- Dashboardは読み取り専用です。
- Paper Tradingの自動起動設定は変更しません。
