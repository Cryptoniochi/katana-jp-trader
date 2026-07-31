# Sprint93-1 Strategy Registry

## 目的

ORBを維持したまま、複数のリアルタイム戦略を安全に登録できる
Strategy Registryを導入します。

## 追加・置換ファイル

```text
app/market/strategy_registry.py
app/market/realtime_signal_engine.py
tests/test_strategy_registry.py
tests/test_realtime_signal_engine.py
```

## 競合処理

- 同一足・同一方向のシグナルは1件へ統合
- `supporting_strategies`へ賛同戦略を保存
- BUYとSELLの競合はすべて抑止
- EXITと新規エントリーの競合もすべて抑止
- 競合回数はDiagnosticsへ保存

## 後方互換

- `strategy_factory`は引き続き使用可能
- 既定構成はORB単独
- 既存ORB診断キーは維持

## テスト

```powershell
pytest `
  tests/test_strategy_registry.py `
  tests/test_realtime_signal_engine.py `
  tests/test_orb_signal_strategy.py `
  tests/test_realtime_paper_trading_service.py -q
```
