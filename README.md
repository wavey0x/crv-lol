# CRV.LOL

CRV.LOL contains the web application served at `crv.lol` and the scheduled
Brownie job that publishes its on-chain data snapshot. The public HTTP API is
owned by the separate `wavey-api` repository.

## Layout

- `web/` — React frontend deployed by Vercel.
- `crv_lol/` — liquid-locker, gauge, treasury, and snapshot modules.
- `scripts/refresh.py` — Brownie entry point for the scheduled refresh.
- `tests/` — data-generation and atomic-publication tests.

## Refresh data

```bash
export CRVLOL_SNAPSHOT_PATH=/var/lib/crv-lol/snapshot.json
brownie run refresh --network electro
```

The refresh is assembled in memory and atomically replaces the snapshot only
after validation. A failed refresh leaves the last-known-good snapshot intact.
Production runs `deploy/systemd/crv-lol-refresh.service` from its timer; only
the timer is enabled.
On Electro, installed code is read-only under `/opt/crv-lol`, the private
environment is `/etc/crv-lol.env`, and the service owns its Brownie inputs and
public snapshot under `/var/lib/crv-lol`. The snapshot is world-readable so the
separate API can serve it; no credentials are stored in it. The Brownie cache
contains the contract records needed by this installed version and is captured
with the worker for recovery.

## Price providers

Treasury prices use `defillama,curve,lifi` by default. Set `PRICE_PROVIDERS` in
the worker environment (or local `.env`) to a comma-separated list; append
`enso` to opt in. Empty or unknown lists are rejected. Use this app's own
`WAVEY_PRICES_KEY` or `TOKEN_PRICE_AGG_KEY`; credentials from Tidal are not used.
Each refresh prices only unique tokens with positive balances. Missing prices
remain unpriced and totals are marked partial.

## Web application

```bash
cd web
npm install
npm start
```

## Treasury history

The balance sheet includes a compact stablecoin / governance-token USD chart.
Each successful treasury refresh records its captured block and values, keeping
the latest observation for each UTC day. Today's point uses the same latest block
and prices as the wallet rows. The existing ten-minute refresh updates it; the
page polls at the same interval. A failed refresh preserves the prior snapshot,
and missing observations or prices appear as gaps rather than zero values.

`data/treasury_history.json` seeds 90 completed UTC days (August 19–November 16,
2026). It is merged with retained history on refresh, so existing daily points
are preserved. No database or additional API endpoint is required. Keep the
runtime snapshot when deploying: it contains daily observations after the seed.

To generate or resume a backfill using an Ethereum archive RPC:

```bash
python -m scripts.backfill_treasury --days 90
```

The command uses `ETHEREUM_RPC_URL` (or `MAINNET_RPC_URL`) and writes the public
seed, not the running service's snapshot. It reads balances at the last block
of each completed UTC day and uses dated token/share prices from
[DefiLlama](https://api-docs.defillama.com/llms-free.txt), requiring a quote within
four hours and at least 0.9 confidence. It saves completed days as it goes and
exits unsuccessfully if any day needs a retry. The ordinary refresh adds today's
latest block, using the existing Wavey price source (`WAVEY_PRICES_KEY`).

The historical token universe is the same trusted discovery set used by the
balance sheet, including previous diversification outputs. Classification is
by address in `crv_lol/treasury_history.py`: stablecoins include their
yield-bearing shares, and governance includes CRV plus any CRV vest return
already counted by the balance sheet. Share prices are not assumed to be $1.
Other assets remain in the balance sheet and are explicitly excluded from the
two-series chart. Add newly approved assets to the classification when needed.
