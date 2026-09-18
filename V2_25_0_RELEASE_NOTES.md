# BTC15M Web V2.25.0

- Fixes Entry Quality MP direction mapping (UP/DOWN -> ABOVE/BELOW).
- Profit Protection V2 no longer exits merely because Decision changed while profitable; Decision change becomes protection/deterioration evidence.
- Confirmed reversal remains an immediate profitable exit condition; new FLIP requires additional deterioration/giveback.
- Removes active callers of the legacy Decision compatibility wrapper and corrects stale current-side diagnostic text.
- Adds research-only Technical Anticipation state to API output; it has no production Decision/Forward/TR authority.
- Retains V2.24.7 rollover, chart continuity and earnings-reset fixes.
