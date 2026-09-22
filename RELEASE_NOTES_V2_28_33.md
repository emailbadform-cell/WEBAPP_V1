# BTC15M Web V2.28.33 — RDFZ Export Reliability Hotfix

- Adds Existing RDFZ Exports list with direct download of previously-created ZIPs; no new rotation/rebuild required.
- Adds deletion of a selected saved ZIP only, with explicit confirmation.
- Export/manifest time range now derives from NDJSON record timestamps where available instead of filesystem modification times.
- Manifest records per-file bytes, row counts, first/last record timestamps, total rows, and file count.
- New exports verify ZIP integrity and remove duplicated frozen staging files after successful archive creation, leaving the ZIP as the retained export.
- Existing older exports remain discoverable/downloadable and are not automatically deleted.
- Trading/prediction logic is unchanged: Decision, Settlement, GT1–GT15, Trend Transition V2, Final Target, TR/Flip, Primary Auto Paper gates, Forced Coverage, and Shadow logic are untouched.
