# Sprint94-1C High Breakout Screening CLI

## 追加ファイル

```text
app/strategy/high_breakout_screening_service.py
app/strategy/high_breakout_reporter.py
app/run_high_breakout_screening.py

tests/test_high_breakout_screening_service.py
tests/test_high_breakout_reporter.py
```

## CSV入力

必須列:

```text
code,traded_at,open,high,low,close,volume
```

実行:

```powershell
python -m app.run_high_breakout_screening `
  --csv-path data\daily_prices.csv
```

## SQLite入力

`market_bars`の`interval_minutes=1440`を日足として読み込みます。

```powershell
python -m app.run_high_breakout_screening `
  --database-path data\katana.db
```

銘柄は`config\watchlist.txt`から読み込みます。
CLIで直接指定することもできます。

```powershell
python -m app.run_high_breakout_screening `
  --code 7203 `
  --code 6758
```

## 出力

```text
reports/high_breakout/candidates.json
reports/high_breakout/candidates.csv
reports/high_breakout/candidates.html
reports/high_breakout/summary.txt
```

候補は同時に`high_breakout_candidates`へ保存されます。

## テスト

```powershell
pytest `
  tests/test_high_breakout_screening_service.py `
  tests/test_high_breakout_reporter.py `
  tests/test_high_breakout_candidate_repository.py `
  tests/test_high_breakout_screener.py -q
```
