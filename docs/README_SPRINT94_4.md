# Sprint94-4 High Breakout Operation Runner

## 目的

High Breakout運用前の処理を1コマンドへまとめます。

```text
分足 → 日足生成 → 候補抽出 → レポート → 任意でPaper Trading
```

## 追加ファイル

```text
app/run_high_breakout_operation.py
scripts/run_high_breakout_operation.ps1
scripts/run_high_breakout_operation.cmd
tests/test_run_high_breakout_operation.py
```

## 通常実行

```powershell
python -m app.run_high_breakout_operation
```

または:

```powershell
.\scripts\run_high_breakout_operation.ps1
```

## Paper Tradingも起動

```powershell
python -m app.run_high_breakout_operation `
  --start-paper-trading
```

候補が0件の場合はPaper Tradingを起動しません。

## 起動コマンドだけ確認

```powershell
python -m app.run_high_breakout_operation `
  --start-paper-trading `
  --paper-trading-dry-run
```

## テスト

```powershell
pytest `
  tests/test_run_high_breakout_operation.py `
  tests/test_intraday_daily_bar_builder.py `
  tests/test_high_breakout_screening_service.py `
  tests/test_high_breakout_strategy.py -q
```

## 推奨運用

当面はPaper Trading自動起動を使わず、次だけ実行します。

```powershell
python -m app.run_high_breakout_operation
```

候補数とHTMLレポートを確認後、High Breakout単独の
Paper Tradingを手動で開始してください。
