# Sprint103-1A Legacy Scheduler Test Isolation

## 原因

Sprint103-1で、Paper Trading Schedulerは市場セッション起動前に
Production Readiness Checkを実行するようになりました。

既存の`test_business_day_starts_market_session`は、
営業日時刻に市場セッションが起動することだけを検証する旧テストです。

テスト環境には実際のkabuステーション設定がないため、
Readiness Checkが失敗し、期待していた`running`ではなく`failed`になりました。

これは本体の安全機能が正しく動いた結果です。

## 修正

旧ライフサイクルテストでは次を指定し、
スケジュール制御だけを独立して検証します。

```python
readiness_check_enabled=False
```

Readiness Checkそのものは次で別途検証します。

```text
tests/test_scheduled_paper_trading_preflight.py
```

## 差し替え対象

```text
tests/test_scheduled_paper_trading.py
```

## 再テスト

```powershell
pytest tests/test_paper_trading_scheduler_service_integration.py tests/test_scheduled_paper_trading_preflight.py tests/test_service_task_autonomous_operation.py tests/test_scheduled_paper_trading.py tests/test_run_katana_service.py -q
```
