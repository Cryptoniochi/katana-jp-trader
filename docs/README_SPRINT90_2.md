# Sprint90-2 kabuステーションPaper Trading統合

## 配置

```text
app/market/kabu_station_completed_bar_provider.py
app/runtime/paper_trading_composition.py       # 完成版で置換
app/run_paper_trading.py                       # 完成版で置換

tests/test_kabu_station_completed_bar_provider.py
tests/test_paper_trading_composition.py        # 完成版で置換
tests/test_run_paper_trading.py                # 完成版で置換
```

## テスト

```powershell
python -m pytest tests/test_kabu_station_completed_bar_provider.py -q
python -m pytest tests/test_paper_trading_composition.py -q
python -m pytest tests/test_run_paper_trading.py -q
```

続けて関連テストも実行します。

```powershell
python -m pytest tests/test_kabu_station_realtime_service.py -q
python -m pytest tests/test_realtime_market_service.py -q
```

## 実市場Paper Trading

kabuステーションへログインしてAPIを有効にし、本番用APIパスワードを
現在のPowerShellセッションへ設定します。

```powershell
$env:KABU_STATION_API_PASSWORD="本番用APIパスワード"
```

まず1銘柄・少数サイクルで起動します。

```powershell
python -m app.run_paper_trading `
  --market-data-mode kabu-station-realtime `
  --code 7203 `
  --maximum-cycles 20 `
  --cycle-interval 30
```

このモードはkabuステーションからリアルタイムPUSHを受信します。
完成した5分足だけを既存RealtimeMarketMonitorへ渡し、SQLite保存、
ORB、Signal Engine、Paper Broker、通知の既存経路へ流します。

実注文は送信しません。
