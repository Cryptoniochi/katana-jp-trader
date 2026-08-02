# Sprint110-1 Full Market Universe Foundation

## 目的

現行Dynamic Watchlistの母集団は、SQLiteに価格履歴がある107銘柄です。

このSprintでは、東証全市場に相当する約4,000銘柄を管理し、
一次スクリーニングで最大300銘柄へ絞り込む基盤を追加します。

## 構成

```text
上場銘柄マスターCSV
        ↓
listed_symbols
        ↓
普通株・市場区分フィルター
        ↓
日足価格・出来高・売買代金
        ↓
100株95万円以下
        ↓
最大300銘柄
        ↓
data/universe_candidates.txt
```

## 追加ファイル

```text
app/universe/__init__.py
app/universe/universe_models.py
app/universe/listed_symbol_repository.py
app/universe/listed_symbol_csv_importer.py
app/universe/universe_primary_screener.py

app/run_listed_symbol_import.py
app/run_universe_primary_screening.py

tests/test_listed_symbol_csv_importer.py
tests/test_universe_primary_screener.py
```

## 銘柄マスター取込

CSVには、次の列を使用できます。

```text
code / 銘柄コード
name / 銘柄名
market / 市場区分 / 市場・商品区分
security_type / 商品区分
trading_unit / 単元株数 / 売買単位
```

文字コードは次を自動判定します。

```text
UTF-8 BOM
CP932
UTF-8
```

実行例:

```powershell
python -m app.run_listed_symbol_import `
  data\listed_symbols.csv
```

結果はSQLiteの次のテーブルへ保存されます。

```text
listed_symbols
```

## 一次スクリーニング

```powershell
python -m app.run_universe_primary_screening
```

初期条件:

```text
市場区分         Prime / Standard / Growth
証券種別         common_stock
最大購入金額     950,000円
最低株価         100円
最高株価         9,500円
最低平均出来高   5,000株
最低平均売買代金 5,000,000円
最大候補数       300銘柄
```

出力:

```text
reports/universe/primary_screening_latest.json
data/universe_candidates.txt
```

## テスト

```powershell
pytest tests/test_listed_symbol_csv_importer.py tests/test_universe_primary_screener.py -q
```

## 現時点の制約

このSprintで4,000銘柄のマスターは管理できますが、
一次スクリーニングで評価できるのは、SQLiteの`market_bars`に
日足データが存在する銘柄です。

したがって現在の107銘柄しか日足がなければ、
`universe_count`は約4,000でも`evaluated_count`は107前後です。

次のSprint110-2では、全市場の日足データを段階的に蓄積する
Universe Market Data Collectorを追加します。
kabuステーションの最大50銘柄リアルタイム枠とは分離して実装します。
