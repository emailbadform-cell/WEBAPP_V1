# BTC15M Web V2.26.0 / Research V10.37

## New
- Adds Settlement forecast display beside Market Decision.
- Settlement shows predicted final side, confidence, and nearest frozen checkpoint.
- Includes 1m/5m/15m range and trend-channel context through the V10.37 core.
- Adds HEAD / = 200.
- Warmup API state exposes history_ready, history_rows, and model_ready.
- Health endpoint reports history readiness and row count.
- Profit Protection no longer exits solely because reversal becomes CONFIRMED; additional evidence is required.
- Removes duplicate active Move Projection implementation in bundled core.
- Corrects Anticipation EMA convergence sign handling while keeping Anticipation research-only.

## Important
Decision logic remains unchanged. Settlement does not override Decision, Forward, TR, FLIP/RE-FLIP, MP, or Chart.
