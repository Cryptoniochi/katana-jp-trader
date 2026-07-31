# Sprint91-5A Trace初期化修正

## 原因

アップロードされた最新版では、Trace RecorderはCompositionへ正しく
接続されていました。また、Risk判定はRealtimePaperTradingService側で
既に記録するため、Risk Providerへ追加コールバックを接続する必要は
ありません。追加するとRiskイベントが二重記録になります。

今回修正する問題は次の2点です。

1. TraceファイルをRuntime起動時に必ず作成する
2. 相対パスをプロジェクトルート基準の絶対パスへ正規化する

## 配置

```text
app/risk/paper_trading_trace.py                 # 完成版で置換
app/runtime/paper_trading_composition.py        # 完成版で置換
tests/test_paper_trading_trace_initialization.py
docs/README_SPRINT91_5A.md
```

## テスト

```powershell
python -m pytest tests/test_paper_trading_trace_initialization.py -q
python -m pytest tests/test_paper_trading_trace.py -q
python -m pytest tests/test_realtime_paper_trading_service.py -q
python -m pytest tests/test_paper_trading_composition.py -q
```

## 確認

Paper Tradingを起動した直後から、シグナルが0件でも次が存在します。

```text
C:\projects\katana\logs\risk\paper_trading_trace.jsonl
```

先頭または末尾には`runtime_started`イベントが記録されます。

```powershell
Get-Content .\logs\risk\paper_trading_trace.jsonl -Tail 10
```
