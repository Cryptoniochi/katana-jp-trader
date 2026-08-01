# Sprint97-1 Performance Breakdown and Secure Mobile Path

## 実装内容

Trade Journalを次の軸で集計します。

- 曜日別
- エントリー時間帯別
- 銘柄別
- Exit Reason別

既存Desktop DashboardとMobile Dashboardの両方へ表示します。

## 追加・置換ファイル

```text
app/analytics/performance_breakdown_models.py
app/analytics/performance_breakdown_service.py
app/run_performance_breakdown.py

app/dashboard/dashboard_launcher.py
app/dashboard/dashboard_web_app.py
app/dashboard/templates/dashboard.html
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css

scripts/run_dashboard_tailscale.ps1

tests/test_performance_breakdown_service.py
tests/test_dashboard_performance_breakdown_api.py
tests/test_dashboard_performance_breakdown_templates.py
```

## API

```text
GET /api/dashboard/performance-breakdown
```

## CLI

```powershell
python -m app.run_performance_breakdown
```

出力:

```text
reports/performance_breakdown.json
```

## 通常Dashboard

標準設定は引き続きローカル専用です。

```powershell
python -m app.dashboard `
  --host 127.0.0.1 `
  --database data\katana.db
```

## スマホで見るための検討結果

同一Wi-Fi向けLAN公開は標準採用しません。

外出先からスマホで見る場合だけ、Tailscale導入後に次を実行します。

```powershell
.\scripts\run_dashboard_tailscale.ps1
```

このスクリプトはTailscale IPv4を取得し、そのIPだけにDashboardを
バインドします。`0.0.0.0`では待ち受けません。

表示されたURLを、同じTailscaleネットワークへ接続したスマホで開きます。

```text
http://100.x.x.x:8000/mobile
```

ルーターのポート開放や一般LAN向けFirewallルールは使用しません。

## テスト

```powershell
pytest `
  tests/test_performance_breakdown_service.py `
  tests/test_dashboard_performance_breakdown_api.py `
  tests/test_dashboard_performance_breakdown_templates.py `
  tests/test_dashboard_performance_launcher.py `
  tests/test_dashboard_performance_api.py `
  tests/test_strategy_performance_service.py -q
```
