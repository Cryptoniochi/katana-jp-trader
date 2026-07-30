# Sprint89-1B

## 配置先

```text
app/market/kabu_station_websocket.py
app/market/realtime_bar_aggregator.py
app/market/kabu_station_realtime_service.py
app/market/kabu_station_realtime_provider.py  # 完成版で置換

tests/test_kabu_station_websocket.py
tests/test_realtime_bar_aggregator.py
tests/test_kabu_station_realtime_service.py
```

## 依存パッケージ

```powershell
python -m pip install -r requirements_sprint89_1b.txt
```

## テスト

```powershell
python -m pytest tests/test_kabu_station_websocket.py -q
python -m pytest tests/test_realtime_bar_aggregator.py -q
python -m pytest tests/test_kabu_station_realtime_service.py -q
python -m pytest tests/test_kabu_station_realtime_provider.py -q
```

## 今回の到達点

- kabuステーションWebSocketへの接続
- JSON PUSHの受信
- 切断後の指数バックオフ再接続
- 価格更新のTick変換
- 重複・古いTickの除外
- 累積出来高から区間出来高への変換
- 5分OHLCVバー生成
- Provider接続診断との統合

本番のAPIパスワードはソースコードへ記載しないでください。
