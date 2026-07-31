# Sprint95-2 Mobile Dashboard

## 概要

既存Dashboardをスマホ向けに拡張します。

デスクトップ画面:

```text
http://PC_ADDRESS:8000/
```

スマホ画面:

```text
http://PC_ADDRESS:8000/mobile
```

## 追加・置換ファイル

```text
app/dashboard/dashboard_web_app.py
app/dashboard/dashboard_launcher.py
app/dashboard/templates/mobile_dashboard.html
app/dashboard/static/dashboard.css

scripts/run_dashboard_mobile.ps1
scripts/run_dashboard_mobile.cmd
scripts/allow_dashboard_firewall.ps1

tests/test_dashboard_mobile_page.py
tests/test_dashboard_mobile_launcher.py
```

## 起動

```powershell
.\scripts\run_dashboard_mobile.ps1
```

Dashboardは`0.0.0.0:8000`で待ち受けます。

## 同じWi-Fiから見る

Windows PCのIPアドレスを確認します。

```powershell
ipconfig
```

例:

```text
IPv4 Address: 192.168.1.25
```

iPhoneのSafariで次を開きます。

```text
http://192.168.1.25:8000/mobile
```

Windows Firewallでブロックされる場合は、管理者PowerShellで次を実行します。

```powershell
.\scripts\allow_dashboard_firewall.ps1
```

## 外出先から見る

PCとiPhoneへTailscaleを導入し、同じアカウントで接続します。
PCのTailscale IPが`100.x.x.x`なら、iPhoneから次を開きます。

```text
http://100.x.x.x:8000/mobile
```

ルーターのポート開放は行わないでください。

## テスト

```powershell
pytest `
  tests/test_dashboard_mobile_page.py `
  tests/test_dashboard_mobile_launcher.py `
  tests/test_dashboard_strategy_service.py `
  tests/test_dashboard_strategy_web_api.py `
  tests/test_dashboard_web_app.py `
  tests/test_dashboard_launcher.py -q
```
