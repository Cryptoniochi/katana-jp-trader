# Sprint111-1 Unified Runtime Environment

`app/run_paper_trading.py`が、OS環境変数だけでなくプロジェクト直下の
`.env`も読み込むように修正します。

優先順位:

```text
明示的な環境変数 / OS環境変数
        ↓ 優先
.env
        ↓ 不足キーのみ補完
共通Runtime Environment
```

この共通環境を、Paper Trading設定、Production Readiness、
通知設定、Runtime通知Gatewayで使用します。

## 置換ファイル

```text
app/run_paper_trading.py
```

## 追加テスト

```text
tests/test_run_paper_trading_environment.py
```

## テスト

```powershell
pytest `
  tests/test_run_paper_trading_environment.py `
  tests/test_katana_service_manager.py `
  tests/test_run_katana_service.py `
  -q
```

## Service再起動

```powershell
schtasks /End /TN "Project KATANA Service"
Start-Sleep -Seconds 5
schtasks /Run /TN "Project KATANA Service"
Start-Sleep -Seconds 70
```

確認:

```powershell
$status = Get-Content `
  reports\service\katana_service_status.json `
  -Raw |
ConvertFrom-Json

$status |
Select-Object `
  generated_at,
  service_state,
  kabu_station_readiness
```

期待値:

```text
service_state             healthy
kabu_station_readiness    connected
```
