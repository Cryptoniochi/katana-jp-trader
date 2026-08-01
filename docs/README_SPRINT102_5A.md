# Sprint102-5A Quiet Hours Fix

## 原因

実行結果が次でした。

```text
delivered_count=0
failed_count=0
suppressed=True
```

Daily ReportはINFO通知です。

既存Notification Rule EngineはUTCで現在時刻を評価し、
既定設定では22:00～07:00を静穏時間としてINFO通知を抑止します。

日本時間12:09はUTCでは03:09なので、静穏時間に該当していました。

## 修正

Daily Report通知CLI専用Policyでは、静穏時間による抑止を無効化します。

```python
quiet_hours_suppressed_severities=frozenset()
```

重複抑止も引き続き無効です。

```python
duplicate_cooldown_seconds=0
```

また、通知が抑止された場合は理由を表示します。

```text
suppression_reasons=quiet_hours
```

## 差し替え対象

```text
app/run_daily_report_notification.py
tests/test_daily_report_notification_policy.py
```

## テスト

```powershell
pytest tests/test_daily_report_notification_policy.py tests/test_daily_report_formatter.py tests/test_daily_report_notification_service.py -q
```

## 実送信

```powershell
python -m app.run_daily_report_notification --report-date 2026-08-01
```

期待値:

```text
delivered_count=2
failed_count=0
suppressed=False
```
