"""Hermes as the plugin calls it: the key sent as a bearer token and kept
nowhere, each answer kept before it is read, every value an exact decimal,
and Pyth's catalogue sorted into the datasets."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from meridian.edge import RawStore

from pyth.catalogue import Catalogue, read_catalogue
from pyth.hermes import Hermes, HermesError, read_updates
from pyth.synthetic import Synthetic

from conftest import Sample, ids_of

KEY = "test-key-not-real"


def test_an_update_is_exact() -> None:
    body = json.dumps(
        {"parsed": [{"id": "0xAB", "price": {"price": "6812345678901", "conf": "2345678901",
                                             "expo": -8, "publish_time": 1793386800}}]}
    )  # fmt: skip
    [update] = read_updates(body)
    assert update.feed_id == "ab"
    assert update.price == Decimal("68123.45678901")
    assert update.confidence == Decimal("23.45678901")
    assert update.published_ns == 1_793_386_800 * 10**9


def test_an_update_that_does_not_read_is_left_out() -> None:
    assert read_updates(json.dumps({"parsed": [{"id": "ab", "price": {"price": "x"}}]})) == []


def test_the_key_is_sent_as_a_bearer_token_and_kept_nowhere(tmp_path: Path) -> None:
    sample = Sample()
    hermes = Hermes(RawStore(tmp_path), sample, "live", KEY)
    hermes.latest(ids_of("Crypto.BTC"))
    assert sample.headers[-1]["Authorization"] == f"Bearer {KEY}"
    kept = "".join(p.read_text() for p in tmp_path.rglob("*") if p.is_file())
    assert kept and KEY not in kept


def test_without_a_key_no_authorization_is_sent(tmp_path: Path) -> None:
    sample = Sample()
    Hermes(RawStore(tmp_path), sample, "live").catalogue()
    assert "Authorization" not in sample.headers[-1]


def test_a_refusal_is_said_without_the_key(tmp_path: Path) -> None:
    hermes = Hermes(RawStore(tmp_path), Sample(status=401), "live", KEY)
    with pytest.raises(HermesError) as refused:
        hermes.latest(ids_of("Crypto.BTC"))
    assert refused.value.status == 401
    assert "Pyth API key" in str(refused.value) and KEY not in str(refused.value)
    assert hermes.health.failures == 1 and KEY not in hermes.health.last_error


def test_the_catalogue_is_sorted_into_the_datasets() -> None:
    catalogue = Catalogue(read_catalogue(Synthetic().catalogue))
    assert catalogue.counts() == {
        "crypto": 4, "fx": 2, "equity": 2, "metal": 1, "commodities": 1, "rates": 7,
        "treasury_prices": 4, "": 10,
    }  # fmt: skip
    tenors = sorted((f.tenor for f in catalogue.of("rates")), key=lambda t: int(t[:-1]))
    assert tenors == ["2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
    aapl = next(f for f in catalogue.of("equity") if f.symbol == "Equity.US.AAPL/USD")
    assert (aapl.base, aapl.quote) == ("AAPL", "USD")
    eth_btc = next(f for f in catalogue.of("crypto") if f.symbol == "Crypto.ETH/BTC")
    assert (eth_btc.base, eth_btc.quote) == ("ETH", "BTC")
    why = {f.symbol: f.why_not for f in catalogue.feeds if not f.dataset}
    assert "deferred" in why["InterestRate.Index.CMUS10YDF"]
    assert "effective date" in why["InterestRate.SOFR"]
    assert why["FundingRate.Binance.BTC/USDT"]


def test_a_past_moment_without_a_price_is_none(tmp_path: Path) -> None:
    class Missing(Sample):
        def get(self, url: str, headers: dict[str, str]) -> tuple[int, str]:
            return (404, "not found") if "/updates/price/1" in url else super().get(url, headers)

    hermes = Hermes(RawStore(tmp_path), Missing(), "live", KEY)
    assert hermes.at(1_700_000_000, ids_of("InterestRate.Index.CMUS10Y")) == []
