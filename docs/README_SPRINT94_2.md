# Sprint94-2 High Breakout Realtime Strategy

## 追加・置換

```text
app/backtest/high_breakout_strategy.py
app/market/high_breakout_candidate_provider.py
app/market/realtime_signal_engine.py
app/runtime/paper_trading_composition.py
app/run_paper_trading.py

tests/test_high_breakout_strategy.py
tests/test_paper_trading_composition.py
tests/test_run_paper_trading.py
```

## 動作

- `high_breakout_candidates`に当日候補がある銘柄だけ評価
- 直前4本の5分足高値を終値で上抜け
- 出来高倍率を確認
- BUYを生成
- 損切り、利確、トレーリング、15:20強制決済

## 事前処理

High Breakoutを使用する前に候補抽出を実行します。

```powershell
python -m app.run_high_breakout_screening
```

## 有効化

```text
KATANA_ENABLED_STRATEGIES=high-breakout
```

3戦略:

```text
KATANA_ENABLED_STRATEGIES=orb,pullback,high-breakout
```

## テスト

```powershell
pytest `
  tests/test_high_breakout_strategy.py `
  tests/test_realtime_signal_engine.py `
  tests/test_paper_trading_composition.py `
  tests/test_run_paper_trading.py `
  tests/test_strategy_registry.py `
  tests/test_realtime_paper_trading_service.py -q
```
