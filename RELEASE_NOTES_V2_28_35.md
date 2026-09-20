# BTC15M Web V2.28.35 — Atomic Cumulative RDFZ Export

- Fixes RDFZ timestamp discovery for current log schemas (`logged_at_utc`, `server_received_utc`, `source_timestamp_utc`, and fallbacks).
- Freezes byte boundaries before export; manifest and ZIP use the exact same boundaries.
- Live RDFZ files remain appendable during export.
- Export remains cumulative and non-destructive.
- No permanent server-side ZIP/export duplication.
- ZIP integrity and frozen byte lengths are verified before response.
- No Decision, Settlement, GT, Transition, TR, Flip, OF, Final Target, Auto Paper, Forced Coverage, or Shadow trading-rule changes.
- Render lifecycle persistence remains an infrastructure limitation; this release does not claim to preserve local files across instance replacement.
