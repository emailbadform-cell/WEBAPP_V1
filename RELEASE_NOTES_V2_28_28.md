# BTC15M Web V2.28.28

- Leaves the existing BRTI display unchanged.
- Adds a separate Final Target display using FINAL_TARGET_PROXY_V1: a running one-observation-per-second BRTI average during the final 60 seconds.
- Exposes Final Target state through /api/state for synchronized RDFZ research logging.
- Final Target is explicitly a reconstructed proxy, not an official Kalshi settlement value.
- No Decision, Settlement, GT, TR, Flip, MP, OF/L2 or frozen Auto Paper authority changes.
- Retains all V2.28.27 fast export, re-download, clear-exported, delete-active, storage inspector and deleted-open-file diagnostics.
