# Sprint91-3 緊急安全修正

## 監査で判明した2つの別問題

### 1. リスク管理未接続

本番Compositionが`RealtimePaperTradingService`へRisk Gateを渡して
いなかったため、注文が従来の無検査経路へフォールバックしていました。

今回の修正では、本番CompositionでRisk Gateを必須化し、未接続なら
起動または注文執行を拒否します。

強制する制限:

- 最大保有銘柄数: 5
- 1銘柄最大投資額: 1,000,000円
- 最大総エクスポージャー: 5,000,000円
- 最低現金残高: 500,000円
- 日次損失上限: 100,000円
- 1日最大新規エントリー: 5
- 同一銘柄の重複保有禁止
- 損失上限到達後もEXIT注文だけは許可

### 2. 15:30の二重通知・異常な対象銘柄数

提示された終了レポートは次の状態でした。

```text
Replay mode: previous-day-replay
対象銘柄数: 103
```

Sprint91の30銘柄kabuステーション運用ではありません。古いReplay
ランタイムまたはWindowsタスクが同時に動作していた可能性が高く、
二重通知の最有力原因です。

修正確認まではWindowsタスクスケジューラの旧KATANAタスクを停止し、
`run_katana_full_session.cmd`も実行しないでください。

## 配置

```text
app/risk/paper_trading_pretrade_risk.py
app/market/realtime_paper_trading_service.py
app/runtime/paper_trading_composition.py

tests/test_paper_trading_pretrade_risk.py
```

後ろ2つは完成版で置換します。

## テスト

```powershell
python -m pytest tests/test_paper_trading_pretrade_risk.py -q
python -m pytest tests/test_realtime_paper_trading_service.py -q
python -m pytest tests/test_paper_trading_composition.py -q
```

## 安全確認

修正後も終日運転は禁止です。まず1銘柄・短時間で、終了レポートの
`リスク判定済みサイクル`が1以上になることを確認します。

Risk判定0のまま注文が生成された場合、修正未反映として直ちに停止します。
