# Sprint94-1CB

非ブレイクテストを、生成後のCSVを書き換える方式から、
最初から有効な非ブレイク日足を生成する方式へ変更しました。

これにより、Windows上のファイルハンドルやCSV再書込み、
OHLC値の不整合に影響されません。

## 上書き対象

```text
tests/test_high_breakout_screening_service.py
```

## 再テスト

```powershell
pytest `
  tests/test_high_breakout_screening_service.py `
  tests/test_high_breakout_reporter.py `
  tests/test_high_breakout_candidate_repository.py `
  tests/test_high_breakout_screener.py -q
```
