# Sprint111-2 kabu Station Readiness Notifications

## 目的

KATANA Serviceがkabuステーションの接続状態変化を検出したとき、
LINE・Discordへ自動通知します。

## 通知条件

```text
not_checked → connected
disconnected → connected
connected → disconnected
connected → timeout
connected → error
```

同じ状態が継続している間は、通知を繰り返しません。

## 通知レベル

```text
connected                  INFO
disconnected/timeout/error CRITICAL
```

切断通知には、Paper Tradingを開始しないよう明記します。

## 安全設計

通知チャネルの初期化や送信に失敗しても、
KATANA Service Managerと接続監視は停止しません。

通知失敗は`recent_events`へ記録されます。

## 置換ファイル

```text
app/runtime/katana_service_manager.py
app/run_katana_service.py
tests/test_katana_service_manager.py
tests/test_run_katana_service.py
```

## 追加ファイル

```text
tests/test_katana_service_readiness_notification.py
```

## テスト

```powershell
pytest `
  tests/test_katana_service_manager.py `
  tests/test_run_katana_service.py `
  tests/test_katana_service_readiness_notification.py `
  -q
```

## Service再起動

```powershell
schtasks /End /TN "Project KATANA Service"
Start-Sleep -Seconds 5
schtasks /Run /TN "Project KATANA Service"
Start-Sleep -Seconds 70
```

## 通知の動作確認

kabuステーションをログアウトまたは終了し、最大60秒待ちます。

期待結果:

```text
KATANA: kabu Station Disconnected
```

再ログイン後、最大60秒待ちます。

期待結果:

```text
KATANA: kabu Station Connected
```

検証中に通知を止める場合:

```powershell
python -m app.run_katana_service `
  --disable-readiness-notifications
```
