# Sprint91-1A Database Fix

The failure was caused by an old paper position stored in `data\katana.db`.

```text
PortfolioConsistencyError:
Broker has no matching position. code=4751 side=long
```

The production portfolio repository restored the old 4751 position, while the
new in-memory paper broker started empty. The consistency check correctly
stopped the runtime before market processing.

These replacement CMD files use an isolated validation database:

```text
data\katana_sprint91_validation.db
```

This preserves the existing `data\katana.db` and starts the Sprint91
validation with an empty, internally consistent paper portfolio.

Replace:

```text
run_kabu_station_30_symbols_short.cmd
run_kabu_station_30_symbols_full.cmd
```

Run the short validation:

```powershell
.\run_kabu_station_30_symbols_short.cmd
```
