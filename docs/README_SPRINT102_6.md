# Sprint102-6 Automated Daily Report Schedule

## 目的

営業日の15:40に次を自動実行します。

```text
Daily Report生成
        ↓
LINE通知
        ↓
Discord通知
        ↓
送信済みマーカー保存
```

## 追加・置換ファイル

```text
app/runtime/daily_report_schedule_models.py
app/runtime/daily_report_scheduler.py
app/run_daily_report_scheduler.py

app/runtime/katana_service_models.py
app/runtime/katana_service_manager.py
app/run_katana_service.py

scripts/run_katana_service_task.cmd

tests/test_daily_report_scheduler.py
tests/test_daily_report_scheduler_service_integration.py

docs/README_SPRINT102_6.md
```

## 安全性

- 売買注文は送信しません。
- Paper Trading設定は変更しません。
- JPX休場日は処理しません。
- 15:40より前は待機します。
- 送信成功後は日付別マーカーを保存し、重複通知を防ぎます。
- 失敗時は5分待って再試行します。
- 生成と通知の両方が成功した場合だけ完了扱いです。

## 送信済みマーカー

```text
reports/daily/notifications/YYYY-MM-DD.sent.json
```

再送信が必要な場合だけ、対象日のマーカーを手動削除します。

## テスト

```powershell
pytest tests/test_daily_report_scheduler.py tests/test_daily_report_scheduler_service_integration.py tests/test_daily_report_models.py tests/test_daily_report_service.py tests/test_daily_report_formatter.py tests/test_daily_report_notification_service.py -q
```

## 無効状態の確認

```powershell
python -m app.run_daily_report_scheduler --once
```

## Serviceへ反映

更新版CMDには次が追加されています。

```text
--enable-daily-report-schedule
```

Serviceを再起動します。

```powershell
schtasks /End /TN "Project KATANA Service"
```

```powershell
schtasks /Run /TN "Project KATANA Service"
```

## 状態ファイル

```text
reports/service/daily_report_schedule.json
```

確認:

```powershell
Get-Content reports/service/daily_report_schedule.json
```

15:40より前の営業日は`waiting`、休場日は`closed_day`になります。
