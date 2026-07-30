# Sprint91-1A CMD修正版

PowerShellスクリプトは、Windows PowerShellがファイルを異なる文字コードとして
読み込んでいるため、置換後も構文エラーになっています。

今回はPowerShellスクリプトを使用せず、文字コード問題と実行ポリシーの影響を
受けないWindows CMDファイルを使用します。

## 配置

```text
C:\projects\katana\run_kabu_station_30_symbols_short.cmd
C:\projects\katana\run_kabu_station_30_symbols_full.cmd
```

## 約10分の確認

PowerShellからそのまま実行できます。

```powershell
.\run_kabu_station_30_symbols_short.cmd
```

## 終日確認

```powershell
.\run_kabu_station_30_symbols_full.cmd
```

APIパスワードは、実行するPowerShellで事前に設定してください。

```powershell
$env:KABU_STATION_API_PASSWORD="本番用APIパスワード"
```

古い`run_kabu_station_30_symbols.ps1`は使用しません。
