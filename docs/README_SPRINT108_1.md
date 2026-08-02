# Sprint108-1 Symbol Strategy Routing Core

## 目的

Dynamic Watchlistの`preferred_strategy`を、銘柄別の戦略ルートとして
安全に読み込める基盤を追加します。

```text
7203 → pullback
8306 → pullback
6758 → pullback
9432 → pullback
9984 → orb
```

## 追加ファイル

```text
app/dynamic_watchlist/strategy_routing_models.py
app/dynamic_watchlist/strategy_routing_repository.py
app/market/symbol_strategy_router.py
app/run_strategy_routing.py

tests/test_strategy_routing_repository.py
tests/test_symbol_strategy_router.py
```

## 安全設計

ルートが存在する銘柄:

```text
preferred_strategyだけを返す
```

ルートが存在しない銘柄:

```text
orb
pullback
high-breakout
```

の既存3戦略へFallbackします。

このため、Dynamic Watchlistレポートの欠落銘柄を誤って無監視にしません。

## テスト

```powershell
pytest tests/test_strategy_routing_repository.py tests/test_symbol_strategy_router.py -q
```

## 手動確認

```powershell
python -m app.run_strategy_routing
```

出力:

```text
reports/watchlist/strategy_routing_latest.json
```

## Tier制限の例

B以上だけを銘柄別ルーティングする場合:

```powershell
python -m app.run_strategy_routing `
  --minimum-rating-tier B
```

C銘柄はルーティング表から外れますが、Paper Trading側では既存3戦略へ
Fallbackさせる設計です。

## このSprintの範囲

このSprintは、戦略ルーティングのモデル、読込、判定、監査レポートまでです。

既存のRealtimeSignalEngineへ直接組み込む変更は、現在のエンジン実装と
Strategy Registryの完成版を確認したうえでSprint108-2で行います。
エンジン全体を推測で置換し、既存のORB診断・High Breakout Candidate・
重複シグナル解決を壊すことを避けるため、段階的に導入します。
