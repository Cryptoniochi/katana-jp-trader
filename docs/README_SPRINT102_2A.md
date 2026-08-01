# Sprint102-2A Breakdown Ordering Test Fix

## 原因

日次レポートの戦略別集計は、`net_profit_loss`の降順で並びます。

テストデータでは次の結果です。

```text
ORB       1000 - 400 = 600
Pullback   500 +   0 = 500
```

したがって先頭は`pullback`ではなく`orb`が正しいです。

## 修正

`tests/test_daily_report_service.py`の期待値を実装仕様に合わせ、
各行の損益も明示的に検証するようにしました。

## 差し替え対象

```text
tests/test_daily_report_service.py
```

## 再テスト

```powershell
pytest tests/test_daily_report_models.py tests/test_daily_report_service.py -q
```
