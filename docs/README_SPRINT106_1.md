# Sprint106-1 Dynamic Watchlist Automation

## 目的

営業日8:20に、kabuステーション由来でSQLiteへ蓄積された市場データから
Dynamic Watchlistを生成し、watchlist.txtへ安全に適用します。

## 自動運転フロー

```text
08:20 Dynamic Watchlist生成・適用
08:40 Morning Pre-Flight
08:45 Paper Trading Scheduler開始窓
09:00 Paper Trading開始
15:40 Daily Report
```

## 資金条件

```text
運用資金上限  1,000,000円
購入予算        950,000円
売買単位              100株
```

## 初期最低銘柄数

現時点のDry Runでは5銘柄が適格だったため、初期運用では
`minimum_symbols=5`としています。

候補母集団と履歴が増えたら、10銘柄以上へ引き上げます。

## 安全動作

- 営業日以外は実行しない
- 同日2回適用しない
- `run_dynamic_watchlist --apply`が成功した場合だけ完了扱い
- 5銘柄未満ならFAILED
- 失敗時は既存watchlist.txtを維持
- Morning Pre-FlightがDynamic Watchlist失敗を検知
- Paper Trading Scheduler Guardが起動を阻止

## 追加・置換ファイル

```text
app/runtime/dynamic_watchlist_schedule_models.py
app/runtime/dynamic_watchlist_scheduler.py
app/run_dynamic_watchlist_scheduler.py

app/runtime/katana_service_models.py
app/runtime/katana_service_manager.py
app/run_katana_service.py

app/runtime/autonomous_operation_models.py
app/runtime/autonomous_operation_validator.py
app/run_autonomous_operation_validation.py

scripts/run_katana_service_task.cmd

tests/test_dynamic_watchlist_scheduler.py
tests/test_dynamic_watchlist_scheduler_service_integration.py
tests/test_autonomous_operation_dynamic_watchlist.py
```

## テスト

```powershell
pytest tests/test_dynamic_watchlist_scheduler.py tests/test_dynamic_watchlist_scheduler_service_integration.py tests/test_autonomous_operation_dynamic_watchlist.py tests/test_dynamic_watchlist_service.py -q
```

## Dry Run

```powershell
python -m app.run_katana_service --dry-run
```

期待値:

```text
dynamic_watchlist_scheduler: enabled=True
morning_preflight_scheduler: enabled=True
daily_report_scheduler: enabled=True
paper_trading_scheduler: enabled=True
paper_trading: enabled=False
```

## 休場日の単発確認

```powershell
python -m app.run_dynamic_watchlist_scheduler --enable --once
```

休場日は`closed_day`になります。

## Service反映

```powershell
schtasks /End /TN "Project KATANA Service"
```

残留プロセスがある場合は停止してから:

```powershell
schtasks /Run /TN "Project KATANA Service"
```

状態ファイル:

```text
reports/service/dynamic_watchlist_schedule.json
```

適用済みマーカー:

```text
reports/service/dynamic_watchlist/YYYY-MM-DD.applied.json
```
