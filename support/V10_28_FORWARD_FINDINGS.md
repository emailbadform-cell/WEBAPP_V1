# V10.28 forward revalidation

Source: user V10.27 forward log, 7,522 snapshots, 9 contracts, 8 full completed contracts.

## Settlement
Across 72 fixed checkpoint observations, Decision accuracy was 77.8%; Chart was 61.1%; MP was 62.5%.

## Target Reachability
Raw TR: AUC 0.890, Brier 0.121, 50% accuracy 87.5%.
Calibrated TR: AUC 0.890, Brier 0.149, 50% accuracy 77.8%.
This small new block does not justify refitting calibration yet.

## FLIP
All 8 full contracts entered the $10 arming zone and all 8/8 subsequently crossed through at least once. This supports the reach-through definition but is not a calibrated 100% probability.

## Order flow
The frozen 60% Crypto.com + 40% Coinbase Validated OF did not reproduce its prior edge in this eight-contract block. At 5-second sampled observations and |score| >= .15, its 10-second accuracy was 48.3%. We do not re-optimize weights on this same block. Validated OF remains research/context only.

## MP lifecycle
V10.27 produced 117 direction-change reprojections across eight full contracts. A 5-second direction confirmation would retain 66 of 117 structural changes, an estimated 43.6% reduction in direction-change churn. V10.28 implements this confirmation while preserving immediate Base rearm.

## Feed / rollover
Median BRTI quote age remained 0.66s and 7092/7092 full-contract snapshots used WS_5HZ. However, next_prefetched was never true and every observed rollover used DISCOVERY. V10.28 adds deterministic next-ticker direct lookup before broad discovery.

## Chart gaps
V2.12 repairs missing historical 1-minute chart slots at the presentation layer only by inserting flat carry-forward candles. Model candles remain untouched, so the visual repair cannot fabricate Chart/MP features.
