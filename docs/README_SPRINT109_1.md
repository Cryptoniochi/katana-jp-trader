# Sprint109-1 Strategy Learning Core

## 目的

既存の`trade_journal`を使い、銘柄×戦略単位の過去成績を
学習用サマリーへ変換します。

既存の戦略別Analyticsは維持し、新しい取引履歴テーブルは作りません。
追加するのは集計結果の保存テーブルだけです。

## 追加ファイル

```text
app/learning/__init__.py
app/learning/strategy_learning_models.py
app/learning/strategy_learning_repository.py
app/learning/strategy_learning_service.py
app/run_strategy_learning.py

tests/test_strategy_learning_service.py
tests/test_strategy_learning_repository.py
```

## 保存テーブル

```text
strategy_learning_summary
```

主キー:

```text
code + strategy_name
```

保存項目:

```text
trade_count
win_rate
profit_factor
expectancy
average_return_rate
average_holding_minutes
sample_confidence
historical_score
eligible_for_feedback
```

## Historical Score

最大20点です。

```text
Win Rate       最大6点
Profit Factor  最大8点
Expectancy     最大4点
Sample Size    最大2点
```

さらに取引数に応じて信頼度を掛けます。

初期値:

```text
最低反映取引数          10
完全信頼取引数          30
```

例えば1勝だけでは高得点にならず、10件未満はDynamic Watchlistへ
反映できない状態として保存されます。

## テスト

```powershell
pytest tests/test_strategy_learning_service.py tests/test_strategy_learning_repository.py -q
```

## 実行

```powershell
python -m app.run_strategy_learning
```

出力:

```text
reports/learning/strategy_learning_latest.json
```

## 注意

このSprintでは学習結果の生成・保存・推奨戦略判定までです。

Dynamic Watchlistの総合スコアやStrategy Routingへ自動反映する変更は
次のSprint109-2で行います。営業日数が少なく取引件数が不足している間は、
推奨戦略は`pending`になります。
