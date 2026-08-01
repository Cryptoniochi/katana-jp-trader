# Sprint97-1A

PowerShell 5.1でUTF-8日本語文字列が文字化けし、ParserErrorになる問題を修正しました。

## 差し替え対象

```text
scripts/run_dashboard_tailscale.ps1
```

スクリプト内の表示文をASCIIへ変更し、UTF-8 BOM付きで保存しています。

## 実行

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\run_dashboard_tailscale.ps1
```
