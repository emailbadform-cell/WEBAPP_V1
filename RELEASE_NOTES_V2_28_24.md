# V2.28.24 — Safe timestamped RDFZ export and storage monitor

- Timestamped Web RDFZ filenames include actual frozen batch time range.
- Export atomically rotates active RDFZ files into a frozen batch; new observations immediately continue in fresh active files.
- Dashboard shows persistent disk usage, active RDFZ bytes, exported bytes awaiting clear, and 70/85/95% warning levels.
- Clear Exported RDFZ Data removes only the last frozen exported batch after explicit confirmation. It never clears new active data.
- Download never deletes data.
- Auto Paper V1 and prediction architectures are unchanged.
