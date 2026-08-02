# Sprint107-1 Dynamic Watchlist Feature Engine

## 目的

Dynamic Watchlistへ説明可能な特徴量スコアと、
銘柄ごとの戦略適性を追加します。

## 総合100点

```text
流動性                 20点
出来高急増             15点
ATR・値動き            15点
Gap                    10点
VWAP乖離               10点
ORB適性                10点
Pullback適性           10点
High Breakout適性       5点
```

各スコアは上限内に正規化され、総合点は100点以下です。

## Rating Tier

```text
A+  80点以上
A   65点以上
B   50点以上
C   50点未満
```

`strict` / `fallback`はデータ品質の区分として残し、
`A+ / A / B / C`は銘柄評価として別に保持します。

## Preferred Strategy

各銘柄について次から最高点の戦略を記録します。

```text
orb
pullback
high-breakout
```

この段階では推奨戦略をレポートへ記録するだけで、
Paper Tradingの戦略実行を制限しません。

## 追加・置換ファイル

```text
app/dynamic_watchlist/dynamic_watchlist_feature_models.py
app/dynamic_watchlist/dynamic_watchlist_feature_engine.py
app/dynamic_watchlist/dynamic_watchlist_models.py
app/dynamic_watchlist/dynamic_watchlist_service.py
app/run_dynamic_watchlist.py

tests/test_dynamic_watchlist_feature_engine.py
tests/test_dynamic_watchlist_feature_integration.py
tests/test_dynamic_watchlist_service.py
```

## テスト

```powershell
pytest tests/test_dynamic_watchlist_feature_engine.py tests/test_dynamic_watchlist_feature_integration.py tests/test_dynamic_watchlist_service.py -q
```

## Dry Run

```powershell
python -m app.run_dynamic_watchlist
```

出力例:

```text
Rank  Code  Tier  Strategy       Score  Price  100-share amount
1     6758  A     orb            66.80  3804   380400
```

詳細スコアはJSON・CSVへ保存されます。

```text
reports/watchlist/latest.json
reports/watchlist/dynamic_watchlist_YYYY-MM-DD.json
reports/watchlist/dynamic_watchlist_YYYY-MM-DD.csv
```

## 次のSprint

Sprint107-2でDashboardへランキングと各戦略スコアを表示します。
