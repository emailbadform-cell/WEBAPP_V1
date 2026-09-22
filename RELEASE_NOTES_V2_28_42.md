# BTC15M Web V2.28.42 — Direct RDFZ Download

- Removes server-side ZIP/compression from the normal RDFZ download path.
- Keeps SCAN STORAGE, one-button DOWNLOAD ALL RDFZ FILES, CLEAR EXPORTED, and DELETE ACTIVE RDFZ.
- One-button download freezes each active file's byte boundary, then streams each file directly from disk in 256 KiB chunks.
- No temporary ZIP is built and no archive is retained on the server.
- Active logging continues during download.
- CLEAR EXPORTED removes legacy `_exports` artifacts only; active RDFZ is protected.
- Existing trading architectures and Auto Paper strategy logic are unchanged.
