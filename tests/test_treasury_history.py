from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest

from crv_lol import treasury, treasury_history as history


def sheet(timestamp=history.DAY * 100 + 100, block=1000):
    return {
        "captured_at": timestamp,
        "captured_block": block,
        "wallets": [
            {
                "rows": [
                    {"token_address": treasury.USDC.lower(), "usd_value": "10.25"},
                    {"token_address": treasury.CRV, "usd_value": "20.01"},
                    {
                        "token_address": "0xb45ad160634c528Cc3D2926d9807104FA3157305",
                        "usd_value": "1.42",
                    },
                ]
            },
            {
                "rows": [
                    {
                        "token_address": treasury.CRV,
                        "kind": "vest_return",
                        "usd_value": "3",
                    },
                    {"token_address": "0xunknown", "symbol": "USDC", "usd_value": "7"},
                ]
            },
        ],
    }


def test_categories_reconcile_across_wallets_and_include_vest_return():
    point = history.summarize_balance_sheet(sheet())
    assert point["stablecoins_usd"] == "11.67"
    assert point["governance_usd"] == "23.01"
    assert point["other_usd"] == "7"
    assert point["complete"] is True
    assert sum(
        Decimal(point[key])
        for key in ("stablecoins_usd", "governance_usd", "other_usd")
    ) == Decimal("41.68")


def test_unpriced_asset_marks_point_incomplete():
    data = sheet()
    data["wallets"][0]["rows"][0]["usd_value"] = None
    assert history.summarize_balance_sheet(data)["complete"] is False


def test_latest_block_replaces_today_without_losing_earlier_days(monkeypatch, tmp_path):
    monkeypatch.setattr(history, "SEED_PATH", tmp_path / "absent.json")
    yesterday = history.summarize_balance_sheet(sheet(history.DAY * 99, 900))
    first = history.summarize_balance_sheet(sheet())
    previous = {"history": [yesterday, first]}
    result = history.attach_history(sheet(history.DAY * 100 + 200, 1010), previous)
    assert [point["captured_block"] for point in result["history"]] == [900, 1010]
    # An older observation arriving late must not roll the chart backwards.
    assert history.merge_daily_history(result["history"], [first]) == result["history"]
    assert previous["history"] == [yesterday, first]


def test_seed_merges_with_existing_history_and_latest_wins(monkeypatch, tmp_path):
    import json

    seed = tmp_path / "seed.json"
    seed.write_text(
        json.dumps([history.summarize_balance_sheet(sheet(history.DAY * 99, 900))])
    )
    monkeypatch.setattr(history, "SEED_PATH", seed)
    result = history.attach_history(sheet(), {"history": []})
    assert [point["captured_block"] for point in result["history"]] == [900, 1000]
    assert history.attach_history(sheet(), result)["history"] == result["history"]


@pytest.mark.parametrize(
    "change",
    [
        {"price": -1},
        {"price": "NaN"},
        {"timestamp": 1},
        {"confidence": 0.1},
    ],
)
def test_backfill_rejects_bad_historical_prices(monkeypatch, change):
    quote = {"price": 1.42, "timestamp": 100000, "confidence": 0.99, **change}
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"coins": {f"ethereum:{treasury.USDC.lower()}": quote}},
    )
    monkeypatch.setattr(history.requests, "get", lambda *a, **k: response)
    with pytest.raises(ValueError, match="No reliable historical price"):
        history.load_historical_prices([treasury.USDC], 100000)


def test_historical_share_price_is_not_assumed_to_be_one_dollar(monkeypatch):
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "coins": {
                f"ethereum:{treasury.SCRVUSD.lower()}": {
                    "price": "1.105",
                    "timestamp": 100000,
                    "confidence": 0.99,
                }
            }
        },
    )
    monkeypatch.setattr(history.requests, "get", lambda *a, **k: response)
    quotes = history.load_historical_prices([treasury.SCRVUSD], 100000)
    assert quotes[treasury.SCRVUSD]["price"] == Decimal("1.105")


def test_historical_builder_cannot_silently_use_current_prices():
    with pytest.raises(
        ValueError, match="Historical balances require historical prices"
    ):
        treasury.build_treasury_balance_sheet(123)


@pytest.mark.parametrize("timestamp, expected", [(10, 0), (22, 1), (30, 1), (70, 3)])
def test_block_search_handles_missed_slots_and_exact_timestamps(timestamp, expected):
    blocks = [{"number": i, "timestamp": ts} for i, ts in enumerate([10, 22, 46, 70])]
    client = SimpleNamespace(
        eth=SimpleNamespace(get_block=lambda number: blocks[number])
    )
    assert (
        history.find_block_at_or_before(client, timestamp, blocks[0], blocks[-1])
        == blocks[expected]
    )


@pytest.mark.parametrize("refresh_fails", [False, True])
def test_refresh_only_advances_history_with_a_fresh_balance_sheet(
    monkeypatch, tmp_path, refresh_fails
):
    import sys

    monkeypatch.setitem(sys.modules, "brownie", SimpleNamespace(chain=None))
    monkeypatch.setitem(
        sys.modules,
        "crv_lol.liquid_lockers",
        SimpleNamespace(
            build_liquid_locker_data=lambda: ({"new": True}, 200),
            build_chart_data=lambda _: {"new": True},
        ),
    )
    monkeypatch.setattr(history, "SEED_PATH", tmp_path / "absent.json")
    from scripts import refresh
    from crv_lol.snapshot import load_snapshot, publish_snapshot

    path = tmp_path / "snapshot.json"
    old_sheet = history.attach_history(sheet(), {})
    previous = {
        "ll_data": {"old": True},
        "last_updated": 100,
        "chart_data": {"old": True},
        "treasury_balance_sheet": old_sheet,
        "curve_gauge_data": {"old": True},
        "curve_gauges_by_name": {"old": True},
    }
    publish_snapshot(deepcopy(previous), path)
    monkeypatch.setattr(refresh, "get_snapshot_path", lambda: path)
    monkeypatch.setattr(
        refresh, "build_liquid_locker_data", lambda: ({"new": True}, 200)
    )
    monkeypatch.setattr(refresh, "build_chart_data", lambda _: {"new": True})
    monkeypatch.setattr(refresh, "fetch_curve_gauge_data", lambda: None)

    def fail():
        raise RuntimeError("test refresh failure")

    fresh_sheet = sheet(history.DAY * 101 + 100, 1100)
    monkeypatch.setattr(
        refresh,
        "build_treasury_balance_sheet",
        fail if refresh_fails else lambda: deepcopy(fresh_sheet),
    )
    refresh.main()
    actual = load_snapshot(path)["treasury_balance_sheet"]
    if refresh_fails:
        assert actual == old_sheet
    else:
        assert [point["captured_block"] for point in actual["history"]] == [1000, 1100]
        assert actual["history"][-1] == history.summarize_balance_sheet(fresh_sheet)
