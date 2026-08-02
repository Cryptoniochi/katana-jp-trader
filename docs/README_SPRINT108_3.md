# Sprint108-3 Strategy Routing Trace

## 目的

Dynamic WatchlistからBrokerまでの経路へ、銘柄別戦略ルーティング情報を
監査可能な形で記録します。

## Trace順序

```text
strategy_route_resolved
        ↓
signal_generated
        ↓
queue_enqueued
        ↓
risk_evaluated
        ↓
broker_executed / broker_skipped
```

## strategy_route_resolved Payload

Dynamic Watchlistルートがある場合:

```json
{
  "routed": true,
  "selected_strategy_names": ["pullback"],
  "route_source": "dynamic_watchlist",
  "rating_tier": "B",
  "total_score": 57.4,
  "strategy_score": 6.78,
  "source_generated_at": "2026-08-03T08:20:00+09:00"
}
```

Fallbackの場合:

```json
{
  "routed": false,
  "selected_strategy_names": [
    "orb",
    "pullback",
    "high-breakout"
  ],
  "route_source": "fallback",
  "rating_tier": null,
  "total_score": null,
  "strategy_score": null
}
```

## 置換ファイル

```text
app/market/realtime_paper_trading_service.py
app/risk/paper_trading_trace.py
tests/test_realtime_paper_trading_service.py
tests/test_paper_trading_trace.py
```

## テスト

```powershell
pytest tests/test_realtime_paper_trading_service.py tests/test_paper_trading_trace.py tests/test_realtime_signal_engine_strategy_routing.py tests/test_strategy_routing_repository.py tests/test_symbol_strategy_router.py -q
```

## Trace確認

営業日のPaper Trading後:

```powershell
Get-Content logs\risk\paper_trading_trace.jsonl -Tail 30
```

戦略ルートだけを確認:

```powershell
Get-Content logs\risk\paper_trading_trace.jsonl |
Select-String '"event_type": "strategy_route_resolved"'
```

## 集計項目

`PaperTradingTraceSnapshot`へ次を追加します。

```text
strategy_route_resolved_count
routed_strategy_count
fallback_strategy_count
```

これによりDynamic WatchlistルートとFallbackが何件使用されたかを
Runtime中に集計できます。
