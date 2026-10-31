"""Hermes as the plugin calls it: the key sent as a bearer token and kept
nowhere, each answer kept before it is read, every value an exact decimal,
and Pyth's catalogue sorted into the datasets."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from decimal import Decimal
from pathlib import Path

import pytest
from meridian.edge import RawStore

from pyth.catalogue import Catalogue, read_catalogue
from pyth.hermes import RETRIES, Hermes, HermesError, backoff, read_updates, retry_after
from pyth.synthetic import Synthetic
from pyth.work import stream_pause

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
        def get(self, url: str, headers: dict[str, str]) -> tuple[int, str, Mapping[str, str]]:
            if "/updates/price/1" in url:
                return 404, "not found", {}
            return super().get(url, headers)

    hermes = Hermes(RawStore(tmp_path), Missing(), "live", KEY)
    assert hermes.at(1_700_000_000, ids_of("InterestRate.Index.CMUS10Y")) == []


class Limited(Sample):
    """Hermes answering 429 to the first `times` price requests, with a
    `Retry-After` where given; a stream refused the same way."""

    def __init__(self, times: int, after: str | None = None) -> None:
        super().__init__()
        self.times, self.after = times, after

    def get(self, url: str, headers: dict[str, str]) -> tuple[int, str, Mapping[str, str]]:
        if "/updates/" in url and self.times > 0:
            self.times -= 1
            self.requests.append(url)
            said = {} if self.after is None else {"Retry-After": self.after}
            return 429, "too many requests", said
        return super().get(url, headers)

    def lines(self, url: str, headers: dict[str, str]) -> Iterator[str]:
        raise HermesError(429, "Hermes is limiting this key's requests (429)", 7.0)
        yield ""  # pragma: no cover - a generator


def test_a_429_is_waited_out_as_retry_after_asks(tmp_path: Path) -> None:
    waited: list[float] = []
    hermes = Hermes(RawStore(tmp_path), Limited(2, "3"), "live", KEY, sleep=waited.append)
    assert hermes.latest(ids_of("Crypto.BTC"))
    assert waited == [3.0, 3.0]
    assert hermes.health.rate_limited == 2 and hermes.health.failures == 0
    assert hermes.health.calls == 3


def test_a_429_without_retry_after_backs_off_with_jitter(tmp_path: Path) -> None:
    waited: list[float] = []
    hermes = Hermes(
        RawStore(tmp_path), Limited(3), "live", KEY, sleep=waited.append, rand=lambda: 0.5
    )
    assert hermes.latest(ids_of("Crypto.BTC"))
    assert waited == [0.75, 1.5, 3.0]


def test_jitter_keeps_each_wait_between_half_and_the_whole() -> None:
    assert backoff(0, lambda: 0.0) == 0.5 and backoff(0, lambda: 1.0) == 1.0
    assert backoff(2, lambda: 0.0) == 2.0 and backoff(2, lambda: 1.0) == 4.0
    assert stream_pause(10, lambda: 0.0) == 10 and stream_pause(10, lambda: 1.0) == 15


def test_a_429_past_the_retries_fails_said(tmp_path: Path) -> None:
    waited: list[float] = []
    hermes = Hermes(RawStore(tmp_path), Limited(RETRIES + 5, "1"), "live", KEY, sleep=waited.append)
    with pytest.raises(HermesError) as refused:
        hermes.latest(ids_of("Crypto.BTC"))
    assert refused.value.status == 429 and "(429)" in str(refused.value)
    assert len(waited) == RETRIES
    assert hermes.health.rate_limited == RETRIES + 1 and hermes.health.failures == 1


def test_retry_after_is_read_in_seconds_only() -> None:
    assert retry_after({"retry-after": "12"}) == 12.0
    assert retry_after({"Retry-After": " 1.5 "}) == 1.5
    assert retry_after({"Retry-After": "Fri, 30 Oct 2026 19:00:00 GMT"}) is None
    assert retry_after({}) is None


def test_a_refused_stream_counts_its_429(tmp_path: Path) -> None:
    hermes = Hermes(RawStore(tmp_path), Limited(0), "live", KEY)
    with pytest.raises(HermesError) as refused:
        next(hermes.stream(ids_of("InterestRate.Index.CMUS10Y")))
    assert refused.value.retry_after == 7.0
    assert hermes.health.rate_limited == 1
