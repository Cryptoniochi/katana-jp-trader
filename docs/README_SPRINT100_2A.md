# Sprint100-2A

## 原因

`test_status_contains_uptime_and_start_event`で、現在時刻を3件だけ持つ
iteratorから返していました。

Service Managerは状態ファイル書き込みやイベント記録でも現在時刻を取得するため、
想定より多く`now_provider()`が呼ばれ、iteratorが尽きて`StopIteration`になりました。

## 修正

iteratorを廃止し、テスト内の`current_time`を返す固定Providerへ変更しました。

Service開始後に`current_time`を65秒進めてから状態を取得するため、
`uptime_seconds == 65`を安定して確認できます。

## 差し替え対象

```text
tests/test_katana_service_self_healing.py
```

## 再テスト

```powershell
pytest tests/test_katana_service_self_healing.py tests/test_kabu_station_readiness_probe.py tests/test_katana_service_runtime_status_reader.py tests/test_self_healing_dashboard_templates.py tests/test_katana_service_manager.py tests/test_run_katana_service.py -q
```
