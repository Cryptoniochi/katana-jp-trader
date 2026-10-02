# Live Read-Only Phase 5

## Scope

This phase adds a separate Live Readiness diagnostic without enabling live
brokerage orders. It obtains only the following kabu Station GET resources:

- cash wallet;
- margin wallet;
- positions;
- orders and executions.

No `sendorder` or `cancelorder` method is implemented. The existing execution
mode router continues to reject Live mode even when both arming values are
present.

## Command

Run with kabu Station open and API enabled:

```powershell
.\.venv\Scripts\python.exe -m app.run_live_readiness
```

The command reads `KABU_STATION_API_PASSWORD` and the optional
`KABU_STATION_BASE_URL` from the process environment or `.env`.

Reports:

- `reports/live/kabu_station_read_only.json`
- `reports/live/live_readiness.json`

The API token is never written to either report.

## Expected result

The desired Phase 5 result is:

```text
Live Read-Only: READY
Live Trading: BLOCKED
```

An active order in the brokerage account is reported explicitly. Existing
positions are inventoried but are not changed. Shadow consistency is reported
independently. A future phase must add explicit Paper/Shadow/Broker ownership
mapping, restart recovery, and a constrained live order adapter before Live
Trading can ever become READY.
