# Frontend Dashboard

Desktop-first React + TypeScript + Vite dashboard for Trade Automation.

## What It Covers

- Overview: equity, exposure, risk, stream posture, and recent events
- Market Monitor: live quote and order-book view from backend websocket channels
- Execution Desk: positions, orders, trades, and manual paper-order controls
- Research Lab: backtest runner and optimizer trigger
- News + AI: ingested news and LLM review activity
- Settings + Safety: live flags, kill-switch posture, and runtime config visibility

## Local Development

From the repo root, start the API first:

```bash
uv run uvicorn app.main:app --reload
```

Then in this directory:

```bash
npm install
npm run dev
```

The Vite dev server proxies `/api` and `/ws` to `http://localhost:8000`.

## Verification

```bash
npm run lint
npm run test
npm run build
```

## Docker

The root `docker-compose.yml` builds this frontend into an Nginx container and serves it on [http://localhost:4173](http://localhost:4173), proxying API and websocket traffic to the backend service.
