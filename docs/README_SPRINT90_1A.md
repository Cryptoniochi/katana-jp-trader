# Sprint90-1A 実接続確認

## 配置

```text
app/market/kabu_station_bar_sink.py
app/run_kabu_station_realtime_check.py

tests/test_kabu_station_bar_sink.py
tests/test_run_kabu_station_realtime_check.py
```

## APIパスワードの設定

PowerShellの現在のセッションだけへ設定します。

```powershell
$env:KABU_STATION_API_PASSWORD="kabuステーションで設定したAPIパスワード"
```

パスワードをソースコード、README、Gitへ記録しないでください。

## テスト

```powershell
python -m pytest tests/test_kabu_station_bar_sink.py -q
python -m pytest tests/test_run_kabu_station_realtime_check.py -q
```

## トークン取得だけ確認

kabuステーションへログインし、APIが有効な状態で実行します。

```powershell
python -m app.run_kabu_station_realtime_check --token-only
```

## PUSH受信確認

市場時間中に、まず1銘柄・60秒で確認します。

```powershell
python -m app.run_kabu_station_realtime_check --code 7203 --duration 60
```

PUSHは価格等に変化があった場合に届きます。5分足は次の時間区間へ
移った時点で確定保存されます。終了時には集計途中のバーもフラッシュ
されます。

これはPaper Trading専用の接続確認です。実注文は送信しません。
