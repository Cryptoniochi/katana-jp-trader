# Loss Control Review (2026-10-02)

This change tightens the default paper-trading loss controls after an ORB
position was allowed to remain open with a large unrealized loss.

## Root cause

`OrbSignalStrategySettings.stop_loss_rate` defaulted to `None`.  Therefore an
ORB position had no price-based stop and could remain open until the force-exit
time.  Pullback and High Breakout had their own stops, but there was no
consistent production default across the enabled strategies.

## New defaults

| Control | Previous | New |
| --- | ---: | ---: |
| ORB stop loss | disabled | 1.0% |
| ORB take profit | disabled | 2.0% |
| Pullback stop loss | 1.0% | 1.0% |
| Pullback take profit | 2.0% | 2.0% |
| Pullback trailing stop | 1.2% | 1.0% |
| High Breakout stop loss | 1.2% | 1.0% |
| High Breakout take profit | 2.5% | 2.0% |
| High Breakout trailing stop | 1.5% | 1.0% |
| Daily loss entry circuit breaker | JPY 100,000 | JPY 50,000 |

The daily loss limit prevents additional entry orders.  It does not replace
the per-position exit rules.

## Important limitation

Strategy exits are evaluated on completed five-minute bars.  A price gap or a
fast move can execute below the nominal 1.0% stop level.  Before enabling live
broker order submission, KATANA still needs an independent tick-level
protective stop or broker-native stop order.

## Safe installation

Run `install_after_close.ps1` only after the Paper Trading and Daily Report
schedules are both completed.  The installer checks those states, backs up all
replaced files, installs complete replacement files, and runs targeted tests.
It does not restart resident services and does not enable live order
submission.
