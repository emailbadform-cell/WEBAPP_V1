# V2.28.2 KXBTC15M startup discovery fix
- Current-contract startup no longer depends on Kalshi `status=open`.
- Computes the deterministic current quarter-hour KXBTC15M ticker and tries it directly first.
- Falls back to the unfiltered KXBTC15M series listing and accepts only the immediate current 15-minute window.
- Retains the old `status=open` request as a final compatibility fallback.
- Tolerates strike aliases through a single target parser.
- Preserves V2.28.1 startup diagnostics and V10.39.2 recursive GT logic.
