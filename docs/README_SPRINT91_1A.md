# Sprint91-1A：30銘柄リアルタイム運用検証

## 配置

```text
C:\projects\katana\watchlist_kabu_30.txt
C:\projects\katana\run_kabu_station_30_symbols.ps1
C:\projects\katana\docs\README_SPRINT91_1A.md
```

## 実行前

1. kabuステーションを起動して通常ログインします。
2. 板・現在値が表示されることを確認します。
3. 同じPowerShellで本番用APIパスワードを設定します。

```powershell
$env:KABU_STATION_API_PASSWORD="本番用APIパスワード"
```

## 30銘柄・短時間確認

約10分間です。

```powershell
.\run_kabu_station_30_symbols.ps1 `
  -MaximumCycles 20 `
  -CycleIntervalSeconds 30
```

## 終日確認

9:00から15:30まで30秒間隔なら、おおむね780サイクルです。

```powershell
.\run_kabu_station_30_symbols.ps1
```

実行ログは次へ保存されます。

```text
logs\sprint91\paper_trading_YYYYMMDD_HHMMSS.log
```

## 合格基準

終了通知・ログで次を確認します。

- 失敗サイクル: 0
- Runtimeエラー: なし
- 市場監視サイクル: 1以上
- 取得足数: 1以上
- NEW_BARS_SAVED: 1以上
- 保存失敗: 0
- Paper Trading呼出: 1以上
- Signal Engine呼出: 1以上
- ORB評価記録数: 1以上
- LINE・Discord通知成功

シグナル生成0件、約定0件は、条件に該当しなければ正常です。

## J-Quants解約判断

30銘柄の短時間確認と、2営業日の終日確認で上記基準を満たしたら、
J-Quantsの分足アドオンを解約する判断へ進みます。

このスクリプトはPaper Tradingを起動するだけで、実注文は送りません。
