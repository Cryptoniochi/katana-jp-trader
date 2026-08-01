# Sprint99-3D Fixed CMD Generation Compatibility

## 原因

既存テストは、一時プロジェクト内に
`scripts/run_katana_service_task.cmd`がまだ無い状態で
`write_task_command()`を呼び、CMDが生成されることを期待していました。

Sprint99-3Cでは既存の固定CMDを返すだけだったため、テスト用の一時
ディレクトリではファイルが見つからず失敗しました。

## 修正

`write_task_command()`を次の動作へ変更しました。

1. 固定CMDが既に存在する場合は、そのまま再利用
2. 存在しない場合は、安全な固定内容で新規生成
3. `.venv\Scripts\python.exe`の存在を確認
4. Service Manager・Tailscale待機・ログ出力設定を記述

本番環境では配布済みCMDを再利用するため、通常の運用動作は変わりません。

## 差し替え対象

```text
app/katana_service_autostart.py
tests/test_katana_service_autostart_generation.py
```

## テスト

```powershell
pytest tests/test_katana_service_autostart_generation.py tests/test_katana_service_autostart_compatibility.py tests/test_katana_service_autostart_fixed_cmd.py tests/test_katana_service_autostart.py tests/test_katana_service_unification.py tests/test_katana_service_manager.py tests/test_run_katana_service.py -q
```
