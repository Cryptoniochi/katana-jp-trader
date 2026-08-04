# Sprint112-2 Paper Trading Runtime Dashboard

## 目的

Service Managerの直接起動用コンポーネント
`paper_trading=disabled`は、Scheduler運用では正常ですが、
モバイル画面では実Runtimeが止まっているように見えました。

Sprint112-2では、Schedulerが公開する
`paper_trading_schedule.json`を実Runtimeの正しい情報源として表示します。

## 表示状態

```text
before_start  WAITING
running       RUNNING
lunch_break   LUNCH BREAK
completed     COMPLETED
failed        FAILED
closed_day    CLOSED DAY
disabled      DISABLED
```

## Runtimeカード

```text
Trading Date
Runtime PID
Last Exit
Next Action
Status Message
```

## Service Components

誤解を招く直接起動用`paper_trading`カードはモバイル画面から除外します。
`paper_trading_scheduler`は引き続き表示します。

## 置換ファイル

```text
app/dashboard/dashboard_web_app.py
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css
tests/test_dashboard_web_app.py
```

## テスト

```powershell
pytest `
  tests/test_dashboard_web_app.py `
  -q `
  --basetemp=.pytest_tmp
```

## Service再起動

```powershell
schtasks /End /TN "Project KATANA Service"
Start-Sleep -Seconds 5
schtasks /Run /TN "Project KATANA Service"
Start-Sleep -Seconds 20
```

## 確認URL

```text
http://100.64.14.23:8000/mobile
```

ブラウザに旧HTMLが残る場合は、ページを再読み込みしてください。
