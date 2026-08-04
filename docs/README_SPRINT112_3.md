# Sprint112-3 Paper Trading Activity Monitor

## 目的

Paper Tradingが実際に何サイクル動き、何件のシグナル・約定を
処理したかをリアルタイムで確認できるようにします。

## Runtime状態ファイル

```text
reports/service/paper_trading_runtime_status.json
```

Runtime開始時、各Cycle完了時、正常終了時、異常終了時に
一時ファイルから原子的に更新します。

## 表示項目

```text
Runtime State
Runtime PID
Trading Date
Cycle Count
Successful Cycles
Failed Cycles
Last Cycle
Signals
Executions
Open Positions
Today's P/L
Risk Evaluated
Risk Blocked
```

## 置換ファイル

```text
app/runtime/paper_trading_runtime.py
app/dashboard/dashboard_web_app.py
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css
tests/test_paper_trading_runtime.py
tests/test_dashboard_web_app.py
```

## 追加ファイル

```text
app/dashboard/paper_trading_runtime_status_reader.py
tests/test_paper_trading_runtime_status_reader.py
```

## テスト

```powershell
pytest `
  tests/test_paper_trading_runtime.py `
  tests/test_paper_trading_runtime_status_reader.py `
  tests/test_dashboard_web_app.py `
  -q `
  --basetemp=.pytest_tmp
```

## 再起動

```powershell
schtasks /End /TN "Project KATANA Service"
Start-Sleep -Seconds 5
schtasks /Run /TN "Project KATANA Service"
Start-Sleep -Seconds 20
```

営業時間中は各サイクル後に数値が更新されます。
市場終了後も当日の最終値を保持します。
