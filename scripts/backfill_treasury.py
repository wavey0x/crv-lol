"""Backfill daily treasury values without writing to the production snapshot.

Run from the repository root: python -m scripts.backfill_treasury --days 90
The small, public seed is merged into the normal snapshot by the next refresh.
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from web3 import Web3

from crv_lol import treasury
from crv_lol.treasury_discovery import discover_treasury_tokens
from crv_lol.treasury_history import (
    DAY,
    SEED_PATH,
    find_block_at_or_before,
    load_historical_prices,
    merge_daily_history,
    summarize_balance_sheet,
)


def write_history(path, history):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(history, indent=2) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--output", type=Path, default=SEED_PATH)
    args = parser.parse_args()
    if not 1 <= args.days <= 365:
        parser.error("--days must be between 1 and 365")
    rpc_url = os.getenv("ETHEREUM_RPC_URL") or os.getenv("MAINNET_RPC_URL")
    if not rpc_url:
        parser.error("Set ETHEREUM_RPC_URL or MAINNET_RPC_URL")
    client = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    if client.eth.chain_id != 1:
        parser.error("The archive RPC must be Ethereum mainnet")
    treasury.web3 = client
    latest = client.eth.get_block("latest")
    today = latest["timestamp"] // DAY * DAY
    history = json.loads(args.output.read_text()) if args.output.exists() else []
    completed = {point["captured_at"] // DAY for point in history if point["complete"]}

    print("Resolving daily closing blocks", flush=True)
    lower = client.eth.get_block(0)
    blocks = []
    for days_ago in range(args.days, 0, -1):
        timestamp = today - (days_ago - 1) * DAY - 1
        if timestamp // DAY in completed:
            continue
        lower = find_block_at_or_before(client, timestamp, lower, latest)
        blocks.append(lower)
    print(f"Backfilling {len(blocks)} daily observations", flush=True)
    if not blocks:
        print("All requested days are already saved")
        return

    # Discover the trusted token universe once, including former swap outputs.
    # Historical balances and share prices are still read at each day's block.
    discovery = discover_treasury_tokens(latest["number"], web3_client=client)

    def collect(block):
        sheet = treasury.build_treasury_balance_sheet(
            block["number"],
            token_discovery=discovery,
            price_loader=load_historical_prices,
        )
        return summarize_balance_sheet(sheet, price_source="defillama")

    failures = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {pool.submit(collect, block): block for block in blocks}
        for future in as_completed(pending):
            block = pending[future]
            date = datetime.fromtimestamp(block["timestamp"], timezone.utc).date()
            try:
                point = future.result()
            except Exception as error:
                # RPC exceptions can include private endpoint URLs.
                print(f"{date}: {type(error).__name__}; rerun to retry", flush=True)
                failures.append(date)
                continue
            history = merge_daily_history(history, [point])
            write_history(args.output, history)
            print(f"{date}: block {point['captured_block']}", flush=True)

    # Only completed days belong in the seed. The normal refresh adds today's
    # latest block together with the matching balance-sheet rows and total.
    print(f"Saved {len(history)} daily observations; refresh adds the latest block")
    if failures:
        raise SystemExit(f"{len(failures)} days need a retry; completed days are saved")


if __name__ == "__main__":
    main()
