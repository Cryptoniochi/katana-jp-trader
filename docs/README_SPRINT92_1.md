# Sprint92-1 J-Quants依存棚卸し・古いPaper Trading整理

## 配置

```text
audit_jquants_dependencies.py
cleanup_old_paper_validation.py
docs/README_SPRINT92_1.md
```

2つのPythonファイルはProject KATANAのルートへ置きます。

## 1. J-Quants依存棚卸し

```powershell
python audit_jquants_dependencies.py
```

生成物:

```text
reports\jquants_dependency_audit.md
reports\jquants_dependency_audit.json
```

## 2. 古いPaper Tradingの監査

最初は変更を加えない監査モードで実行します。

```powershell
python cleanup_old_paper_validation.py
```

確認対象:

- Windowsタスクスケジューラ
- Project KATANA配下で動くPython/CMDプロセス
- 古い検証DB・ログ・起動スクリプト

生成物:

```text
reports\old_paper_validation_audit.json
```

## 3. 古いタスクとプロセスを停止

監査結果を確認後に実行します。

```powershell
python cleanup_old_paper_validation.py `
  --disable-old-tasks `
  --stop-old-processes
```

現行の`kabu-station-realtime`や
`run_katana_risk_validation`を含む経路は通常除外されます。

## 4. 古い検証ファイルを隔離

削除ではなくarchive配下へ移動します。

```powershell
python cleanup_old_paper_validation.py `
  --archive-old-artifacts
```

移動先:

```text
archive\old_paper_validation_YYYYMMDD_HHMMSS\
```

## 注意

通常は次を指定しません。

```text
--include-current-realtime
```

これを指定すると現行リアルタイム経路も停止対象に含まれます。
