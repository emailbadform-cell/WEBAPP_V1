# BTC15M Web V2.28.29

- Fixes Final Target placement by anchoring metric metadata inside its card and labels it Final Target (Est.).
- Adds Final Target sampling/window-health diagnostics and research-only GT15 Final-Target challenger state.
- Adds Flip Challenger V1 prospective capture metadata; it has zero Decision/Settlement/trading authority.
- Auto Paper V1 now starts enabled after server startup/redeploy; manual OFF remains available for the running server. Entry/exit policy remains frozen and paper-only.
- Preserves current BRTI display, production Decision/Settlement/GT control, rollover, fast RDFZ export, cached re-download, clear-exported, delete-active, and storage diagnostics.
- Prospective RDFZ state logging includes the new challenger fields.
