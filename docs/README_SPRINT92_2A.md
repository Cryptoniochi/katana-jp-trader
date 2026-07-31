# Sprint92-2A

`tests/test_run_paper_trading.py` の環境変数テストデータへ、
次の2設定を復元しました。

- `KATANA_COMMISSION_PER_ORDER=100`
- `KATANA_SLIPPAGE_RATE=0.001`

本体コードの不具合ではなく、Sprint92-2で生成したテストファイル側の
入力データ不足を修正するものです。

## 再テスト

```powershell
pytest `
  tests/test_paper_trading_composition.py `
  tests/test_run_paper_trading.py `
  tests/test_production_readiness.py `
  tests/test_realtime_market_service.py -q
```
