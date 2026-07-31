# Sprint93-2A

Pullback Breakoutのテスト系列を修正しました。

原因:
- 押し目高値が1015
- 再ブレイク足の高値も1015
- 終値は1014

このため、戦略仕様の「押し目高値を終値で再上抜け」を満たしていませんでした。

修正:
- 再ブレイク足の高値を1018
- 終値を1017

本体戦略コードの変更はありません。

## 再テスト

```powershell
pytest `
  tests/test_pullback_breakout_strategy.py `
  tests/test_strategy_registry.py `
  tests/test_realtime_signal_engine.py `
  tests/test_paper_trading_composition.py `
  tests/test_run_paper_trading.py `
  tests/test_realtime_paper_trading_service.py -q
```
