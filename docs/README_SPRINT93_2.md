# Sprint93-2 Pullback Breakout

## 追加戦略

5分足だけで完結する `pullback-breakout-v1` を追加します。

判定:

1. 指定期間の上昇を確認
2. 浅すぎず深すぎない押し目を確認
3. 押し目高値を終値で再上抜け
4. 出来高倍率・売買代金・株価帯を確認
5. BUYを生成

決済:

- 固定損切り
- 固定利確
- トレーリングストップ
- 15:20強制決済

## 戦略の有効化

ORBのみ（既定）:

```text
KATANA_ENABLED_STRATEGIES=orb
```

Pullbackのみ:

```text
KATANA_ENABLED_STRATEGIES=pullback
```

両方:

```text
KATANA_ENABLED_STRATEGIES=orb,pullback
```

CLIでも指定できます。

```powershell
python -m app.run_paper_trading `
  --strategy orb `
  --strategy pullback
```

## テスト

```powershell
pytest `
  tests/test_pullback_breakout_strategy.py `
  tests/test_strategy_registry.py `
  tests/test_realtime_signal_engine.py `
  tests/test_paper_trading_composition.py `
  tests/test_run_paper_trading.py `
  tests/test_realtime_paper_trading_service.py -q
```

最初の実市場検証では、ORBとPullbackを同時稼働させず、
それぞれ別DBで単独運転して比較することを推奨します。
