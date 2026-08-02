# Sprint110-2 Universe Daily Market Data Import

## 目的

Sprint110-1の約4,000銘柄ユニバースを実際に評価するため、
全市場の日足CSVを既存の`market_bars`へ一括取込します。

## 重要な設計判断

kabuステーションAPIはリアルタイム取引向けであり、
Project KATANAの現行構成でも登録銘柄上限50を前提としています。

そのため、約4,000銘柄の過去日足をkabuステーションだけから
収集する設計にはしていません。

```text
全市場の日足データ
        ↓ CSV
Universe Daily Import
        ↓
market_bars（1440分足）
        ↓
Universe Primary Screening
        ↓
最大300銘柄
        ↓
Dynamic Watchlist
        ↓
上位50銘柄をkabuステーションでリアルタイム監視
```

## 追加ファイル

```text
app/universe/universe_daily_bar_models.py
app/universe/universe_daily_bar_repository.py
app/universe/universe_daily_bar_csv_importer.py
app/run_universe_daily_import.py

tests/test_universe_daily_bar_csv_importer.py
```

## CSV形式

英語:

```csv
code,date,open,high,low,close,volume
7203,2026-08-03,3000,3050,2980,3030,1000000
```

日本語:

```csv
銘柄コード,日付,始値,高値,安値,終値,出来高
7203,20260803,3000,3050,2980,3030,1000000
```

文字コード:

```text
UTF-8 BOM
CP932
UTF-8
```

## 実行

```powershell
python -m app.run_universe_daily_import `
  data\universe_daily_bars.csv
```

不正行を飛ばす場合:

```powershell
python -m app.run_universe_daily_import `
  data\universe_daily_bars.csv `
  --skip-invalid-rows
```

## その後

```powershell
python -m app.run_universe_primary_screening
```

日足が約4,000銘柄分入っていれば、概ね次になります。

```text
universe_count ≒ 4,000
evaluated_count ≒ 4,000
selected_count <= 300
```

## テスト

```powershell
pytest tests/test_universe_daily_bar_csv_importer.py tests/test_universe_primary_screener.py -q
```

## 次のSprint

Sprint110-3で一次候補300銘柄から、Dynamic Watchlist用の
二次候補50銘柄へ接続します。

現時点では、日足CSVの取得元そのものはProject KATANAの外部です。
利用するデータ提供元を確定した後、専用Downloader Adapterを追加できます。
