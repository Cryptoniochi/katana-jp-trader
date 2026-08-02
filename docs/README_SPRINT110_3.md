# Sprint110-3 Full Market Watchlist Pipeline

Sprint110-1と110-2を統合し、欠けていた一次スクリーナー関連ファイルも
同梱した完全版です。

## 完成フロー

```text
listed_symbols 約4,000銘柄
        ↓
market_bars 日足
        ↓
UniversePrimaryScreener
        ↓
最大300銘柄
data/universe_candidates.txt
        ↓
DynamicWatchlistService
        ↓
最大50銘柄
watchlist.txt
```

## 一括実行

```powershell
python -m app.run_full_market_watchlist
```

本番適用:

```powershell
python -m app.run_full_market_watchlist --apply
```

## テスト

```powershell
pytest `
  tests/test_listed_symbol_csv_importer.py `
  tests/test_universe_daily_bar_csv_importer.py `
  tests/test_universe_primary_screener.py `
  tests/test_full_market_watchlist_integration.py `
  -q
```

## 個別実行

```powershell
python -m app.run_listed_symbol_import `
  data\listed_symbols.csv

python -m app.run_universe_daily_import `
  data\universe_daily_bars.csv

python -m app.run_universe_primary_screening

python -m app.run_dynamic_watchlist `
  --require-candidate-universe
```

候補ファイルを使わず従来の全market_bars評価へ戻す場合:

```powershell
python -m app.run_dynamic_watchlist `
  --ignore-candidate-universe
```
