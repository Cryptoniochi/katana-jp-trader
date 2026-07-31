# Sprint91-5B 実行経路監査

アップロードされた現在の`paper_trading_composition.py`を確認したところ、
Trace Recorderの生成はありましたが、次の呼出がありませんでした。

```python
trace_recorder.runtime_started(...)
```

そのためファイルだけが0バイトで作られ、`runtime_started`が記録されて
いませんでした。

## 配置

```text
app/runtime/paper_trading_composition.py       # 完成版で置換
audit_katana_execution_path.py
tests/test_execution_path_audit.py
docs/README_SPRINT91_5B.md
```

## 監査

```powershell
python audit_katana_execution_path.py
```

成功時:

```text
run_module_composition_identity=YES
composition_has_runtime_started=YES
settings_normalizes_trace_path=YES
trace_path_under_project_root=YES

AUDIT PASSED
```

## テスト

```powershell
python -m pytest tests/test_execution_path_audit.py -q
python -m pytest tests/test_paper_trading_trace_initialization.py -q
python -m pytest tests/test_paper_trading_composition.py -q
```

## 本番経路確認

監査とテストの後に短時間起動します。

```powershell
$env:KABU_STATION_API_PASSWORD="本番用APIパスワード"
.\run_katana_risk_validation.cmd
```

終了後:

```powershell
Get-Content .\logs\risk\paper_trading_trace.jsonl -Tail 10
```

`runtime_started`が表示されれば修正完了です。
