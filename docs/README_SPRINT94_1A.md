# Sprint94-1A High Breakout Screener

## 追加ファイル

```text
app/strategy/high_breakout_models.py
app/strategy/high_breakout_screener.py
tests/test_high_breakout_screener.py
```

## 判定内容

最新の日足について次を評価します。

- 20日高値更新
- 60日高値更新
- 年初来高値更新
- 出来高倍率
- 売買代金
- 株価帯
- ATR率
- 候補スコア

## 重要

本Sprintでは候補抽出ロジックのみ追加します。

まだ以下は行いません。

- SQLiteへの候補保存
- CSV/JSON/HTML出力
- Paper Tradingへのリアルタイム接続

## テスト

```powershell
pytest `
  tests/test_high_breakout_screener.py `
  tests/test_historical_backtest_service.py `
  tests/test_market_calendar.py -q
```

## 次Sprint

Sprint94-1Bで次を追加します。

```text
high_breakout_candidates
```

候補保存テーブル、Repository、スキーマバージョン更新を実装します。
