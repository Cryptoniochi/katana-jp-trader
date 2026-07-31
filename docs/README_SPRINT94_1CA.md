# Sprint94-1CA

`test_service_returns_empty_for_non_breakout` のテスト用日足を修正しました。

## 原因

旧テストは終値だけを前日安値へ変更していましたが、当日の安値よりも
低い終値になり、`HistoricalBar` のOHLC整合性検証で拒否されていました。

## 修正

最新日足を次の条件に変更しました。

- 高値は直前高値と同値
- 終値は直前高値を1円下回る
- 始値・終値は当日高値と安値の範囲内
- 出来高はそのまま

これにより「有効な日足だが新高値ではない」テストになります。

## 再テスト

```powershell
pytest `
  tests/test_high_breakout_screening_service.py `
  tests/test_high_breakout_reporter.py `
  tests/test_high_breakout_candidate_repository.py `
  tests/test_high_breakout_screener.py -q
```
