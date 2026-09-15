# V2.3 Multi-Exchange Order Flow — No Logging

The visible multi-exchange panel now shows only:
- Pressure
- 5bp imbalance
- Ask depletion
- Bid depletion
- Combined normalized values
- Order-flow consensus

Venues: Coinbase, Kraken, Bitstamp, Gemini.

Exchange spot prices, median, mean and cross-exchange price spread are intentionally hidden because BRTI is the
price reference for the Kalshi contract.

This web build records no research CSV data and does not alter the live prediction with multi-exchange order flow.
