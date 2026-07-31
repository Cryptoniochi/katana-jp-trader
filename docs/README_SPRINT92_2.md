# Sprint92-2: J-Quants Runtime完全撤去

## 置換対象

- `app/runtime/paper_trading_composition.py`
- `app/run_paper_trading.py`
- `app/runtime/production_readiness.py`
- `app/market/realtime_market_service.py`
- 対応する4テストファイル

## 主な変更

- 本番市場データモードを `kabu-station-realtime` に一本化
- J-Quants APIキー・タイムアウト・Replay設定を削除
- Production ReadinessのJ-Quants APIキー検査を削除
- Realtime Monitorの例外を汎用 `RealtimeProviderRateLimitError` に変更
- Replay診断表示をランチャーから削除

## 配置後のテスト

```powershell
pytest `
  tests/test_paper_trading_composition.py `
  tests/test_run_paper_trading.py `
  tests/test_production_readiness.py `
  tests/test_realtime_market_service.py -q
```

## 本番診断

```powershell
python -m app.run_paper_trading --check
```

`.env`には次が必要です。

```text
KABU_STATION_API_PASSWORD=...
KATANA_MARKET_DATA_MODE=kabu-station-realtime
```
