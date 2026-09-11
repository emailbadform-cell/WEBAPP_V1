# BTC15M Web App V1

Web interface for the V10.11 BTC/Kalshi engine. The model, BRTI feed, Kalshi market discovery, Target Reachability, Move Projection, Decision Signal, Coinbase order flow, auto-roll and research logging remain server-side.

## Local Windows
1. Keep the same environment variables already used by V10.11: `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH`.
2. Run `install_web.bat` once.
3. Run `run_web.bat`.
4. Open `http://127.0.0.1:8000`.

## Cloud deployment
Use the included Dockerfile. Set these secrets on the host:
- `KALSHI_API_KEY_ID`
- either `KALSHI_PRIVATE_KEY_PATH` pointing at a mounted secret file, or `KALSHI_PRIVATE_KEY_PEM` containing the PEM text
- optional `ALLOW_COINBASE_FALLBACK=1`

Do not put the private key in frontend JavaScript or commit it to Git.

## API
- `GET /api/state` — complete computed dashboard state
- `GET /api/health` — basic service health

The browser polls `/api/state` once per second while the BRTI and Coinbase workers refresh independently in the background.


## Web version logging
Research/data logging is disabled in this web build. The app does not persist the V10.11 MTF/MP/OF research dataset locally.
