# BTC15M Web V2.28.25

## Read-only persistent-storage inspector
- Adds `SCAN STORAGE (READ ONLY)` to the RDFZ Storage card.
- Adds `GET /api/storage/inspect`.
- Scans file metadata under the persistent-data root (normally `/var/data`) without opening, moving, compressing, or deleting file contents.
- Reports whole-disk used/total/free, bytes accounted for by regular files, unaccounted used space, top-level directory/file sizes, file counts, and the 30 largest files.
- Intended to diagnose the unexpected ~325 GB persistent-disk usage before any deletion is attempted.

## Safety
- No trading architecture changes.
- Auto Paper V1 remains frozen.
- Existing RDFZ export/clear behavior is unchanged.
- Storage Inspector is read-only and has no delete action.
