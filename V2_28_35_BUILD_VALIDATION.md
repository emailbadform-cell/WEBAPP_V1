# V2.28.35 Build Validation

- Python compile: PASS
- Timestamp parser tested against the user's latest V2.28.34 RDFZ export: PASS
- Detected actual data range: 2026-09-20T05:11:52.967332+00:00 through 2026-09-20T05:12:29.390605+00:00
- All five current NDJSON stream types produced non-null record timestamps: PASS
- Export design freezes source byte lengths before manifest scan and ZIP copy.
- ZIP entries are verified against the captured byte lengths before download response.
- Active source files are not moved, truncated, rotated, or deleted.
- No trading/model architecture logic changed.
