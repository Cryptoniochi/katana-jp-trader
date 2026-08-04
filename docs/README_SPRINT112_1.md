# Sprint112-1 Paper Trading Market-Close Stabilization

## 原因

従来は15:35の`stop_at`まで運転対象でした。
`run_market_session`が15:30に終了すると、Schedulerは子プロセス不在と判断し、
15:35まで約5秒ごとに再起動していました。

## 修正

```text
15:30 market_close_at
    ↓
子Runtimeを安全停止
    ↓
state=completed
    ↓
同じ営業日は再起動禁止
    ↓
翌営業日にロック解除
```

15:30前の異常終了は従来どおり再起動対象です。

## 置換ファイル

```text
app/runtime/scheduled_paper_trading.py
tests/test_scheduled_paper_trading.py
```

## テスト

```powershell
pytest tests/test_scheduled_paper_trading.py -q
```

## 期待効果

```text
15:30以降のruntime_started連続記録を防止
市場終了後通知の大量送信を防止
paper_trading_schedule.jsonがcompletedを維持
翌営業日は通常起動
```

Service Managerの直接起動用`paper_trading=disabled`表示は別問題です。
Dashboard表示統合はSprint112-2で扱います。
