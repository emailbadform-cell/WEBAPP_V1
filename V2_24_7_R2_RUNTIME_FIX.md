# Web V2.24.7 R2 runtime correction

Packaging/runtime correction only. No model, threshold, Forward, TR, GT, MP, FLIP, RE-FLIP, or Profit Protection changes.

- Restores a compatibility `decision_signal()` wrapper required by three stale dashboard/research helper callers.
- Wrapper returns the already-attached V10.35 predictive Decision when present.
- If called before the cached Decision exists, it computes the same frozen predictive Decision with no Current Side input rather than restoring the deleted legacy Current Side anchored Decision.
- Prevents the `NameError: name 'decision_signal' is not defined` initialization/runtime failure seen in Research V10.35 and possible in the web runtime.
