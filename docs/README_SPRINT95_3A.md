# Sprint95-3A

Windowsで失敗していたPath比較テストを修正しました。

## 差し替え対象

```text
tests/test_run_trade_journal.py
```

## 修正内容

文字列末尾比較:

```python
str(arguments.database_path).endswith("data/test.db")
```

を、OS非依存のPath比較へ変更しました。

```python
arguments.database_path == Path("data/test.db")
```

## 再テスト

```powershell
pytest `
  tests/test_trade_journal_repository.py `
  tests/test_trade_journal_service.py `
  tests/test_run_trade_journal.py `
  tests/test_dashboard_strategy_service.py `
  tests/test_dashboard_strategy_web_api.py `
  tests/test_trade_execution_repository.py -q
```
