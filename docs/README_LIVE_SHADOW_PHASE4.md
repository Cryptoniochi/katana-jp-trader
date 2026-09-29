# Live Shadow Phase 4

Phase 4 adds a controlled activation path from the resident KATANA service to
the Paper Trading runtime.

## Runtime path

The explicit `--enable-shadow-replication` flag is forwarded through:

1. `app.run_katana_service_resilient`;
2. `app.run_katana_service`;
3. `app.run_scheduled_paper_trading`;
4. `app.run_market_session`;
5. `app.run_paper_trading`.

The scheduled Preflight now runs with the same Paper runtime arguments, so an
enabled Shadow configuration is checked before the market session starts.

## Readiness output

Production Readiness includes a `Shadow Replication` item:

- disabled is reported as the safe default;
- enabled validates separate ledger and report paths;
- unusable directories or non-file destinations fail readiness;
- the composition initializes the daily reconciliation report.

## Protected activation

Use `scripts/set_shadow_replication.ps1` after 15:40 local time. The script
refuses to change configuration between 08:30 and 15:40 on weekdays. It makes
a temporary backup before changing `scripts/run_katana_service_task.cmd`.

Enable the next service start without restarting the current service:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  scripts\set_shadow_replication.ps1
```

Enable and restart after market close:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  scripts\set_shadow_replication.ps1 -RestartService
```

Disable after market close:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  scripts\set_shadow_replication.ps1 -Disable -RestartService
```

Live brokerage submission remains unavailable and locked.
