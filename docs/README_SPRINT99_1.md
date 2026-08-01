# Sprint99-1 KATANA Service Manager

## 方針

現行の市場データ基盤は **kabuステーションAPI** です。
J-QuantsはService Managerの起動・監視対象に含めません。

## 追加ファイル

```text
app/runtime/katana_service_models.py
app/runtime/katana_service_manager.py
app/run_katana_service.py

scripts/run_katana_service.cmd

tests/test_katana_service_manager.py
tests/test_run_katana_service.py
```

## 安全設計

Sprint99-1では次の方針を採用します。

- DashboardとPaper Tradingは別プロセス
- Dashboardは既定で有効
- Paper Tradingは明示的な指定がない限り起動しない
- Paper Tradingの自動再起動は行わない
- Paper Trading起動前に既存の`--check`を実行
- 市場データモードは`kabu-station-realtime`
- Live Orderは実装・起動しない

## Dashboardだけを管理

```powershell
python -m app.run_katana_service
```

これは既存のTailscale対応Dashboard Residentを管理します。

## 起動内容の確認

```powershell
python -m app.run_katana_service --dry-run
```

## Paper Tradingも起動する場合

```powershell
python -m app.run_katana_service --enable-paper-trading
```

既定では次の3戦略を指定します。

```text
orb
pullback
high-breakout
```

戦略を限定する場合:

```powershell
python -m app.run_katana_service --enable-paper-trading --strategy orb
```

## 状態ファイル

```text
reports/service/katana_service_status.json
```

主な内容:

- Service全体状態
- kabuステーションReadiness状態
- Dashboard状態
- Paper Trading状態
- PID
- 再起動回数
- 最終終了コード

## テスト

貼り付けやすい1行です。

```powershell
pytest tests/test_katana_service_manager.py tests/test_run_katana_service.py tests/test_run_dashboard_resident.py tests/test_dashboard_resident_recovery.py -q
```

## 次のSprint

Sprint99-2で状態ファイルを既存Dashboardへ表示し、以下をスマホから確認できるようにします。

- kabuステーションReadiness
- Dashboardプロセス
- Paper Tradingプロセス
- PID
- 再起動回数
- 最終終了コード
