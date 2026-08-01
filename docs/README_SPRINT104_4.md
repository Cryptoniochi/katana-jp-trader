# Sprint104-4 Automated Morning Pre-Flight

## 目的

営業日8:40にMorning Pre-Flightを自動実行し、
LINE・Discordへ1日1回だけ通知します。

## 追加・置換ファイル

```text
app/runtime/morning_preflight_schedule_models.py
app/runtime/morning_preflight_scheduler.py
app/run_morning_preflight_scheduler.py

app/runtime/katana_service_models.py
app/runtime/katana_service_manager.py
app/run_katana_service.py

tests/test_morning_preflight_scheduler.py
tests/test_morning_preflight_scheduler_service_integration.py

docs/README_SPRINT104_4.md
```

## 自動実行フロー

```text
営業日判定
  ↓
08:40まで待機
  ↓
python -m app.run_morning_preflight
  ↓
LINE・Discord通知
  ↓
送信済みマーカー保存
```

## 重複防止

```text
reports/service/morning_preflight/YYYY-MM-DD.sent.json
```

同日中にServiceが再起動しても再送信しません。

## 状態ファイル

```text
reports/service/morning_preflight_schedule.json
```

## テスト

```powershell
pytest tests/test_morning_preflight_scheduler.py tests/test_morning_preflight_scheduler_service_integration.py tests/test_morning_preflight_formatter.py tests/test_morning_preflight_notification_service.py tests/test_autonomous_operation_validator.py -q
```

## Service Dry Run

```powershell
python -m app.run_katana_service --dry-run
```

期待値:

```text
morning_preflight_scheduler: enabled=True
daily_report_scheduler: enabled=True
paper_trading_scheduler: enabled=True
paper_trading: enabled=False
```

## Serviceへ反映

Windowsタスクの起動コマンドへ次を追加してください。

```text
--enable-morning-preflight-schedule
```

その後Serviceを完全再起動します。

```powershell
schtasks /End /TN "Project KATANA Service"
schtasks /Run /TN "Project KATANA Service"
```

## 手動状態確認

```powershell
python -m app.run_morning_preflight_scheduler --once
```

休場日は`closed_day`になります。
