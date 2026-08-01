# Sprint102-3 Daily Report Dashboard API

## 目的

Sprint102-2で生成した日次レポートJSONを読み込み、
Dashboard APIから取得できるようにします。

このSprintではHTML・CSS・LINE・Discordは変更しません。

## 追加・置換ファイル

```text
app/dashboard/daily_report_reader.py
app/dashboard/dashboard_launcher.py
app/dashboard/dashboard_web_app.py

tests/test_daily_report_reader.py
tests/test_dashboard_daily_report_api.py

docs/README_SPRINT102_3.md
```

## API

最新レポート:

```text
GET /api/dashboard/daily-report
```

日付指定:

```text
GET /api/dashboard/daily-report?report_date=2026-08-03
```

日付形式は`YYYY-MM-DD`です。

## 読み込み元

```text
reports/daily/YYYY-MM-DD.json
```

最新レポートは、ISO日付形式のファイル名から選択します。
`summary.json`など日付ではないJSONは無視します。

## テスト

```powershell
pytest tests/test_daily_report_reader.py tests/test_dashboard_daily_report_api.py tests/test_dashboard_launcher.py tests/test_dashboard_web_app.py -q
```

## 確認

Serviceタスク再起動後:

```powershell
schtasks /End /TN "Project KATANA Service"
schtasks /Run /TN "Project KATANA Service"
```

API確認:

```powershell
Invoke-RestMethod http://100.64.14.23:8000/api/dashboard/daily-report
```

レポート未生成時は`available=false`を返します。
