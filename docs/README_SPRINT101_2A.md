# Sprint101-2A Market Calendar Import Fix

## 原因

Project KATANAの営業日カレンダーは次にあります。

```text
app/market/market_calendar.py
```

Sprint101-2では誤って次からimportしていました。

```text
app.market_calendar
```

## 修正

```python
from app.market.market_calendar import TokyoMarketCalendar
```

へ修正しました。

## 差し替え対象

```text
app/runtime/scheduled_paper_trading.py
```

## import確認

```powershell
python -c "from app.runtime.scheduled_paper_trading import ScheduledPaperTradingController; print('import ok')"
```

## 再テスト

```powershell
pytest tests/test_scheduled_paper_trading.py tests/test_paper_trading_schedule_status_reader.py tests/test_dashboard_paper_trading_schedule_api.py tests/test_paper_trading_schedule_templates.py tests/test_dashboard_launcher.py tests/test_dashboard_web_app.py -q
```
