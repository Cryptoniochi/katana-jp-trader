# Sprint91-3B Risk Gate強制検証

## 配置

```text
app/run_paper_trading.py                         # 完成版で置換
tests/test_run_paper_trading.py                  # 完成版で置換
tests/test_production_risk_gate_integration.py
run_katana_risk_validation.cmd
docs/README_SPRINT91_3B.md
```

## 今回の追加

リスク上限をCLIまたは環境変数から明示できるようにしました。

```text
--max-position-count
--max-position-value
--max-total-exposure
--minimum-cash-balance
--max-daily-loss
--max-daily-entries
```

起動時ログにも全リスク上限を表示します。設定誤りを運転前に確認できます。

## テスト

```powershell
python -m pytest tests/test_production_risk_gate_integration.py -q
python -m pytest tests/test_run_paper_trading.py -q
python -m pytest tests/test_paper_trading_pretrade_risk.py -q
python -m pytest tests/test_realtime_paper_trading_service.py -q
python -m pytest tests/test_paper_trading_composition.py -q
```

## 強制リスク検証

この検証は非常に厳しい上限を使います。

```text
最大保有銘柄数: 1
1銘柄最大投資額: 100,000円
最大総エクスポージャー: 100,000円
最低現金残高: 9,900,000円
日次損失上限: 1,000円
1日最大エントリー: 1
```

市場時間中に実行します。

```powershell
.\run_katana_risk_validation.cmd
```

注文候補が発生した場合はRisk Gateで許可または拒否され、Broker送信前に
必ず判定されます。終了レポートでリスク判定回数・停止回数を確認します。

この検証が終わるまで終日運転は再開しません。
