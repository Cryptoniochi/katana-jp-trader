# Sprint99-3C Compatibility Fix

## 原因

既存テストが次の旧APIを参照していました。

```text
write_task_command
```

Sprint99-3Bでは固定CMD方式へ移行したため、この関数を削除していました。
そのため、機能本体ではなく旧テストとの互換性で1件失敗していました。

## 修正

`write_task_command()`を互換APIとして復元しました。

ただし、Sprint99-3B以降はCMDを動的生成しません。
配布済みの次の固定ファイルを返します。

```text
scripts/run_katana_service_task.cmd
```

## 差し替え対象

```text
app/katana_service_autostart.py
tests/test_katana_service_autostart_compatibility.py
```

## テスト

```powershell
pytest tests/test_katana_service_autostart_compatibility.py tests/test_katana_service_autostart_fixed_cmd.py tests/test_katana_service_autostart.py tests/test_katana_service_unification.py tests/test_katana_service_manager.py tests/test_run_katana_service.py -q
```
