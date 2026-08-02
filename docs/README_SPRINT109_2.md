# Sprint109-2 Learning Feedback Integration

## 目的

Sprint109-1で生成した`strategy_learning_summary`を、
Dynamic WatchlistのランキングとStrategy Routingへ安全に反映します。

## 処理フロー

```text
trade_journal
    ↓
Strategy Learning
    ↓
strategy_learning_summary
    ↓
Dynamic Watchlist
    ↓
Technical Score + Historical Score
    ↓
Learning-adjusted Preferred Strategy
    ↓
Strategy Routing
```

## スコア

```text
technical_score
historical_score
total_score = min(100, technical_score + historical_score)
```

初期係数:

```text
learning_total_score_weight=1.0
learning_strategy_score_weight=0.25
```

戦略選択では、各戦略のテクニカル適性へ
`historical_score × 0.25`を加えます。

総合ランキングには最大20点を加えますが、合計は100点で上限を設けます。

## 安全条件

次の条件を満たす学習結果だけを使用します。

```text
eligible_for_feedback = true
既知の戦略名
historical_score 0〜20
```

取引件数が最低件数未満の結果は無視されます。

学習テーブルが存在しない場合も、従来のテクニカルスコアだけで動作します。

## 追加・置換ファイル

```text
app/learning/strategy_learning_feedback.py

app/dynamic_watchlist/dynamic_watchlist_models.py
app/dynamic_watchlist/dynamic_watchlist_service.py
app/dynamic_watchlist/strategy_routing_repository.py
app/run_dynamic_watchlist.py

tests/test_strategy_learning_feedback.py
tests/test_dynamic_watchlist_learning_integration.py
tests/test_strategy_routing_learning_feedback.py
```

Sprint109-1のLearningファイルも引き続き必要です。

## テスト

```powershell
pytest tests/test_strategy_learning_feedback.py tests/test_dynamic_watchlist_learning_integration.py tests/test_strategy_routing_learning_feedback.py tests/test_dynamic_watchlist_service.py tests/test_strategy_routing_repository.py -q
```

## 実行順

まずLearningを更新します。

```powershell
python -m app.run_strategy_learning
```

次にDynamic Watchlistを確認します。

```powershell
python -m app.run_dynamic_watchlist
```

表示例:

```text
Rank Code Tier Strategy       Tech   Hist  Total
1    7203 A    pullback      57.40  12.00  69.40
```

Learningを一時的に無効化:

```powershell
python -m app.run_dynamic_watchlist --disable-learning-feedback
```

## 注意

取引履歴が少ない現在は、`historical_score=0`の銘柄が多くなります。
これは正常です。10件以上の完了取引が蓄積した銘柄・戦略から順に反映されます。
