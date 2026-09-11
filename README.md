# BTC15M Web App V2 — Render Ready, No Logging

This build removes the V10.11 research logger from the hosted web app. It keeps the live Chart Signal, Decision Signal, Target Reachability, Move Projection, Coinbase Order Flow, market structure, BRTI feed, countdown, and contract auto-roll.

## Required GitHub contents
Upload the **contents of this folder**, not the ZIP itself. In particular, keep `static/index.html` in the repository. No `templates` folder is used.

## Render
Create a **Web Service** from the GitHub repository. This project uses the included `Dockerfile`, so Build Command and Start Command can remain blank in Render.

### Environment variable
Set `KALSHI_API_KEY_ID` to your Kalshi API Key ID.

### Private key — recommended Render Secret File
Create a Render Secret File named exactly:

`kalshi_private_key.pem`

Paste the complete PEM contents, including the BEGIN/END lines. The app automatically detects it at `/etc/secrets/kalshi_private_key.pem`. You do **not** need to set `KALSHI_PRIVATE_KEY_PATH` when using that filename.

Alternatively, set `KALSHI_PRIVATE_KEY_PEM` as a secret environment variable containing the full PEM text.

Never upload your API credentials or `.pem` file to GitHub.

## Health check
`/api/health` returns the backend status.
