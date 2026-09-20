# BTC15M Web V2.28.34 — Cumulative RDFZ Storage/Export Hotfix

- RDFZ export is now cumulative and non-destructive: download never moves or rotates active logs.
- Every export includes all RDFZ data currently retained by the running service, including data exported previously.
- ZIP is built in temporary runtime storage, verified, streamed to the browser, then deleted automatically.
- No `_exports` duplicate data tree is created for new exports.
- Manifest start/end come from record timestamps and include per-file bytes, row counts, first/last record timestamps.
- Existing prediction/trading architectures and Auto Paper policy are unchanged.
- This update cannot turn an ephemeral Render filesystem into persistent storage. Deploy-surviving retention still requires a genuinely mounted persistent disk or external store. Within a running deployment, repeated exports no longer remove prior data.
