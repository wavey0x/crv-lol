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

## Web application

```bash
cd web
npm install
npm start
```
