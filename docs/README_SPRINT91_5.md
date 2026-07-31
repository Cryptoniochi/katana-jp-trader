# Sprint91-5 Signal-Risk-Broker Trace

## 目的

本番Paper Trading経路をsignal_id単位で追跡します。

```text
Signal生成
→ Queue登録
→ Risk判定
→ ALLOW/BLOCK
→ Broker実行/スキップ
```

## 配置

```text
app/risk/paper_trading_trace.py
app/risk/paper_trading_pretrade_risk.py          # 完成版で置換
app/market/realtime_paper_trading_service.py     # 完成版で置換
app/runtime/paper_trading_composition.py         # 完成版で置換

tests/test_paper_trading_trace.py
docs/README_SPRINT91_5.md
```

## Trace出力先

```text
logs/risk/paper_trading_trace.jsonl
```

1行1JSONで、各イベントに次を記録します。

- event_type
- signal_id
- code
- action
- quantity
- Risk判定理由
- 日次損益
- エクスポージャー
- Broker実行またはスキップ

APIパスワードや通知トークンは記録しません。

## テスト

```powershell
python -m pytest tests/test_paper_trading_trace.py -q
python -m pytest tests/test_paper_trading_pretrade_risk.py -q
python -m pytest tests/test_realtime_paper_trading_service.py -q
python -m pytest tests/test_paper_trading_composition.py -q
```

## 確認方法

短時間運転後に次を実行します。

```powershell
Get-Content .\logs\risk\paper_trading_trace.jsonl -Tail 30
```

シグナルが発生した場合、同じsignal_idについて少なくとも次が並びます。

許可:

```text
signal_generated
queue_enqueued
risk_evaluated allowed=true
broker_executed
```

拒否:

```text
signal_generated
queue_enqueued
risk_evaluated blocked=true
broker_skipped
```

`signal_generated`があるのに`risk_evaluated`がない場合はFail-Closed違反として
運転を停止します。
