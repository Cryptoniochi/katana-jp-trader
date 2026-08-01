# Sprint102-1 Daily Report Models

## 目的

日次取引レポートのデータ構造だけを追加します。

このSprintでは以下を行いません。

- SQLiteからの集計
- Dashboard API
- Dashboard画面変更
- LINE通知
- Discord通知
- Paper Trading設定変更

## 追加ファイル

```text
app/runtime/daily_report_models.py
tests/test_daily_report_models.py
docs/README_SPRINT102_1.md
```

## モデル

### DailyReportSummary

```text
trade_count
win_count
loss_count
flat_count
gross_profit
gross_loss
net_profit_loss
win_rate
profit_factor
average_win
average_loss
maximum_drawdown
```

### DailyReportBreakdownRow

戦略別・銘柄別の共通集計行です。

```text
key
label
trade_count
net_profit_loss
win_rate
profit_factor
```

### DailyTradingReport

```text
report_date
generated_at
status
summary
strategy_breakdown
symbol_breakdown
error_count
recovery_count
notes
```

`status`は次の3種類です。

```text
complete
partial
empty
```

## テスト

```powershell
pytest tests/test_daily_report_models.py -q
```

## import確認

```powershell
python -c "from app.runtime.daily_report_models import DailyTradingReport; print('import ok')"
```

## 次のSprint

Sprint102-2で、既存のTrade JournalとService Statusを読み、
日次損益・勝率・Profit Factor・戦略別・銘柄別集計を生成する
Serviceを追加します。
