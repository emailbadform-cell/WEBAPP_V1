# BTC15M Web V2.28.38

- Repairs Final Target accumulation: backfills every source-timestamped BRTI second from the engine tick buffer into an immutable per-contract 60-second bucket.
- Final Target sample_count is monotonic for a contract and can reach 60; completed seconds are not discarded during the active/just-completed contract transition.
- Preserved Final Target buckets no longer add a synthetic current quote that can distort the source-second count.
- Keeps V2.28.37 compact/full safe compressed RDFZ export behavior.
- Keeps V2.28.36 Transition V2 runtime plumbing and fast-rollover work.
- Version metadata advanced to Web V2.28.38 / Research V10.39.22.
- No frozen Primary Auto Paper gate or production Decision/Settlement/GT/TR/Flip mathematics changed.
