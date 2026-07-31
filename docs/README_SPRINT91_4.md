# Sprint91-4 強制シグナルRisk Gate実証

市場やORBシグナルの発生を待たず、決定論的なFake SignalでRisk Gateを
実証します。

## 配置

```text
app/run_risk_gate_proof.py
tests/test_risk_gate_proof.py
run_risk_gate_proof.cmd
docs/README_SPRINT91_4.md
```

## 自動テスト

```powershell
python -m pytest tests/test_risk_gate_proof.py -q
```

## 画面での実証

```powershell
.\run_risk_gate_proof.cmd
```

次の5シナリオを検証します。

1. 1銘柄最大投資額超過をBroker送信前に拒否
2. 日次損失上限超過をBroker送信前に拒否
3. 1日最大エントリー数超過をBroker送信前に拒否
4. 同一銘柄の重複保有をBroker送信前に拒否
5. 日次損失上限到達後もEXITだけは許可

拒否シナリオでは、下流のBroker相当サービスの呼出回数が0であることまで
確認します。許可シナリオでは呼出回数が1になることを確認します。

この検証は以下を使用しません。

- kabuステーション
- J-Quants
- SQLite
- LINE
- Discord
- 実注文

成功時の最後の表示:

```text
ALL RISK GATE PROOFS PASSED
```
