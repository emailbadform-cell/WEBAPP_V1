# BTC15M Web V2.28.37

Export reliability/performance hotfix on top of V2.28.36.

- Default `/api/rdfz/download` is now a compact compressed research export.
- Added `/api/rdfz/download-full` for optional full raw WS-inclusive export.
- Uses ZIP DEFLATE level 1 instead of ZIP_STORED to reduce transfer size while keeping build CPU low.
- Mutable JSON state files (notably `BTC15M_AUTO_PAPER_STATE.json`) are snapshotted into memory at export start and are no longer treated as append-only streams.
- Append-only NDJSON files retain frozen byte-boundary semantics and validation.
- Adds a non-blocking export lock to prevent concurrent large export builds.
- Export failures return structured HTTP errors and clean temporary archives.
- Active RDFZ logging remains non-destructive and continues while ZIP is built/downloaded.
- UI now separates normal Compact Download from optional Full Raw Download.
- No Decision, Settlement, GT, TR, Flip, Transition, Auto Paper gate, or trading-model mathematics changed.
