"""Daily treasury composition, using the same holdings as the balance sheet."""

import json
from decimal import Decimal
from pathlib import Path

import requests

from crv_lol.treasury import CRV, CRVUSD, SCRVUSD, USDC, decimal_to_string

DAY = 86_400
STABLECOINS = {
    address.lower()
    for address in (
        CRVUSD,
        SCRVUSD,
        USDC,
        "0xCAcd6fd266aF91b8AeD52aCCc382b4e165586E29",  # frxUSD
        "0xcf62F905562626CfcDD2261162a51fd02Fc9c5b6",  # sfrxUSD
        "0x865377367054516e17014CcdED1e7d814EDC9ce4",  # DOLA
        "0xb45ad160634c528Cc3D2926d9807104FA3157305",  # sDOLA
    )
}
GOVERNANCE_TOKENS = {CRV.lower()}
PRICE_WINDOW = 4 * 60 * 60
SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "treasury_history.json"


def summarize_balance_sheet(sheet, price_source="wavey"):
    totals = {name: Decimal("0") for name in ("stablecoins", "governance", "other")}
    complete = True
    for wallet in sheet["wallets"]:
        for row in wallet["rows"]:
            address = row["token_address"].lower()
            category = (
                "stablecoins"
                if address in STABLECOINS
                else "governance" if address in GOVERNANCE_TOKENS else "other"
            )
            if row["usd_value"] is None:
                complete = False
                continue
            value = Decimal(row["usd_value"])
            if not value.is_finite() or value < 0:
                raise ValueError("Invalid treasury USD value")
            totals[category] += value

    return {
        "captured_at": sheet["captured_at"],
        "captured_block": sheet["captured_block"],
        **{f"{key}_usd": decimal_to_string(value) for key, value in totals.items()},
        "complete": complete,
        "price_source": price_source,
    }


def merge_daily_history(previous, incoming):
    """Keep the latest observation per UTC day; retries cannot add duplicates."""
    by_day = {}
    for point in [*previous, *incoming]:
        day = int(point["captured_at"]) // DAY
        if day not in by_day or point["captured_at"] >= by_day[day]["captured_at"]:
            by_day[day] = point
    return [by_day[day] for day in sorted(by_day)]


def attach_history(sheet, previous):
    seed = json.loads(SEED_PATH.read_text()) if SEED_PATH.exists() else []
    sheet["history"] = merge_daily_history(
        seed, [*previous.get("history", []), summarize_balance_sheet(sheet)]
    )
    return sheet


def load_historical_prices(tokens, timestamp):
    """Use dated token/share prices, never today's price or an assumed $1 peg.

    https://api-docs.defillama.com/llms-free.txt — /prices/historical
    Reject missing, stale, low-confidence or invalid quotes rather than guessing.
    """
    if not tokens:
        return {}
    coins = ",".join(f"ethereum:{token.lower()}" for token in tokens)
    response = requests.get(
        f"https://coins.llama.fi/prices/historical/{timestamp}/{coins}",
        params={"searchWidth": "4h"},
        timeout=30,
    )
    response.raise_for_status()
    quotes = response.json()["coins"]
    snapshots = {}
    for token in tokens:
        quote = quotes.get(f"ethereum:{token.lower()}", {})
        price = Decimal(str(quote.get("price", "NaN")))
        if (
            not price.is_finite()
            or price <= 0
            or abs(quote.get("timestamp", 0) - timestamp) > PRICE_WINDOW
            or quote.get("confidence", 0) < 0.9
        ):
            raise ValueError(f"No reliable historical price for {token} at {timestamp}")
        snapshots[token] = {
            "price": price,
            "status": "priced",
            "logo_url": "",
        }
    return snapshots


def find_block_at_or_before(client, timestamp, lower, upper):
    """Binary search the private archive RPC; lower/upper are block objects."""
    if not lower["timestamp"] <= timestamp <= upper["timestamp"]:
        raise ValueError("Timestamp is outside the block search bounds")
    while lower["number"] + 1 < upper["number"]:
        # Interpolation finds recent Ethereum timestamps in a handful of reads.
        fraction = (timestamp - lower["timestamp"]) / (
            upper["timestamp"] - lower["timestamp"]
        )
        number = lower["number"] + int(fraction * (upper["number"] - lower["number"]))
        number = max(lower["number"] + 1, min(number, upper["number"] - 1))
        block = client.eth.get_block(number)
        if block["timestamp"] <= timestamp:
            lower = block
        else:
            upper = block
    return upper if upper["timestamp"] <= timestamp else lower
