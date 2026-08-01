# Sprint102-5 Daily Report Notification

## 目的

生成済みDaily Trading Reportを、既存のLINE・Discord通知基盤へ配信します。

新しいWebhookや通知チャネルは作りません。

## 追加ファイル

```text
app/notifications/daily_report_formatter.py
app/notifications/daily_report_notification_service.py
app/run_daily_report_notification.py

tests/test_daily_report_formatter.py
tests/test_daily_report_notification_service.py

docs/README_SPRINT102_5.md
```

## 通知経路

```text
reports/daily/YYYY-MM-DD.json
        ↓
DailyReportReader
        ↓
DailyReportNotificationFormatter
        ↓
NotificationGateway
        ↓
LINE / Discord
```

## 通知内容

```text
Report Date
Today's P/L
Trades
Win Rate
Profit Factor
Max Drawdown
Best Strategy
Worst Strategy
Top Symbol
Errors
Recoveries
Notes
```

## テスト

```powershell
pytest tests/test_daily_report_formatter.py tests/test_daily_report_notification_service.py tests/test_notification_gateway.py tests/test_discord_notification_channel.py tests/test_line_notification_channel.py -q
```

既存テスト名に`(1)`等が付いている場合は、新規2テストだけ先に実行できます。

```powershell
pytest tests/test_daily_report_formatter.py tests/test_daily_report_notification_service.py -q
```

## Dry Run

外部送信せず本文を確認します。

```powershell
python -m app.run_daily_report_notification --dry-run
```

日付指定:

```powershell
python -m app.run_daily_report_notification --report-date 2026-08-01 --dry-run
```

## 実送信

`.env`に設定済みのLINE・Discordへ送信します。

```powershell
python -m app.run_daily_report_notification
```

日付指定:

```powershell
python -m app.run_daily_report_notification --report-date 2026-08-01
```

## 安全性

- 実注文は送信しません。
- Paper Trading設定は変更しません。
- 通知チャネルが未設定なら送信せず終了コード2を返します。
- 片方のチャネルが失敗しても、既定ではもう片方の送信を継続します。

## 自動実行

このSprintでは手動送信までです。

次のSprintで、営業日15:40の自動生成・自動通知をService Managerへ統合します。
