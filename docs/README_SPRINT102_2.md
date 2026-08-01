# Sprint102-2 Daily Report Service

## 目的

Sprint102-1の日次レポートモデルを使い、取引データから
日次損益と各種統計を生成します。

Dashboard、LINE、Discordにはまだ接続しません。

## 追加ファイル

```text
app/runtime/daily_report_service.py
app/run_daily_report.py
tests/test_daily_report_service.py
docs/README_SPRINT102_2.md
```

## 集計項目

```text
取引件数
勝ち・負け・引き分け件数
Gross Profit
Gross Loss
Net P/L
勝率
Profit Factor
平均利益
平均損失
最大ドローダウン
戦略別集計
銘柄別集計
```

## SQLite対応

次のテーブル名を順に探索します。

```text
trade_journal
paper_trades
trades
```

次の列名候補を自動判定します。

```text
決済日時:
closed_at / exited_at / exit_at / completed_at

銘柄:
symbol / code / stock_code

戦略:
strategy_name / strategy

実現損益:
realized_profit_loss / profit_loss / pnl / realized_pnl
```

実際のDBスキーマが上記と異なる場合は、推測で処理せず
必要な列一覧を含むエラーを返します。

## テスト

```powershell
pytest tests/test_daily_report_models.py tests/test_daily_report_service.py -q
```

## CLI

```powershell
python -m app.run_daily_report --report-date 2026-08-03
```

出力先:

```text
reports/daily/2026-08-03.json
```

## 次のSprint

Sprint102-3で、生成済みJSONを読み取るDashboard APIを追加します。
