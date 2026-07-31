# Sprint94-1B High Breakout Candidate Repository

## 追加・置換ファイル

```text
app/database.py
app/strategy/high_breakout_candidate_repository.py
app/strategy/high_breakout_models.py
tests/test_high_breakout_candidate_repository.py
docs/README_SPRINT94_1B.md
```

`high_breakout_models.py`はSprint94-1Aと同一内容です。
ZIPをそのまま展開して上書きできます。

## データベース変更

```text
SCHEMA_VERSION = 13
```

新規テーブル:

```text
high_breakout_candidates
```

一意キー:

```text
code + trading_date
```

同一銘柄・同一営業日の再保存はUpsertされます。

## 保存内容

- 銘柄コード
- 営業日
- ブレイク種別
- 終値
- 20日・60日・年初来の直前高値
- 出来高倍率
- 売買代金
- ATR
- ATR率
- 候補スコア

## テスト

```powershell
pytest `
  tests/test_high_breakout_candidate_repository.py `
  tests/test_high_breakout_screener.py `
  tests/test_market_calendar.py -q
```

## 次Sprint

Sprint94-1Cでは次を実装します。

- 日足CSVまたはSQLiteからの入力
- Screener実行CLI
- CSV・JSON・HTMLレポート
- 候補のSQLite保存
