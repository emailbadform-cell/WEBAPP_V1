# BTC15M Decision Terminal V2.24.3 / V10.34

Web reliability release: smooth browser-side contract countdown, hardened GT/MTF chart rendering and autoscaling, and prominent live/realized P&L for $100 paper trades. Predictive models unchanged.


## V2.24.3 patch
- Forward Signal display now shows `UP`/`DOWN` for internally classified reversals while retaining `UP — CONTINUATION`/`DOWN — CONTINUATION` for continuation states.
- Internal `phase=REVERSAL` remains available for research/logging; model behavior and thresholds are unchanged.

## V2.24.2 patch
Move Projection Progress rendering is hardened against transient incomplete state and is recalculated from the active projection leg and current BRTI each refresh. Profit Protection remains unchanged.
