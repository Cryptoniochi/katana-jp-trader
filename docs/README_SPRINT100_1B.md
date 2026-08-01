# Sprint100-1B

## 原因

既存テストは`generated_at`を固定日時にしていましたが、
新しい鮮度監視は現在時刻との差が30秒を超えると`stale`にします。

テストが`now_provider`を指定していなかったため、
実行時点では固定日時が古くなり、正しく`stale`判定されていました。

## 修正

テストへ固定の現在時刻を注入し、状態ファイルが10秒前の
新鮮なデータであることを明示しました。

## 差し替え対象

```text
tests/test_katana_service_status_reader.py
```

## 再テスト

```powershell
pytest tests/test_operational_log_rotation.py tests/test_katana_service_status_staleness.py tests/test_operational_status_templates.py tests/test_katana_service_status_reader.py tests/test_dashboard_service_status_api.py tests/test_dashboard_service_status_templates.py -q
```
