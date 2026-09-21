# V2.28.26 — Deleted Open File Diagnostic

- Adds read-only `/proc/*/fd` diagnostic for deleted files still held open by running processes.
- Reports PID, process, FD, deleted target, and apparent file size.
- Deduplicates hard references by device/inode.
- Does not delete, close, move, truncate, or modify any file or process.
- Trading architectures and Auto Paper are unchanged.
