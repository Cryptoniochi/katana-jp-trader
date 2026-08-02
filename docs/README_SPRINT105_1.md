# Sprint105-1 Dynamic Watchlist Core

## 目的

SQLiteに保存された市場データから、当日の監視対象を自動選定します。

初期資金100万円を前提に、1単元を購入できる銘柄だけを候補にします。

## 購入可能条件

```text
購入必要額 = 最新価格 × 売買単位
```

初期設定:

```text
運用資金上限  1,000,000円
購入予算        950,000円
売買単位              100株
```

95万円を上限とし、価格変動や手数料等の余裕を5万円残します。

## スコア

```text
High Breakout適合度  30点
20日モメンタム       20点
流動性               20点
出来高増加率         15点
ATR・値動き          15点
```

## 必須条件

- 1単元の購入額が購入予算以下
- 20日以上の履歴
- データが古すぎない
- 最低平均出来高以上
- 最低平均売買代金以上
- 最大50銘柄
- 重複なし

## 追加ファイル

```text
app/watchlist/dynamic_watchlist_models.py
app/watchlist/dynamic_watchlist_service.py
app/run_dynamic_watchlist.py

tests/test_dynamic_watchlist_service.py
docs/README_SPRINT105_1.md
```

## テスト

```powershell
pytest tests/test_dynamic_watchlist_service.py -q
```

## Dry Run

watchlist.txtは変更しません。

```powershell
python -m app.run_dynamic_watchlist
```

出力レポート:

```text
reports/watchlist/dynamic_watchlist_YYYY-MM-DD.json
reports/watchlist/dynamic_watchlist_YYYY-MM-DD.csv
reports/watchlist/latest.json
```

## 実適用

```powershell
python -m app.run_dynamic_watchlist --apply
```

適用前のwatchlist.txtは次へバックアップされます。

```text
reports/watchlist/backups/watchlist_YYYY-MM-DD.txt
```

候補が最低件数未満なら既存watchlist.txtを維持します。

## 100万円を完全上限にする場合

```powershell
python -m app.run_dynamic_watchlist `
  --purchase-budget 1000000 `
  --apply
```

安全余裕を考えると、初期値95万円のままを推奨します。

## 次のSprint

Dry Run結果を確認後、Sprint105-2で次を追加します。

- 選定根拠のDashboard表示
- 08:20の自動実行
- Morning Pre-FlightへのDynamic Watchlist検証追加
- 100万円運用向けRisk設定
