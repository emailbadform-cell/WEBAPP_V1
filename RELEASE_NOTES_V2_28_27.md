# BTC15M Web V2.28.27 — Fast RDFZ Export + Independent Delete

- FAST DOWNLOAD now rotates active RDFZ first and packages the frozen batch with ZIP_STORED (no compression) for much faster server-side preparation.
- Completed export archive is cached with its frozen batch. RE-DOWNLOAD LAST EXPORT serves it without rebuilding.
- DELETE ACTIVE RDFZ permanently deletes current active RDFZ log files without requiring a prior download.
- DELETE ACTIVE preserves frozen/exported batches, export metadata, and Auto Paper persistent state.
- Existing CLEAR EXPORTED remains independent and deletes only the last completed frozen export batch.
- Storage Inspector and deleted-open-file diagnostic retained.
- No Decision, GT, Settlement, Auto Paper policy, execution gate, or trading architecture changes.
