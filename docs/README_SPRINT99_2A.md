# Sprint99-2A Dashboard Clean Restart

## 原因

ログでは既存APIが200を返す一方、次だけが404でした。

```text
GET /api/dashboard/service-status 404 Not Found
```

配布済みPythonファイルにはルートが存在するため、古いDashboard子プロセスが
TCP 8000を保持したまま残り、新しいタスクが最新コードを読み込めていない
可能性が高い状態です。

Task Schedulerのタスクを終了しても、子のUvicornプロセスが残る場合があります。

## 内容

Dashboard関連ファイル一式を完成版として再収録し、次を追加しました。

```text
scripts/restart_dashboard_clean.cmd
tests/test_dashboard_service_status_route.py
```

`restart_dashboard_clean.cmd`は次を一括で行います。

1. Dashboardタスク停止
2. TCP 8000を保持する残存プロセス停止
3. ポート解放待機
4. Dashboardタスク再実行
5. LISTENING待機
6. `/api/dashboard/service-status` がHTTP 200か確認

## 差し替え対象

ZIP内の相対パスどおりに、すべて上書きしてください。

## テスト

```powershell
pytest tests/test_dashboard_service_status_route.py tests/test_katana_service_status_reader.py tests/test_dashboard_service_status_api.py tests/test_dashboard_service_status_templates.py tests/test_dashboard_launcher.py tests/test_dashboard_web_app.py -q
```

## クリーン再起動

管理者として起動したVS Codeのターミナルで、次の1行を実行します。

```powershell
.\scripts\restart_dashboard_clean.cmd
```

成功時:

```text
HTTP 200 http://100.x.x.x:8000/api/dashboard/service-status
Dashboard refresh completed.
Mobile: http://100.x.x.x:8000/mobile
```

その後、iPhoneの画面を再読み込みしてください。

Service Manager自体をまだ起動していない場合でもAPIは200になり、
Service Status欄には状態ファイル未生成の案内が表示されます。
