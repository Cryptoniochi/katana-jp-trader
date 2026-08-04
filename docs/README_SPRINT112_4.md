# Sprint112-4 JST Display and Today's Executions

- モバイルDashboardの主要日時をJST表示
- `Recent Trades`を`Today's Executions`へ変更
- 日本時間の当日約定だけを表示
- 過去のテスト約定・旧運用約定を当日画面から除外
- 当日約定なしは`No executions today.`

現在のProduction CompositionにはExecutionNotificationServiceが接続済みで、
LINE・Discordが有効なら保存済み約定ごとに通知される構成です。

置換:
- app/dashboard/templates/mobile_dashboard.html
- tests/test_dashboard_web_app.py
