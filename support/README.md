# BTC15M Decision Terminal V2.24.4 / V10.34

Web reliability release: smooth browser-side contract countdown, hardened GT/MTF chart rendering and autoscaling, and prominent live/realized P&L for $100 paper trades. Predictive models unchanged.


## V2.24.4 patch
- Live Forward display path in `advanced_signals.py` now renders reversal-phase states as `UP` or `DOWN` without the word `REVERSAL`.
- `UP — CONTINUATION` and `DOWN — CONTINUATION` remain unchanged.
- Internal/research `phase=REVERSAL` is preserved.
- Duplicate Forward Signal group removed from Advanced Diagnostics; main Forward Signal tile remains active.
- No model, threshold, Decision, Profit Protection, GT, TR, MP, OF/L2, or research-logging logic changes.

## V2.24.3 patch
- Forward Signal display now shows `UP`/`DOWN` for internally classified reversals while retaining `UP — CONTINUATION`/`DOWN — CONTINUATION` for continuation states.
- Internal `phase=REVERSAL` remains available for research/logging; model behavior and thresholds are unchanged.

## V2.24.2 patch
Move Projection Progress rendering is hardened against transient incomplete state and is recalculated from the active projection leg and current BRTI each refresh. Profit Protection remains unchanged.
