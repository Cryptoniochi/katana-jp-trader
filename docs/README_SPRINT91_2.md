# Sprint91-2 終日運用・Git保存

## 配置

プロジェクトルートへ配置します。

```text
C:\projects\katana\run_katana_short_session.cmd
C:\projects\katana\run_katana_full_session.cmd
C:\projects\katana\save_sprint91_to_git.cmd
```

## 短時間確認

```powershell
.\run_katana_short_session.cmd
```

約10分、30銘柄、20サイクルで実行します。

## 終日確認

kabuステーションを起動してログインし、同じPowerShellで本番用API
パスワードを設定します。

```powershell
$env:KABU_STATION_API_PASSWORD="本番用APIパスワード"
```

9:00前後に次を実行します。

```powershell
.\run_katana_full_session.cmd
```

30秒間隔・最大780サイクルです。ログは次へ保存されます。

```text
logs\sprint91\full_session_YYYYMMDD_HHMMSS.log
```

市場終了をKATANAが先に検知した場合は、780サイクル未満でも正常終了
します。

## Gitへ保存

```powershell
.\save_sprint91_to_git.cmd
```

この処理は次を行います。

1. `git status`
2. KATANAのソース・テスト・docs・運用ファイルをステージ
3. ローカルGitへコミット
4. 最新コミットを表示

GitHubにも保存する場合は、コミット成功後に実行します。

```powershell
git push
```

APIパスワードは環境変数だけで管理し、ファイルやGitへ保存しません。

## 終日テストの合格基準

- Runtime状態: completed
- 失敗サイクル: 0
- Runtimeエラー: なし
- NEW_BARS_SAVED: 1以上
- 保存失敗: 0
- Paper Trading呼出: 1以上
- Signal Engine呼出: 1以上
- ORB評価記録数: 1以上
- LINE・Discordの開始・終了通知成功

シグナル生成と約定が0件でも、条件不成立なら正常です。
