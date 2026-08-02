# Sprint105-2 Dynamic Watchlist Adaptive Selection

## 重要な訂正

Dynamic Watchlistの本番市場データ源はJ-Quantsではなく、
Project KATANAですでに稼働しているkabuステーションAPIです。

このSprintでは、kabuステーションから保存されたローカル市場データを使い、
履歴不足時も候補が全滅しない二段階選定を追加します。

kabuステーションのWebSocket登録上限は50銘柄のため、最終選定結果も
最大50銘柄です。

## 二段階選定

### Strict

```text
20日以上の履歴
データ経過10日以内
平均出来高 50,000株以上
平均売買代金 5,000万円以上
```

### Fallback

```text
3日以上の履歴
データ経過45日以内
平均出来高 5,000株以上
平均売買代金 500万円以上
```

共通必須条件:

```text
100株購入額 <= 950,000円
```

Strict候補を先に並べ、不足分だけFallback候補で補います。

## データ源

```text
kabuステーションAPI
        ↓
Project KATANA Market Monitor
        ↓
SQLite market_bars
        ↓
Dynamic Watchlist
        ↓
最大50銘柄
        ↓
kabuステーション WebSocket登録
```

kabuステーションAPIだけで東証全銘柄の長期履歴を一括取得する機能は
ありません。そのため、現段階ではProject KATANAが蓄積済みの107銘柄を
候補母集団として利用します。蓄積銘柄が増えるほど候補母集団も拡大します。

## 置換ファイル

```text
app/dynamic_watchlist/dynamic_watchlist_models.py
app/dynamic_watchlist/dynamic_watchlist_service.py
app/run_dynamic_watchlist.py
tests/test_dynamic_watchlist_service.py
```

## テスト

```powershell
pytest tests/test_dynamic_watchlist_service.py -q
```

## Dry Run

```powershell
python -m app.run_dynamic_watchlist
```

出力の`Tier`は次のいずれかです。

```text
strict
fallback
```

## 実適用

Dry Runの選定内容を確認した後:

```powershell
python -m app.run_dynamic_watchlist --apply
```

## 次段階

次は08:20自動実行とMorning Pre-Flight連携を実装します。
