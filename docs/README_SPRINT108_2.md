# Sprint108-2 Realtime Strategy Routing

## 目的

Dynamic Watchlistの`preferred_strategy`を、実際の
`RealtimeSignalEngine`とPaper Trading Compositionへ接続します。

```text
Dynamic Watchlist latest.json
        ↓
Strategy Routing Repository
        ↓
SymbolStrategyRouter
        ↓
RealtimeSignalEngine
        ↓
銘柄ごとのStrategy Registry
        ↓
Paper Trading
```

## 置換ファイル

```text
app/market/realtime_signal_engine.py
app/runtime/paper_trading_composition.py
```

## 追加テスト

```text
tests/test_realtime_signal_engine_strategy_routing.py
tests/test_paper_trading_composition_strategy_routing.py
```

Sprint108-1の次のファイルも必要です。

```text
app/dynamic_watchlist/strategy_routing_models.py
app/dynamic_watchlist/strategy_routing_repository.py
app/market/symbol_strategy_router.py
```

## Routing動作

Dynamic Watchlistにルートがある場合:

```text
7203 → pullbackのみ
9984 → orbのみ
```

ルートがない場合:

```text
enabled_strategy_namesに設定された全戦略
```

へ安全にFallbackします。

推奨戦略がグローバル設定で無効の場合も、グローバル設定へFallbackします。
意図せず無戦略になることはありません。

## Composition設定

初期値:

```text
strategy_routing_enabled=True
strategy_routing_report_path=reports/watchlist/latest.json
strategy_routing_minimum_rating_tier=C
strategy_routing_minimum_total_score=0
strategy_routing_fail_open=True
```

`fail_open=True`では、レポートが存在しない、または読み込めない場合、
従来の`enabled_strategy_names`で運用を継続します。

厳格に停止したい場合:

```python
strategy_routing_fail_open=False
```

## テスト

```powershell
pytest tests/test_realtime_signal_engine_strategy_routing.py tests/test_paper_trading_composition_strategy_routing.py tests/test_realtime_signal_engine.py tests/test_strategy_routing_repository.py tests/test_symbol_strategy_router.py -q
```

## Production Readiness

```powershell
python -m app.run_paper_trading --check
```

## ルート確認

```powershell
python -m app.run_strategy_routing
```

## 注意

このSprintで銘柄別戦略ルーティングはPaper Trading本体へ接続されます。

ただし、現在のDynamic Watchlistスコアは実績データによる十分な
キャリブレーション前です。初期ペーパートレードでは、約定・損益・
シグナル数を戦略別に観察してからTierや最低スコアを引き上げてください。
