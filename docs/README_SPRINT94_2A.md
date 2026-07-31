# Sprint94-2A

Sprint94-2で、Sprint93-2Aにて修正済みだったPullbackテスト系列を
旧版へ戻してしまったため、再ブレイク足を復元しました。

修正内容:

```text
高値: 1015 -> 1018
終値: 1014 -> 1017
```

これにより「押し目高値を終値で再上抜け」の条件を満たします。

## 上書き対象

```text
tests/test_realtime_signal_engine.py
```

## 再テスト

```powershell
pytest `
  tests/test_high_breakout_strategy.py `
  tests/test_realtime_signal_engine.py `
  tests/test_paper_trading_composition.py `
  tests/test_run_paper_trading.py `
  tests/test_strategy_registry.py `
  tests/test_realtime_paper_trading_service.py -q
```
