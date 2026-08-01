# Sprint100-1A

`app.runtime.operational_log_rotation` が見つからない問題を修正する再配布です。

## 差し替え・追加対象

```text
app/runtime/operational_log_rotation.py
app/run_operational_maintenance.py
tests/test_operational_log_rotation.py
```

## 確認

```powershell
python -c "from app.runtime.operational_log_rotation import rotate_log_file; print('import ok')"
```

## テスト

```powershell
pytest tests/test_operational_log_rotation.py tests/test_katana_service_status_staleness.py tests/test_operational_status_templates.py tests/test_katana_service_status_reader.py tests/test_dashboard_service_status_api.py tests/test_dashboard_service_status_templates.py -q
```
