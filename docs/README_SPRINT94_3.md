# Sprint94-3 Intraday to Daily Bars

## 目的

J-Quantsを使わず、kabuステーションから保存した分足を
日足へ集約します。

## 追加ファイル

```text
app/market/intraday_daily_bar_builder.py
app/run_build_daily_bars.py
tests/test_intraday_daily_bar_builder.py
tests/test_run_build_daily_bars.py
```

## 集約方法

同一銘柄・同一営業日の分足から次を作ります。

- 始値: 最初の分足の始値
- 高値: 全分足の最高値
- 安値: 全分足の最安値
- 終値: 最後の分足の終値
- 出来高: 全分足の合計

生成した日足は既存`market_bars`へ保存します。

```text
interval_minutes=1440
data_source=kabu-station-aggregated-daily
```

## 実行

```powershell
python -m app.run_build_daily_bars
```

5分足以外を元にする場合:

```powershell
python -m app.run_build_daily_bars `
  --source-interval-minutes 1
```

## High Breakout候補抽出

日足生成後:

```powershell
python -m app.run_high_breakout_screening
```

## テスト

```powershell
pytest `
  tests/test_intraday_daily_bar_builder.py `
  tests/test_run_build_daily_bars.py `
  tests/test_high_breakout_screening_service.py `
  tests/test_high_breakout_strategy.py -q
```

## 制約

この方法で過去日足を作れるのは、SQLiteに分足が保存されている期間だけです。
High Breakoutの60日判定には、少なくとも60営業日分の分足蓄積が必要です。
