# BTC15M Web V2.24.6 / Research V10.35 — GT Next 1m Direction Tile

## UI change
- Added a dedicated **GT Next 1m** tile in Core Signals, immediately beside Chart.
- The tile reads the same `ghost_thread.direction` used by the GT projected 1-minute candle.
- `UP` renders green.
- `DOWN` renders red.
- If GT has no directional prediction, the tile renders `—` rather than inventing a direction.
- The tile meta line includes the current GT stage when available.

## Architecture unchanged
No GT model, Forward model, TR, Decision, FLIP/RE-FLIP, Profit Protection, L2/OF authority, or V10.35 research logic was changed. This is a presentation-only GT addition.
