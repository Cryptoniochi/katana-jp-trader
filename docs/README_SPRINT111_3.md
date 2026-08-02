# Sprint111-3 Direct kabu Station API Probe

## 修正理由

従来のReadiness Probeは`python -m app.run_paper_trading --check`の
終了コードを使っていました。この総合診断は設定・DB・Compositionを
検査しますが、kabuステーションAPIの実接続を必ず確認するものでは
ありませんでした。

そのため、kabuステーションを終了してTCP 18080が閉じていても、
`connected`のままになることがありました。

## 新しい判定

```text
.envからAPIパスワードを取得
        ↓
POST http://localhost:18080/kabusapi/token
        ↓
Token取得成功        → connected
接続拒否・HTTP失敗   → disconnected
タイムアウト          → timeout
不正JSON              → error
```

監視間隔の既定値は、軽量な直接Probeへ変更したため60秒から15秒へ
短縮しました。

## 置換ファイル

```text
app/runtime/kabu_station_readiness_probe.py
app/run_katana_service.py
```

## 追加テスト

```text
tests/test_kabu_station_readiness_probe.py
```

## テスト

```powershell
pytest `
  tests/test_kabu_station_readiness_probe.py `
  tests/test_katana_service_manager.py `
  tests/test_run_katana_service.py `
  tests/test_katana_service_readiness_notification.py `
  -q
```

## Service再起動

```powershell
schtasks /End /TN "Project KATANA Service"
Start-Sleep -Seconds 5

Get-CimInstance Win32_Process |
Where-Object {
    $_.CommandLine -like "*app.run_katana_service*" -or
    $_.CommandLine -like "*app.dashboard*" -or
    $_.CommandLine -like "*app.run_dynamic_watchlist_scheduler*" -or
    $_.CommandLine -like "*app.run_morning_preflight_scheduler*" -or
    $_.CommandLine -like "*app.run_daily_report_scheduler*" -or
    $_.CommandLine -like "*app.run_scheduled_paper_trading*"
} |
ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

schtasks /Run /TN "Project KATANA Service"
Start-Sleep -Seconds 25
```

## 動作確認

kabuステーション終了後、15～25秒程度で次になります。

```text
kabu_station_readiness = disconnected
```

LINE・Discordへ切断通知が届きます。

再起動・ログイン後、15～25秒程度で次になります。

```text
kabu_station_readiness = connected
```

復旧通知が届きます。
