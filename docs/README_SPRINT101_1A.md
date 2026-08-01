# Sprint101-1A Missing Module Fix

## 原因

次の新規モジュールがプロジェクトへ配置されていないため、
Dashboard関連テストのimport時に失敗していました。

```text
app/runtime/operational_readiness_models.py
app/runtime/operational_readiness_service.py
```

## 追加・差し替え対象

ZIP内の相対パスどおりに、すべて上書きしてください。

```text
app/runtime/operational_readiness_models.py
app/runtime/operational_readiness_service.py
app/run_operational_readiness.py

tests/test_operational_readiness_service.py
tests/test_dashboard_operational_readiness_api.py
tests/test_operational_readiness_templates.py
```

## import確認

```powershell
python -c "from app.runtime.operational_readiness_service import OperationalReadinessService; print('import ok')"
```

## 再テスト

```powershell
pytest tests/test_operational_readiness_service.py tests/test_dashboard_operational_readiness_api.py tests/test_operational_readiness_templates.py tests/test_dashboard_launcher.py tests/test_dashboard_web_app.py -q
```
