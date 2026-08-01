# Sprint104-2 Morning Pre-Flight Notification

## 目的

Sprint104-1のAutonomous Operation Validatorを実行し、
結果をLINE・DiscordへMorning Checkとして送信します。

このSprintではまだ時刻スケジューラへ統合しません。
まず手動送信を安定させます。

## 追加ファイル

```text
app/notifications/morning_preflight_formatter.py
app/notifications/morning_preflight_notification_service.py
app/run_morning_preflight.py

tests/test_morning_preflight_formatter.py
tests/test_morning_preflight_notification_service.py

docs/README_SPRINT104_2.md
```

## Dry Run

```powershell
python -m app.run_morning_preflight --dry-run
```

## 実送信

```powershell
python -m app.run_morning_preflight
```

READY時の例:

```text
[OK] KATANA Service
[OK] Service Components
[OK] Paper Trading Scheduler
[OK] Daily Report Scheduler
[OK] Watchlist
[OK] Database
[OK] Production Readiness

Overall
READY

Trading
READY FOR TRADING
```

BLOCKED時は失敗項目と理由を通知します。

## 通知ルール

Morning Checkは朝に送るため、静穏時間抑止を無効化します。

```python
quiet_hours_suppressed_severities=frozenset()
```

重複抑止も無効です。

```python
duplicate_cooldown_seconds=0
```

## テスト

```powershell
pytest tests/test_morning_preflight_formatter.py tests/test_morning_preflight_notification_service.py tests/test_autonomous_operation_validator.py -q
```

## 次のSprint

Sprint104-3で、営業日8:40の自動実行と、
Paper Trading Schedulerの開始禁止Guardを追加します。
