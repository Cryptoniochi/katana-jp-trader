# Sprint90-1B リアルタイムPUSH確認

## 配置

```text
app/market/kabu_station_tick_monitor.py
app/market/kabu_station_realtime_service.py  # 完成版で置換
app/run_kabu_station_realtime_check.py       # 完成版で置換

tests/test_kabu_station_tick_monitor.py
tests/test_kabu_station_realtime_service.py  # 完成版で置換
```

## テスト

```powershell
python -m pytest tests/test_kabu_station_tick_monitor.py -q
python -m pytest tests/test_kabu_station_realtime_service.py -q
python -m pytest tests/test_run_kabu_station_realtime_check.py -q
```

## 実PUSH受信

kabuステーションへログインし、本番用APIパスワードを現在の
PowerShellセッションへ設定します。

```powershell
$env:KABU_STATION_API_PASSWORD="本番用APIパスワード"
```

市場時間中に、まず1銘柄を180秒受信します。

```powershell
python -m app.run_kabu_station_realtime_check --code 7203 --duration 180
```

Tickを受信すると次の形式で表示されます。

```text
TICK code=7203 time=... price=... cumulative_volume=...
```

市場時間外または価格更新がない場合、受信Tick数は0になります。
この確認プログラムは実注文を送信しません。
