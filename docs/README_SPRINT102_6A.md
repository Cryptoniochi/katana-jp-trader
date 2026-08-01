# Sprint102-6A Windows Path Test Fix

## 原因

`Path("data/katana.db")`を文字列化すると、Windowsでは次になります。

```text
data\katana.db
```

既存テストはUnix形式の次の文字列だけを期待していました。

```text
data/katana.db
```

機能本体の問題ではなく、OSごとのパス区切り文字を考慮していない
テストが原因です。

## 修正

コマンド内の`--database-path`直後の値を取得し、
文字列ではなく`Path`として比較します。

```python
assert Path(database_argument) == Path("data/katana.db")
```

## 差し替え対象

```text
tests/test_daily_report_scheduler_service_integration.py
```

## 再テスト

```powershell
pytest tests/test_daily_report_scheduler.py tests/test_daily_report_scheduler_service_integration.py tests/test_daily_report_models.py tests/test_daily_report_service.py tests/test_daily_report_formatter.py tests/test_daily_report_notification_service.py -q
```
