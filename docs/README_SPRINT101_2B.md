# Sprint101-2B Test Import Fix

## 原因

本体ファイルのimportは修正済みでしたが、テストファイル側に旧importが残っていました。

旧:

```python
from app.market_calendar import TokyoMarketCalendar
```

修正後:

```python
from app.market.market_calendar import TokyoMarketCalendar
```

## 差し替え対象

```text
tests/test_scheduled_paper_trading.py
```

## 再テスト

```powershell
pytest tests/test_scheduled_paper_trading.py tests/test_paper_trading_schedule_status_reader.py tests/test_dashboard_paper_trading_schedule_api.py tests/test_paper_trading_schedule_templates.py tests/test_dashboard_launcher.py tests/test_dashboard_web_app.py -q
```
